"""Root-basket classify / diff / significance — no live chain."""

from __future__ import annotations

from datetime import datetime, timezone

from baskets_scan import (
    NEW_LEFTOVER_MIN_TAO,
    OUR_VALIDATOR_HOTKEY,
    annotate,
    build_snapshot,
    change_reasons,
    classify,
    digest_payload,
    diff_funds,
    history_row,
    is_significant,
    normalize_fund,
    parse_holdings,
    parse_weights,
    summarise,
)

RIZZO = "5F2CsUDVbRbVMXTh9fAzF9GacjVX7UapvRxidrxe7z8BYckQ"
TAOSTATS = "5GKH9FPPnWSUoeeTJp19wVtd84XqFW4pyK2ijV2GsFbhTrP1"
OTF = "5H98bUQdryePyJ4pwnYMgwaxUyAUQ47uBzDM6fQ974pHh4Wh"
# 32-byte AccountId that encodes to OTF above (live spike sample).
OTF_BYTES = [
    224, 141, 108, 168, 174, 249, 153, 232, 22, 252, 254, 64, 67, 199, 187, 238,
    157, 207, 75, 250, 233, 222, 7, 226, 135, 88, 18, 39, 44, 200, 148, 115,
]


def _w(*pairs):
    return list(pairs)


def _h(netuid, alpha=0.0, realizable=0.0, spot=None):
    return {
        "netuid": netuid,
        "alpha": alpha,
        "spot_tao": spot if spot is not None else realizable,
        "realizable_tao": realizable,
    }


def _fund(hotkey, kind, share_pp=0.0, dests=16, sn21_tao=0.0, nav=100.0, name=None):
    share = share_pp / 100.0
    return annotate(
        [{
            "hotkey": hotkey,
            "hotkey_short": hotkey[:8] + "…" + hotkey[-4:],
            "nav_tao": nav,
            "spot_nav_tao": nav,
            "shares": 1,
            "kind": kind,
            "share": share,
            "share_pp": share_pp,
            "dests": dests,
            "sn21_alpha": 0.0,
            "sn21_tao": sn21_tao,
        }],
        names={hotkey: name} if name else {},
        house=set(),
    )[0]


# ── classify ────────────────────────────────────────────────────────────────


def test_curated_when_21_in_weights():
    sig = classify(_w((0, 1), (21, 1), (8, 1)), [_h(3, realizable=9.0)])
    assert sig["kind"] == "curated"
    assert sig["dests"] == 3
    assert abs(sig["share"] - 1 / 3) < 1e-9


def test_leftover_when_21_holding_no_weight():
    sig = classify(_w((0, 1), (8, 1)), [_h(21, alpha=10.0, realizable=2.5)])
    assert sig["kind"] == "leftover"
    assert sig["share"] == 0.0
    assert sig["sn21_tao"] == 2.5
    assert sig["sn21_alpha"] == 10.0


def test_null_strategy_empty_weights_with_holding_is_leftover():
    sig = classify([], [_h(21, realizable=0.4)])
    assert sig["kind"] == "leftover"
    assert sig["dests"] == 0


def test_netuid_0_is_not_sn21():
    sig = classify(_w((0, 4096), (8, 4096)), [_h(0, realizable=50.0)])
    assert sig["kind"] is None
    assert sig["sn21_tao"] == 0.0


def test_share_from_u16_weights():
    # Equal 16-way split, 21 included.
    pairs = [(i, 4096) for i in (0, 1, 3, 4, 5, 8, 9, 11, 13, 19, 21, 23, 34, 51, 64, 77)]
    sig = classify(pairs, [])
    assert sig["kind"] == "curated"
    assert sig["dests"] == 16
    assert abs(sig["share_pp"] - 6.25) < 1e-6


# ── decode ──────────────────────────────────────────────────────────────────


def test_normalize_decodes_newtype_wrappers_and_ss58():
    raw = {
        "hotkey": [OTF_BYTES],
        "nav_tao": [4_156_730_000_000],
        "spot_nav_tao": [4_200_000_000_000],
        "shares": 386,
        "deposited_tao": [0],
        "redeemed_tao": [0],
        "weights": [([21], 4096), ([8], 4096)],
        "holdings": [{
            "netuid": [21],
            "alpha": [1_500_000_000],
            "spot_tao": [200_000_000],
            "realizable_tao": [152_700_000],
        }],
    }
    row = normalize_fund(raw)
    assert row["hotkey"] == OTF
    assert row["kind"] == "curated"
    assert row["dests"] == 2
    assert abs(row["share"] - 0.5) < 1e-9
    assert row["sn21_alpha"] == 1.5
    assert abs(row["sn21_tao"] - 0.1527) < 1e-9
    assert abs(row["nav_tao"] - 4156.73) < 1e-6


def test_parse_weights_drops_zero_and_accepts_pairs():
    assert parse_weights([([21], 0), (8, 100), {"netuid": [3], "weight": 50}]) == [
        (8, 100), (3, 50),
    ]


def test_parse_holdings_tuple_shape():
    rows = parse_holdings([(21, 2_000_000_000, 1_000_000_000)])
    assert rows[0]["netuid"] == 21
    assert rows[0]["alpha"] == 2.0
    assert rows[0]["realizable_tao"] == 1.0


# ── significance ────────────────────────────────────────────────────────────


def test_curated_add_always_significant():
    today = _fund(RIZZO, "curated", share_pp=6.25, dests=16, sn21_tao=0.01, name="Rizzo")
    reasons = change_reasons(today, None)
    assert reasons == ["curated_add"]
    assert is_significant(reasons, today) is True


def test_curated_drop_always_significant():
    prior = _fund(RIZZO, "curated", share_pp=6.25, dests=16, sn21_tao=0.2, name="Rizzo")
    today = _fund(RIZZO, "leftover", dests=16, sn21_tao=0.2, name="Rizzo")
    reasons = change_reasons(today, prior)
    assert "curated_drop" in reasons
    assert is_significant(reasons, today) is True


def test_leftover_that_starts_curating_is_add_not_leftover_clear():
    prior = _fund(RIZZO, "leftover", dests=0, sn21_tao=8.0, name="Rizzo")
    today = _fund(RIZZO, "curated", share_pp=6.25, dests=16, sn21_tao=8.0, name="Rizzo")
    reasons = change_reasons(today, prior)
    assert reasons == ["curated_add"]
    assert "leftover_clear" not in reasons
    assert is_significant(reasons, today) is True


def test_share_move_037pp_is_noise():
    # 16-way 1/N → 17-way 1/N ≈ 0.3676 pp.
    prior = _fund(RIZZO, "curated", share_pp=6.25, dests=16, sn21_tao=2.0)
    today = _fund(RIZZO, "curated", share_pp=round(100 / 17, 4), dests=17, sn21_tao=2.0)
    reasons = change_reasons(today, prior)
    assert "share_move" not in reasons
    assert is_significant(reasons, today) is False


def test_share_move_1pp_is_significant():
    prior = _fund(RIZZO, "curated", share_pp=6.25, dests=16, sn21_tao=2.0)
    today = _fund(RIZZO, "curated", share_pp=7.25, dests=16, sn21_tao=2.0)
    reasons = change_reasons(today, prior)
    assert "share_move" in reasons
    assert is_significant(reasons, today) is True


def test_position_1tao_and_10pct_is_significant():
    prior = _fund(RIZZO, "curated", share_pp=6.25, dests=16, sn21_tao=10.0)
    today = _fund(RIZZO, "curated", share_pp=6.25, dests=16, sn21_tao=11.2)
    reasons = change_reasons(today, prior)
    assert "position_move" in reasons
    assert is_significant(reasons, today) is True


def test_position_1tao_but_under_10pct_is_not():
    prior = _fund(RIZZO, "curated", share_pp=6.25, dests=16, sn21_tao=20.0)
    today = _fund(RIZZO, "curated", share_pp=6.25, dests=16, sn21_tao=21.5)
    reasons = change_reasons(today, prior)
    assert "position_move" not in reasons
    assert is_significant(reasons, today) is False


def test_position_under_1tao_even_if_10pct_is_not():
    prior = _fund(RIZZO, "curated", share_pp=6.25, dests=16, sn21_tao=2.0)
    today = _fund(RIZZO, "curated", share_pp=6.25, dests=16, sn21_tao=2.3)
    reasons = change_reasons(today, prior)
    assert "position_move" not in reasons
    assert is_significant(reasons, today) is False


def test_new_leftover_5tao_is_significant():
    today = _fund(TAOSTATS, "leftover", dests=0, sn21_tao=NEW_LEFTOVER_MIN_TAO, name="Taostats")
    reasons = change_reasons(today, None)
    assert reasons == ["leftover_new"]
    assert is_significant(reasons, today) is True


def test_new_leftover_under_5tao_is_not():
    today = _fund(TAOSTATS, "leftover", dests=0, sn21_tao=4.9, name="Taostats")
    reasons = change_reasons(today, None)
    assert reasons == ["leftover_new"]
    assert is_significant(reasons, today) is False


def test_first_snapshot_is_baseline_no_significance():
    raw = [{
        "hotkey": RIZZO,
        "nav_tao": 100 * 1_000_000_000,
        "weights": [(21, 4096), (8, 4096)],
        "holdings": [_h(21, realizable=3.0)],
    }]
    # holdings in this raw are already decoded floats — parse_holdings treats
    # them as rao. Use rao units so normalize matches.
    raw[0]["holdings"] = [{
        "netuid": 21,
        "alpha": 3_000_000_000,
        "spot_tao": 3_000_000_000,
        "realizable_tao": 3_000_000_000,
    }]
    snap = build_snapshot(
        raw,
        prior_funds=None,
        names={RIZZO: "Rizzo"},
        house=set(),
        fetched_at=datetime(2026, 8, 29, 9, 18, tzinfo=timezone.utc),
        block=8_938_465,
    )
    assert snap["is_baseline"] is True
    assert snap["summary"]["is_baseline"] is True
    assert snap["summary"]["n_curating"] == 1
    assert snap["summary"]["n_significant"] == 0
    assert snap["changes"] == []
    assert snap["funds"][0]["significant"] is False
    assert snap["date"] == "2026-08-29"


def test_diff_add_drop_and_digest_puts_adds_first():
    prior = [
        _fund(RIZZO, "curated", share_pp=6.25, dests=16, sn21_tao=2.0, name="Rizzo"),
        _fund(OTF, "leftover", dests=0, sn21_tao=1.0, name="OTF"),
    ]
    today = [
        _fund(TAOSTATS, "curated", share_pp=6.25, dests=16, sn21_tao=0.5, name="Taostats"),
        _fund(OTF, "leftover", dests=0, sn21_tao=1.0, name="OTF"),
    ]
    annotated, changes = diff_funds(today, prior)
    kinds = [c["reasons"][0] for c in changes]
    assert kinds[0] == "curated_add"
    assert "curated_drop" in kinds
    sig = [c for c in changes if c["significant"]]
    assert [c["name"] for c in sig if "curated_add" in c["reasons"]] == ["Taostats"]
    assert [c["name"] for c in sig if "curated_drop" in c["reasons"]] == ["Rizzo"]

    summary = summarise(annotated, changes, is_baseline=False, n_all_funds=40)
    assert summary["add_names"] == ["Taostats"]
    assert summary["drop_names"] == ["Rizzo"]
    payload = digest_payload({
        "summary": summary,
        "changes": changes,
    })
    assert payload["available"] is True
    assert payload["adds"] == ["Taostats"]
    assert payload["drops"] == ["Rizzo"]
    assert payload["significant"][0]["reasons"] == ["curated_add"]


def test_history_row_is_compact():
    summary = {
        "n_curating": 2,
        "n_leftover": 5,
        "realizable_tao_21": 12.5,
        "n_significant": 1,
        "add_names": ["Rizzo"],
        "drop_names": [],
    }
    row = history_row("2026-08-29", summary, 8_938_465)
    assert row == {
        "date": "2026-08-29",
        "block": 8_938_465,
        "n_curating": 2,
        "n_leftover": 5,
        "realizable_tao_21": 12.5,
        "n_significant": 1,
        "adds": ["Rizzo"],
        "drops": [],
    }


def test_annotate_house_and_ours():
    rows = annotate(
        [{
            "hotkey": OUR_VALIDATOR_HOTKEY,
            "hotkey_short": "5Gui…",
            "nav_tao": 1.0,
            "spot_nav_tao": 1.0,
            "shares": 1,
            "kind": "curated",
            "share": 0.06,
            "share_pp": 6.0,
            "dests": 16,
            "sn21_alpha": 0.0,
            "sn21_tao": 0.1,
        }],
        names={OUR_VALIDATOR_HOTKEY: "Ours"},
        house={OUR_VALIDATOR_HOTKEY},
    )
    assert rows[0]["is_ours"] is True
    assert rows[0]["is_house"] is True
    assert rows[0]["name"] == "Ours"
