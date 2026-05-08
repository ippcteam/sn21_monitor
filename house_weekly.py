"""
Weekly House earnings rollup.

Sums the daily per-UID snapshots in `neurons_daily.json` over each SN21
mining/validation week (Mon 12:00 ET → following Mon 12:00 ET) and pairs
it with the owner-key 18% emissions stored in the daily collector log.

Burn awareness:
  - House miner GROSS  = sum(daily_mining_alpha)
  - House miner BURNED = sum(daily_burned_alpha)
  - House miner NET    = gross - burned   ← realised earnings post-burn
  - House validators and the owner-key 18% are burn-immune and reported as-is.
"""

from __future__ import annotations

import logging
import os
from datetime import date, datetime
from typing import Any

from collector import load_json
from config import DAILY_LOG
from neurons_daily_sync import NEURONS_DAILY_STORE
from windows import date_in_weekly_window, previous_weekly_window, weekly_window

logger = logging.getLogger(__name__)


def _burn_flip_date() -> str | None:
    raw = (os.environ.get("BURN_FLIP_DATE") or "").strip()
    if not raw:
        return None
    try:
        date.fromisoformat(raw)
        return raw
    except ValueError:
        return None


def _summarise_window(
    start_et: datetime,
    end_et: datetime,
    rows: list[dict[str, Any]],
    daily_log: list[dict[str, Any]],
) -> dict[str, Any]:
    in_week_rows = [r for r in rows if date_in_weekly_window(r.get("date") or "", start_et, end_et)]
    in_week_daily = [
        e for e in daily_log
        if date_in_weekly_window(e.get("date") or "", start_et, end_et)
    ]

    house_miners = [r for r in in_week_rows if r.get("is_house") and not r.get("validator_permit")]
    house_vals   = [r for r in in_week_rows if r.get("is_house") and r.get("validator_permit")]
    all_miners   = [r for r in in_week_rows if not r.get("validator_permit")]

    miner_gross  = sum((r.get("daily_mining_alpha") or 0.0) for r in house_miners)
    miner_burned = sum((r.get("daily_burned_alpha") or 0.0) for r in house_miners)
    miner_net    = miner_gross - miner_burned
    val_alpha    = sum((r.get("daily_validating_alpha") or 0.0) for r in house_vals)

    # Owner-key emissions: prefer authoritative `our_entitled_alpha` from the
    # collector daily log; fall back to summing daily_owner_alpha for any row
    # tagged is_owner_hotkey.
    owner_alpha = sum(
        ((e.get("subnet") or {}).get("our_entitled_alpha") or 0.0)
        for e in in_week_daily
    )
    if owner_alpha == 0.0:
        owner_alpha = sum(
            (r.get("daily_owner_alpha") or 0.0)
            for r in in_week_rows if r.get("is_owner_hotkey")
        )

    # Subnet-wide burn rate over the week (alpha-weighted).
    total_mining_gross  = sum((r.get("daily_mining_alpha") or 0.0) for r in all_miners)
    total_mining_burned = sum((r.get("daily_burned_alpha") or 0.0) for r in all_miners)
    burn_rate = (
        round(total_mining_burned / total_mining_gross, 6)
        if total_mining_gross > 0 else None
    )

    # Latest TAO/USD price seen in the week (used to convert alpha → USD).
    last_alpha_tao = next(
        (r.get("alpha_price_tao") for r in reversed(in_week_rows) if r.get("alpha_price_tao")),
        None,
    )
    last_tao_usd = next(
        (r.get("tao_price_usd") for r in reversed(in_week_rows) if r.get("tao_price_usd")),
        None,
    )

    def to_tao(v: float) -> float | None:
        return round(v * last_alpha_tao, 8) if last_alpha_tao else None

    def to_usd(v: float) -> float | None:
        if last_alpha_tao is None or last_tao_usd is None:
            return None
        return round(v * last_alpha_tao * last_tao_usd, 2)

    days_with_data = len({r["date"] for r in in_week_rows if r.get("date")})

    return {
        "start_et": start_et.isoformat(),
        "end_et": end_et.isoformat(),
        "coverage": {
            "days_with_data": days_with_data,
            "days_in_window": 7,
        },
        "burn": {
            "rate": burn_rate,
            "subnet_mining_alpha_gross": round(total_mining_gross, 9),
            "subnet_mining_alpha_burned": round(total_mining_burned, 9),
        },
        "house_miners": {
            "alpha_gross":  round(miner_gross, 9),
            "alpha_burned": round(miner_burned, 9),
            "alpha_net":    round(miner_net, 9),
            "tao_net":      to_tao(miner_net),
            "usd_net":      to_usd(miner_net),
            "tao_gross":    to_tao(miner_gross),
            "usd_gross":    to_usd(miner_gross),
            "uid_count":    len({r.get("uid") for r in house_miners}),
        },
        "house_validators": {
            "alpha":     round(val_alpha, 9),
            "tao":       to_tao(val_alpha),
            "usd":       to_usd(val_alpha),
            "uid_count": len({r.get("uid") for r in house_vals}),
        },
        "owner_key": {
            "alpha":     round(owner_alpha, 9),
            "tao":       to_tao(owner_alpha),
            "usd":       to_usd(owner_alpha),
        },
    }


def _wow_pct(curr: float | None, prev: float | None) -> float | None:
    if curr is None or prev in (None, 0):
        return None
    try:
        return round((curr - prev) / prev * 100, 2)
    except Exception:
        return None


def get_weekly(weeks: int = 4) -> dict[str, Any]:
    """Build the current week + N prior weeks of House earnings."""
    weeks = max(1, min(weeks, 26))

    store = load_json(NEURONS_DAILY_STORE, {"rows": []})
    rows = (store or {}).get("rows") or []
    daily_log = load_json(DAILY_LOG, [])

    series: list[dict[str, Any]] = []
    cur_start, cur_end = weekly_window()
    series.append(_summarise_window(cur_start, cur_end, rows, daily_log))
    for i in range(1, weeks + 1):
        s, e = previous_weekly_window(i)
        series.append(_summarise_window(s, e, rows, daily_log))

    # Compute WoW deltas on the most-recent week vs the immediately previous one.
    wow = {}
    if len(series) >= 2:
        cur, prev = series[0], series[1]
        wow = {
            "house_miners_alpha_net": _wow_pct(
                cur["house_miners"]["alpha_net"], prev["house_miners"]["alpha_net"]
            ),
            "house_miners_alpha_gross": _wow_pct(
                cur["house_miners"]["alpha_gross"], prev["house_miners"]["alpha_gross"]
            ),
            "house_validators_alpha": _wow_pct(
                cur["house_validators"]["alpha"], prev["house_validators"]["alpha"]
            ),
            "owner_key_alpha": _wow_pct(
                cur["owner_key"]["alpha"], prev["owner_key"]["alpha"]
            ),
        }

    return {
        "now_utc": datetime.utcnow().isoformat() + "Z",
        "burn_flip_date": _burn_flip_date(),
        "current": series[0],
        "previous": series[1] if len(series) >= 2 else None,
        "history": series,  # most-recent first
        "wow_pct": wow,
    }
