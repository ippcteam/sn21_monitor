"""Validator-basket snapshot: parse, share, enter/exit, holders join."""

from __future__ import annotations

from datetime import datetime, timezone

from validator_basket_sync import (
    OUR_VALIDATOR_HOTKEY,
    annotate,
    build_snapshot,
    diff_baskets,
    history_row,
    index_holders_by_hotkey,
    parse_available_row,
    summarise,
)

RIZZO = "5F2CsUDVbRbVMXTh9fAzF9GacjVX7UapvRxidrxe7z8BYckQ"
TAOSTATS = "5GKH9FPPnWSUoeeTJp19wVtd84XqFW4pyK2ijV2GsFbhTrP1"
UNNAMED = "5DD6hMnCXMvSCstpfrc8mkew8CK2nhzksKzu7L9JWFpnP3KL"


def _raw(ss58, name, alpha_rao):
    return {
        "address": {"ss58": ss58, "hex": "0x00"},
        "name": name,
        "netuid": 21,
        "hotkey_alpha": str(alpha_rao),
    }


def test_parse_available_row_reads_address_ss58_and_rao():
    row = parse_available_row(_raw(RIZZO, "Rizzo", 1_500_000_000))
    assert row["hotkey"] == RIZZO
    assert row["name"] == "Rizzo"
    assert row["is_named"] is True
    assert row["alpha"] == 1.5


def test_parse_blank_name_is_unnamed():
    row = parse_available_row(_raw(UNNAMED, "  ", 1_000_000_000))
    assert row["is_named"] is False
    assert row["name"] is None


def test_parse_skips_row_without_hotkey():
    assert parse_available_row({"name": "Ghost", "hotkey_alpha": "1"}) is None


def test_index_holders_counts_nominators_per_hotkey():
    holders = [
        {"hotkey": RIZZO, "coldkey": "ck1", "balance_rao": 2_000_000_000},
        {"hotkey": RIZZO, "coldkey": "ck2", "balance_rao": 500_000_000},
        {"hotkey": TAOSTATS, "coldkey": "ck3", "balance_rao": 1_000_000_000},
    ]
    idx = index_holders_by_hotkey(holders)
    assert idx[RIZZO]["nominators"] == 2
    assert idx[RIZZO]["holder_alpha"] == 2.5
    assert idx[TAOSTATS]["nominators"] == 1


def test_annotate_share_house_and_ours():
    rows = [
        {"hotkey": OUR_VALIDATOR_HOTKEY, "hotkey_short": "5Gui…", "name": "Ours", "is_named": True, "alpha": 25.0},
        {"hotkey": RIZZO, "hotkey_short": "5F2C…", "name": "Rizzo", "is_named": True, "alpha": 75.0},
    ]
    out = annotate(
        rows,
        holders_by_hotkey={RIZZO: {"nominators": 4, "holder_alpha": 75.0}},
        house={OUR_VALIDATOR_HOTKEY},
    )
    by_hk = {r["hotkey"]: r for r in out}
    assert by_hk[RIZZO]["share_pct"] == 75.0
    assert by_hk[RIZZO]["nominators"] == 4
    assert by_hk[RIZZO]["is_ours"] is False
    assert by_hk[OUR_VALIDATOR_HOTKEY]["is_ours"] is True
    assert by_hk[OUR_VALIDATOR_HOTKEY]["is_house"] is True
    assert by_hk[OUR_VALIDATOR_HOTKEY]["nominators"] is None
    assert out[0]["hotkey"] == RIZZO  # sorted by α desc


def test_diff_first_run_has_no_enter_exit():
    today = annotate(
        [{"hotkey": RIZZO, "hotkey_short": "x", "name": "Rizzo", "is_named": True, "alpha": 10.0}],
        house=set(),
    )
    annotated, entered, exited = diff_baskets(today, None)
    assert entered == []
    assert exited == []
    assert annotated[0]["is_new"] is False
    assert annotated[0]["alpha_delta"] is None


def test_diff_enter_exit_and_alpha_delta():
    prior = annotate(
        [
            {"hotkey": RIZZO, "hotkey_short": "r", "name": "Rizzo", "is_named": True, "alpha": 10.0},
            {"hotkey": UNNAMED, "hotkey_short": "u", "name": None, "is_named": False, "alpha": 3.0},
        ],
        house=set(),
    )
    today = annotate(
        [
            {"hotkey": RIZZO, "hotkey_short": "r", "name": "Rizzo", "is_named": True, "alpha": 12.0},
            {"hotkey": TAOSTATS, "hotkey_short": "t", "name": "Taostats", "is_named": True, "alpha": 8.0},
        ],
        house=set(),
    )
    annotated, entered, exited = diff_baskets(today, prior)
    assert [e["name"] for e in entered] == ["Taostats"]
    assert entered[0]["is_new"] is True
    assert [x["hotkey"] for x in exited] == [UNNAMED]
    assert exited[0]["is_exited"] is True
    by_hk = {r["hotkey"]: r for r in annotated}
    assert by_hk[RIZZO]["alpha_delta"] == 2.0
    assert by_hk[TAOSTATS]["alpha_delta"] == 8.0


def test_summarise_and_history_row_use_display_names():
    validators, entered, exited = diff_baskets(
        annotate(
            [
                {"hotkey": RIZZO, "hotkey_short": "5F2CsUDV…YckQ", "name": "Rizzo", "is_named": True, "alpha": 10.0},
                {"hotkey": UNNAMED, "hotkey_short": "5DD6hMnC…P3KL", "name": None, "is_named": False, "alpha": 2.0},
            ],
            house=set(),
        ),
        annotate(
            [{"hotkey": TAOSTATS, "hotkey_short": "5GKH9FPP…TrP1", "name": "Taostats", "is_named": True, "alpha": 5.0}],
            house=set(),
        ),
    )
    summary = summarise(validators, entered, exited)
    assert summary["validator_count"] == 2
    assert summary["named_count"] == 1
    assert summary["unnamed_count"] == 1
    assert summary["total_alpha"] == 12.0
    assert summary["named_alpha"] == 10.0
    assert summary["entered_names"] == ["Rizzo", "5DD6hMnC…P3KL"]
    assert summary["exited_names"] == ["Taostats"]
    row = history_row("2026-08-17", summary)
    assert row["date"] == "2026-08-17"
    assert row["entered"] == summary["entered_names"]
    assert row["exited"] == ["Taostats"]


def test_build_snapshot_dedups_hotkey_and_joins_holders():
    raw = [
        _raw(RIZZO, "Rizzo", 10_000_000_000),
        _raw(RIZZO, "Rizzo", 1_000_000_000),  # duplicate, smaller — dropped
        _raw(TAOSTATS, "Taostats", 5_000_000_000),
    ]
    snap = build_snapshot(
        raw,
        holders_by_hotkey={RIZZO: {"nominators": 3, "holder_alpha": 10.0}},
        prior_validators=None,
        fetched_at=datetime(2026, 8, 17, 8, 50, tzinfo=timezone.utc),
        house=set(),
        holders_joined=True,
    )
    assert snap["date"] == "2026-08-17"
    assert snap["holders_joined"] is True
    assert snap["summary"]["validator_count"] == 2
    assert snap["summary"]["total_alpha"] == 15.0
    rizzo = next(v for v in snap["validators"] if v["hotkey"] == RIZZO)
    assert rizzo["alpha"] == 10.0
    assert rizzo["nominators"] == 3
    assert rizzo["share_pct"] == 66.6667
