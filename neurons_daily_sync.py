"""
Daily per-UID earnings snapshot — the foundation for weekly House rollups.

For each scheduled run we capture every SN21 UID with its run-rate alpha
fields (mining gross / mining net / burned / validating / owner) plus the
TAO and alpha prices in effect at snapshot time. Summed across the days
inside a mining/validation week, these rows produce realised weekly
earnings — chain-verifiable via Taostats.

Storage: data/neurons_daily.json
  { "rows": [
      { "date": "YYYY-MM-DD", "fetched_at_utc": ISO, "block": int,
        "alpha_price_tao": float|None, "alpha_price_usd": float|None,
        "tao_price_usd": float|None,
        "uid": int, "hotkey": str, "coldkey": str,
        "is_house": bool, "validator_permit": bool, "is_owner_hotkey": bool,
        "active": bool, "submitting_in_window": bool|None,
        "daily_mining_alpha": float|None,
        "daily_mining_alpha_net": float|None,
        "daily_burned_alpha": float|None,
        "daily_validating_alpha": float|None,
        "daily_owner_alpha": float|None } ] }

Re-running on the same date replaces that day's rows (idempotent).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from collector import load_json, save_json
from config import DATA_DIR

logger = logging.getLogger(__name__)

NEURONS_DAILY_STORE = DATA_DIR / "neurons_daily.json"
RETENTION_DAYS = 90


def _latest_subnet_prices() -> dict[str, float | None]:
    """Pull the most recent alpha + TAO prices from the daily collector log."""
    from config import DAILY_LOG
    log = load_json(DAILY_LOG, [])
    if not log:
        return {"alpha_price_tao": None, "alpha_price_usd": None, "tao_price_usd": None}
    sub = (log[-1] or {}).get("subnet") or {}
    return {
        "alpha_price_tao": sub.get("alpha_price_tao"),
        "alpha_price_usd": sub.get("alpha_price_usd"),
        "tao_price_usd": sub.get("tao_price_usd"),
    }


def sync_neurons_daily() -> dict[str, Any]:
    """Take a per-UID earnings snapshot and persist it for today's date."""
    from neurons_sync import fetch_neurons

    payload = fetch_neurons()
    if "error" in payload:
        return {"skipped": True, "reason": payload["error"]}

    fetched_at = datetime.now(timezone.utc)
    date_str = fetched_at.strftime("%Y-%m-%d")
    prices = _latest_subnet_prices()

    rows: list[dict[str, Any]] = []
    block = payload.get("block_number")
    for n in (payload.get("validators") or []) + (payload.get("miners") or []):
        rows.append({
            "date": date_str,
            "fetched_at_utc": fetched_at.isoformat(),
            "block": block,
            "alpha_price_tao": prices["alpha_price_tao"],
            "alpha_price_usd": prices["alpha_price_usd"],
            "tao_price_usd": prices["tao_price_usd"],
            "uid": n.get("uid"),
            "hotkey": n.get("hotkey"),
            "coldkey": n.get("coldkey"),
            "is_house": bool(n.get("is_house")),
            "is_owner_hotkey": bool(n.get("is_owner_hotkey")),
            "validator_permit": bool(n.get("validator_permit")),
            "active": bool(n.get("active")),
            "submitting_in_window": n.get("submitting_in_window"),
            "daily_mining_alpha": n.get("daily_mining_alpha"),
            "daily_mining_alpha_net": n.get("daily_mining_alpha_net"),
            "daily_burned_alpha": n.get("daily_burned_alpha"),
            "daily_validating_alpha": n.get("daily_validating_alpha"),
            "daily_owner_alpha": n.get("daily_owner_alpha"),
        })

    store = load_json(NEURONS_DAILY_STORE, {"rows": []})
    if not isinstance(store, dict) or "rows" not in store:
        store = {"rows": []}

    # Replace today's rows; keep last RETENTION_DAYS days.
    kept = [r for r in store["rows"] if r.get("date") != date_str]
    kept.extend(rows)
    kept.sort(key=lambda r: (r.get("date") or "", r.get("uid") or 0))
    if RETENTION_DAYS > 0:
        cutoff_dates = sorted({r["date"] for r in kept if r.get("date")})
        if len(cutoff_dates) > RETENTION_DAYS:
            keep_dates = set(cutoff_dates[-RETENTION_DAYS:])
            kept = [r for r in kept if r.get("date") in keep_dates]
    store["rows"] = kept
    save_json(NEURONS_DAILY_STORE, store)

    burn = payload.get("burn") or {}
    logger.info(
        "Neurons daily snapshot: %d rows · burn rate=%s · stored days=%d",
        len(rows),
        burn.get("rate"),
        len({r["date"] for r in kept if r.get("date")}),
    )
    return {
        "skipped": False,
        "date": date_str,
        "rows_written": len(rows),
        "burn_rate": burn.get("rate"),
        "path": str(NEURONS_DAILY_STORE),
    }
