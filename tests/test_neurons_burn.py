"""burn_summary must count the burn sink wherever it sits in the metagraph.

SN21 burns via the owner hotkey (UID 135), which holds a validator permit — so
any aggregate restricted to the non-permit `miners` split reports 0% burn while
the chain burns ~45%. These tests pin the shape of the live 2026-07-31 snapshot.
"""

from neurons_sync import burn_summary


def _uid(uid, *, permit=False, mining=None, burned=None):
    return {
        "uid": uid,
        "validator_permit": permit,
        "daily_mining_alpha": mining,
        "daily_burned_alpha": burned,
    }


# Live shape @ block 8,741,513: UID 135 (permit-holding owner hotkey) mines
# 1330.66 α and burns all of it; the 247 miners share 1618.00 α between them and
# every one of them reports daily_burned_alpha: null.
LIVE_SNAPSHOT = [
    _uid(135, permit=True, mining=1330.66349279, burned=1330.66349279),
    _uid(240, mining=38.9185626),
    _uid(202, mining=38.9185626),
    _uid(92, mining=1540.1628748),
]


def test_permit_holding_burn_sink_is_counted():
    """The regression: excluding permit holders zeroed the numerator."""
    assert burn_summary(LIVE_SNAPSHOT)["rate"] == 0.451277


def test_rate_matches_chain_minerburned():
    """Chain MinerBurned(21) == Taostats incentive_burn == 0.4508 on this snapshot."""
    assert abs(burn_summary(LIVE_SNAPSHOT)["rate"] - 0.4508) < 0.01


def test_gross_burned_and_net_totals():
    assert burn_summary(LIVE_SNAPSHOT) == {
        "rate": 0.451277,
        "total_mining_alpha_gross": 2948.66349279,
        "total_mining_alpha_burned": 1330.66349279,
        "total_mining_alpha_net": 1618.0,
    }


def test_null_burn_fields_count_as_zero_burned_not_zero_gross():
    """Miners report daily_burned_alpha: null — that must read as 0 burned while
    their mining alpha still lands in the denominator."""
    assert burn_summary([_uid(1, mining=100.0), _uid(2, mining=100.0, burned=50.0)]) == {
        "rate": 0.25,
        "total_mining_alpha_gross": 200.0,
        "total_mining_alpha_burned": 50.0,
        "total_mining_alpha_net": 150.0,
    }


def test_full_burn_reads_one():
    s = burn_summary([_uid(135, permit=True, mining=42.0, burned=42.0)])
    assert s["rate"] == 1.0
    assert s["total_mining_alpha_net"] == 0.0


def test_no_mining_alpha_gives_no_rate():
    """Zero gross must be None — not a ZeroDivisionError, and not 0% burn."""
    assert burn_summary([_uid(1), _uid(2, permit=True)])["rate"] is None
    assert burn_summary([])["rate"] is None
