"""
Mining / Validation week schedule for SN21 (America/New_York timezone).

Confirmed with the operator:
  Mining window     — Mon 12:00 ET → Sun 00:00 ET   (5d 12h)
  Validation window — Sun 00:00 ET → Mon 12:00 ET   (1d 12h)

Windows partition the week with no overlap and no gap. Eastern Time auto-
handles DST transitions (EDT/EST).
"""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

WindowKind = Literal["mining", "validation"]

MINING_START_HOUR = 12          # Monday noon ET
VALIDATION_END_HOUR = 12        # Monday noon ET (validation ends, mining begins)
# Validation runs Sun 00:00 → Mon 12:00. Mining runs Mon 12:00 → Sun 00:00 (= Sat 24:00).


def _et_now(now_utc: datetime | None = None) -> datetime:
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    return now_utc.astimezone(ET)


def _at(d: datetime, hour: int) -> datetime:
    """Return ET-aware datetime at hour:00 on the same calendar day as `d`."""
    return datetime.combine(d.date(), time(hour, 0, tzinfo=ET))


def current_window(now_utc: datetime | None = None) -> tuple[WindowKind, datetime, datetime]:
    """
    Determine the active mining/validation window covering `now_utc`.

    Returns (kind, start_et, end_et). The two boundaries are inclusive-start,
    exclusive-end. All datetimes are timezone-aware in America/New_York.
    """
    et = _et_now(now_utc)
    weekday = et.weekday()  # Monday=0 … Sunday=6
    hour = et.hour

    # Validation: Sunday 00:00 (weekday=6) up to Monday 12:00 (weekday=0, hour<12)
    in_validation = weekday == 6 or (weekday == 0 and hour < VALIDATION_END_HOUR)

    if in_validation:
        # Validation start = Sunday 00:00 ET this week
        if weekday == 6:
            start = _at(et, 0)
        else:  # Monday morning
            start = _at(et - timedelta(days=1), 0)
        end = _at(start + timedelta(days=1), VALIDATION_END_HOUR)  # Mon 12:00 ET
        return ("validation", start, end)

    # Mining: Mon 12:00 → Sun 00:00 (= Sat 24:00). We're somewhere in there.
    # Walk back to the most recent Monday 12:00 ET.
    days_since_mon = weekday  # Mon=0 → 0 back; Tue=1 → 1 back …
    monday = et - timedelta(days=days_since_mon)
    start = _at(monday, MINING_START_HOUR)
    if et < start:
        # Edge case: Monday before noon counted as validation above — guard anyway.
        start = start - timedelta(days=7)
    end = _at(start + timedelta(days=6), 0)  # Sunday 00:00 ET (= Sat 24:00)
    return ("mining", start, end)


def block_to_utc(current_block: int, current_block_time_utc: datetime, target_block: int,
                 block_seconds: float = 12.0) -> datetime:
    """
    Approximate UTC timestamp for an arbitrary block, given a known reference
    (`current_block` at `current_block_time_utc`). Bittensor blocks are ~12s;
    accuracy is good enough for window boundary checks (minute granularity).
    """
    if current_block_time_utc.tzinfo is None:
        current_block_time_utc = current_block_time_utc.replace(tzinfo=timezone.utc)
    delta_blocks = target_block - current_block
    return current_block_time_utc + timedelta(seconds=delta_blocks * block_seconds)


def is_submitting_in_window(
    last_update_block: int,
    current_block: int,
    current_block_time_utc: datetime,
    window_start_et: datetime,
    block_seconds: float = 12.0,
) -> bool:
    """A UID is "submitting in this window" if its last weight-set block falls
    inside the active window."""
    last_dt_utc = block_to_utc(current_block, current_block_time_utc, last_update_block, block_seconds)
    return last_dt_utc.astimezone(ET) >= window_start_et
