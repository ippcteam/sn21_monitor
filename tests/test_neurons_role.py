"""Neurons tables split by live role, not validator_permit."""

from datetime import datetime
from zoneinfo import ZoneInfo

from house_weekly import _summarise_window
from neurons_sync import is_mining_role, is_validating_role, neuron_role

ET = ZoneInfo("America/New_York")


def _n(**kwargs):
    return kwargs


def test_permit_holding_miner_is_miner():
    """UID 154: stake permit + miner incentive, zero vTrust → miner."""
    n = _n(validator_permit=True, incentive=0.36794, validator_trust=0,
           dividends=0, daily_mining_alpha=1086.0, daily_validating_alpha=0)
    assert is_mining_role(n) is True
    assert is_validating_role(n) is False
    assert neuron_role(n) == "miner"


def test_idle_house_miner_stays_miner():
    """UID 1: no permit, no incentive — still a miner, not dropped."""
    n = _n(validator_permit=False, incentive=0, validator_trust=0,
           dividends=0, daily_mining_alpha=0, daily_validating_alpha=0)
    assert is_mining_role(n) is True
    assert is_validating_role(n) is False
    assert neuron_role(n) == "miner"


def test_true_validator_is_validator():
    n = _n(validator_permit=True, incentive=0, validator_trust=1.0,
           dividends=0.58, daily_mining_alpha=0, daily_validating_alpha=12.4)
    assert is_validating_role(n) is True
    assert is_mining_role(n) is False
    assert neuron_role(n) == "validator"


def test_dividends_alone_count_as_validating():
    n = _n(validator_permit=True, dividends=0.01, validator_trust=0,
           incentive=0, daily_mining_alpha=0, daily_validating_alpha=0)
    assert neuron_role(n) == "validator"


def test_dual_uid_is_both():
    n = _n(validator_permit=True, incentive=0.02, validator_trust=0.9,
           dividends=0.1, daily_mining_alpha=5.0, daily_validating_alpha=3.0)
    assert is_mining_role(n) is True
    assert is_validating_role(n) is True
    assert neuron_role(n) == "dual"


def test_permit_alone_is_not_a_validator():
    """Idle high-stake UID with a permit and no validating signal → miner."""
    n = _n(validator_permit=True, incentive=0, validator_trust=0,
           dividends=0, daily_mining_alpha=0, daily_validating_alpha=0)
    assert neuron_role(n) == "miner"


def test_historical_row_without_vtrust_uses_alpha():
    """Daily snapshots before role fields still classify from earnings."""
    miner = _n(is_house=True, validator_permit=True, daily_mining_alpha=54.3)
    val = _n(is_house=True, validator_permit=True, daily_validating_alpha=8.0)
    assert neuron_role(miner) == "miner"
    assert neuron_role(val) == "validator"


def test_house_weekly_counts_permit_miner_earnings():
    """UID 154-shaped row: permit + mining α must land in house miners, not vals."""
    start = datetime(2026, 8, 17, 12, 0, tzinfo=ET)
    end = datetime(2026, 8, 24, 12, 0, tzinfo=ET)
    rows = [{
        "date": "2026-08-20",
        "is_house": True,
        "validator_permit": True,
        "incentive": 0.37,
        "daily_mining_alpha": 1086.0,
        "daily_burned_alpha": 0,
        "daily_validating_alpha": 0,
        "alpha_price_tao": 0.0033,
        "tao_price_usd": 209.0,
    }]
    out = _summarise_window(start, end, rows, [])
    assert out["house_miners"]["alpha_gross"] == 1086.0
    assert out["house_miners"]["uid_count"] == 1
    assert out["house_validators"]["alpha"] == 0.0
    assert out["house_validators"]["uid_count"] == 0
