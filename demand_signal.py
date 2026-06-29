"""
Demand signal — SN21 holder base + protocol buy pressure over time, for the Social tab.

The June-2026 attribution baseline (docs/Alpha_Price_Attribution_2026-06.md) found the rally was
SN21-specific demand that on-chain mechanics don't explain — the signature being holder count
*broadening* while protocol_buy_pressure stays negative (attention-driven, off-protocol buying).
This module surfaces that signature by merging two ledgers we already capture daily:

  - holder_count: holders_sync daily snapshots (holders_snapshots.json, ~31d)
  - buy_pressure + price: movers_attribution signal ledger (movers_signal_ledger.json, ~120d), SN21 row

No new capture infra — pure read/merge. The series accrues as those jobs run.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from collector import load_json
from holders_sync import HOLDERS_STORE
from movers_attribution import SIGNAL_LEDGER_STORE

SN21 = "21"
SERIES_DAYS = 60


def _pct(now: float | None, prev: float | None) -> float | None:
    if now is None or prev is None or prev == 0:
        return None
    return round((now - prev) / prev * 100.0, 2)


def demand_series() -> dict[str, Any]:
    """Merge holder count + SN21 buy_pressure/price by date into one time series, newest last,
    plus a `current` summary with the 7-day holder-count change."""
    led = load_json(SIGNAL_LEDGER_STORE, {}) or {}
    holders = (load_json(HOLDERS_STORE, {"snapshots": []}) or {}).get("snapshots", [])

    holder_by_date = {
        s["date"]: s.get("holder_count")
        for s in holders
        if s.get("date") and s.get("holder_count") is not None
    }

    cutoff = (datetime.now(timezone.utc) - timedelta(days=SERIES_DAYS)).strftime("%Y-%m-%d")
    dates = sorted(d for d in (set(led) | set(holder_by_date)) if d >= cutoff)

    series = []
    for d in dates:
        sn = (led.get(d) or {}).get(SN21) or {}
        series.append({
            "date": d,
            "holder_count": holder_by_date.get(d),
            "buy_pressure": sn.get("buy_pressure"),
            "price": sn.get("price"),
        })

    # current summary + 7d holder delta
    hc_dates = sorted(holder_by_date)
    cur_hc = holder_by_date.get(hc_dates[-1]) if hc_dates else None
    hc_7d = None
    if hc_dates:
        target = (datetime.strptime(hc_dates[-1], "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")
        prior = [d for d in hc_dates if d <= target] or hc_dates[:1]
        hc_7d = holder_by_date.get(prior[-1]) if prior else None

    latest_sn = None
    for d in reversed(dates):
        sn = (led.get(d) or {}).get(SN21)
        if sn:
            latest_sn = sn
            break

    current = {
        "holder_count": cur_hc,
        "holder_count_7d_ago": hc_7d,
        "holder_count_pct_7d": _pct(cur_hc, hc_7d),
        "buy_pressure": (latest_sn or {}).get("buy_pressure"),
        "price": (latest_sn or {}).get("price"),
        "as_of": dates[-1] if dates else None,
    }

    return {
        "n_days": len(series),
        "series": series,
        "current": current,
        "note": (
            "Demand signature: holder count broadening while buy pressure stays negative = "
            "attention-driven, off-protocol buying (see Alpha_Price_Attribution_2026-06)."
        ),
    }
