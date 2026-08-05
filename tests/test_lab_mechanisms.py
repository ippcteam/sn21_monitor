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


# ── Actual emission = injection + chain-buy legs (excess-TAO gate fix) ────────
def test_actual_share_counts_excess_tao():
    """The reproduction ground truth must include SubnetExcessTao (chain buys):
    tao_in_emission alone drops capped subnets' emission and inflates SN21's
    apparent share — the old 'SN21 over-emits 3x' artifact."""
    from lab.runner import actual_sn21_share
    s = _state()
    # give subnet 1 a large chain-buy leg; SN21 has none
    next(x for x in s["subnets"] if x["netuid"] == 1)["excess_tao_emission"] = 0.01
    with_excess = actual_sn21_share(s)
    for sub in s["subnets"]:
        sub.pop("excess_tao_emission", None)
    without = actual_sn21_share(s)
    assert with_excess < without  # counting the buy leg deflates SN21's share


def test_effective_burn_invariant_ok_when_actual_matches_model():
    """When 'actual' emission equals the modeled share, effective burn == nominal
    (the invariant check reads OK — no artifact gap)."""
    from lab.runner import sn21_effective_burn
    new = M.get("root_reborn_v346_421")
    s = _state(b_sn21=0.6)
    s["root_tao"] = s["root_stake_tao"]
    scores = {sub["netuid"]: new.score(sub, s) for sub in s["subnets"]}
    tot = sum(scores.values())
    for sub in s["subnets"]:
        sub["tao_in_emission"] = scores[sub["netuid"]] / tot
        sub["excess_tao_emission"] = 0.0
    out = sn21_effective_burn(s, new)
    assert out["effective_burn"] == pytest.approx(0.6, abs=0.01)
    assert "INVARIANT OK" in out["note"]


# ── S6: burn → price trajectory properties ────────────────────────────────────
def _s6_state(b=0.7):
    s = _state(b_sn21=b)
    s["root_tao"] = s["root_stake_tao"]
    s["owner_cut"] = 0.18
    for sub in s["subnets"]:
        sub["excess_tao_emission"] = 0.0005
        sub["alpha_out_emission"] = 1.0
    return s


def test_s6_deeper_cut_higher_price_at_no_dump():
    from lab.scenarios import s6_burn_price
    out = s6_burn_price(_s6_state(), burns=(None, 0.35, 0.0), dump_fracs=(0.0,), days=90)
    rows = {r["b"]: r["d90_vs_hold_pct"] for r in out["table"]}
    assert rows[0.0] >= rows[0.35] >= rows[0.7] == pytest.approx(0.0, abs=0.01)


def test_s6_full_dump_can_underperform_hold():
    from lab.scenarios import s6_burn_price
    out = s6_burn_price(_s6_state(), burns=(None, 0.0), dump_fracs=(0.0, 1.0), days=90)
    full = next(r for r in out["table"] if r["b"] == 0.0 and r["dump_frac"] == 1.0)
    none = next(r for r in out["table"] if r["b"] == 0.0 and r["dump_frac"] == 0.0)
    assert full["d90_vs_hold_pct"] < none["d90_vs_hold_pct"]


# ── spec-425 mechanism (PR #2800): no root_prop in the share ─────────────────
def test_v425_share_ignores_root_prop():
    """Two subnets with equal price and burn split emission 50/50 under v425
    regardless of issuance (root_prop) — mirrors the PR's own unit test."""
    v425 = M.get("root_reborn_v425_2800")
    s = _s6_state(b=0.0)
    sub1 = next(x for x in s["subnets"] if x["netuid"] == 21)
    sub2 = next(x for x in s["subnets"] if x["netuid"] != 21)
    sub2["ema_price"] = sub1["ema_price"]
    sub2["miner_burn"] = 0.0
    sub2["alpha_issued"] = (sub1.get("alpha_issued") or 0.0) * 10  # very different root_prop
    assert v425.score(sub1, s) == pytest.approx(v425.score(sub2, s))


def test_v425_emission_disabled_zeroes_score():
    """Emit-disabled subnets (SubnetEmissionEnabled=false, #2787) get zero share
    and their slice renormalises to the enabled subnets — mirrors v432
    get_subnet_block_emissions."""
    v425 = M.get("root_reborn_v425_2800")
    s = _s6_state(b=0.0)
    other = next(x for x in s["subnets"] if x["netuid"] != 21)
    share_before = M.emission_share(v425, s)
    other["emission_enabled"] = False
    assert v425.score(other, s) == 0.0
    assert M.emission_share(v425, s) > share_before  # renormalised upward


def test_gate_anchors_on_live_mechanism_with_regression_detector():
    """Since the v430-432 deploys the gate anchors on the LIVE price x (1-b)
    mechanism; the superseded three-switch formula is refit as a regression
    detector (fires if the coinbase changes back under us)."""
    from lab.runner import reproduction_gate
    g = reproduction_gate(_s6_state())
    assert g["mechanism"] == M.LIVE_VERSION
    assert "old_formula_median_rel_err" in g and "old_formula_fits_better" in g


# ── S7: stake + retention policy properties ───────────────────────────────────
def test_s7_higher_retention_higher_price():
    from lab.scenarios import s7_stake_retention
    out = s7_stake_retention(_s6_state(), burns=(0.0,), retentions=(0.0, 0.85, 1.0), days=90)
    rows = {r["retention"]: r["d90_vs_hold_pct"] for r in out["table"]}
    assert rows[1.0] >= rows[0.85] >= rows[0.0]


def test_s7_entry_buys_lift_price():
    """The entry-stake leg is a net buy — its isolated contribution is positive."""
    from lab.scenarios import s7_stake_retention
    out = s7_stake_retention(_s6_state(), burns=(0.2,), retentions=(0.85,), days=90)
    assert out["table"][0]["entry_leg_d90_pp"] > 0


def test_s7_stress_underperforms_base_case():
    """Exit-cascade stress (dumping locked stock) can only hurt the trajectory."""
    from lab.scenarios import s7_stake_retention
    out = s7_stake_retention(_s6_state(), burns=(0.2, 0.0), retentions=(0.85, 1.0), days=180)
    for r in out["table"]:
        assert r["stress_d180_vs_hold_pct"] <= r["d180_vs_hold_pct"] + 0.01


def test_s7_retention_one_matches_s6_no_dump_ex_entry():
    """With the entry leg removed, r=1.0 must reproduce S6's dump_frac=0 row —
    the policy engine is S6's, not a fork of it."""
    from lab.scenarios import s6_burn_price, s7_stake_retention
    s = _s6_state()
    s6 = s6_burn_price(s, burns=(0.0,), dump_fracs=(0.0,), days=90)
    s7 = s7_stake_retention(s, burns=(0.0,), retentions=(1.0,), stake_weeks=0.0, days=90)
    r6 = next(r for r in s6["table"] if r["b"] == 0.0)
    r7 = next(r for r in s7["table"] if r["b"] == 0.0)
    assert r7["d90_vs_hold_pct"] == pytest.approx(r6["d90_vs_hold_pct"], abs=0.05)
