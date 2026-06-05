"""
Scout — candidate-subnet scanner. For each shortlisted netuid, compute the
economics of running our validator there:

  Permit feasibility (vs lowest active permit-holder),
  Projected emission share + annual ROI,
  Round-trip AMM slippage cost (SN21 sell → target buy → target sell),
  Health/risk signals (burn, concentration, capital flow, miner activity).

Reads only the Taostats endpoints already wired into the dashboard:

  /api/metagraph/latest/v1       — stake ladder + per-UID validator emissions
  /api/dtao/pool/latest/v1       — AMM reserves + 24h volume
  /api/subnet/latest/v1          — burn, registration cost, validator/miner counts
  /api/dtao/stake_balance/latest/v1 — total holders

Writes:

  data/subnet_scan.json          — latest scan, ranked.
  data/subnet_scan_history.json  — daily rows, 90d retention.
  data/subnet_notes.json         — manual qualitative overrides (penalty + note).
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from collector import load_json, save_json
from config import DATA_DIR

logger = logging.getLogger(__name__)

TAOSTATS_API_BASE = os.environ.get("TAOSTATS_API_BASE", "https://api.taostats.io").rstrip("/")
METAGRAPH_PATH = "/api/metagraph/latest/v1"
POOL_PATH = "/api/dtao/pool/latest/v1"
SUBNET_PATH = "/api/subnet/latest/v1"
STAKE_BALANCE_PATH = "/api/dtao/stake_balance/latest/v1"
PRICE_PATH = "/api/price/latest/v1"

NETUID_SN21 = 21
RAO_PER_TAO = 1_000_000_000

SCAN_STORE = DATA_DIR / "subnet_scan.json"
SCAN_HISTORY_STORE = DATA_DIR / "subnet_scan_history.json"
NOTES_STORE = DATA_DIR / "subnet_notes.json"
HISTORY_RETENTION_DAYS = 90

# Pacing — Phase 0 confirmed these survive the free-tier rate limit.
INTER_CALL_SLEEP = 2.0
INTER_SUBNET_SLEEP = 5.0
MAX_429_RETRIES = 10


def _api_key() -> str | None:
    return (os.environ.get("TAOSTATS_API_KEY") or "").strip() or None


def _headers() -> dict[str, str]:
    key = _api_key()
    return {"Authorization": key, "Accept": "application/json"} if key else {}


def _shortlist() -> list[int]:
    raw = (os.environ.get("SCAN_NETUIDS") or "2,8,13,28,43").strip()
    out = []
    for tok in raw.split(","):
        tok = tok.strip()
        if not tok:
            continue
        try:
            n = int(tok)
            if n != NETUID_SN21 and n not in out:
                out.append(n)
        except ValueError:
            logger.warning("Scout: ignoring non-int netuid %r", tok)
    return out


def _budget_sn21_alpha() -> float:
    try:
        return float(os.environ.get("SCAN_BUDGET_SN21_ALPHA") or "500000")
    except (TypeError, ValueError):
        return 500000.0


def _to_float(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _rao_to_tao(v: Any) -> float | None:
    f = _to_float(v)
    return None if f is None else f / RAO_PER_TAO


def _coldkey(row: dict) -> str | None:
    ck = row.get("coldkey")
    if isinstance(ck, dict):
        return ck.get("ss58")
    return ck


# ── HTTP ──────────────────────────────────────────────────────────────────────


def _get_json(session: requests.Session, path: str, params: dict[str, Any]) -> dict[str, Any]:
    url = f"{TAOSTATS_API_BASE}{path}"
    for attempt in range(MAX_429_RETRIES):
        r = session.get(url, params=params, headers=_headers(), timeout=60)
        if r.status_code == 429:
            wait = min(3 + attempt * 3, 45)
            logger.warning(
                "Scout 429 %s netuid=%s attempt %s/%s sleep %ss",
                path, params.get("netuid"), attempt + 1, MAX_429_RETRIES, wait,
            )
            time.sleep(wait)
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError(f"Scout: persistent 429 on {path} netuid={params.get('netuid')}")


def _fetch_metagraph(session, netuid: int) -> list[dict[str, Any]]:
    rows = []
    page = 1
    while True:
        body = _get_json(session, METAGRAPH_PATH, {"netuid": netuid, "limit": 100, "page": page})
        page_rows = body.get("data") or []
        rows.extend(page_rows)
        pag = body.get("pagination") or {}
        if not page_rows or not pag.get("next_page") or page >= (pag.get("total_pages") or 0):
            break
        page = int(pag["next_page"])
        if page > 20:
            break
        time.sleep(1.5)
    return rows


def _fetch_pool(session, netuid: int):
    body = _get_json(session, POOL_PATH, {"netuid": netuid})
    rows = body.get("data") or []
    return rows[0] if rows else None


def _fetch_subnet(session, netuid: int):
    body = _get_json(session, SUBNET_PATH, {"netuid": netuid})
    rows = body.get("data") or []
    return rows[0] if rows else None


def _fetch_holders(session, netuid: int):
    body = _get_json(session, STAKE_BALANCE_PATH, {"netuid": netuid, "limit": 1})
    rows = body.get("data") or []
    return rows[0].get("subnet_total_holders") if rows else None


def _fetch_tao_usd(session):
    body = _get_json(session, PRICE_PATH, {"asset": "tao"})
    rows = body.get("data") or []
    return _to_float(rows[0]["price"]) if rows else None


# ── AMM (constant product x·y = k) ────────────────────────────────────────────


def amm_buy_alpha_with_tao(
    tao_pool: float, alpha_pool: float, tao_spend: float
) -> tuple[float, float | None]:
    """
    Spend `tao_spend` TAO at an x·y=k pool. Receive `alpha_out` alpha.
    Returns (alpha_out, effective_price_tao_per_alpha).
    """
    if tao_pool <= 0 or alpha_pool <= 0 or tao_spend <= 0:
        return 0.0, None
    alpha_out = alpha_pool * tao_spend / (tao_pool + tao_spend)
    eff_price = tao_spend / alpha_out if alpha_out > 0 else None
    return alpha_out, eff_price


def amm_sell_alpha_for_tao(
    tao_pool: float, alpha_pool: float, alpha_sell: float
) -> tuple[float, float | None]:
    """
    Sell `alpha_sell` alpha at an x·y=k pool. Receive `tao_out` TAO.
    Returns (tao_out, effective_price_tao_per_alpha).
    """
    if tao_pool <= 0 or alpha_pool <= 0 or alpha_sell <= 0:
        return 0.0, None
    tao_out = tao_pool * alpha_sell / (alpha_pool + alpha_sell)
    eff_price = tao_out / alpha_sell if alpha_sell > 0 else None
    return tao_out, eff_price


def _slippage_pct(effective: float | None, spot: float | None, *, side: str) -> float | None:
    """side='buy' → positive slippage = paid above spot; side='sell' → received below spot."""
    if effective is None or not spot:
        return None
    if side == "buy":
        return round((effective - spot) / spot * 100, 4)
    return round((spot - effective) / spot * 100, 4)


# ── Metagraph analysis ────────────────────────────────────────────────────────


def _parse_metagraph(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    parsed = []
    for r in rows:
        parsed.append({
            "uid": r.get("uid"),
            "coldkey": _coldkey(r),
            "validator_permit": bool(r.get("validator_permit")),
            "active": bool(r.get("active")),
            "is_immunity_period": bool(r.get("is_immunity_period")),
            "total_alpha_stake": _rao_to_tao(r.get("total_alpha_stake")) or 0.0,
            "alpha_stake": _rao_to_tao(r.get("alpha_stake")) or 0.0,
            "root_stake_as_alpha": _rao_to_tao(r.get("root_stake_as_alpha")) or 0.0,
            "daily_validating_alpha": _rao_to_tao(r.get("daily_validating_alpha")) or 0.0,
            # `daily_validating_alpha_as_tao` is the TAO-equivalent of the alpha
            # emission earned that day — the right unit for cross-subnet ROI math.
            # The raw `daily_validating_tao` field on metagraph rows is a different
            # (much larger) Taostats-internal metric; don't use it for emissions.
            "daily_validating_alpha_as_tao": _rao_to_tao(r.get("daily_validating_alpha_as_tao")) or 0.0,
            "dividends": _to_float(r.get("dividends")) or 0.0,
            "incentive": _to_float(r.get("incentive")) or 0.0,
        })
    return parsed


# ── Risk / health signals ─────────────────────────────────────────────────────


def _risk_signals(parsed: list[dict[str, Any]], pool: dict[str, Any], sub: dict[str, Any]) -> dict[str, Any]:
    total_alpha = sum(n["total_alpha_stake"] for n in parsed)
    by_stake = sorted(parsed, key=lambda x: -x["total_alpha_stake"])
    top10 = sum(n["total_alpha_stake"] for n in by_stake[:10])
    top64 = sum(n["total_alpha_stake"] for n in by_stake[:64])
    permits = [n for n in parsed if n["validator_permit"]]
    nonzero_permits = [n for n in permits if n["total_alpha_stake"] > 0]

    mcap_tao = _rao_to_tao(pool.get("market_cap"))
    net_flow_30d = _rao_to_tao(sub.get("net_flow_30_days"))
    net_flow_30d_pct_of_mcap = (
        round(net_flow_30d / mcap_tao * 100, 2) if (net_flow_30d is not None and mcap_tao) else None
    )

    return {
        "incentive_burn_pct": round((_to_float(sub.get("incentive_burn")) or 0.0) * 100, 2),
        "top10_stake_share_pct": round(top10 / total_alpha * 100, 2) if total_alpha > 0 else None,
        "top64_stake_share_pct": round(top64 / total_alpha * 100, 2) if total_alpha > 0 else None,
        "unique_coldkeys_top64": len({n["coldkey"] for n in by_stake[:64] if n["coldkey"]}),
        "net_flow_30d_tao": round(net_flow_30d, 2) if net_flow_30d is not None else None,
        "net_flow_30d_pct_of_mcap": net_flow_30d_pct_of_mcap,
        "active_validators": sub.get("active_validators"),
        "active_miners": sub.get("active_miners"),
        "n_permits_issued": len(permits),
        "n_permits_nonzero_stake": len(nonzero_permits),
        "neuron_registration_cost_tao": _rao_to_tao(sub.get("neuron_registration_cost")),
        "registration_allowed": sub.get("registration_allowed"),
    }


# ── Scoring per subnet ────────────────────────────────────────────────────────


def _score_subnet(
    *,
    netuid: int,
    parsed: list[dict[str, Any]],
    pool: dict[str, Any],
    sub: dict[str, Any],
    holders: int | None,
    budget_tao: float,
    sn21_pool: dict[str, Any] | None,
    sn21_alpha_budget: float,
    tao_usd: float | None,
    note: dict[str, Any] | None,
) -> dict[str, Any]:
    """Compute feasibility, yield, slippage, composite score for one subnet."""
    alpha_price_tao = _to_float(pool.get("price")) or 0.0
    target_tao_pool = _rao_to_tao(pool.get("total_tao")) or 0.0
    # AMM alpha reserve must satisfy spot = T_pool / A_pool. Taostats' raw
    # `total_alpha` field includes off-pool minted alpha and is ~2-3× the
    # effective swap reserve. Derive from T and spot so x·y=k is self-consistent.
    target_alpha_pool = (
        target_tao_pool / alpha_price_tao if (alpha_price_tao > 0 and target_tao_pool > 0) else 0.0
    )
    alpha_vol_24h = _rao_to_tao(pool.get("alpha_volume_24_hr"))

    # 1) Convert budget: simulate selling SN21 alpha at SN21 pool.
    sn21_sell_slippage_pct = None
    if sn21_pool:
        sn21_spot = _to_float(sn21_pool.get("price")) or 0.0
        sn21_tao_pool = _rao_to_tao(sn21_pool.get("total_tao")) or 0.0
        sn21_alpha_pool = (
            sn21_tao_pool / sn21_spot if (sn21_spot > 0 and sn21_tao_pool > 0) else 0.0
        )
        tao_proceeds, sn21_eff = amm_sell_alpha_for_tao(
            sn21_tao_pool, sn21_alpha_pool, sn21_alpha_budget
        )
        sn21_sell_slippage_pct = _slippage_pct(sn21_eff, sn21_spot, side="sell")
    else:
        tao_proceeds = budget_tao  # caller supplied straight TAO budget

    # 2) Buy target alpha with proceeds at target pool.
    target_alpha_out, target_buy_eff = amm_buy_alpha_with_tao(
        target_tao_pool, target_alpha_pool, tao_proceeds
    )
    target_buy_slippage_pct = _slippage_pct(target_buy_eff, alpha_price_tao, side="buy")

    # 3) Simulate immediate exit (round-trip impact estimate; same pool reserves).
    tao_recovered, target_sell_eff = amm_sell_alpha_for_tao(
        target_tao_pool, target_alpha_pool, target_alpha_out
    )
    target_sell_slippage_pct = _slippage_pct(target_sell_eff, alpha_price_tao, side="sell")
    round_trip_cost_tao = max(tao_proceeds - tao_recovered, 0.0)
    round_trip_cost_pct = (
        round(round_trip_cost_tao / tao_proceeds * 100, 4) if tao_proceeds > 0 else None
    )

    # 4) Permit feasibility — find lowest non-zero active permit-holder.
    permits = sorted(
        [n for n in parsed if n["validator_permit"]],
        key=lambda x: -x["total_alpha_stake"],
    )
    nonzero_permits = [n for n in permits if n["total_alpha_stake"] > 0]
    lowest_permit_alpha = nonzero_permits[-1]["total_alpha_stake"] if nonzero_permits else 0.0
    lowest_permit_tao_equiv = lowest_permit_alpha * alpha_price_tao
    headroom_ratio = (
        target_alpha_out / lowest_permit_alpha if lowest_permit_alpha > 0 else float("inf")
    )

    # 5) Yield projection — share of validator-pool emissions weighted by stake.
    # Use `daily_validating_alpha_as_tao` (the TAO value of daily alpha
    # emissions) for cross-subnet comparability.
    sum_permit_alpha = sum(n["total_alpha_stake"] for n in nonzero_permits)
    total_validator_pool_daily_tao = sum(
        n["daily_validating_alpha_as_tao"] for n in nonzero_permits
    )
    my_share = (
        target_alpha_out / (sum_permit_alpha + target_alpha_out)
        if (sum_permit_alpha + target_alpha_out) > 0 else 0.0
    )
    projected_daily_tao = my_share * total_validator_pool_daily_tao
    projected_annual_tao = projected_daily_tao * 365
    annual_roi_pct = (
        round(projected_annual_tao / tao_proceeds * 100, 2)
        if tao_proceeds > 0 else None
    )

    # 6) Risk signals.
    risk = _risk_signals(parsed, pool, sub)

    # 7) Composite score:  annual_roi × (1 − round-trip slippage) × manual_multiplier.
    manual_multiplier = float((note or {}).get("multiplier") or 1.0)
    rt_factor = 1.0 - (round_trip_cost_pct or 0) / 100.0
    composite_score = (
        round((annual_roi_pct or 0) * max(rt_factor, 0) * manual_multiplier, 2)
        if annual_roi_pct is not None else None
    )

    return {
        "netuid": netuid,
        "pool": {
            "alpha_price_tao": alpha_price_tao,
            "alpha_price_usd": round(alpha_price_tao * tao_usd, 4) if tao_usd else None,
            "market_cap_tao": _rao_to_tao(pool.get("market_cap")),
            "market_cap_usd": (_rao_to_tao(pool.get("market_cap")) or 0) * tao_usd if tao_usd else None,
            "mcap_rank": pool.get("rank"),
            "alpha_volume_24h_tao": alpha_vol_24h,
            "total_alpha_pool": target_alpha_pool,
            "total_tao_pool": target_tao_pool,
            "price_change_7d_pct": _to_float(pool.get("price_change_1_week")),
        },
        "feasibility": {
            "lowest_permit_alpha": round(lowest_permit_alpha, 2),
            "lowest_permit_tao_equiv": round(lowest_permit_tao_equiv, 2),
            "lowest_permit_usd_equiv": (
                round(lowest_permit_tao_equiv * tao_usd, 2) if tao_usd else None
            ),
            "my_alpha_after_buy": round(target_alpha_out, 2),
            "headroom_ratio": (
                round(headroom_ratio, 2) if headroom_ratio != float("inf") else None
            ),
            "permit_secured": (
                lowest_permit_alpha == 0.0 or headroom_ratio >= 1.5
            ),
        },
        "yield": {
            "sum_permit_alpha": round(sum_permit_alpha, 2),
            "total_validator_pool_daily_tao": round(total_validator_pool_daily_tao, 4),
            "projected_emission_share_pct": round(my_share * 100, 4),
            "projected_daily_tao": round(projected_daily_tao, 4),
            "projected_annual_tao": round(projected_annual_tao, 2),
            "projected_annual_roi_pct": annual_roi_pct,
            "tao_invested": round(tao_proceeds, 2),
            "tao_invested_usd": round(tao_proceeds * tao_usd, 2) if tao_usd else None,
        },
        "slippage": {
            "sn21_sell_slippage_pct": sn21_sell_slippage_pct,
            "target_buy_slippage_pct": target_buy_slippage_pct,
            "target_sell_slippage_pct": target_sell_slippage_pct,
            "round_trip_cost_tao": round(round_trip_cost_tao, 2),
            "round_trip_cost_pct": round_trip_cost_pct,
        },
        "risk_signals": risk,
        "holders": holders,
        "manual_override": {
            "multiplier": manual_multiplier,
            "note": (note or {}).get("note", ""),
        },
        "composite_score": composite_score,
    }


# ── Notes (manual qualitative overrides) ──────────────────────────────────────


def _ensure_seed_notes() -> None:
    if NOTES_STORE.exists():
        return
    seed = {
        "28": {
            "multiplier": 0.5,
            "note": "Pending review of prior emission-farming incidents; halve composite score until cleared.",
        },
    }
    save_json(NOTES_STORE, seed)


def load_notes() -> dict[str, Any]:
    _ensure_seed_notes()
    notes = load_json(NOTES_STORE, {})
    return notes if isinstance(notes, dict) else {}


def set_note(netuid: int, *, multiplier: float | None = None, note: str | None = None) -> dict[str, Any]:
    notes = load_notes()
    key = str(netuid)
    entry = notes.get(key) or {}
    if multiplier is not None:
        entry["multiplier"] = float(multiplier)
    if note is not None:
        entry["note"] = note
    notes[key] = entry
    save_json(NOTES_STORE, notes)
    return entry


def delete_note(netuid: int) -> bool:
    notes = load_notes()
    key = str(netuid)
    if key in notes:
        del notes[key]
        save_json(NOTES_STORE, notes)
        return True
    return False


# ── Orchestration ─────────────────────────────────────────────────────────────


def run_scan() -> dict[str, Any]:
    """Fetch + score the shortlist. Persists current + appends history row. Returns ranked payload."""
    if not _api_key():
        logger.warning("Scout scan skipped: TAOSTATS_API_KEY not set")
        return {"skipped": True, "reason": "missing TAOSTATS_API_KEY"}

    session = requests.Session()
    netuids = _shortlist()
    if not netuids:
        return {"skipped": True, "reason": "empty SCAN_NETUIDS"}

    notes = load_notes()
    tao_usd = _fetch_tao_usd(session)
    time.sleep(INTER_CALL_SLEEP)

    # SN21 pool — needed once to convert the budget.
    sn21_pool = _fetch_pool(session, NETUID_SN21)
    time.sleep(INTER_CALL_SLEEP)

    sn21_alpha_budget = _budget_sn21_alpha()
    sn21_spot = _to_float((sn21_pool or {}).get("price")) or 0.0
    sn21_tao_pool = _rao_to_tao((sn21_pool or {}).get("total_tao")) or 0.0
    # Derive A_pool from T_pool / spot — see _score_subnet for the reasoning.
    sn21_alpha_pool = (
        sn21_tao_pool / sn21_spot if (sn21_spot > 0 and sn21_tao_pool > 0) else 0.0
    )
    tao_proceeds, sn21_eff_sell = amm_sell_alpha_for_tao(
        sn21_tao_pool, sn21_alpha_pool, sn21_alpha_budget
    )
    sn21_sell_slippage_pct = _slippage_pct(sn21_eff_sell, sn21_spot, side="sell")

    scans: list[dict[str, Any]] = []
    errors: dict[str, str] = {}

    for i, netuid in enumerate(netuids):
        logger.info("Scout: scanning netuid %s", netuid)
        try:
            meta = _fetch_metagraph(session, netuid)
            time.sleep(INTER_CALL_SLEEP)
            pool = _fetch_pool(session, netuid)
            time.sleep(INTER_CALL_SLEEP)
            sub = _fetch_subnet(session, netuid)
            time.sleep(INTER_CALL_SLEEP)
            holders = _fetch_holders(session, netuid)

            parsed = _parse_metagraph(meta)
            scored = _score_subnet(
                netuid=netuid,
                parsed=parsed,
                pool=pool or {},
                sub=sub or {},
                holders=holders,
                budget_tao=tao_proceeds,
                sn21_pool=sn21_pool,
                sn21_alpha_budget=sn21_alpha_budget,
                tao_usd=tao_usd,
                note=notes.get(str(netuid)),
            )
            scans.append(scored)
        except Exception as e:
            logger.exception("Scout: netuid %s failed", netuid)
            errors[str(netuid)] = str(e)
        if i < len(netuids) - 1:
            time.sleep(INTER_SUBNET_SLEEP)

    # Rank — highest composite score first; None scores last.
    scans.sort(key=lambda s: -(s.get("composite_score") or float("-inf")))
    for rank, s in enumerate(scans, start=1):
        s["rank"] = rank

    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "fetched_at_utc": now.isoformat(),
        "date": now.strftime("%Y-%m-%d"),
        "tao_usd": tao_usd,
        "budget": {
            "sn21_alpha": sn21_alpha_budget,
            "tao_proceeds_after_sn21_sell": round(tao_proceeds, 2),
            "tao_proceeds_usd": round(tao_proceeds * tao_usd, 2) if tao_usd else None,
            "sn21_sell_slippage_pct": sn21_sell_slippage_pct,
            "sn21_alpha_price_tao": sn21_spot,
        },
        "shortlist": netuids,
        "scans": scans,
        "errors": errors,
    }

    save_json(SCAN_STORE, payload)
    _append_history(payload)
    logger.info(
        "Scout scan: %s subnets ranked (top=%s, score=%s)",
        len(scans),
        scans[0]["netuid"] if scans else None,
        scans[0].get("composite_score") if scans else None,
    )
    return payload


def _append_history(payload: dict[str, Any]) -> None:
    history = load_json(SCAN_HISTORY_STORE, [])
    if not isinstance(history, list):
        history = []
    date_str = payload["date"]
    history = [h for h in history if h.get("date") != date_str]
    history.append({
        "date": date_str,
        "fetched_at_utc": payload["fetched_at_utc"],
        "tao_usd": payload.get("tao_usd"),
        "budget": payload.get("budget"),
        "summary": [
            {
                "netuid": s["netuid"],
                "rank": s.get("rank"),
                "composite_score": s.get("composite_score"),
                "annual_roi_pct": (s.get("yield") or {}).get("projected_annual_roi_pct"),
                "round_trip_cost_pct": (s.get("slippage") or {}).get("round_trip_cost_pct"),
                "permit_secured": (s.get("feasibility") or {}).get("permit_secured"),
                "headroom_ratio": (s.get("feasibility") or {}).get("headroom_ratio"),
            }
            for s in payload.get("scans") or []
        ],
    })
    history.sort(key=lambda h: h.get("date") or "")
    if len(history) > HISTORY_RETENTION_DAYS:
        history = history[-HISTORY_RETENTION_DAYS:]
    save_json(SCAN_HISTORY_STORE, history)


def latest_scan() -> dict[str, Any]:
    return load_json(SCAN_STORE, {})


def scan_history(days: int = 30) -> list[dict[str, Any]]:
    rows = load_json(SCAN_HISTORY_STORE, [])
    if not isinstance(rows, list):
        return []
    return rows[-max(1, min(days, HISTORY_RETENTION_DAYS)):]
