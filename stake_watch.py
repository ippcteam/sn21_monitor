"""
Owner-share stake watch — confirm the daily emission shares keep landing.

Our owner-share coldkey (`TAOSTATS_OWNER_ID`, default 5DkEA99g…) receives its cut of
SN21 emissions NOT as TAO transfers but as **alpha (α) staked** onto our validator
hotkey (5GuiHB…, UID 64) on netuid 21. The owner key holder pushes two stakings a day
— the owner share and the validator share — so the wallet's staked-α balance should
grow ~daily. Because alpha staking never shows up on the Taostats /transfer endpoint,
the only reliable signal is the staked-α *balance series*.

This module pulls that series from Taostats `dtao/stake_balance` (history + latest),
measures inflow over a rolling lookback window, and raises a Telegram alert when a full
day passes with no meaningful inflow (i.e. the owner key holder's daily push stalled).

Docs: https://docs.taostats.io/reference — GET /api/dtao/stake_balance/{history,latest}/v1
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

from collector import load_json, save_json
from config import DATA_DIR

logger = logging.getLogger(__name__)

TAOSTATS_API_BASE = os.environ.get("TAOSTATS_API_BASE", "https://api.taostats.io").rstrip("/")
HISTORY_PATH = "/api/dtao/stake_balance/history/v1"
LATEST_PATH = "/api/dtao/stake_balance/latest/v1"

NETUID = int(os.environ.get("SN21_NETUID", "21"))
# Our owner-share recipient coldkey (the wallet the shares are staked *onto*).
OWNER_SHARE_COLDKEY = (
    os.environ.get("OWNER_SHARE_COLDKEY")
    or os.environ.get("TAOSTATS_OWNER_ID")
    or "5DkEA99gAAF2Ge6X3h76x98LbYtqT7gJ6h9VaApfMkKJCPJM"
).strip()
# The validator hotkey the shares are staked through (UID 64).
OUR_VALIDATOR_HOTKEY = (
    os.environ.get("OUR_VALIDATOR_HOTKEY")
    or "5GuiHBTfciFauoF1XuyvVuWYrQaS7LExrbsqV5EmDU2ibJEz"
).strip()

RAO_PER_ALPHA = 1_000_000_000

# Tuning. A normal day delivers ~365–450 α; these thresholds sit well clear of noise.
LOOKBACK_HOURS = float(os.environ.get("STAKE_WATCH_LOOKBACK_HOURS", "30"))
MIN_INFLOW_ALPHA = float(os.environ.get("STAKE_WATCH_MIN_INFLOW_ALPHA", "150"))

STAKE_WATCH_STORE = DATA_DIR / "stake_watch.json"
STAKE_WATCH_HISTORY = DATA_DIR / "stake_watch_history.json"
HISTORY_RETENTION = 180


def _api_key() -> str | None:
    return (os.environ.get("TAOSTATS_API_KEY") or "").strip() or None


def _headers() -> dict[str, str]:
    key = _api_key()
    return {"Authorization": key, "Accept": "application/json"} if key else {}


def _get(session: requests.Session, path: str, params: dict[str, Any]) -> dict[str, Any]:
    import time

    url = f"{TAOSTATS_API_BASE}{path}"
    for attempt in range(5):
        r = session.get(url, params=params, timeout=120)
        if r.status_code == 429:
            wait = min(2**attempt, 60)
            logger.warning("Taostats rate limited (429); retry in %ss", wait)
            time.sleep(wait)
            continue
        r.raise_for_status()
        return r.json()
    r = session.get(url, params=params, timeout=120)
    r.raise_for_status()
    return r.json()


def _parse_ts(s: str) -> datetime:
    """Parse Taostats ISO timestamps (sometimes with millis, always Z/UTC)."""
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _alpha(balance_rao: Any) -> float:
    return int(balance_rao) / RAO_PER_ALPHA


def fetch_series(session: requests.Session, limit: int = 30) -> list[dict[str, Any]]:
    """
    Return the staked-α balance series for our owner-share position, oldest→newest.
    Combines the daily history snapshots with the live `latest` point so an inflow
    that lands after the last daily snapshot is still seen.
    """
    base = {"coldkey": OWNER_SHARE_COLDKEY, "hotkey": OUR_VALIDATOR_HOTKEY, "netuid": NETUID}

    hist = _get(session, HISTORY_PATH, {**base, "limit": limit}).get("data") or []
    points: dict[str, dict[str, Any]] = {}
    for row in hist:
        ts = row.get("timestamp")
        if not ts:
            continue
        points[ts] = {
            "timestamp": ts,
            "block": row.get("block_number"),
            "alpha": _alpha(row["balance"]),
            "balance_as_tao": float(row.get("balance_as_tao") or 0) / RAO_PER_ALPHA,
        }

    latest_rows = _get(session, LATEST_PATH, base).get("data") or []
    for row in latest_rows:
        ts = row.get("timestamp")
        if ts:
            points[ts] = {
                "timestamp": ts,
                "block": row.get("block_number"),
                "alpha": _alpha(row["balance"]),
                "balance_as_tao": float(row.get("balance_as_tao") or 0) / RAO_PER_ALPHA,
                "is_latest": True,
            }

    return sorted(points.values(), key=lambda p: p["timestamp"])


def _inflow_over_window(series: list[dict[str, Any]], now: datetime, hours: float) -> dict[str, Any]:
    """Inflow (Δα) between `now - hours` and the latest point."""
    if not series:
        return {"inflow_alpha": None, "from": None, "to": None}
    latest = series[-1]
    cutoff = now - timedelta(hours=hours)
    # Baseline = newest point at or before the cutoff; else the oldest we have.
    baseline = series[0]
    for p in series:
        if _parse_ts(p["timestamp"]) <= cutoff:
            baseline = p
        else:
            break
    return {
        "inflow_alpha": round(latest["alpha"] - baseline["alpha"], 6),
        "from": baseline["timestamp"],
        "to": latest["timestamp"],
        "baseline_alpha": round(baseline["alpha"], 6),
        "latest_alpha": round(latest["alpha"], 6),
    }


def _daily_deltas(series: list[dict[str, Any]], days: int = 7) -> list[dict[str, Any]]:
    """Per-UTC-day inflow, newest first (collapses any intra-day duplicate snapshots)."""
    by_day: dict[str, float] = {}
    for p in series:
        by_day[p["timestamp"][:10]] = p["alpha"]  # last seen wins → end-of-day balance
    days_sorted = sorted(by_day)
    out: list[dict[str, Any]] = []
    for i in range(1, len(days_sorted)):
        d = days_sorted[i]
        out.append({"date": d, "inflow_alpha": round(by_day[d] - by_day[days_sorted[i - 1]], 3)})
    return list(reversed(out))[:days]


def run_stake_watch(notify: bool = True, *, _now: datetime | None = None) -> dict[str, Any]:
    """
    Pull the staked-α series, judge whether the daily emission shares are still landing,
    persist a snapshot, and (on a fresh OK→ALERT transition) fire a Telegram alert.
    """
    now = _now or datetime.now(timezone.utc)
    session = requests.Session()
    session.headers.update(_headers())

    series = fetch_series(session)
    if not series:
        raise RuntimeError("stake_balance series empty — check Taostats key / coldkey / hotkey")

    window = _inflow_over_window(series, now, LOOKBACK_HOURS)
    daily = _daily_deltas(series)
    latest = series[-1]
    inflow = window["inflow_alpha"] or 0.0
    ok = inflow >= MIN_INFLOW_ALPHA
    status = "ok" if ok else "alert"

    hours_since = None
    last_inflow_ts = None
    for i in range(len(series) - 1, 0, -1):
        if series[i]["alpha"] - series[i - 1]["alpha"] >= MIN_INFLOW_ALPHA:
            last_inflow_ts = series[i]["timestamp"]
            hours_since = round((now - _parse_ts(last_inflow_ts)).total_seconds() / 3600, 1)
            break

    result = {
        "checked_at": now.isoformat(),
        "status": status,
        "coldkey": OWNER_SHARE_COLDKEY,
        "hotkey": OUR_VALIDATOR_HOTKEY,
        "netuid": NETUID,
        "current_alpha": round(latest["alpha"], 4),
        "current_block": latest.get("block"),
        "latest_point_at": latest["timestamp"],
        "lookback_hours": LOOKBACK_HOURS,
        "min_inflow_alpha": MIN_INFLOW_ALPHA,
        "window_inflow_alpha": round(inflow, 4),
        "window_from": window["from"],
        "last_inflow_at": last_inflow_ts,
        "hours_since_last_inflow": hours_since,
        "daily_inflow_alpha": daily,
        "avg_daily_inflow_alpha": (
            round(sum(d["inflow_alpha"] for d in daily) / len(daily), 2) if daily else None
        ),
    }

    prev = load_json(STAKE_WATCH_STORE, {})
    save_json(STAKE_WATCH_STORE, result)

    hist = load_json(STAKE_WATCH_HISTORY, [])
    if isinstance(hist, list):
        hist.append(
            {k: result[k] for k in ("checked_at", "status", "current_alpha", "window_inflow_alpha")}
        )
        save_json(STAKE_WATCH_HISTORY, hist[-HISTORY_RETENTION:])

    # Alert only on a fresh OK→ALERT transition, so we don't re-spam every run.
    transitioned = status == "alert" and prev.get("status") != "alert"
    result["alerted"] = False
    if notify and transitioned:
        try:
            result["alerted"] = _send_alert(result)
        except Exception:
            logger.exception("Stake-watch Telegram alert failed")

    logger.info(
        "Stake watch: %s — current %.1f α, %.1f α in last %sh (min %s), %s daily avg",
        status.upper(),
        result["current_alpha"],
        inflow,
        LOOKBACK_HOURS,
        MIN_INFLOW_ALPHA,
        result["avg_daily_inflow_alpha"],
    )
    return result


def _send_alert(result: dict[str, Any]) -> bool:
    from digest.channels import telegram as telegram_channel

    last = result["last_inflow_at"] or "unknown"
    lines = [
        "⚠️ SN21 owner-share emission shares STALLED",
        "",
        f"No alpha staked to our owner-share wallet in the last "
        f"{result['lookback_hours']:.0f}h.",
        f"  • Window inflow: {result['window_inflow_alpha']:.1f} α "
        f"(expected ≥ {result['min_inflow_alpha']:.0f})",
        f"  • Current staked: {result['current_alpha']:.1f} α",
        f"  • Last meaningful inflow: {last}",
        f"  • 7-day avg: {result['avg_daily_inflow_alpha']} α/day",
        "",
        f"Wallet {result['coldkey'][:10]}… via validator {result['hotkey'][:10]}… (UID 64).",
        "Check the owner key holder's daily owner-share + validator-share staking.",
    ]
    telegram_channel.send("\n".join(lines))
    return True


if __name__ == "__main__":
    import json

    logging.basicConfig(level=logging.INFO)
    print(json.dumps(run_stake_watch(notify=False), indent=2))
