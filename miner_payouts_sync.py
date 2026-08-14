"""
Durable daily miner-payout ledger (subnet-wide).

`neurons_daily.json` keeps per-UID rows for only 90 days — too short to answer
"how much α have miners been paid since go-live?". This store keeps **one
compact row per UTC day forever** (or until disk policy changes):

  mining_alpha_gross / mining_alpha_burned / mining_alpha_net
  + incentive_burn + prices + source

Go-live seed (`seeds/miner_payouts_since_2026-05-27.json`) backfills
2026-05-27 → first live capture from Taostats `incentive_burn` history.
Each scheduled run overwrites *today* with metagraph-observed totals from
`neurons_sync.burn_summary` (sums all UIDs, including the burn sink).

Storage: data/miner_payouts_daily.json
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from collector import load_json, save_json
from config import DATA_DIR

logger = logging.getLogger(__name__)

GO_LIVE_DATE = date(2026, 5, 27)
MINER_PAYOUTS_STORE = DATA_DIR / "miner_payouts_daily.json"
SEED_PATH = Path(__file__).resolve().parent / "seeds" / "miner_payouts_since_2026-05-27.json"

# Used only when estimating a missing historical day (no seed, no live row).
GROSS_MINER_ALPHA_PER_DAY = 2952.0  # 7200 × 0.82 × 0.5


def _empty_store() -> dict[str, Any]:
    return {
        "go_live_date": GO_LIVE_DATE.isoformat(),
        "updated_at_utc": None,
        "rows": [],
    }


def _load_store() -> dict[str, Any]:
    store = load_json(MINER_PAYOUTS_STORE, _empty_store())
    if not isinstance(store, dict):
        return _empty_store()
    store.setdefault("go_live_date", GO_LIVE_DATE.isoformat())
    store.setdefault("rows", [])
    if not isinstance(store["rows"], list):
        store["rows"] = []
    return store


def _rows_by_date(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        d = r.get("date")
        if d:
            out[str(d)] = r
    return out


def _load_seed_rows() -> list[dict[str, Any]]:
    if not SEED_PATH.exists():
        logger.warning("Miner payouts seed missing at %s", SEED_PATH)
        return []
    seed = load_json(SEED_PATH, {})
    rows = seed.get("rows") if isinstance(seed, dict) else None
    return list(rows) if isinstance(rows, list) else []


def ensure_seed_backfill(store: dict[str, Any] | None = None) -> dict[str, Any]:
    """Merge go-live seed rows for any dates not yet in the store.

    Never overwrites a row whose source is ``metagraph`` (live capture wins).
    """
    store = store if store is not None else _load_store()
    by_date = _rows_by_date(store["rows"])
    added = 0
    for seed_row in _load_seed_rows():
        d = seed_row.get("date")
        if not d:
            continue
        existing = by_date.get(d)
        if existing and existing.get("source") == "metagraph":
            continue
        if existing and existing.get("source") == "incentive_burn_estimate":
            # Keep whatever is already on disk; seed is bootstrap only.
            continue
        by_date[d] = {
            "date": d,
            "source": "incentive_burn_estimate",
            "incentive_burn": seed_row.get("incentive_burn"),
            "mining_alpha_gross": seed_row.get("mining_alpha_gross"),
            "mining_alpha_burned": seed_row.get("mining_alpha_burned"),
            "mining_alpha_net": seed_row.get("mining_alpha_net"),
            "validating_alpha": None,
            "owner_alpha": None,
            "alpha_price_tao": None,
            "alpha_price_usd": None,
            "tao_price_usd": None,
            "block": None,
            "fetched_at_utc": None,
            "observed_burn": seed_row.get("observed_burn"),
        }
        added += 1

    store["rows"] = sorted(by_date.values(), key=lambda r: r.get("date") or "")
    if added:
        store["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
        save_json(MINER_PAYOUTS_STORE, store)
        logger.info("Miner payouts seed backfill: +%d days → %s", added, MINER_PAYOUTS_STORE)
    return store


def _prices_from_payload(payload: dict[str, Any]) -> dict[str, float | None]:
    from neurons_daily_sync import _latest_subnet_prices

    prices = _latest_subnet_prices()
    # Prefer prices attached to the neurons payload when present.
    for key in ("alpha_price_tao", "alpha_price_usd", "tao_price_usd"):
        if payload.get(key) is not None:
            prices[key] = payload.get(key)
    return prices


def sync_miner_payouts() -> dict[str, Any]:
    """Capture today's subnet-wide miner payout totals; seed any missing history."""
    from neurons_sync import fetch_neurons

    store = ensure_seed_backfill()

    payload = fetch_neurons()
    if "error" in payload:
        return {"skipped": True, "reason": payload["error"], "path": str(MINER_PAYOUTS_STORE)}

    burn = payload.get("burn") or {}
    fetched_at = datetime.now(timezone.utc)
    date_str = fetched_at.strftime("%Y-%m-%d")
    prices = _prices_from_payload(payload)

    neurons = (payload.get("validators") or []) + (payload.get("miners") or [])
    validating = sum((n.get("daily_validating_alpha") or 0.0) for n in neurons)
    owner = sum((n.get("daily_owner_alpha") or 0.0) for n in neurons)

    row = {
        "date": date_str,
        "source": "metagraph",
        "incentive_burn": burn.get("rate"),
        "mining_alpha_gross": burn.get("total_mining_alpha_gross"),
        "mining_alpha_burned": burn.get("total_mining_alpha_burned"),
        "mining_alpha_net": burn.get("total_mining_alpha_net"),
        "validating_alpha": round(validating, 9),
        "owner_alpha": round(owner, 9),
        "alpha_price_tao": prices.get("alpha_price_tao"),
        "alpha_price_usd": prices.get("alpha_price_usd"),
        "tao_price_usd": prices.get("tao_price_usd"),
        "block": payload.get("block_number"),
        "fetched_at_utc": fetched_at.isoformat(),
        "observed_burn": True,
    }

    by_date = _rows_by_date(store["rows"])
    by_date[date_str] = row
    store["rows"] = sorted(by_date.values(), key=lambda r: r.get("date") or "")
    store["updated_at_utc"] = fetched_at.isoformat()
    save_json(MINER_PAYOUTS_STORE, store)

    logger.info(
        "Miner payouts daily: %s gross=%.4f burned=%.4f net=%.4f burn_rate=%s · days=%d",
        date_str,
        row["mining_alpha_gross"] or 0.0,
        row["mining_alpha_burned"] or 0.0,
        row["mining_alpha_net"] or 0.0,
        row["incentive_burn"],
        len(store["rows"]),
    )
    return {
        "skipped": False,
        "date": date_str,
        "row": row,
        "days_stored": len(store["rows"]),
        "path": str(MINER_PAYOUTS_STORE),
    }


def get_payouts_summary(
    since: str | None = None,
    until: str | None = None,
) -> dict[str, Any]:
    """Cumulative miner payouts over `[since, until]` (inclusive ISO dates)."""
    store = ensure_seed_backfill()
    since_d = date.fromisoformat(since) if since else GO_LIVE_DATE
    until_d = date.fromisoformat(until) if until else datetime.now(timezone.utc).date()
    if until_d < since_d:
        raise ValueError("until must be >= since")

    rows = []
    for r in store["rows"]:
        d = r.get("date")
        if not d:
            continue
        try:
            dd = date.fromisoformat(d)
        except ValueError:
            continue
        if since_d <= dd <= until_d:
            rows.append(r)

    rows.sort(key=lambda r: r.get("date") or "")
    gross = sum((r.get("mining_alpha_gross") or 0.0) for r in rows)
    burned = sum((r.get("mining_alpha_burned") or 0.0) for r in rows)
    net = sum((r.get("mining_alpha_net") or 0.0) for r in rows)
    live_days = sum(1 for r in rows if r.get("source") == "metagraph")
    estimate_days = sum(1 for r in rows if r.get("source") == "incentive_burn_estimate")

    # Calendar coverage (gaps)
    have = {r["date"] for r in rows if r.get("date")}
    missing: list[str] = []
    d = since_d
    while d <= until_d:
        iso = d.isoformat()
        if iso not in have:
            missing.append(iso)
        d += timedelta(days=1)

    last = rows[-1] if rows else None
    return {
        "go_live_date": GO_LIVE_DATE.isoformat(),
        "since": since_d.isoformat(),
        "until": until_d.isoformat(),
        "days_with_data": len(rows),
        "days_missing": missing,
        "live_metagraph_days": live_days,
        "estimate_days": estimate_days,
        "totals": {
            "mining_alpha_gross": round(gross, 6),
            "mining_alpha_burned": round(burned, 6),
            "mining_alpha_net": round(net, 6),
        },
        "latest": last,
        "updated_at_utc": store.get("updated_at_utc"),
        "path": str(MINER_PAYOUTS_STORE),
    }


def get_payouts_daily(
    since: str | None = None,
    until: str | None = None,
) -> dict[str, Any]:
    """Raw daily rows for the inclusive window."""
    summary = get_payouts_summary(since=since, until=until)
    store = _load_store()
    since_d = date.fromisoformat(summary["since"])
    until_d = date.fromisoformat(summary["until"])
    rows = []
    for r in store["rows"]:
        d = r.get("date")
        if not d:
            continue
        try:
            dd = date.fromisoformat(d)
        except ValueError:
            continue
        if since_d <= dd <= until_d:
            rows.append(r)
    return {**summary, "rows": rows}
