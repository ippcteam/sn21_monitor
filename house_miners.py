"""
House Miners — alpha holdings + rolling earnings for our in-house miners.

"Essentially my money": for each House-labelled miner (see labels.py /
DEFAULT_HOUSE_KEYS) this reports the alpha currently held (staked alpha on the
hotkey), plus rolling 4-week mined alpha and the trend vs the prior 4 weeks, so
miner earnings can be sized against opex.

Sources (no new chain calls):
  - neurons_sync.fetch_neurons()  → live holding (total_alpha_stake), incentive,
    emission, is_house flag, current prices.
  - data/neurons_daily.json       → per-UID daily_mining_alpha_net history (90d)
    for the trailing-28d and prior-28d sums + trend.

Storage: data/house_miners.json (latest snapshot).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from collector import load_json, save_json
from config import DATA_DIR
from neurons_daily_sync import NEURONS_DAILY_STORE, _latest_subnet_prices

logger = logging.getLogger(__name__)

HOUSE_MINERS_STORE = DATA_DIR / "house_miners.json"
WINDOW_DAYS = 28


def _earnings_windows(rows: list[dict], uid: int, today: datetime) -> dict:
    """Trailing-28d and prior-28d net mined alpha for a UID, + trend + coverage."""
    cur_start = (today - timedelta(days=WINDOW_DAYS - 1)).strftime("%Y-%m-%d")
    prev_start = (today - timedelta(days=2 * WINDOW_DAYS - 1)).strftime("%Y-%m-%d")
    prev_end = (today - timedelta(days=WINDOW_DAYS)).strftime("%Y-%m-%d")
    cur = prev = 0.0
    cur_days = prev_days = 0
    for r in rows:
        if r.get("uid") != uid:
            continue
        d = r.get("date")
        net = r.get("daily_mining_alpha_net") or 0.0
        if d and d >= cur_start:
            cur += net
            cur_days += 1
        elif d and prev_start <= d <= prev_end:
            prev += net
            prev_days += 1
    trend = ((cur - prev) / prev * 100.0) if prev > 0 else None
    return {
        "earned_28d_alpha": round(cur, 6),
        "earned_prev_28d_alpha": round(prev, 6),
        "trend_pct": round(trend, 1) if trend is not None else None,
        "days_covered": cur_days,
        "prev_days_covered": prev_days,
    }


def build_house_miners() -> dict[str, Any]:
    """Build the House-miners holdings + earnings snapshot."""
    from neurons_sync import fetch_neurons

    payload = fetch_neurons()
    if "error" in payload:
        return {"error": payload["error"]}

    miners = [m for m in (payload.get("miners") or []) if m.get("is_house")]
    daily = load_json(NEURONS_DAILY_STORE, {})
    rows = daily.get("rows", []) if isinstance(daily, dict) else []

    prices = _latest_subnet_prices()
    alpha_usd = prices.get("alpha_price_usd") or 0.0
    alpha_tao = prices.get("alpha_price_tao") or 0.0
    today = datetime.now(timezone.utc)

    out_miners: list[dict[str, Any]] = []
    for m in miners:
        uid = m.get("uid")
        holding = m.get("total_alpha_stake") or 0.0
        win = _earnings_windows(rows, uid, today)
        out_miners.append({
            "uid": uid,
            "hotkey": m.get("hotkey"),
            "hotkey_short": m.get("hotkey_short"),
            "coldkey": m.get("coldkey"),
            "holding_alpha": round(holding, 6),
            "holding_usd": round(holding * alpha_usd, 2) if alpha_usd else None,
            "holding_tao": round(holding * alpha_tao, 6) if alpha_tao else None,
            "incentive": m.get("incentive"),
            "emission_alpha_per_tempo": m.get("emission_alpha_per_tempo"),
            "submitting_in_window": m.get("submitting_in_window"),
            **win,
            "earned_28d_usd": round((win["earned_28d_alpha"]) * alpha_usd, 2) if alpha_usd else None,
        })

    out_miners.sort(key=lambda x: (-(x.get("holding_alpha") or 0.0), x.get("uid") or 0))

    totals = {
        "n_miners": len(out_miners),
        "holding_alpha": round(sum((m["holding_alpha"] or 0.0) for m in out_miners), 6),
        "holding_usd": round(sum((m["holding_usd"] or 0.0) for m in out_miners), 2) if alpha_usd else None,
        "earned_28d_alpha": round(sum((m["earned_28d_alpha"] or 0.0) for m in out_miners), 6),
        "earned_28d_usd": round(sum((m["earned_28d_usd"] or 0.0) for m in out_miners), 2) if alpha_usd else None,
        "earned_prev_28d_alpha": round(sum((m["earned_prev_28d_alpha"] or 0.0) for m in out_miners), 6),
    }
    et = totals["earned_28d_alpha"]
    ep = totals["earned_prev_28d_alpha"]
    totals["trend_pct"] = round((et - ep) / ep * 100.0, 1) if ep > 0 else None

    snapshot = {
        "fetched_at_utc": today.isoformat(),
        "block": payload.get("block_number"),
        "window_days": WINDOW_DAYS,
        "alpha_price_tao": alpha_tao or None,
        "alpha_price_usd": alpha_usd or None,
        "tao_price_usd": prices.get("tao_price_usd"),
        "miners": out_miners,
        "totals": totals,
    }
    save_json(HOUSE_MINERS_STORE, snapshot)
    logger.info("House miners snapshot: %d miners, holding %.2f alpha",
                totals["n_miners"], totals["holding_alpha"])
    return snapshot


def get_house_miners() -> dict[str, Any]:
    """Latest snapshot from disk (build it on demand if missing)."""
    snap = load_json(HOUSE_MINERS_STORE, None)
    if not snap:
        return {"error": "No house-miners snapshot yet — POST /api/house/miners/sync"}
    return snap
