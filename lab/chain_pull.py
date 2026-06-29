"""
Lab data layer (§4.1) — pull SN21's real chain state for emission modelling.

One `all_subnets()` call returns fully-decoded DynamicInfo for every subnet
(alpha_out = issued alpha A, alpha_in/tao_in = pool reserves, moving_price = the
EMA salary, price = spot, *_emission = the actual per-block emission the chain
is paying right now). Add one `TaoWeight` query and the root-stake sum and we
have every primitive the doc's three switches need:

    emission_share_i = root_prop_i x price_i x (1 - miner_burn_i)
    root_prop_i      = R / (R + A_i),   R = T_root x tao_weight,  A_i = alpha issued

The per-block emission fields (tao_in_emission, alpha_out_emission) are what the
reproduction gate (§4.3) validates a modelled mechanism against — they are the
chain's own ground-truth output, stronger than a taostats cross-check.

Storage names + scaling confirmed against live finney @ block ~8,468,621:
    TaoWeight (global u64, /2**64)        ~ 0.180
    SubnetOwnerCut (global u16, /65535)   ~ 0.180
    DynamicInfo.alpha_out / .alpha_in / .tao_in   Balance (decimal TAO/alpha units)
    DynamicInfo.moving_price                      float (EMA, TAO/alpha)
    DynamicInfo.price                             Balance spot (TAO/alpha)

Reuses the finney SSL fix + NETWORK from collector.py, like market_sync.py.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

from collector import _configure_chain_ssl, load_json, NETWORK
from config import DATA_DIR

logger = logging.getLogger(__name__)

NETUID_SN21 = 21
U64_MAX = 2 ** 64                       # TaoWeight normalisation
U16_MAX = 65535                         # SubnetOwnerCut normalisation
SUBNET_DAILY_STORE = DATA_DIR / "subnet_daily.json"  # Taostats incentive_burn lives here
SUBNET_LATEST_PATH = "/api/subnet/latest/v1"          # live fallback for incentive_burn


def _f(x: Any) -> float | None:
    """Best-effort float of a bittensor Balance / fixed-point / number.
    Balance.__float__ already returns the decimal (TAO/alpha) value."""
    if x is None:
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        for attr in ("tao", "rao"):
            v = getattr(x, attr, None)
            if v is not None:
                return float(v) / (1e9 if attr == "rao" else 1.0)
    return None


def _burn_from_subnet_daily() -> float | None:
    """Latest persisted Taostats `incentive_burn` (subnet_sync writes it daily —
    the same source the daily digest reports)."""
    log = load_json(SUBNET_DAILY_STORE, [])
    if isinstance(log, list) and log:
        ib = (log[-1].get("subnet") or {}).get("incentive_burn")
        try:
            return float(ib) if ib is not None else None
        except (TypeError, ValueError):
            return None
    return None


def _burn_from_taostats() -> float | None:
    """Live `incentive_burn` from Taostats — the economic miner-emission burn."""
    key = (os.environ.get("TAOSTATS_API_KEY") or "").strip()
    if not key:
        return None
    base = os.environ.get("TAOSTATS_API_BASE", "https://api.taostats.io").rstrip("/")
    try:
        import requests
        r = requests.get(base + SUBNET_LATEST_PATH, params={"netuid": NETUID_SN21},
                         headers={"Authorization": key, "Accept": "application/json"},
                         timeout=30)
        r.raise_for_status()
        row = (r.json().get("data") or [{}])[0]
        ib = row.get("incentive_burn")
        return float(ib) if ib is not None else None
    except Exception as e:  # noqa: BLE001 — never let burn lookup kill the pull
        logger.warning("Lab: live incentive_burn fetch failed: %s", e)
        return None


def _current_miner_burn(default: float = 0.77) -> float:
    """SN21's live miner_burn b for the (1 - b) emission gate.

    This MUST be the *economic* burn — the fraction of miner (incentive) emission
    that is burned/recycled rather than paid out — read from Taostats
    `incentive_burn`. Do NOT use the weight-scan `burn_fraction`: that is the
    fraction of *validators* routing weight to the owner UID (a headcount gated at
    a 0.98 threshold), which reads ~1.0 even when the economic burn is ~0.77.
    Conflating the two zeroed the modelled emission share (1-b=0) and broke the
    reproduction gate. Source order: persisted subnet_daily.json -> live Taostats
    -> default (last-known ~0.77). Scenarios that sweep b ignore this; it only
    seeds the 'current' point."""
    b = _burn_from_subnet_daily()
    if b is None:
        b = _burn_from_taostats()
    if b is None:
        logger.warning("Lab: no incentive_burn available; defaulting b=%.2f", default)
        return default
    return b


def _root_stake_tao(network: str = NETWORK) -> float | None:
    """Total root (netuid 0) stake in TAO = T_root, the numerator weight of
    root_prop. Summed from the netuid-0 metagraph, as root_reborn_model.py does.
    Heavy (~10-20s metagraph sync); guarded so a failure doesn't kill the pull."""
    try:
        import bittensor as bt

        mg0 = bt.Metagraph(netuid=0, network=network, sync=True)
        return sum(float(s) for s in mg0.S)
    except Exception as e:  # noqa: BLE001
        logger.warning("root stake (netuid 0) sum failed: %s", e)
        return None


def pull_chain_state(netuid: int = NETUID_SN21, network: str = NETWORK,
                     include_root_stake: bool = True) -> dict:
    """Pull a complete, self-describing ChainState snapshot.

    Returns a dict (JSON-safe) with global params + a per-subnet list. Snapshotted
    verbatim into every lab run so historical runs stay reproducible. Raises on a
    failed connection so callers never silently model stale state."""
    _configure_chain_ssl()
    import bittensor as bt

    st = bt.Subtensor(network=network, log_verbose=False)
    raw = st.all_subnets() or []
    try:
        block = int(st.get_current_block())
    except Exception:  # noqa: BLE001
        block = None

    # Global tao_weight (u64 normalised to 1.0).
    try:
        tw_raw = st.substrate.query("SubtensorModule", "TaoWeight", []).value
        tao_weight = float(tw_raw) / U64_MAX
    except Exception as e:  # noqa: BLE001
        logger.warning("TaoWeight query failed: %s", e)
        tao_weight = None

    # Global owner cut (u16 normalised) — the 18% slice.
    try:
        oc_raw = st.substrate.query("SubtensorModule", "SubnetOwnerCut", []).value
        owner_cut = float(oc_raw) / U16_MAX
    except Exception as e:  # noqa: BLE001
        logger.warning("SubnetOwnerCut query failed: %s", e)
        owner_cut = None

    subnets = []
    for d in raw:
        nu = getattr(d, "netuid", None)
        if nu is None:
            continue
        nu = int(nu)
        if nu == 0:
            continue  # root has no alpha pool
        alpha_in = _f(getattr(d, "alpha_in", None))
        tao_in = _f(getattr(d, "tao_in", None))
        alpha_out = _f(getattr(d, "alpha_out", None))
        spot = (tao_in / alpha_in) if (alpha_in and tao_in and alpha_in > 0) else None
        moving = _f(getattr(d, "moving_price", None))
        subnets.append({
            "netuid": nu,
            "name": getattr(d, "subnet_name", None),
            "alpha_in": alpha_in,            # pool alpha reserve
            "tao_in": tao_in,                # pool TAO reserve
            "alpha_issued": alpha_out,       # A — alpha outstanding (SubnetAlphaOut)
            "spot_price": spot,              # tao_in / alpha_in
            "ema_price": moving,             # SubnetMovingPrice (the 'salary')
            "tempo": _int(getattr(d, "tempo", None)),
            # chain's actual per-block emission — reproduction-gate ground truth
            "tao_in_emission": _f(getattr(d, "tao_in_emission", None)),
            "alpha_out_emission": _f(getattr(d, "alpha_out_emission", None)),
            "alpha_in_emission": _f(getattr(d, "alpha_in_emission", None)),
        })

    root_stake = _root_stake_tao(network) if include_root_stake else None

    sn21 = next((s for s in subnets if s["netuid"] == netuid), None)
    if sn21 is None:
        raise RuntimeError(f"netuid {netuid} not present/priced in all_subnets()")

    return {
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "block": block,
        "network": network,
        "netuid": netuid,
        "tao_weight": tao_weight,
        "owner_cut": owner_cut,
        "root_stake_tao": root_stake,
        "sn21_miner_burn": _current_miner_burn(),
        "n_subnets": len(subnets),
        "subnets": subnets,
    }


def _int(x: Any) -> int | None:
    try:
        return int(x)
    except (TypeError, ValueError):
        return None


def sn21(state: dict) -> dict:
    """Convenience: the SN21 row out of a ChainState."""
    return next(s for s in state["subnets"] if s["netuid"] == state.get("netuid", NETUID_SN21))


if __name__ == "__main__":  # quick manual probe
    logging.basicConfig(level=logging.INFO)
    s = pull_chain_state(include_root_stake=True)
    me = sn21(s)
    print(f"block {s['block']}  tao_weight={s['tao_weight']:.4f}  "
          f"owner_cut={s['owner_cut']:.4f}  root_stake={s['root_stake_tao']}")
    print(f"SN21: A(issued)={me['alpha_issued']:,.0f}  reserve_alpha={me['alpha_in']:,.0f}  "
          f"tao_in={me['tao_in']:,.0f}  spot={me['spot_price']:.6f}  ema={me['ema_price']:.6f}  "
          f"b={s['sn21_miner_burn']}")
    print(f"chain per-block emission — tao_in={me['tao_in_emission']}, "
          f"alpha_out={me['alpha_out_emission']}")
