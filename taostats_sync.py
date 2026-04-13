"""
Fetch owner coldkey transfer history from Taostats API (source of truth for on-chain TAO flows).

Docs: https://docs.taostats.io/reference/get-transfers
GET https://api.taostats.io/api/transfer/v1 — filter by `address` (SS58), `network=finney`, paginate.

Note: Taostats “account /transactions” UI may list extrinsics beyond TAO transfers; this endpoint
covers documented coldkey transfers. Extend with additional API paths if you need full parity.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

import requests

from collector import save_json
from config import DATA_DIR

logger = logging.getLogger(__name__)

TAOSTATS_API_BASE = os.environ.get("TAOSTATS_API_BASE", "https://api.taostats.io").rstrip("/")
TRANSFER_PATH = "/api/transfer/v1"
TAOSTATS_STORE = DATA_DIR / "taostats_owner_transfers.json"

# Pagination safety (200 max per page per API docs)
_DEFAULT_LIMIT = 200
_MAX_PAGES = int(os.environ.get("TAOSTATS_MAX_PAGES", "500"))


def _api_key() -> str | None:
    return (os.environ.get("TAOSTATS_API_KEY") or "").strip() or None


def _owner_ss58() -> str | None:
    for key in ("TAOSTATS_OWNER_ID", "TAOSTATS_ACCOUNT_SS58"):
        v = (os.environ.get(key) or "").strip()
        if v:
            return v
    return None


def _headers() -> dict[str, str]:
    key = _api_key()
    if not key:
        return {}
    # OpenAPI: apiKey in Authorization header (raw key; do not prefix "Bearer " per Taostats docs)
    return {"Authorization": key, "Accept": "application/json"}


def _get_json(session: requests.Session, params: dict[str, Any]) -> dict[str, Any]:
    """GET transfer endpoint with retries on rate limit."""
    url = f"{TAOSTATS_API_BASE}{TRANSFER_PATH}"
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


def _fetch_pages_for_params(
    session: requests.Session,
    base_params: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Paginate one query shape; return rows + last pagination."""
    all_rows: list[dict[str, Any]] = []
    last_pagination: dict[str, Any] = {}
    page = 1

    while page <= _MAX_PAGES:
        params = {
            **base_params,
            "page": page,
            "limit": min(int(base_params.get("limit", _DEFAULT_LIMIT)), 200),
        }
        body = _get_json(session, params)
        rows = body.get("data") or []
        all_rows.extend(rows)
        last_pagination = body.get("pagination") or {}
        next_page = last_pagination.get("next_page")
        total_pages = last_pagination.get("total_pages") or 0

        if not rows:
            break
        if not next_page or page >= total_pages:
            break
        page = int(next_page)

    return all_rows, last_pagination


def fetch_all_transfers(
    *,
    address: str,
    network: str = "finney",
    limit: int = _DEFAULT_LIMIT,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    Return (transfer rows, last pagination).

    Uses `address=` (SS58) per Taostats — TAO coldkey transfers only. Subnet alpha moves
    may appear under other extrinsics; see Taostats docs if you need full /transactions parity.
    """
    session = requests.Session()
    session.headers.update(_headers())

    base: dict[str, Any] = {
        "network": network,
        "address": address,
        "limit": limit,
        "order": "timestamp_desc",
    }
    rows, last_pag = _fetch_pages_for_params(session, base)

    # Optional: merge `from` and `to` queries (extra API calls). Enable if `address` misses rows.
    if os.environ.get("TAOSTATS_TRANSFER_MERGE_DIRECTIONS", "").strip().lower() in ("1", "true", "yes"):
        seen: dict[str, dict[str, Any]] = {}
        for row in rows:
            rid = row.get("id") or row.get("transaction_hash")
            if rid:
                seen[rid] = row
        for key in ("from", "to"):
            b2 = {k: v for k, v in base.items() if k != "address"}
            b2[key] = address
            extra, last_pag = _fetch_pages_for_params(session, b2)
            for row in extra:
                rid = row.get("id") or row.get("transaction_hash")
                if rid and rid not in seen:
                    seen[rid] = row
        rows = sorted(
            seen.values(),
            key=lambda r: (r.get("timestamp") or "", r.get("block_number") or 0),
            reverse=True,
        )

    return rows, last_pag


def sync_owner_transfers() -> dict[str, Any]:
    """
    Pull all pages of transfers for the configured owner SS58 and write JSON snapshot.

    Returns a status dict (for API / logs). On missing config, returns skipped=True without raising.
    """
    key = _api_key()
    addr = _owner_ss58()

    if not key:
        logger.warning("Taostats sync skipped: TAOSTATS_API_KEY not set")
        return {"skipped": True, "reason": "missing TAOSTATS_API_KEY"}

    if not addr:
        logger.warning("Taostats sync skipped: set TAOSTATS_OWNER_ID (SS58) or TAOSTATS_ACCOUNT_SS58")
        return {"skipped": True, "reason": "missing owner address"}

    logger.info("Taostats sync: fetching transfers for %s…", addr[:12] + "…")
    rows, pagination = fetch_all_transfers(address=addr)
    now = datetime.now(timezone.utc).isoformat()

    payload: dict[str, Any] = {
        "source": "taostats",
        "api": {"base": TAOSTATS_API_BASE, "path": TRANSFER_PATH},
        "account_ss58": addr,
        "fetched_at_utc": now,
        "transfer_count": len(rows),
        "last_pagination": pagination,
        "transfers": rows,
    }
    save_json(TAOSTATS_STORE, payload)
    logger.info("Taostats sync: wrote %s transfers to %s", len(rows), TAOSTATS_STORE)
    return {
        "skipped": False,
        "account_ss58": addr,
        "transfer_count": len(rows),
        "fetched_at_utc": now,
        "path": str(TAOSTATS_STORE),
    }
