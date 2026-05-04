"""
Subnet 21 daily activity sync. Pulls 24h pool volumes + subnet hyperparams from
Taostats and appends a daily row to data/subnet_daily.json. Powers the Activity tab.

Sources verified against the Taostats Pro API:
  GET /api/dtao/pool/latest/v1?netuid=21          → 24h buy/sell volumes, buyers/sellers
  GET /api/subnet/latest/v1?netuid=21             → validators, miners, burn fields
  GET /api/dtao/stake_balance/latest/v1?netuid=21 → subnet_total_holders (only need first row)
"""

from __future__ import annotations

import logging
import os
import time as _time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from collector import save_json, load_json
from config import DATA_DIR

logger = logging.getLogger(__name__)

TAOSTATS_API_BASE = os.environ.get("TAOSTATS_API_BASE", "https://api.taostats.io").rstrip("/")
NETUID = 21
RAO_PER_TAO = 1_000_000_000

POOL_LATEST_PATH = "/api/dtao/pool/latest/v1"
SUBNET_LATEST_PATH = "/api/subnet/latest/v1"
STAKE_BALANCE_LATEST_PATH = "/api/dtao/stake_balance/latest/v1"

SUBNET_DAILY_STORE = DATA_DIR / "subnet_daily.json"
RETENTION_DAYS = 365


def _api_key() -> str | None:
    return (os.environ.get("TAOSTATS_API_KEY") or "").strip() or None


def _headers() -> dict[str, str]:
    key = _api_key()
    return {"Authorization": key, "Accept": "application/json"} if key else {}


def _rao_to_tao(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(int(value)) / RAO_PER_TAO
    except (TypeError, ValueError):
        try:
            return float(value) / RAO_PER_TAO
        except (TypeError, ValueError):
            return None


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


MAX_429_RETRIES = 5


def _get(session: requests.Session, path: str, params: dict[str, Any]) -> dict[str, Any]:
    """Authenticated GET with 429-aware retry (1s, 2s, 4s, 8s, 16s)."""
    url = f"{TAOSTATS_API_BASE}{path}"
    for attempt in range(MAX_429_RETRIES):
        r = session.get(url, params=params, timeout=60)
        if r.status_code == 429:
            wait = min(2 ** attempt + 0.5, 30)
            logger.warning("Subnet sync 429 on %s; retry in %ss (attempt %s/%s)",
                           path, wait, attempt + 1, MAX_429_RETRIES)
            _time.sleep(wait)
            continue
        r.raise_for_status()
        return r.json()
    r = session.get(url, params=params, timeout=60)
    r.raise_for_status()
    return r.json()


def fetch_pool_latest(session: requests.Session) -> dict[str, Any] | None:
    body = _get(session, POOL_LATEST_PATH, {"netuid": NETUID})
    rows = body.get("data") or []
    if not rows:
        return None
    r = rows[0]
    return {
        "block_number": r.get("block_number"),
        "timestamp": r.get("timestamp"),
        "alpha_price_tao": _to_float(r.get("price")),
        "alpha_buy_volume_24h": _rao_to_tao(r.get("alpha_buy_volume_24_hr")),
        "alpha_sell_volume_24h": _rao_to_tao(r.get("alpha_sell_volume_24_hr")),
        "tao_buy_volume_24h": _rao_to_tao(r.get("tao_buy_volume_24_hr")),
        "tao_sell_volume_24h": _rao_to_tao(r.get("tao_sell_volume_24_hr")),
        "alpha_volume_24h": _rao_to_tao(r.get("alpha_volume_24_hr")),
        "tao_volume_24h": _rao_to_tao(r.get("tao_volume_24_hr")),
        "buys_24h": r.get("buys_24_hr"),
        "sells_24h": r.get("sells_24_hr"),
        "buyers_24h": r.get("buyers_24_hr"),
        "sellers_24h": r.get("sellers_24_hr"),
        "liquidity_tao": _rao_to_tao(r.get("liquidity")),
        "market_cap_tao": _rao_to_tao(r.get("market_cap")),
        "total_alpha": _rao_to_tao(r.get("total_alpha")),
        "total_tao": _rao_to_tao(r.get("total_tao")),
        "price_change_1d_pct": _to_float(r.get("price_change_1_day")),
        "price_change_7d_pct": _to_float(r.get("price_change_1_week")),
        "rank": r.get("rank"),
        "fear_and_greed_index": _to_float(r.get("fear_and_greed_index")),
        "fear_and_greed_sentiment": r.get("fear_and_greed_sentiment"),
    }


def fetch_subnet_latest(session: requests.Session) -> dict[str, Any] | None:
    body = _get(session, SUBNET_LATEST_PATH, {"netuid": NETUID})
    rows = body.get("data") or []
    if not rows:
        return None
    r = rows[0]
    return {
        "block_number": r.get("block_number"),
        "timestamp": r.get("timestamp"),
        "validators": r.get("validators"),
        "active_validators": r.get("active_validators"),
        "active_miners": r.get("active_miners"),
        "active_keys": r.get("active_keys"),
        "max_neurons": r.get("max_neurons"),
        "neuron_registrations_this_interval": r.get("neuron_registrations_this_interval"),
        "registration_allowed": r.get("registration_allowed"),
        "neuron_registration_cost_tao": _rao_to_tao(r.get("neuron_registration_cost")),
        "tempo": r.get("tempo"),
        "incentive_burn": _to_float(r.get("incentive_burn")),
        "min_burn_tao": _rao_to_tao(r.get("min_burn")),
        "max_burn_tao": _rao_to_tao(r.get("max_burn")),
        "burn_half_life": r.get("burn_half_life"),
        "burn_increase_mult": _to_float(r.get("burn_increase_mult")),
        "recycled_24h_tao": _rao_to_tao(r.get("recycled_24_hours")),
        "recycled_lifetime_tao": _rao_to_tao(r.get("recycled_lifetime")),
        "net_flow_1d_tao": _rao_to_tao(r.get("net_flow_1_day")),
        "net_flow_7d_tao": _rao_to_tao(r.get("net_flow_7_days")),
        "net_flow_30d_tao": _rao_to_tao(r.get("net_flow_30_days")),
    }


def fetch_total_holders(session: requests.Session) -> int | None:
    body = _get(session, STAKE_BALANCE_LATEST_PATH, {"netuid": NETUID, "limit": 1})
    rows = body.get("data") or []
    if not rows:
        return None
    return rows[0].get("subnet_total_holders")


def sync_subnet_daily() -> dict[str, Any]:
    """Append today's row to subnet_daily.json (replaces row if same date already present)."""
    if not _api_key():
        logger.warning("Subnet daily sync skipped: TAOSTATS_API_KEY not set")
        return {"skipped": True, "reason": "missing TAOSTATS_API_KEY"}

    session = requests.Session()
    session.headers.update(_headers())

    pool = fetch_pool_latest(session)
    subnet = fetch_subnet_latest(session)
    total_holders = fetch_total_holders(session)
    fetched_at = datetime.now(timezone.utc)
    date_str = fetched_at.strftime("%Y-%m-%d")

    row = {
        "date": date_str,
        "fetched_at_utc": fetched_at.isoformat(),
        "block": (pool or {}).get("block_number") or (subnet or {}).get("block_number"),
        "subnet_total_holders": total_holders,
        "pool": pool or {},
        "subnet": subnet or {},
    }

    log = load_json(SUBNET_DAILY_STORE, [])
    if not isinstance(log, list):
        log = []
    log = [e for e in log if e.get("date") != date_str]
    log.append(row)
    log.sort(key=lambda e: e["date"])
    if len(log) > RETENTION_DAYS:
        log = log[-RETENTION_DAYS:]
    save_json(SUBNET_DAILY_STORE, log)

    logger.info(
        "Subnet daily sync: holders=%s validators=%s miners=%s buys=%s sells=%s",
        total_holders,
        (subnet or {}).get("active_validators"),
        (subnet or {}).get("active_miners"),
        (pool or {}).get("buys_24h"),
        (pool or {}).get("sells_24h"),
    )

    return {
        "skipped": False,
        "date": date_str,
        "block": row["block"],
        "subnet_total_holders": total_holders,
        "rows_stored": len(log),
        "path": str(SUBNET_DAILY_STORE),
    }
