"""
SN21 neurons (validators + miners) view powered by Taostats metagraph endpoint.

Source: GET /api/metagraph/latest/v1?netuid=21 (256 UIDs, paginated 100 per page).
Per-UID fields verified live: uid, hotkey, coldkey, validator_permit, active,
incentive, dividends, emission, daily_mining_alpha, daily_burned_alpha,
daily_validating_alpha, daily_owner_alpha (+ *_as_tao), axon, updated,
registered_at_block, is_owner_hotkey, is_child_key, is_immunity_period.

`updated` = blocks since the UID last set weights / served. Combined with the
mining/validation window from windows.py, we mark each UID "submitting in
current window" or not.
"""

from __future__ import annotations

import logging
import os
import threading
import time as _time
from datetime import datetime, timezone
from typing import Any

import requests

from windows import current_window, is_submitting_in_window, ET

logger = logging.getLogger(__name__)

TAOSTATS_API_BASE = os.environ.get("TAOSTATS_API_BASE", "https://api.taostats.io").rstrip("/")
METAGRAPH_LATEST_PATH = "/api/metagraph/latest/v1"
NETUID = 21
RAO_PER_TAO = 1_000_000_000
PAGE_SIZE = 100
CACHE_TTL_SECONDS = 60
MAX_429_RETRIES = 5

_cache_lock = threading.Lock()
_cache: dict[str, Any] = {"fetched_at": 0.0, "payload": None}


def _api_key() -> str | None:
    return (os.environ.get("TAOSTATS_API_KEY") or "").strip() or None


def _headers() -> dict[str, str]:
    key = _api_key()
    return {"Authorization": key, "Accept": "application/json"} if key else {}


def _to_float(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _rao_to_tao(v: Any) -> float | None:
    f = _to_float(v)
    return None if f is None else f / RAO_PER_TAO


def _ss58(v: Any) -> str | None:
    if isinstance(v, dict):
        return v.get("ss58")
    return v


def _short(addr: str | None, head: int = 8, tail: int = 4) -> str | None:
    if not addr:
        return None
    return f"{addr[:head]}…{addr[-tail:]}" if len(addr) > head + tail + 1 else addr


def _fetch_page(session: requests.Session, page: int) -> dict[str, Any]:
    """One paged read of /metagraph/latest with 429-aware retry."""
    url = f"{TAOSTATS_API_BASE}{METAGRAPH_LATEST_PATH}"
    params = {"netuid": NETUID, "limit": PAGE_SIZE, "page": page}
    for attempt in range(MAX_429_RETRIES):
        r = session.get(url, params=params, timeout=60)
        if r.status_code == 429:
            wait = min(2 ** attempt + 0.5, 30)
            logger.warning("Neurons sync 429 on page %s; retry in %ss (attempt %s/%s)",
                           page, wait, attempt + 1, MAX_429_RETRIES)
            _time.sleep(wait)
            continue
        r.raise_for_status()
        return r.json()
    r = session.get(url, params=params, timeout=60)
    r.raise_for_status()
    return r.json()


def _fetch_all_uids(session: requests.Session) -> tuple[list[dict[str, Any]], int | None, str | None]:
    page = 1
    rows: list[dict[str, Any]] = []
    block_number: int | None = None
    timestamp: str | None = None
    while True:
        body = _fetch_page(session, page)
        page_rows = body.get("data") or []
        rows.extend(page_rows)
        for r in page_rows:
            if block_number is None:
                block_number = r.get("block_number")
                timestamp = r.get("timestamp")
        pag = body.get("pagination") or {}
        next_page = pag.get("next_page")
        total_pages = pag.get("total_pages") or 0
        if not page_rows or not next_page or page >= total_pages:
            break
        page = int(next_page)
        if page > 10:  # paranoia cap; SN21 has 256 UIDs = 3 pages max
            break
        _time.sleep(0.4)  # gentle inter-page pacing to dodge bursts of 429s
    return rows, block_number, timestamp


def _normalise_row(
    r: dict[str, Any],
    current_block: int | None,
    current_block_time: datetime | None,
    window_start_et: datetime | None,
) -> dict[str, Any]:
    hotkey = _ss58(r.get("hotkey"))
    coldkey = _ss58(r.get("coldkey"))
    updated = int(r.get("updated") or 0)
    last_update_block = (current_block or 0) - updated
    submitting = None
    last_update_utc = None
    if (
        current_block is not None
        and current_block_time is not None
        and window_start_et is not None
        and updated >= 0
    ):
        try:
            submitting = is_submitting_in_window(
                last_update_block, current_block, current_block_time, window_start_et
            )
            from windows import block_to_utc
            last_update_utc = block_to_utc(current_block, current_block_time, last_update_block).isoformat()
        except Exception:
            submitting = None

    axon = r.get("axon") or {}
    return {
        "uid": r.get("uid"),
        "hotkey": hotkey,
        "hotkey_short": _short(hotkey),
        "coldkey": coldkey,
        "coldkey_short": _short(coldkey),
        "validator_permit": bool(r.get("validator_permit")),
        "active": bool(r.get("active")),
        "is_owner_hotkey": bool(r.get("is_owner_hotkey")),
        "is_child_key": bool(r.get("is_child_key")),
        "is_immunity_period": bool(r.get("is_immunity_period")),
        "incentive": _to_float(r.get("incentive")) or 0.0,
        "dividends": _to_float(r.get("dividends")) or 0.0,
        "trust": _to_float(r.get("trust")),
        "validator_trust": _to_float(r.get("validator_trust")),
        "consensus": _to_float(r.get("consensus")),
        "rank": r.get("rank"),
        "stake_tao": _rao_to_tao(r.get("stake")),
        "alpha_stake": _rao_to_tao(r.get("alpha_stake")),
        "root_stake": _rao_to_tao(r.get("root_stake")),
        "root_stake_as_alpha": _rao_to_tao(r.get("root_stake_as_alpha")),
        "total_alpha_stake": _rao_to_tao(r.get("total_alpha_stake")),
        "emission_alpha_per_tempo": _rao_to_tao(r.get("emission")),
        "daily_reward_tao": _rao_to_tao(r.get("daily_reward")),
        "daily_mining_alpha": _rao_to_tao(r.get("daily_mining_alpha")),
        "daily_mining_alpha_as_tao": _rao_to_tao(r.get("daily_mining_alpha_as_tao")),
        "daily_mining_tao": _rao_to_tao(r.get("daily_mining_tao")),
        "daily_burned_alpha": _rao_to_tao(r.get("daily_burned_alpha")),
        "daily_burned_alpha_as_tao": _rao_to_tao(r.get("daily_burned_alpha_as_tao")),
        "daily_validating_alpha": _rao_to_tao(r.get("daily_validating_alpha")),
        "daily_validating_alpha_as_tao": _rao_to_tao(r.get("daily_validating_alpha_as_tao")),
        "daily_validating_tao": _rao_to_tao(r.get("daily_validating_tao")),
        "daily_owner_alpha": _rao_to_tao(r.get("daily_owner_alpha")),
        "daily_owner_alpha_as_tao": _rao_to_tao(r.get("daily_owner_alpha_as_tao")),
        "axon_ip": axon.get("ip") if isinstance(axon, dict) else None,
        "axon_port": axon.get("port") if isinstance(axon, dict) else None,
        "axon_block": axon.get("block") if isinstance(axon, dict) else None,
        "updated_blocks_ago": updated,
        "last_update_block": last_update_block,
        "last_update_utc": last_update_utc,
        "registered_at_block": r.get("registered_at_block"),
        "submitting_in_window": submitting,
    }


def fetch_neurons() -> dict[str, Any]:
    """
    Pull fresh metagraph snapshot (cached 60 s), classify into validators and
    miners, mark each with submitting_in_window for the active window.
    """
    now = _time.time()
    with _cache_lock:
        if _cache["payload"] and (now - _cache["fetched_at"]) < CACHE_TTL_SECONDS:
            return _cache["payload"]

    if not _api_key():
        return {"error": "TAOSTATS_API_KEY not set"}

    session = requests.Session()
    session.headers.update(_headers())

    rows, block_number, timestamp = _fetch_all_uids(session)

    current_block_time = None
    if timestamp:
        try:
            current_block_time = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except Exception:
            current_block_time = None

    kind, win_start, win_end = current_window()
    win_start_et = win_start
    win_end_et = win_end

    normalised = [
        _normalise_row(r, block_number, current_block_time, win_start_et) for r in rows
    ]

    validators = [n for n in normalised if n["validator_permit"]]
    miners = [n for n in normalised if not n["validator_permit"]]

    validators.sort(key=lambda n: (-(n.get("daily_validating_alpha") or 0.0), n["uid"]))
    miners.sort(key=lambda n: (-(n.get("incentive") or 0.0), -(n.get("daily_mining_alpha") or 0.0), n["uid"]))

    val_active_window = "validation"
    miner_active_window = "mining"

    submitters_validators = sum(1 for v in validators if v.get("submitting_in_window"))
    submitters_miners = sum(1 for m in miners if m.get("submitting_in_window"))

    payload = {
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "block_number": block_number,
        "block_timestamp": timestamp,
        "totals": {
            "uids": len(normalised),
            "validators": len(validators),
            "miners": len(miners),
            "active_validators": sum(1 for v in validators if v.get("active")),
            "active_miners": sum(1 for m in miners if m.get("active")),
        },
        "window": {
            "current_kind": kind,
            "start_et": win_start_et.isoformat(),
            "end_et": win_end_et.isoformat(),
            "now_et": datetime.now(timezone.utc).astimezone(ET).isoformat(),
            "validators_relevant": kind == val_active_window,
            "miners_relevant": kind == miner_active_window,
        },
        "submitting_in_window": {
            "validators": submitters_validators,
            "miners": submitters_miners,
        },
        "validators": validators,
        "miners": miners,
    }

    with _cache_lock:
        _cache["payload"] = payload
        _cache["fetched_at"] = now

    logger.info(
        "Neurons sync: %d validators (%d submitting), %d miners (%d submitting), window=%s",
        len(validators),
        submitters_validators,
        len(miners),
        submitters_miners,
        kind,
    )
    return payload
