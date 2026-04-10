"""
SN21 ownership entitlement schedule (fraction of full owner-key alpha pool).

Tiers are calendar-based from OWNERSHIP_START:
  months 1–6:   25%  |  months 7–12:  50%  |  months 13–24: 75%  |  month 25+: 90%
"""

from __future__ import annotations

import os
from datetime import date, datetime, time, timezone
from typing import Any

from dateutil.relativedelta import relativedelta


def _parse_start() -> date:
    raw = os.environ.get("OWNERSHIP_START_DATE", "2026-02-19").strip()
    return date.fromisoformat(raw)


OWNERSHIP_START: date = _parse_start()


def tier_boundaries() -> tuple[date, date, date]:
    """Dates when tier 2, 3, and 4 begin (inclusive)."""
    s = OWNERSHIP_START
    return (
        s + relativedelta(months=6),
        s + relativedelta(months=12),
        s + relativedelta(months=24),
    )


def entitlement_rate_on(day: date) -> float:
    """
    Our share of the full owner-pool alpha for `day` (UTC calendar date).
    Before ownership start: 0.
    """
    if day < OWNERSHIP_START:
        return 0.0
    b6, b12, b24 = tier_boundaries()
    if day < b6:
        return 0.25
    if day < b12:
        return 0.50
    if day < b24:
        return 0.75
    return 0.90


def entitlement_rate_for_snapshot_date(date_str: str) -> float:
    return entitlement_rate_on(date.fromisoformat(date_str[:10]))


def tier_label(rate: float) -> str:
    return {0.25: "25%", 0.50: "50%", 0.75: "75%", 0.90: "90%"}.get(rate, f"{rate * 100:.0f}%")


def next_tier_info(today: date | None = None) -> dict[str, Any]:
    """Human-readable current tier and next step."""
    today = today or date.today()
    rate = entitlement_rate_on(today)
    b6, b12, b24 = tier_boundaries()
    if today < OWNERSHIP_START:
        return {
            "current_rate": 0.0,
            "label": "—",
            "next_change_date": OWNERSHIP_START.isoformat(),
            "next_rate": 0.25,
            "note": "Before recorded ownership start",
        }
    if today < b6:
        return {
            "current_rate": rate,
            "label": tier_label(rate),
            "next_change_date": b6.isoformat(),
            "next_rate": 0.50,
            "note": f"Until {b6.isoformat()} (then 50%)",
        }
    if today < b12:
        return {
            "current_rate": rate,
            "label": tier_label(rate),
            "next_change_date": b12.isoformat(),
            "next_rate": 0.75,
            "note": f"Until {b12.isoformat()} (then 75%)",
        }
    if today < b24:
        return {
            "current_rate": rate,
            "label": tier_label(rate),
            "next_change_date": b24.isoformat(),
            "next_rate": 0.90,
            "note": f"Until {b24.isoformat()} (then 90%)",
        }
    return {
        "current_rate": rate,
        "label": tier_label(rate),
        "next_change_date": None,
        "next_rate": None,
        "note": "Final tier (90%)",
    }


def scheduled_tier_events() -> list[tuple[datetime, str]]:
    """
    UTC midnight on each tier boundary for one-off scheduler jobs (logging).
    (start+6m → 50%, +12m → 75%, +24m → 90%)
    """
    b6, b12, b24 = tier_boundaries()
    out: list[tuple[datetime, str]] = []
    for boundary, msg in (
        (b6, "Entitlement tier now 50% (months 7–12)"),
        (b12, "Entitlement tier now 75% (months 13–24)"),
        (b24, "Entitlement tier now 90% (month 25 onward)"),
    ):
        out.append(
            (
                datetime.combine(boundary, time(0, 0, 0), tzinfo=timezone.utc),
                msg,
            )
        )
    return out
