"""Conviction-tripwire tier model — pure-function tests (no chain connection)."""

from __future__ import annotations

from conviction_watch import assess, ONE_YEAR_BLOCKS

OWNER_CK = "5Owner"
OWNER_HK = "5OwnerHot"


def _chain(entries, alpha_out=3_600_000.0, age=ONE_YEAR_BLOCKS * 2):
    return {
        "block": 8_700_000,
        "owner_coldkey": OWNER_CK,
        "owner_hotkey": OWNER_HK,
        "alpha_out": alpha_out,
        "registered_at_block": 1,
        "age_blocks": age,
        "entries": entries,
    }


def _lock(hotkey, coldkey, mass, conviction=0.0):
    return {
        "hotkey": hotkey,
        "coldkey": coldkey,
        "is_owner": coldkey == OWNER_CK or hotkey == OWNER_HK,
        "locked_mass_alpha": mass,
        "conviction_alpha": conviction,
        "last_update_block": 8_600_000,
    }


def test_no_locks_is_clear():
    a = assess(_chain([]))
    assert a["tier"] == 0 and a["status"] == "ok"
    assert a["age_armed"] is True
    # 10% of alpha_out
    assert a["takeover_threshold_alpha"] == 360_000


def test_owner_lock_alone_stays_clear():
    a = assess(_chain([_lock(OWNER_HK, OWNER_CK, 50_000, 20_000)]))
    assert a["tier"] == 0 and a["status"] == "ok"
    assert a["owner_conviction_alpha"] == 20_000


def test_any_third_party_lock_trips_tier_1():
    a = assess(_chain([_lock("5Attacker", "5AttCk", 500)]))
    assert a["tier"] == 1 and a["status"] == "alert"
    assert a["third_party_locked_mass_alpha"] == 500


def test_mass_tiers_escalate_on_threshold_fractions():
    # threshold = 360k: 25% -> 90k, 50% -> 180k, 75% -> 270k
    for mass, tier in ((90_000, 2), (180_000, 3), (270_000, 4)):
        a = assess(_chain([_lock("5Att", "5AttCk", mass)]))
        assert a["tier"] == tier, f"mass={mass}"


def test_tier_5_needs_threshold_mass_and_out_convicting_owner():
    third_full = _lock("5Att", "5AttCk", 400_000, conviction=100_000)
    # owner still out-convicts -> capped at tier 4
    a = assess(_chain([third_full, _lock(OWNER_HK, OWNER_CK, 300_000, 150_000)]))
    assert a["tier"] == 4
    # owner conviction below the attacker's -> takeover technically possible
    a = assess(_chain([third_full, _lock(OWNER_HK, OWNER_CK, 300_000, 50_000)]))
    assert a["tier"] == 5


def test_age_disarmed_still_reports():
    a = assess(_chain([_lock("5Att", "5AttCk", 500)], age=ONE_YEAR_BLOCKS // 2))
    assert a["age_armed"] is False
    assert a["tier"] == 1  # tripwire still fires; age only gates the chain's clause
