"""CPMM residual floor + SN29 d2tao BIT identities (lab/amm.py).

These encode the PDF's claimed algebra against x·y=k, not a finney
reproduction. See docs/SN21_AMM_Floor_BIT_2026-08-20.md.
"""

from __future__ import annotations

import math

import pytest

from lab.amm import (
    amm_floor_from_row,
    amm_price_floor_cpmm,
    d2tao_instant_price_factor,
    d2tao_new_spot,
    liquidation_price,
    locked_tao_cpmm,
)


# Disposition-shaped July snapshot (α_in derived from τ_in / p).
TAO_IN = 7_369.0
ALPHA_IN = 7_369.0 / 0.00333
ALPHA_HELD = 3_568_900.0


def test_locked_tao_is_fraction_of_pool():
    locked = locked_tao_cpmm(TAO_IN, ALPHA_IN, ALPHA_HELD)
    assert 0 < locked < TAO_IN
    a0 = ALPHA_IN + ALPHA_HELD
    assert locked == pytest.approx(TAO_IN * ALPHA_IN / a0)


def test_plowest_is_locked_over_alpha0():
    a0 = ALPHA_IN + ALPHA_HELD
    floor = amm_price_floor_cpmm(TAO_IN, ALPHA_IN, ALPHA_HELD)
    assert floor == pytest.approx(locked_tao_cpmm(TAO_IN, ALPHA_IN, ALPHA_HELD) / a0)
    # SN21: floor is a small fraction of spot, not a dereg-safe backstop.
    spot = TAO_IN / ALPHA_IN
    assert 0.10 < floor / spot < 0.20
    assert floor == pytest.approx(0.000488, abs=1e-5)


def test_instant_factor_matches_eq11_over_old_spot():
    old = TAO_IN / ALPHA_IN
    new = d2tao_new_spot(TAO_IN, ALPHA_IN, ALPHA_HELD)
    factor = d2tao_instant_price_factor(ALPHA_IN, ALPHA_HELD)
    assert factor == pytest.approx(1.0 + 2.0 * ALPHA_IN / ALPHA_HELD)
    assert new / old == pytest.approx(factor)


def test_liquidation_vs_spot_can_exceed_on_cpmm():
    """Current-pool dereg arb: p_liq can sit above or below spot depending on ADR."""
    p_liq = liquidation_price(TAO_IN, ALPHA_HELD)
    spot = TAO_IN / ALPHA_IN
    assert p_liq > 0
    # July SN21 snapshot: more α held than in-pool → p_liq < spot.
    assert p_liq < spot


def test_last_alpha_factor_is_unbounded():
    assert d2tao_instant_price_factor(1_000.0, 0.0) == math.inf


def test_amm_floor_from_row_uses_issued_as_held():
    row = {
        "tao_in": TAO_IN,
        "alpha_in": ALPHA_IN,
        "alpha_issued": ALPHA_HELD,
        "spot_price": 0.00333,
    }
    snap = amm_floor_from_row(row)
    assert snap["locked_tao"] == pytest.approx(locked_tao_cpmm(TAO_IN, ALPHA_IN, ALPHA_HELD))
    assert snap["plowest"] == pytest.approx(amm_price_floor_cpmm(TAO_IN, ALPHA_IN, ALPHA_HELD))
    assert snap["spot"] == pytest.approx(0.00333)
    assert snap["dereg_safe_hint"] is False
    assert snap["floor_over_spot"] == pytest.approx(snap["plowest"] / 0.00333)


def test_empty_row_is_zero_not_nan():
    snap = amm_floor_from_row({})
    assert snap["locked_tao"] == 0.0
    assert snap["plowest"] == 0.0
    assert snap["dereg_safe_hint"] is False
