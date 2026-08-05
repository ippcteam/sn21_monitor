"""
Conviction tripwire — early warning for the LIVE subnet-ownership takeover clause.

Since the v430-432 runtime deploys (2026-07-13..16), `change_subnet_owner_if_needed`
(staking/lock.rs) runs every epoch: if total rolled lock-conviction on a subnet
reaches 10% of SubnetAlphaOut, the subnet is >= 1 year old (SN21: armed), and a
non-owner hotkey out-convicts the owner hotkey, OWNERSHIP MOVES to that hotkey's
coldkey. Conviction accrues only from explicitly locked alpha (`HotkeyLock`),
maturing at ~50% per 90 days — so an attack is visible on chain for months before
it can fire. That maturity window is the whole defense: this module reads
`HotkeyLock[NETUID]` daily and escalates the moment a third-party lock appears
or grows toward the takeover threshold.

Escalation tiers (alert fires on any tier INCREASE, not on every run):
    0  no third-party locks (all clear)
    1  ANY third-party lock exists            <- the tripwire
    2  third-party locked mass >= 25% of the 10%-of-AlphaOut threshold
    3  >= 50% of threshold
    4  >= 75% of threshold
    5  >= threshold AND top third-party conviction exceeds owner conviction
       (takeover technically possible once matured)

Tiering keys on LOCKED MASS (the committed ceiling), not matured conviction —
conservative by design: mass is what the attacker has already bought and locked;
conviction merely catches up to it over time.

Reads chain storage directly via substrate (no bittensor SDK decode paths — the
spec-430+ typed runtime breaks bittensor 9.x's high-level decoders; raw queries
are what lab/chain_pull.py fell back to as well).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

from collector import _configure_chain_ssl, load_json, save_json
from config import DATA_DIR
from lab.chain_pull import _bits, _unwrap

logger = logging.getLogger(__name__)

NETUID = int(os.environ.get("SN21_NETUID", "21"))
SUBTENSOR_WS_URL = os.environ.get(
    "SUBTENSOR_WS_URL", "wss://entrypoint-finney.opentensor.ai:443"
)

RAO_PER_ALPHA = 1_000_000_000
U64F64_SCALE = 2 ** 64                 # LockState.conviction fixed-point scale
THRESHOLD_FRACTION = 0.10              # takeover needs total conviction >= 10% of AlphaOut
ONE_YEAR_BLOCKS = 365 * 7200           # age gate in change_subnet_owner_if_needed
DUST_ALPHA = 0.1                       # ignore sub-dust lock entries

CONVICTION_WATCH_STORE = DATA_DIR / "conviction_watch.json"
CONVICTION_WATCH_HISTORY = DATA_DIR / "conviction_watch_history.json"
HISTORY_RETENTION = 365

TIER_LABELS = {
    0: "clear — no third-party locks",
    1: "TRIPWIRE — a third-party lock exists",
    2: "third-party locked mass ≥ 25% of takeover threshold",
    3: "third-party locked mass ≥ 50% of takeover threshold",
    4: "third-party locked mass ≥ 75% of takeover threshold",
    5: "TAKEOVER POSSIBLE once matured — threshold met and owner out-convicted",
}


def _conviction_alpha(v: Any) -> float:
    """LockState.conviction (U64F64 bits) -> alpha units."""
    b = _bits(v)
    return (b / U64F64_SCALE) if b else 0.0


def _mass_alpha(v: Any) -> float:
    """LockState.locked_mass (AlphaBalance rao, possibly tuple-wrapped) -> alpha."""
    b = _bits(v)
    return (b / RAO_PER_ALPHA) if b else 0.0


def fetch_lock_state(netuid: int = NETUID) -> dict[str, Any]:
    """One pass over chain storage: owner identity, alpha out, subnet age, and
    every HotkeyLock entry classified owner vs third-party."""
    _configure_chain_ssl()
    from async_substrate_interface.sync_substrate import SubstrateInterface

    with SubstrateInterface(SUBTENSOR_WS_URL) as sub:
        def q(store: str, params: list) -> Any:
            return sub.query("SubtensorModule", store, params)

        head = sub.get_chain_head()
        block = sub.get_block_number(head)
        owner_coldkey = str(_unwrap(q("SubnetOwner", [netuid])) or "")
        owner_hotkey = str(_unwrap(q("SubnetOwnerHotkey", [netuid])) or "")
        alpha_out = _mass_alpha(q("SubnetAlphaOut", [netuid]))
        registered_at = int(_bits(q("NetworkRegisteredAt", [netuid])) or 0)

        entries: list[dict[str, Any]] = []
        for k, v in sub.query_map("SubtensorModule", "HotkeyLock", [netuid], page_size=200):
            hotkey = _unwrap(k)
            hotkey = str(hotkey if not isinstance(hotkey, (list, tuple)) else hotkey[-1])
            state = getattr(v, "value", v) or {}
            mass = _mass_alpha(state.get("locked_mass"))
            if mass < DUST_ALPHA:
                continue
            lock_coldkey = str(_unwrap(q("Owner", [hotkey])) or "")
            is_owner = (lock_coldkey == owner_coldkey) or (hotkey == owner_hotkey)
            entries.append({
                "hotkey": hotkey,
                "coldkey": lock_coldkey,
                "is_owner": is_owner,
                "locked_mass_alpha": round(mass, 3),
                "conviction_alpha": round(_conviction_alpha(state.get("conviction")), 3),
                "last_update_block": int(_bits(state.get("last_update")) or 0),
            })

    return {
        "block": block,
        "owner_coldkey": owner_coldkey,
        "owner_hotkey": owner_hotkey,
        "alpha_out": alpha_out,
        "registered_at_block": registered_at,
        "age_blocks": (block - registered_at) if (block and registered_at) else None,
        "entries": entries,
    }


def assess(chain: dict[str, Any]) -> dict[str, Any]:
    """Pure classification of a fetch_lock_state() result into the tier model."""
    threshold_alpha = THRESHOLD_FRACTION * (chain.get("alpha_out") or 0.0)
    entries = chain.get("entries") or []
    third = [e for e in entries if not e["is_owner"]]
    ours = [e for e in entries if e["is_owner"]]

    third_mass = sum(e["locked_mass_alpha"] for e in third)
    third_conviction = sum(e["conviction_alpha"] for e in third)
    top_third_conviction = max((e["conviction_alpha"] for e in third), default=0.0)
    owner_conviction = sum(e["conviction_alpha"] for e in ours)

    age = chain.get("age_blocks")
    age_armed = age is not None and age >= ONE_YEAR_BLOCKS

    if not third:
        tier = 0
    elif threshold_alpha > 0 and third_mass >= threshold_alpha \
            and top_third_conviction > owner_conviction:
        tier = 5
    elif threshold_alpha > 0 and third_mass >= 0.75 * threshold_alpha:
        tier = 4
    elif threshold_alpha > 0 and third_mass >= 0.50 * threshold_alpha:
        tier = 3
    elif threshold_alpha > 0 and third_mass >= 0.25 * threshold_alpha:
        tier = 2
    else:
        tier = 1

    return {
        "tier": tier,
        "tier_label": TIER_LABELS[tier],
        "status": "ok" if tier == 0 else "alert",
        "age_armed": age_armed,
        "takeover_threshold_alpha": round(threshold_alpha, 0),
        "third_party_locks": sorted(third, key=lambda e: -e["locked_mass_alpha"]),
        "third_party_locked_mass_alpha": round(third_mass, 3),
        "third_party_conviction_alpha": round(third_conviction, 3),
        "third_party_mass_vs_threshold_pct": (
            round(100.0 * third_mass / threshold_alpha, 2) if threshold_alpha > 0 else None
        ),
        "owner_locks": ours,
        "owner_conviction_alpha": round(owner_conviction, 3),
    }


def run_conviction_watch(notify: bool = True) -> dict[str, Any]:
    """Scan HotkeyLock, classify, persist, and alert on any tier ESCALATION.
    De-escalation (locks unwound) is recorded but never alerts."""
    now = datetime.now(timezone.utc)
    chain = fetch_lock_state()
    result = {
        "checked_at": now.isoformat(),
        "netuid": NETUID,
        "block": chain["block"],
        "owner_coldkey": chain["owner_coldkey"],
        "alpha_out": round(chain["alpha_out"] or 0.0, 0),
        "age_blocks": chain["age_blocks"],
        "n_lock_entries": len(chain["entries"]),
        **assess(chain),
    }

    prev = load_json(CONVICTION_WATCH_STORE, {})
    save_json(CONVICTION_WATCH_STORE, result)

    hist = load_json(CONVICTION_WATCH_HISTORY, [])
    if isinstance(hist, list):
        hist.append({k: result[k] for k in (
            "checked_at", "block", "tier", "status",
            "third_party_locked_mass_alpha", "owner_conviction_alpha")})
        save_json(CONVICTION_WATCH_HISTORY, hist[-HISTORY_RETENTION:])

    escalated = result["tier"] > int(prev.get("tier") or 0)
    result["alerted"] = False
    if notify and escalated:
        try:
            result["alerted"] = _send_alert(result, prev_tier=int(prev.get("tier") or 0))
        except Exception:
            logger.exception("Conviction-watch Telegram alert failed")

    logger.info(
        "Conviction watch: %s (tier %s) — %d lock entries, third-party mass %.1f α "
        "(threshold %.0f α, %s%% covered), owner conviction %.1f α",
        result["status"].upper(), result["tier"], result["n_lock_entries"],
        result["third_party_locked_mass_alpha"], result["takeover_threshold_alpha"],
        result["third_party_mass_vs_threshold_pct"] or 0, result["owner_conviction_alpha"],
    )
    return result


def _send_alert(result: dict[str, Any], prev_tier: int) -> bool:
    from digest.channels import telegram as telegram_channel

    top = (result["third_party_locks"] or [{}])[0]
    lines = [
        f"🚨 SN21 CONVICTION TRIPWIRE — tier {prev_tier} → {result['tier']}",
        "",
        result["tier_label"],
        "",
        f"  • Third-party locked mass: {result['third_party_locked_mass_alpha']:,.0f} α "
        f"({result['third_party_mass_vs_threshold_pct']}% of the "
        f"{result['takeover_threshold_alpha']:,.0f} α takeover threshold)",
        f"  • Third-party matured conviction: {result['third_party_conviction_alpha']:,.0f} α",
        f"  • Our owner conviction: {result['owner_conviction_alpha']:,.0f} α",
    ]
    if top:
        lines.append(f"  • Largest locker: hotkey {str(top.get('hotkey', ''))[:10]}… "
                     f"(coldkey {str(top.get('coldkey', ''))[:10]}…) "
                     f"{top.get('locked_mass_alpha', 0):,.0f} α locked")
    lines += [
        "",
        "Conviction matures ~50%/90d — this is the early-warning window.",
        "Response options: enable owner_cut_auto_lock_enabled, seed-lock owner "
        "alpha, or engage the locker. See lab priority-2 action.",
    ]
    telegram_channel.send("\n".join(lines))
    return True


if __name__ == "__main__":
    import json

    logging.basicConfig(level=logging.INFO)
    print(json.dumps(run_conviction_watch(notify=False), indent=2))
