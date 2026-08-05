"""
Dereg tripwire — SN21's live position in the subnet-pruning queue.

THERE IS NO FIXED DEREGISTRATION PRICE FLOOR. The old `DEREG_FLOOR_TAO = 0.0035`
constant (lab/scenarios.py, root_reborn_model.py) was an unverified assumption and
by 2026-07-29 was actively misleading — SN21's own EMA had fallen below it, so the
lab scored "high" dereg risk against a number the chain never reads.

The real rule, read from subtensor `main` and verified live @ block 8,727,955:

  * `do_register_network` (subnets/subnet.rs): when
    `live_subnets + DissolveCleanupQueue >= SubnetLimit`, a new registration
    IMMEDIATELY dissolves one existing subnet via `get_network_to_prune()`.
    SubnetLimit is 128 and 128 non-root subnets are live => the network is FULL,
    so every single registration kills a subnet.
  * `get_network_to_prune()` (coinbase/root.rs:299): skip subnets younger than
    `NetworkImmunityPeriod` (864,000 blocks = 120 d), then take the LOWEST
    `SubnetMovingPrice` (the EMA alpha price, fixed-point /2**32), ties broken by
    earliest `NetworkRegisteredAt`.
  * So the metric is an EMA-price RANK — relative, not absolute. What matters is
    how many subnets sit below us (the buffer) and how fast that buffer erodes.
  * The EMA is FAST: alpha = SubnetMovingAlpha (0.0003) * b/(b + EMAPriceHalvingBlocks),
    which for SN21 (halving 201,600, b ~ 5.6M blocks) is ~0.00029/block => an
    ~8-HOUR half-life. It tracks spot within a day: no lag protection on the way
    down, but equally no lag on a defensive buy.
  * Cost to force one prune = `NetworkLastLockCost` (~707 TAO on 2026-07-29;
    doubles per registration, decays to NetworkMinLockCost over ~16 d).

The node exposes `subnetInfo_getSubnetToPrune`, so the chain tells us directly
which subnet dies next — we use it as the authoritative cross-check on our own
ranking, and `swap_simSwapTaoForAlpha` to price the defence exactly rather than
inferring it from reserve ratios.

Escalation tiers (alert fires on any tier INCREASE, like conviction_watch.py):
    0  >= 20 non-immune subnets below us      (clear)
    1  10-19 below
    2  5-9 below
    3  2-4 below
    4  exactly 1 below                        (one registration from the block)
    5  SN21 IS the prune target               (the next registration kills it)

Writes data/dereg_watch.json (+ 365-row history). Chain access goes through
chain_compat.py — never the 9.x-era bittensor APIs (see the SDK-11 migration).
"""

from __future__ import annotations

import logging
import os
import struct
from datetime import datetime, timezone
from typing import Any

from chain_compat import bits, qmap, substrate, unwrap
from collector import load_json, save_json
from config import DATA_DIR

logger = logging.getLogger(__name__)

NETUID = int(os.environ.get("SN21_NETUID", "21"))

RAO = 1_000_000_000
MOVING_PRICE_SCALE = 2 ** 32           # SubnetMovingPrice fixed-point (I96F32 bits)
BLOCKS_PER_DAY = 7200

# How much rank buffer we want to keep. The hard floor is the prune target's EMA;
# this is the operating guardrail S4 extraction binds against.
DEREG_BUFFER_MIN = 10

# TAO sizes priced in the defence table (chain swap simulation).
DEFENCE_SIZES_TAO = (100, 250, 500, 1000)

# Relative-drop sensitivities reported alongside the buffer.
SENSITIVITY_PCTS = (5, 10, 15, 20)

# Velocity tripwire. The tier model alone is level-based and would stay silent
# through a 36 -> 24 slide (what actually happened over 8 days to 2026-07-29);
# this fires when the buffer erodes this fast regardless of the tier.
EROSION_WINDOW_DAYS = 14
EROSION_ALERT_PLACES = 8

# Emission-gate hyperparams, watched here because NOTHING else catches them: the
# lab watcher tracks spec versions and PR state, but these move by a single
# `sudo_set_*` ROOT call — no PR, no merge, no runtime upgrade, no release note,
# effective the next block.
#
# v441 (live on finney 2026-08-03, shipped inside PR #2968 "release-root-reborn")
# added `EmissionBarRank` (N) and changed HOW the bar is set. When N > 0 the chain
# pins theta to the Nth-LARGEST demand share and the quantile q is VESTIGIAL —
# watching q alone now tells us nothing. N is a plain u16, not a U64F64 fixed-point
# like q/h/theta, hence the per-param scale below.
#
# Live 2026-08-03: N = 32 (the code default, never explicitly set), q = 0.75 (dead),
# h = 3.0, theta = 0.00732. N = 32 was chosen upstream to sit near the old q = 0.75
# crossing (~rank 28) so the v441 upgrade would not shift the emission curve, and it
# measures out that way: subnets at gate >= 0.5 went ~28 -> 34. SN21 sits at rank 61
# of 83, gate ~0.03.
#
# ANY change to N, q or h is alert-worthy — N most of all, since it is now the live
# lever and a one-call move of it re-prices every subnet's emission. theta is
# different: the chain recomputes it every 360 blocks off the live distribution, so
# it drifts constantly and only a large move (a real re-shaping of the field, or a
# switch of bar mode) is worth waking anyone for.
U64F64_SCALE = 2 ** 64
GATE_PARAMS = {
    "rank": ("EmissionBarRank", 1.0),
    "q": ("EmissionBarQuantile", U64F64_SCALE),
    "h": ("EmissionGateExponent", U64F64_SCALE),
    "theta": ("EmissionGateBar", U64F64_SCALE),
}
# Params set by a ROOT call — discrete, so any change at all is reportable.
GATE_ROOT_PARAMS = ("rank", "q", "h")
THETA_MOVE_ALERT = 0.25          # |dtheta/theta| this large is a distribution shift

DEREG_WATCH_STORE = DATA_DIR / "dereg_watch.json"
DEREG_WATCH_HISTORY = DATA_DIR / "dereg_watch_history.json"
HISTORY_RETENTION = 365

TIER_LABELS = {
    0: "clear — deep rank buffer below us",
    1: "buffer thinning — 10-19 subnets below",
    2: "WATCH — only 5-9 subnets below",
    3: "WARNING — only 2-4 subnets below",
    4: "CRITICAL — one subnet away from being the prune target",
    5: "PRUNE TARGET — the next subnet registration deregisters SN21",
}


def _tier(n_below: int, is_target: bool, immune: bool) -> int:
    if immune:
        return 0
    if is_target:
        return 5
    if n_below <= 1:
        return 4
    if n_below <= 4:
        return 3
    if n_below <= 9:
        return 2
    if n_below <= 19:
        return 1
    return 0


def _sim_buy(sub: Any, netuid: int, tao: float, price_now: float) -> dict[str, Any] | None:
    """Price a TAO->alpha buy through the chain's own swap simulator.

    `swap_simSwapTaoForAlpha` returns a SCALE-encoded SimSwapResult — six u64s:
    (tao_amount, alpha_amount, tao_fee, alpha_fee, tao_slippage, alpha_slippage).
    The simulator gives the executed average price; on a constant-product curve
    avg = p0*(1+x) and the resulting spot is p0*(1+x)**2, so spot_after = avg**2/p0.
    Returns None if the node does not expose the runtime API."""
    try:
        raw = sub.rpc_request("swap_simSwapTaoForAlpha", [netuid, int(tao * RAO)])["result"]
        tao_net, alpha_out, tao_fee = (v / RAO for v in struct.unpack("<6Q", bytes(raw))[:3])
    except Exception:  # noqa: BLE001 — older nodes lack the swap runtime API
        logger.debug("swap_simSwapTaoForAlpha unavailable for netuid %s", netuid, exc_info=True)
        return None
    if alpha_out <= 0 or price_now <= 0:
        return None
    avg = tao_net / alpha_out
    return {
        "tao_in": tao,
        "alpha_out": round(alpha_out, 0),
        "tao_fee": round(tao_fee, 4),
        "avg_price": round(avg, 8),
        "spot_after": round(avg * avg / price_now, 8),
    }


def fetch_prune_state(netuid: int = NETUID) -> dict[str, Any]:
    """One chain pass: every subnet's EMA price + registration block, the global
    prune parameters, and the chain's own answer for who dies next."""
    with substrate() as sub:
        block = int(sub.get_block_number(sub.get_chain_head()))

        moving = qmap(sub, "SubnetMovingPrice", MOVING_PRICE_SCALE)
        tao_in = qmap(sub, "SubnetTAO", RAO)
        alpha_in = qmap(sub, "SubnetAlphaIn", RAO)
        registered_at = qmap(sub, "NetworkRegisteredAt", 1.0)

        added: dict[int, bool] = {}
        for k, v in sub.query_map("SubtensorModule", "NetworksAdded", [], page_size=500):
            added[int(unwrap(k))] = bool(unwrap(v))

        subnet_limit = int(bits(sub.query("SubtensorModule", "SubnetLimit", [])) or 0)
        immunity = int(bits(sub.query("SubtensorModule", "NetworkImmunityPeriod", [])) or 0)
        lock_cost = (bits(sub.query("SubtensorModule", "NetworkLastLockCost", [])) or 0.0) / RAO

        # The chain's own prune decision — authoritative cross-check on our ranking.
        try:
            target = sub.rpc_request("subnetInfo_getSubnetToPrune", [])["result"]
            prune_target = int(unwrap(target)) if target is not None else None
        except Exception:  # noqa: BLE001 — RPC not exposed on every endpoint
            logger.debug("subnetInfo_getSubnetToPrune unavailable", exc_info=True)
            prune_target = None

        # The swap pallet's price is what update_moving_price() actually feeds the
        # EMA — reserve ratio is only a proxy for it.
        try:
            swap_price = sub.rpc_request("swap_currentAlphaPrice", [netuid])["result"] / RAO
        except Exception:  # noqa: BLE001
            swap_price = None

        gate: dict[str, float | None] = {}
        for key, (storage, scale) in GATE_PARAMS.items():
            try:
                raw = bits(sub.query("SubtensorModule", storage, []))
                gate[key] = (raw / scale) if raw is not None else None
            except Exception:  # noqa: BLE001 — pre-v440/v441 runtimes lack these
                logger.debug("%s unavailable (older runtime?)", storage, exc_info=True)
                gate[key] = None
        # Which lever actually sets the bar. N > 0 pins theta to the Nth-largest
        # demand share and q is ignored; N = 0 (or absent, pre-v441) falls back to
        # the v440 q-mass quantile.
        gate["mode"] = "rank" if (gate.get("rank") or 0) > 0 else "quantile"

        cleanup_queue = unwrap(sub.query("SubtensorModule", "DissolveCleanupQueue", [])) or []
        reg_queue = unwrap(sub.query("SubtensorModule", "NetworkRegistrationQueue", [])) or []

        price_now = swap_price or (
            (tao_in.get(netuid, 0.0) / alpha_in[netuid]) if alpha_in.get(netuid) else 0.0
        )
        defence = [d for d in (_sim_buy(sub, netuid, t, price_now) for t in DEFENCE_SIZES_TAO) if d]

    subnets = []
    for n, is_added in sorted(added.items()):
        if not is_added or n == 0:
            continue
        reg = int(registered_at.get(n, 0))
        subnets.append({
            "netuid": n,
            # SubnetMovingPrice is ValueQuery/default 0 — a brand-new subnet has no
            # entry and starts its EMA at zero, building through its immunity window.
            "ema": moving.get(n, 0.0) or 0.0,
            "spot": (tao_in.get(n, 0.0) / alpha_in[n]) if alpha_in.get(n) else None,
            "registered_at": reg,
            "age_blocks": block - reg,
            "immune": (block - reg) < immunity,
        })

    return {
        "block": block,
        "netuid": netuid,
        "subnet_limit": subnet_limit,
        "immunity_blocks": immunity,
        "lock_cost_tao": lock_cost,
        "prune_target_netuid": prune_target,
        "gate": gate,
        "swap_price": swap_price,
        "pool_tao": tao_in.get(netuid),
        "pool_alpha": alpha_in.get(netuid),
        "cleanup_queue_len": len(cleanup_queue) if isinstance(cleanup_queue, (list, tuple)) else 0,
        "registration_queue_len": len(reg_queue) if isinstance(reg_queue, (list, tuple)) else 0,
        "defence": defence,
        "subnets": subnets,
    }


def assess(chain: dict[str, Any]) -> dict[str, Any]:
    """Pure classification of a fetch_prune_state() result: rank buffer, the live
    floor/guard prices, erosion sensitivity and the runway implied by the observed
    registration cadence."""
    netuid = chain["netuid"]
    block = chain["block"]
    subnets = chain["subnets"]
    me = next((s for s in subnets if s["netuid"] == netuid), None)
    if me is None:
        raise ValueError(f"netuid {netuid} is not a live subnet at block {block}")

    prunable = sorted((s for s in subnets if not s["immune"]), key=lambda s: s["ema"])
    below = [s for s in prunable if s["netuid"] != netuid and s["ema"] < me["ema"]]
    below_immune = [s for s in subnets if s["immune"] and s["ema"] < me["ema"]]

    # The hard floor: the EMA of whoever is currently first in line. Fall below it
    # and SN21 becomes the prune target.
    floor = prunable[0]["ema"] if prunable else 0.0
    # The operating guardrail: the EMA that still leaves DEREG_BUFFER_MIN subnets below.
    guard = prunable[DEREG_BUFFER_MIN]["ema"] if len(prunable) > DEREG_BUFFER_MIN else floor

    def n_below_at(price: float) -> int:
        return sum(1 for s in prunable if s["netuid"] != netuid and s["ema"] < price)

    # Registration cadence: while the network is full each registration forces one
    # prune, so registrations-per-day IS the kill rate.
    cadence = {}
    for window in (30, 90, 180):
        n = sum(1 for s in subnets if s["age_blocks"] <= window * BLOCKS_PER_DAY)
        cadence[f"registrations_{window}d"] = n
        cadence[f"days_per_prune_{window}d"] = round(window / n, 1) if n else None
    days_per_prune = cadence["days_per_prune_90d"] or cadence["days_per_prune_180d"]

    n_live = len(subnets)
    is_target = (chain.get("prune_target_netuid") == netuid) or (
        bool(prunable) and prunable[0]["netuid"] == netuid
    )
    tier = _tier(len(below), is_target, me["immune"])

    return {
        "tier": tier,
        "tier_label": TIER_LABELS[tier],
        "status": "ok" if tier == 0 else "alert",
        "network_full": n_live + chain["cleanup_queue_len"] >= chain["subnet_limit"],
        "n_live_subnets": n_live,
        "n_prunable": len(prunable),
        "n_immune": n_live - len(prunable),
        "ema": round(me["ema"], 8),
        "spot": round(me["spot"], 8) if me["spot"] else None,
        "age_days": round(me["age_blocks"] / BLOCKS_PER_DAY, 1),
        "immune": me["immune"],
        "subnets_below": len(below),
        "subnets_below_immune": len(below_immune),
        "rank_from_cheapest": len(below) + 1,
        "netuids_below": [s["netuid"] for s in below],
        "floor_tao": round(floor, 8),
        "floor_netuid": prunable[0]["netuid"] if prunable else None,
        "guard_tao": round(guard, 8),
        "guard_buffer": DEREG_BUFFER_MIN,
        "headroom_pct": round(100.0 * (me["ema"] / floor - 1.0), 1) if floor else None,
        "drop_to_target_pct": round(100.0 * (1.0 - floor / me["ema"]), 1) if me["ema"] else None,
        "sensitivity": {
            f"-{p}%": n_below_at(me["ema"] * (1 - p / 100.0)) for p in SENSITIVITY_PCTS
        },
        "runway_days": (
            round(len(below) * days_per_prune, 0) if days_per_prune else None
        ),
        "days_per_prune": days_per_prune,
        **cadence,
    }


def _erosion(history: list, now: datetime, subnets_below: int) -> dict[str, Any]:
    """Buffer velocity over EROSION_WINDOW_DAYS, from the oldest history row still
    inside the window. Returns places lost (positive = losing ground)."""
    oldest = None
    for row in history:
        try:
            ts = datetime.fromisoformat(row["checked_at"])
        except (KeyError, TypeError, ValueError):
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        age_days = (now - ts).total_seconds() / 86400.0
        if age_days <= EROSION_WINDOW_DAYS and row.get("subnets_below") is not None:
            oldest = row
            break
    if not oldest:
        return {"places_lost": None, "since": None, "alerting": False}
    lost = int(oldest["subnets_below"]) - subnets_below
    return {
        "places_lost": lost,
        "since": oldest["checked_at"],
        "alerting": lost >= EROSION_ALERT_PLACES,
    }


def _gate_changes(prev_gate: dict | None, gate: dict) -> dict[str, Any]:
    """Diff the emission-gate hyperparams against the previous run.

    N (rank), q and h are root-set and discrete: any change at all is reportable.
    theta is recomputed by the chain every 360 blocks off the live distribution, so
    it is only reportable on a large relative move."""
    prev_gate = prev_gate or {}
    changed: list[dict[str, Any]] = []
    for key in GATE_PARAMS:
        was, now = prev_gate.get(key), gate.get(key)
        if was is None or now is None or was == now:
            continue
        if key == "theta":
            # A theta of 0 has no meaningful relative move to measure against;
            # treat any change off zero as reportable rather than dividing by it.
            if was and abs(now - was) / was < THETA_MOVE_ALERT:
                continue
        changed.append({
            "param": key,
            "from": was,
            "to": now,
            "pct": round(100.0 * (now / was - 1.0), 1) if was else None,
        })
    return {
        "changed": changed,
        # N/q/h are the root-settable ones — a theta drift alone is informational.
        "alerting": any(c["param"] in GATE_ROOT_PARAMS for c in changed),
    }


def run_dereg_watch(notify: bool = True) -> dict[str, Any]:
    """Read the chain, classify, persist, and alert on any tier ESCALATION.
    Recovery (buffer rebuilding) is recorded but never alerts."""
    now = datetime.now(timezone.utc)
    chain = fetch_prune_state()
    result = {
        "checked_at": now.isoformat(),
        "netuid": chain["netuid"],
        "block": chain["block"],
        "subnet_limit": chain["subnet_limit"],
        "immunity_days": round(chain["immunity_blocks"] / BLOCKS_PER_DAY, 1),
        "lock_cost_tao": round(chain["lock_cost_tao"], 2),
        "prune_target_netuid": chain["prune_target_netuid"],
        "gate": chain["gate"],
        "pool_tao": round(chain["pool_tao"] or 0.0, 1),
        "pool_alpha": round(chain["pool_alpha"] or 0.0, 0),
        "defence": chain["defence"],
        **assess(chain),
    }
    # Our ranking and the chain's own get_network_to_prune() must agree; if they
    # ever diverge the pruning rule has changed and everything downstream is stale.
    result["prune_target_agrees"] = (
        chain["prune_target_netuid"] is None
        or chain["prune_target_netuid"] == result["floor_netuid"]
    )
    if not result["prune_target_agrees"]:
        logger.warning(
            "Dereg watch: chain prune target is netuid %s but our lowest-EMA "
            "non-immune subnet is %s — the pruning rule may have changed",
            chain["prune_target_netuid"], result["floor_netuid"],
        )

    prev = load_json(DEREG_WATCH_STORE, {})
    hist = load_json(DEREG_WATCH_HISTORY, [])
    hist = hist if isinstance(hist, list) else []
    result["erosion"] = _erosion(hist, now, result["subnets_below"])
    result["gate_changes"] = _gate_changes(prev.get("gate"), result["gate"])

    hist.append({k: result[k] for k in (
        "checked_at", "block", "tier", "status", "ema", "spot",
        "subnets_below", "floor_tao", "guard_tao", "runway_days", "gate")})
    save_json(DEREG_WATCH_HISTORY, hist[-HISTORY_RETENTION:])

    prev_tier = int(prev.get("tier") or 0)
    escalated = result["tier"] > prev_tier
    # Erosion alerts are rate-limited to one per window: only fire when the
    # previous run was not already alerting on it.
    eroding = result["erosion"]["alerting"] and not (prev.get("erosion") or {}).get("alerting")
    result["alerted"] = False
    if notify and (escalated or eroding):
        try:
            result["alerted"] = _send_alert(result, prev_tier=prev_tier)
        except Exception:
            logger.exception("Dereg-watch Telegram alert failed")
    # A gate move is a separate event from the dereg buffer and always alerts on
    # its own — it can land on a run where the buffer has not moved at all.
    result["gate_alerted"] = False
    if notify and result["gate_changes"]["alerting"]:
        try:
            result["gate_alerted"] = _send_gate_alert(result)
        except Exception:
            logger.exception("Gate-param Telegram alert failed")
    if result["gate_changes"]["changed"]:
        logger.warning("Emission gate hyperparams moved: %s", result["gate_changes"]["changed"])

    # Persisted last, so the snapshot records what was actually alerted. `prev` was
    # read before this point, so the comparison above is unaffected.
    save_json(DEREG_WATCH_STORE, result)

    logger.info(
        "Dereg watch: %s (tier %s) — EMA %.8f, %d subnets below (was %s), "
        "floor %.8f on netuid %s, runway ~%s d",
        result["status"].upper(), result["tier"], result["ema"], result["subnets_below"],
        prev.get("subnets_below", "?"), result["floor_tao"], result["floor_netuid"],
        result["runway_days"],
    )
    return result


def _send_alert(result: dict[str, Any], prev_tier: int) -> bool:
    from digest.channels import telegram as telegram_channel

    erosion = result.get("erosion") or {}
    if result["tier"] > prev_tier:
        headline = f"⚠️ SN21 DEREG BUFFER — tier {prev_tier} → {result['tier']}"
    else:
        headline = (f"⚠️ SN21 DEREG BUFFER ERODING — {erosion.get('places_lost')} places lost "
                    f"in ≤{EROSION_WINDOW_DAYS} d (tier {result['tier']})")
    lines = [
        headline,
        "",
        result["tier_label"],
        "",
        f"  • Subnets below us: {result['subnets_below']} of {result['n_prunable']} prunable",
        f"  • Our EMA: {result['ema']:.8f} (spot {result['spot']:.8f})",
        f"  • Prune target now: netuid {result['floor_netuid']} @ {result['floor_tao']:.8f} "
        f"— we are {result['drop_to_target_pct']}% above it",
        f"  • Kill rate: one prune every ~{result['days_per_prune']} d "
        f"→ runway ~{result['runway_days']} d at this rank",
        f"  • Cost for anyone to force a prune: {result['lock_cost_tao']:,.0f} TAO",
    ]
    if result.get("defence"):
        d = result["defence"][0]
        lines.append(
            f"  • Defence: {d['tao_in']:,.0f} TAO staked in → spot {d['spot_after']:.8f} "
            f"(EMA follows within ~1 day)"
        )
    lines += [
        "",
        "Dereg is a RANK on the EMA price, not a fixed floor: the next subnet "
        "registration dissolves whichever non-immune subnet has the lowest EMA.",
    ]
    telegram_channel.send("\n".join(lines))
    return True


def _send_gate_alert(result: dict[str, Any]) -> bool:
    """Alert on an emission-gate hyperparam move. Deliberately does NOT try to
    quantify the emission impact — that is the lab's job (S9 / hill_gate_v440_2990,
    which now reads these same values from chain). This says what moved, so the lab
    gets re-run against the new reality."""
    from digest.channels import telegram as telegram_channel

    g = result["gate"]
    lines = [
        "🚨 SN21 EMISSION GATE PARAMETER CHANGED",
        "",
        "The emission gate moved. N, q and h are set by a single ROOT call — no PR, "
        "no runtime upgrade, no release note — and take effect the next block.",
        "",
    ]
    for c in result["gate_changes"]["changed"]:
        pct = f" ({c['pct']:+.1f}%)" if c["pct"] is not None else ""
        lines.append(f"  • {c['param']}: {c['from']:.6g} → {c['to']:.6g}{pct}")
    lines += [
        "",
        f"  Now: mode={g.get('mode')}, N={g.get('rank')}, q={g.get('q')}, "
        f"h={g.get('h')}, θ={g.get('theta')}",
        "",
    ]
    if g.get("mode") == "rank":
        lines += [
            "RANK MODE (v441): θ is pinned to the Nth-LARGEST demand share, so the "
            f"bar is literally the {g.get('rank')}th subnet — q is ignored. A LOWER "
            "N tightens the gate onto fewer subnets; a HIGHER N loosens it. This is "
            "the live lever: watch N, not q.",
        ]
    else:
        lines += [
            "QUANTILE MODE (v440): θ is the q-mass bar. q is the fraction of demand "
            "carried by subnets ABOVE the bar — a HIGHER q walks θ down (looser "
            "gate, helps us), a LOWER q tightens it. For scale, q→0.61 (the old code "
            "default) was measured at ~×0.11 on SN21's emission.",
        ]
    lines += [
        "",
        "Re-run the lab to quantify against live state.",
    ]
    telegram_channel.send("\n".join(lines))
    return True


# ── Accessors for the lab (replace the old DEREG_FLOOR_TAO constant) ──────────

def load_dereg_state() -> dict[str, Any]:
    """Last persisted snapshot ({} before the first run)."""
    return load_json(DEREG_WATCH_STORE, {})


def dereg_floor_tao(default: float | None = None) -> float | None:
    """Live hard floor: the EMA of the subnet currently first in line to be pruned.
    Fall below it and the next registration takes SN21."""
    return load_dereg_state().get("floor_tao", default)


def dereg_guard_tao(default: float | None = None) -> float | None:
    """Live operating guardrail: the EMA that still leaves DEREG_BUFFER_MIN subnets
    below us. This is what extraction (S4) should bind against — not the hard floor,
    which is 20+ registrations away and offers no early warning."""
    return load_dereg_state().get("guard_tao", default)


if __name__ == "__main__":
    import json

    logging.basicConfig(level=logging.INFO)
    print(json.dumps(run_dereg_watch(notify=False), indent=2))
