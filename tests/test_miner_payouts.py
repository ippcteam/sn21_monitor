"""Miner payouts durable ledger — seed merge + cumulative totals."""

from __future__ import annotations

import json
from pathlib import Path

import miner_payouts_sync as mps


def test_seed_backfill_and_cumulative(tmp_path, monkeypatch):
    store_path = tmp_path / "miner_payouts_daily.json"
    monkeypatch.setattr(mps, "MINER_PAYOUTS_STORE", store_path)

    store = mps.ensure_seed_backfill()
    assert store_path.exists()
    assert len(store["rows"]) >= 70
    assert store["rows"][0]["date"] == "2026-05-27"
    assert store["rows"][0]["source"] == "incentive_burn_estimate"
    # First two weeks were 100% burn → zero net
    may27 = next(r for r in store["rows"] if r["date"] == "2026-05-27")
    assert may27["mining_alpha_net"] == 0.0
    assert may27["incentive_burn"] == 1.0

    summary = mps.get_payouts_summary(since="2026-05-27", until="2026-08-12")
    assert summary["days_with_data"] == 78
    assert summary["days_missing"] == []
    # ~66.7k α net — allow small float slack
    assert 66_000 < summary["totals"]["mining_alpha_net"] < 67_500
    assert summary["totals"]["mining_alpha_gross"] == 230_256.0


def test_metagraph_row_not_overwritten_by_seed(tmp_path, monkeypatch):
    store_path = tmp_path / "miner_payouts_daily.json"
    monkeypatch.setattr(mps, "MINER_PAYOUTS_STORE", store_path)

    live = {
        "go_live_date": "2026-05-27",
        "updated_at_utc": "2026-08-12T12:00:00+00:00",
        "rows": [{
            "date": "2026-08-12",
            "source": "metagraph",
            "incentive_burn": 0.45,
            "mining_alpha_gross": 2950.0,
            "mining_alpha_burned": 1327.5,
            "mining_alpha_net": 1622.5,
            "validating_alpha": 2100.0,
            "owner_alpha": 1296.0,
            "observed_burn": True,
        }],
    }
    store_path.write_text(json.dumps(live), encoding="utf-8")

    store = mps.ensure_seed_backfill()
    by_date = {r["date"]: r for r in store["rows"]}
    assert by_date["2026-08-12"]["source"] == "metagraph"
    assert by_date["2026-08-12"]["mining_alpha_net"] == 1622.5
    assert "2026-05-27" in by_date  # seed filled the gap


def test_seed_file_present():
    assert Path(mps.SEED_PATH).exists()
    seed = json.loads(Path(mps.SEED_PATH).read_text(encoding="utf-8"))
    assert seed["go_live_date"] == "2026-05-27"
    assert len(seed["rows"]) == 78
