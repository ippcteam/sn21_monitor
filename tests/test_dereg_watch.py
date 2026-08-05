"""
Dereg-tripwire tests — the pruning rule encoded as properties, on synthetic chain
state (no connection needed).

The rule under test (subtensor coinbase/root.rs get_network_to_prune): among
subnets whose age >= NetworkImmunityPeriod, the LOWEST SubnetMovingPrice is
dissolved on the next subnet registration. Everything the lab now consumes —
the buffer count, the live floor, the extraction guard — hangs off that.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from dereg_watch import (
    DEREG_BUFFER_MIN,
    EROSION_ALERT_PLACES,
    THETA_MOVE_ALERT,
    _erosion,
    _gate_changes,
    _tier,
    assess,
)

IMMUNITY = 864_000
BLOCK = 10_000_000


def _chain(emas: dict[int, float], immune: set[int] = frozenset(), netuid: int = 21) -> dict:
    """Synthetic fetch_prune_state() result: {netuid: ema}, some marked immune."""
    return {
        "block": BLOCK,
        "netuid": netuid,
        "subnet_limit": 128,
        "immunity_blocks": IMMUNITY,
        "lock_cost_tao": 707.0,
        "prune_target_netuid": None,
        "swap_price": None,
        "pool_tao": 7_367.0,
        "pool_alpha": 2_215_179.0,
        "cleanup_queue_len": 0,
        "registration_queue_len": 0,
        "defence": [],
        "subnets": [
            {
                "netuid": n,
                "ema": ema,
                "spot": ema,
                "registered_at": BLOCK - (1_000 if n in immune else 2 * IMMUNITY),
                "age_blocks": 1_000 if n in immune else 2 * IMMUNITY,
                "immune": n in immune,
            }
            for n, ema in emas.items()
        ],
    }


def test_buffer_counts_only_non_immune_subnets_below_us():
    # 5 cheaper subnets, but two of them are immune and cannot be pruned.
    emas = {21: 0.0040, 1: 0.001, 2: 0.002, 3: 0.003, 4: 0.0035, 5: 0.0038, 9: 0.010}
    out = assess(_chain(emas, immune={2, 4}))
    assert out["subnets_below"] == 3          # 1, 3, 5
    assert out["subnets_below_immune"] == 2   # 2, 4
    assert out["netuids_below"] == [1, 3, 5]


def test_floor_is_the_cheapest_non_immune_subnet():
    # netuid 2 is cheapest overall but immune, so it is NOT the prune target.
    emas = {21: 0.0040, 1: 0.0020, 2: 0.0001, 3: 0.0030}
    out = assess(_chain(emas, immune={2}))
    assert out["floor_netuid"] == 1
    assert out["floor_tao"] == pytest.approx(0.0020)
    # 50% below us: (1 - 0.0020/0.0040)
    assert out["drop_to_target_pct"] == pytest.approx(50.0)


def test_immune_subnet_is_never_at_risk():
    emas = {21: 0.0001, 1: 0.5, 2: 0.6}
    out = assess(_chain(emas, immune={21}))
    assert out["immune"] is True
    assert out["tier"] == 0          # cheapest in the field, but untouchable


def test_cheapest_non_immune_subnet_is_the_prune_target():
    emas = {21: 0.0001, 1: 0.5, 2: 0.6}
    out = assess(_chain(emas))
    assert out["tier"] == 5
    assert out["subnets_below"] == 0
    assert out["status"] == "alert"


def test_guard_price_preserves_the_configured_buffer():
    # 30 subnets below us, evenly spaced: the guard must be the DEREG_BUFFER_MIN-th.
    emas = {n: 0.001 * n for n in range(1, 32) if n != 21}
    emas[21] = 1.0
    out = assess(_chain(emas))
    assert out["subnets_below"] == 30
    # prunable sorted ascending: index DEREG_BUFFER_MIN leaves that many below it.
    assert out["guard_tao"] == pytest.approx(0.001 * (DEREG_BUFFER_MIN + 1))
    assert out["guard_tao"] > out["floor_tao"]


def test_sensitivity_reports_buffer_after_a_relative_drop():
    # Everything sits just under us, so a 10% drop wipes the whole buffer out.
    emas = {21: 1.0, 1: 0.95, 2: 0.96, 3: 0.97}
    out = assess(_chain(emas))
    assert out["subnets_below"] == 3
    assert out["sensitivity"]["-5%"] == 0     # 0.95 is not < 0.95
    assert out["sensitivity"]["-10%"] == 0


def test_runway_is_buffer_times_the_observed_prune_cadence():
    emas = {21: 1.0}
    emas.update({n: 0.1 * n for n in range(1, 10)})   # 9 below us
    chain = _chain(emas)
    # Three registrations inside the last 90 days => one prune every 30 days.
    for s in chain["subnets"][:3]:
        s["age_blocks"] = 10 * 7200
    out = assess(chain)
    assert out["days_per_prune"] == pytest.approx(30.0)
    assert out["runway_days"] == pytest.approx(out["subnets_below"] * 30.0)


@pytest.mark.parametrize("n_below,expected", [(50, 0), (20, 0), (19, 1), (10, 1),
                                              (9, 2), (5, 2), (4, 3), (2, 3), (1, 4), (0, 4)])
def test_tier_ladder(n_below, expected):
    assert _tier(n_below, is_target=False, immune=False) == expected


def test_prune_target_outranks_buffer_count():
    # Being the target is tier 5 even if the ladder would say otherwise.
    assert _tier(0, is_target=True, immune=False) == 5


def test_erosion_measures_places_lost_inside_the_window():
    now = datetime(2026, 7, 29, tzinfo=timezone.utc)
    hist = [
        {"checked_at": (now - timedelta(days=40)).isoformat(), "subnets_below": 60},
        {"checked_at": (now - timedelta(days=8)).isoformat(), "subnets_below": 36},
        {"checked_at": (now - timedelta(days=2)).isoformat(), "subnets_below": 28},
    ]
    out = _erosion(hist, now, subnets_below=24)
    # Oldest row still inside the 14-day window is the 8-day-old one, not the 40-day.
    assert out["places_lost"] == 12
    assert out["alerting"] is True


def test_erosion_ignores_rows_outside_the_window():
    now = datetime(2026, 7, 29, tzinfo=timezone.utc)
    hist = [{"checked_at": (now - timedelta(days=90)).isoformat(), "subnets_below": 99}]
    assert _erosion(hist, now, subnets_below=24)["places_lost"] is None


def test_erosion_does_not_alert_on_a_recovering_buffer():
    now = datetime(2026, 7, 29, tzinfo=timezone.utc)
    hist = [{"checked_at": (now - timedelta(days=5)).isoformat(), "subnets_below": 10}]
    out = _erosion(hist, now, subnets_below=10 + EROSION_ALERT_PLACES)
    assert out["places_lost"] == -EROSION_ALERT_PLACES
    assert out["alerting"] is False


def test_assess_raises_when_our_subnet_is_gone():
    with pytest.raises(ValueError):
        assess(_chain({1: 0.5, 2: 0.6}))


# ── emission gate hyperparam watch ────────────────────────────────────────────
# N (rank), q and h move only by a root call, so any change is reportable; theta is
# recomputed by the chain every 360 blocks and drifts on its own.

# Live on finney 2026-08-03 (v441): rank mode, N = 32 pins theta to the 32nd-largest
# demand share and q is vestigial.
LIVE_GATE = {"rank": 32.0, "q": 0.75, "h": 3.0, "theta": 0.00732, "mode": "rank"}


def test_no_gate_change_is_not_reported():
    out = _gate_changes(LIVE_GATE, dict(LIVE_GATE))
    assert out["changed"] == []
    assert out["alerting"] is False


def test_q_change_alerts():
    out = _gate_changes(LIVE_GATE, {**LIVE_GATE, "q": 0.61})
    assert out["alerting"] is True
    assert out["changed"] == [{"param": "q", "from": 0.75, "to": 0.61, "pct": -18.7}]


def test_h_change_alerts():
    out = _gate_changes(LIVE_GATE, {**LIVE_GATE, "h": 8.0})
    assert out["alerting"] is True
    assert [c["param"] for c in out["changed"]] == ["h"]


def test_small_theta_drift_is_ignored():
    # theta moved 1% — the chain recomputes it every 360 blocks, this is noise.
    out = _gate_changes(LIVE_GATE, {**LIVE_GATE, "theta": LIVE_GATE["theta"] * 1.01})
    assert out["changed"] == []
    assert out["alerting"] is False


def test_large_theta_move_is_reported_but_does_not_alert():
    # A big theta move is a distribution shift, worth recording — but only q and h
    # are root-set, and only those wake anyone up.
    moved = LIVE_GATE["theta"] * (1 + THETA_MOVE_ALERT * 2)
    out = _gate_changes(LIVE_GATE, {**LIVE_GATE, "theta": moved})
    assert [c["param"] for c in out["changed"]] == ["theta"]
    assert out["alerting"] is False


def test_missing_gate_data_never_alerts():
    # Pre-v440 runtime, or the very first run with no previous snapshot.
    assert _gate_changes(None, LIVE_GATE)["alerting"] is False
    assert _gate_changes(
        LIVE_GATE, {"rank": None, "q": None, "h": None, "theta": None}
    )["alerting"] is False


def test_rank_change_alerts():
    # N is the live lever under v441: tightening it from 32 to 16 would halve the
    # set of subnets above the bar, and it moves by one sudo call with no release.
    out = _gate_changes(LIVE_GATE, {**LIVE_GATE, "rank": 16.0})
    assert out["alerting"] is True
    assert out["changed"] == [{"param": "rank", "from": 32.0, "to": 16.0, "pct": -50.0}]


def test_bar_mode_reverting_to_quantile_alerts():
    # N -> 0 hands the bar back to the q-mass quantile. That is a mode switch, and
    # it surfaces as a rank change rather than being silently ignored.
    out = _gate_changes(LIVE_GATE, {**LIVE_GATE, "rank": 0.0, "mode": "quantile"})
    assert out["alerting"] is True
    assert [c["param"] for c in out["changed"]] == ["rank"]


def test_mode_string_is_not_diffed_as_a_param():
    # `mode` is derived, not a chain param — it must never appear in `changed`
    # (and its non-numeric value must not break the diff).
    out = _gate_changes(LIVE_GATE, {**LIVE_GATE, "mode": "quantile"})
    assert out["changed"] == []
    assert out["alerting"] is False
