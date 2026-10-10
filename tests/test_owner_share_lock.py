"""Owner-share lock schedule + pre-flight — pure-function tests (no chain connection)."""

from __future__ import annotations

from datetime import date

from owner_share_lock import SUBNET_OWNER_HOTKEY, last_lock_day, owed_window, preflight


def _state(available=40_000.0, free_tao=0.05, lock=None):
    return {"available_alpha": available, "free_tao": free_tao, "lock": lock}


def test_first_run_covers_mon_21_through_fri_25_sept():
    first, days = owed_window([], through=date(2026, 9, 25))
    assert first == date(2026, 9, 21) and days == 5


def test_following_friday_covers_seven_days():
    records = [{"covered_through": "2026-09-25"}]
    first, days = owed_window(records, through=date(2026, 10, 2))
    assert first == date(2026, 9, 26) and days == 7


def test_rerun_same_friday_owes_nothing():
    records = [{"covered_through": "2026-09-25"}]
    assert owed_window(records, through=date(2026, 9, 25))[1] == 0


def test_missed_friday_rolls_into_next():
    records = [{"covered_through": "2026-09-25"}]
    assert owed_window(records, through=date(2026, 10, 9))[1] == 14


def test_period_ends_on_most_recent_friday():
    assert last_lock_day(date(2026, 9, 25)) == date(2026, 9, 25)  # Friday itself
    assert last_lock_day(date(2026, 9, 26)) == date(2026, 9, 25)  # Saturday catch-up
    assert last_lock_day(date(2026, 10, 1)) == date(2026, 9, 25)  # Thursday


def test_clean_state_passes():
    assert preflight(_state(), 1_620) == []


def test_no_tao_blocks():
    assert any("fund it" in p for p in preflight(_state(free_tao=0.0), 1_620))


def test_insufficient_unlocked_alpha_blocks():
    assert any("unlocked" in p for p in preflight(_state(available=1_000.0), 1_620))


def test_lock_on_other_hotkey_blocks():
    lock = {"hotkey": "5Other", "locked_alpha": 10.0, "is_perpetual": False}
    assert any("LockHotkeyMismatch" in p for p in preflight(_state(lock=lock), 1_620))


def test_perpetual_lock_blocks():
    lock = {"hotkey": SUBNET_OWNER_HOTKEY, "locked_alpha": 10.0, "is_perpetual": True}
    assert any("PERPETUAL" in p for p in preflight(_state(lock=lock), 1_620))
