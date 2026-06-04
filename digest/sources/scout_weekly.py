"""
Weekly Scout digest source. Reads the latest `subnet_scan.json` + 7d history
and returns a structured `inputs` dict for the composer to narrate.

No new fetches — relies on the daily scout scheduler having populated the
stores. If the latest scan is older than 7 days the source returns a hint
flag for the composer.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from collector import load_json
from config import DATA_DIR

logger = logging.getLogger(__name__)

SCAN_STORE = DATA_DIR / "subnet_scan.json"
SCAN_HISTORY_STORE = DATA_DIR / "subnet_scan_history.json"


def _row_by_age(history: list[dict], days_ago: int) -> dict | None:
    """Closest history row to `days_ago` behind the most recent. None if empty."""
    if not history:
        return None
    history = [h for h in history if h.get("date")]
    if not history:
        return None
    history.sort(key=lambda h: h["date"])
    latest_date = history[-1]["date"]
    try:
        latest_dt = datetime.strptime(latest_date, "%Y-%m-%d")
    except ValueError:
        return history[0]
    target = latest_dt.timestamp() - days_ago * 86400
    best = history[0]
    best_diff = abs(datetime.strptime(best["date"], "%Y-%m-%d").timestamp() - target)
    for h in history[1:]:
        try:
            dt = datetime.strptime(h["date"], "%Y-%m-%d").timestamp()
        except ValueError:
            continue
        d = abs(dt - target)
        if d < best_diff:
            best_diff = d
            best = h
    return best


def _summary_index(row: dict | None) -> dict[int, dict]:
    if not row:
        return {}
    return {s["netuid"]: s for s in (row.get("summary") or []) if "netuid" in s}


def _condense_scan(s: dict) -> dict:
    """Trim a per-subnet scan record down to the fields the composer needs."""
    pool = s.get("pool") or {}
    feas = s.get("feasibility") or {}
    yld = s.get("yield") or {}
    slip = s.get("slippage") or {}
    risk = s.get("risk_signals") or {}
    return {
        "netuid": s.get("netuid"),
        "rank": s.get("rank"),
        "composite_score": s.get("composite_score"),
        "alpha_price_usd": pool.get("alpha_price_usd"),
        "market_cap_usd": pool.get("market_cap_usd"),
        "mcap_rank": pool.get("mcap_rank"),
        "price_change_7d_pct": pool.get("price_change_7d_pct"),
        "lowest_permit_usd_equiv": feas.get("lowest_permit_usd_equiv"),
        "headroom_ratio": feas.get("headroom_ratio"),
        "permit_secured": feas.get("permit_secured"),
        "projected_annual_roi_pct": yld.get("projected_annual_roi_pct"),
        "projected_daily_tao": yld.get("projected_daily_tao"),
        "projected_emission_share_pct": yld.get("projected_emission_share_pct"),
        "tao_invested": yld.get("tao_invested"),
        "round_trip_cost_pct": slip.get("round_trip_cost_pct"),
        "incentive_burn_pct": risk.get("incentive_burn_pct"),
        "top10_stake_share_pct": risk.get("top10_stake_share_pct"),
        "unique_coldkeys_top64": risk.get("unique_coldkeys_top64"),
        "net_flow_30d_pct_of_mcap": risk.get("net_flow_30d_pct_of_mcap"),
        "active_validators": risk.get("active_validators"),
        "active_miners": risk.get("active_miners"),
        "n_permits_issued": risk.get("n_permits_issued"),
        "manual_note": (s.get("manual_override") or {}).get("note"),
        "manual_multiplier": (s.get("manual_override") or {}).get("multiplier"),
    }


def _diff_scores(current: list[dict], prior_summary: dict[int, dict]) -> list[dict]:
    """Per-subnet score deltas vs 7 days ago."""
    out = []
    for s in current:
        netuid = s["netuid"]
        prev = prior_summary.get(netuid) or {}
        prev_score = prev.get("composite_score")
        prev_rank = prev.get("rank")
        prev_permit = prev.get("permit_secured")
        cur_score = s.get("composite_score")
        cur_rank = s.get("rank")
        cur_permit = (s.get("feasibility") or {}).get("permit_secured")
        score_delta = (
            round((cur_score or 0) - (prev_score or 0), 2)
            if (cur_score is not None and prev_score is not None) else None
        )
        rank_delta = (
            (prev_rank or 0) - (cur_rank or 0)  # positive = moved up the ranking
            if (cur_rank is not None and prev_rank is not None) else None
        )
        permit_flipped = (
            prev_permit is not None and cur_permit is not None and prev_permit != cur_permit
        )
        out.append({
            "netuid": netuid,
            "rank": cur_rank,
            "rank_prior_7d": prev_rank,
            "rank_delta": rank_delta,
            "score": cur_score,
            "score_prior_7d": prev_score,
            "score_delta": score_delta,
            "permit_secured_now": cur_permit,
            "permit_secured_prior_7d": prev_permit,
            "permit_flipped": permit_flipped,
        })
    return out


def gather() -> dict[str, Any]:
    scan = load_json(SCAN_STORE, {})
    history = load_json(SCAN_HISTORY_STORE, [])
    if not isinstance(history, list):
        history = []

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    scan_date = scan.get("date") or ""
    days_since_scan = None
    if scan_date:
        try:
            days_since_scan = (
                datetime.strptime(today, "%Y-%m-%d") - datetime.strptime(scan_date, "%Y-%m-%d")
            ).days
        except ValueError:
            days_since_scan = None

    prior_row = _row_by_age(history, days_ago=7)
    prior_summary = _summary_index(prior_row)
    scans = scan.get("scans") or []

    return {
        "today": today,
        "scan_date": scan_date,
        "days_since_scan": days_since_scan,
        "stale": (days_since_scan is not None and days_since_scan > 2),
        "budget": scan.get("budget"),
        "tao_usd": scan.get("tao_usd"),
        "shortlist": scan.get("shortlist"),
        "ranked": [_condense_scan(s) for s in scans],
        "diffs_vs_7d_ago": _diff_scores(scans, prior_summary),
        "errors": scan.get("errors") or {},
    }
