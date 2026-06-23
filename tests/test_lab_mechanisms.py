"""
§4.6 property tests — encode the mechanism's claimed properties and confirm our
implementation honours them. If these pass, our code matches the chain's stated
intent; if not, we've misread it.

These run on a small synthetic ChainState (no chain connection needed), so they
are fast and deterministic in CI.
"""

from __future__ import annotations

import copy

import pytest

from lab import mechanisms as M
from lab.amm import price_impact, buy_impact, realized_tao_from_sell


def _with_b(state, b):
    s = copy.copy(state)
    s["sn21_miner_burn"] = b
    return s


def _state(b_sn21=0.0):
    """Three-subnet synthetic state; SN21 is netuid 21."""
    return {
        "netuid": 21,
        "block": 1,
        "tao_weight": 0.18,
        "root_stake_tao": 5_000_000.0,
        "sn21_miner_burn": b_sn21,
        "subnets": [
            {"netuid": 1, "alpha_issued": 5_000_000.0, "alpha_in": 4_000_000.0,
             "tao_in": 20_000.0, "spot_price": 0.005, "ema_price": 0.005,
             "alpha_out_emission": 1.0, "tao_in_emission": 0.001, "tempo": 360},
            {"netuid": 21, "alpha_issued": 3_300_000.0, "alpha_in": 2_000_000.0,
             "tao_in": 7_800.0, "spot_price": 0.0039, "ema_price": 0.0038,
             "alpha_out_emission": 1.0, "tao_in_emission": 0.0006, "tempo": 360},
            {"netuid": 30, "alpha_issued": 1_000_000.0, "alpha_in": 900_000.0,
             "tao_in": 9_000.0, "spot_price": 0.01, "ema_price": 0.01,
             "alpha_out_emission": 1.0, "tao_in_emission": 0.0012, "tempo": 360},
        ],
    }


# ── Linear burn: emission_share (score) scales linearly with (1 - b) ─────────
def test_linear_burn_score():
    """The mechanism's SN21 score is exactly proportional to (1-b) — the §4.6
    'linear burn' property, independent of cross-subnet normalisation."""
    new = M.get("root_reborn_v346_421")
    sn21_row = next(s for s in _state()["subnets"] if s["netuid"] == 21)
    base = new.score(sn21_row, _with_b(_state(), 0.0))
    for b in (0.25, 0.5, 0.75, 0.9):
        sc = new.score(sn21_row, _with_b(_state(), b))
        assert sc / base == pytest.approx(1.0 - b, rel=1e-9), f"b={b}"


def test_burn_share_monotonic():
    """The normalised share falls monotonically as SN21's burn rises."""
    new = M.get("root_reborn_v346_421")
    shares = [M.emission_share(new, _with_b(_state(), b)) for b in (0.0, 0.25, 0.5, 0.75)]
    assert all(shares[i] > shares[i + 1] for i in range(len(shares) - 1))


def test_burn_zero_recovers_full():
    """No memory: setting b back to 0 restores the full (b=0) share exactly."""
    new = M.get("root_reborn_v346_421")
    s0 = copy.copy(_state()); s0["sn21_miner_burn"] = 0.0
    burned = copy.copy(_state()); burned["sn21_miner_burn"] = 0.9
    recovered = copy.copy(_state()); recovered["sn21_miner_burn"] = 0.0
    assert M.emission_share(new, recovered) == pytest.approx(M.emission_share(new, s0))
    assert M.emission_share(new, burned) < M.emission_share(new, s0)


# ── Symmetry: a buy and an equal-notional sell move price equal-and-opposite ──
def test_amm_symmetry():
    # selling x fraction of alpha vs buying the equivalent: impacts are mirror in sign
    x = 0.01
    down = price_impact(x)          # negative
    up = buy_impact(x)              # positive
    assert down < 0 < up
    # for small x, magnitudes match to first order
    assert abs(up) == pytest.approx(abs(down), rel=0.05)


def test_realized_tao_slippage_below_spot():
    """Realized average price from a sell is always below spot (slippage)."""
    A, T = 2_000_000.0, 7_800.0
    spot = T / A
    sold = 0.02 * A
    realized = realized_tao_from_sell(sold, A, T)
    avg = realized / sold
    assert 0 < avg < spot
    # bigger sells slip more
    big = realized_tao_from_sell(0.10 * A, A, T) / (0.10 * A)
    assert big < avg


# ── Share is a proper distribution ───────────────────────────────────────────
def test_shares_sum_to_one():
    new = M.get("root_reborn_v346_421")
    s = _state()
    total = sum(M.emission_share(new, s, netuid=n["netuid"]) for n in s["subnets"])
    assert total == pytest.approx(1.0, rel=1e-9)


def test_registry_populated():
    assert "incumbent" in M.REGISTRY
    assert "root_reborn_v346_421" in M.REGISTRY
