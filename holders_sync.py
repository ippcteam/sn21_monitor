"""
SN21 holder snapshot + 24h movement diff.

Source: GET /api/dtao/stake_balance/latest/v1?netuid=21 (paginated, 200 per page).
At time of build there are ~1,971 (hotkey × coldkey) staking positions on SN21.

Storage: data/holders_snapshots.json keeps the last N daily snapshots:
  {"snapshots": [{"date": "YYYY-MM-DD", "fetched_at_utc": "...", "holders": [...]}, ...]}

Each holder row is keyed by ``f"{hotkey}|{coldkey}"`` so 24h deltas survive
re-staking-to-same-pair.
"""

from __future__ import annotations

import logging
import os
import time as _time
from datetime import datetime, timezone
from typing import Any

import requests

from collector import save_json, load_json
from config import DATA_DIR
from labels import house_set, is_house

logger = logging.getLogger(__name__)

TAOSTATS_API_BASE = os.environ.get("TAOSTATS_API_BASE", "https://api.taostats.io").rstrip("/")
STAKE_BALANCE_LATEST_PATH = "/api/dtao/stake_balance/latest/v1"
NETUID = 21
RAO_PER_TAO = 1_000_000_000
PAGE_SIZE = 200
SNAPSHOT_RETENTION = 7
INTER_PAGE_SLEEP = 0.8        # default pacing between pages
LATE_PAGE_THRESHOLD = 4       # pages > this get extra pacing
LATE_PAGE_SLEEP = 2.0         # Taostats reliably 429s page 6 — slow that ramp
MAX_429_RETRIES = 8           # was 5; total worst-case backoff ~5 min
MAX_BACKOFF_S = 60            # cap any single retry at 60s

HOLDERS_STORE = DATA_DIR / "holders_snapshots.json"


def _retry_after_seconds(resp) -> float | None:
    """Honor Retry-After header if Taostats sends one."""
    raw = resp.headers.get("Retry-After")
    if not raw:
        return None
    try:
        return min(float(raw), MAX_BACKOFF_S)
    except (TypeError, ValueError):
        # HTTP-date form — not worth parsing; let exponential take over.
        return None


def _api_key() -> str | None:
    return (os.environ.get("TAOSTATS_API_KEY") or "").strip() or None


def _headers() -> dict[str, str]:
    key = _api_key()
    return {"Authorization": key, "Accept": "application/json"} if key else {}


def _ss58(v: Any) -> str | None:
    if isinstance(v, dict):
        return v.get("ss58")
    return v


def _to_int(v: Any) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def _fetch_page(session: requests.Session, page: int) -> dict[str, Any]:
    """One paginated read of stake_balance/latest, resilient to Taostats 429s.

    Honors Retry-After when present, otherwise exponential backoff capped at
    MAX_BACKOFF_S. Worst-case total wait ≈ 2+4+8+16+32+60+60+60 ≈ 4 min over
    8 retries, well within the daily window.
    """
    url = f"{TAOSTATS_API_BASE}{STAKE_BALANCE_LATEST_PATH}"
    params = {"netuid": NETUID, "limit": PAGE_SIZE, "page": page, "order": "balance_desc"}
    for attempt in range(MAX_429_RETRIES):
        r = session.get(url, params=params, timeout=120)
        if r.status_code == 429:
            ra = _retry_after_seconds(r)
            wait = ra if ra is not None else min(2 ** attempt + 1.0, MAX_BACKOFF_S)
            logger.warning(
                "Holders sync 429 on page %s; retry in %.1fs (attempt %s/%s%s)",
                page, wait, attempt + 1, MAX_429_RETRIES,
                ", honoring Retry-After" if ra is not None else "",
            )
            _time.sleep(wait)
            continue
        r.raise_for_status()
        return r.json()
    # Final attempt — let the HTTPError surface with full status detail.
    r = session.get(url, params=params, timeout=120)
    r.raise_for_status()
    return r.json()


def _fetch_all_holders(session: requests.Session) -> list[dict[str, Any]]:
    all_rows: list[dict[str, Any]] = []
    page = 1
    while True:
        body = _fetch_page(session, page)
        rows = body.get("data") or []
        for r in rows:
            all_rows.append(
                {
                    "hotkey": _ss58(r.get("hotkey")),
                    "hotkey_name": r.get("hotkey_name"),
                    "coldkey": _ss58(r.get("coldkey")),
                    "balance_rao": _to_int(r.get("balance")),
                    "balance_as_tao_rao": _to_int(r.get("balance_as_tao")),
                    "subnet_rank": r.get("subnet_rank"),
                }
            )
        pag = body.get("pagination") or {}
        next_page = pag.get("next_page")
        total_pages = pag.get("total_pages") or 0
        if not rows or not next_page or page >= total_pages:
            break
        page = int(next_page)
        if page > 100:  # paranoia cap
            break
        # Pages 5+ are where Taostats reliably throttles; pace them more.
        _time.sleep(LATE_PAGE_SLEEP if page > LATE_PAGE_THRESHOLD else INTER_PAGE_SLEEP)
    return all_rows


def sync_holders_snapshot() -> dict[str, Any]:
    """Pull a full holder snapshot for today and persist it (replaces today's row)."""
    if not _api_key():
        logger.warning("Holders sync skipped: TAOSTATS_API_KEY not set")
        return {"skipped": True, "reason": "missing TAOSTATS_API_KEY"}

    session = requests.Session()
    session.headers.update(_headers())

    started = _time.time()
    rows = _fetch_all_holders(session)
    elapsed = _time.time() - started

    fetched_at = datetime.now(timezone.utc)
    date_str = fetched_at.strftime("%Y-%m-%d")
    snapshot = {
        "date": date_str,
        "fetched_at_utc": fetched_at.isoformat(),
        "holder_count": len(rows),
        "holders": rows,
    }

    store = load_json(HOLDERS_STORE, {"snapshots": []})
    if not isinstance(store, dict) or "snapshots" not in store:
        store = {"snapshots": []}
    store["snapshots"] = [s for s in store["snapshots"] if s.get("date") != date_str]
    store["snapshots"].append(snapshot)
    store["snapshots"].sort(key=lambda s: s["date"])
    if len(store["snapshots"]) > SNAPSHOT_RETENTION:
        store["snapshots"] = store["snapshots"][-SNAPSHOT_RETENTION:]
    save_json(HOLDERS_STORE, store)

    logger.info(
        "Holders snapshot: %d rows in %.1fs (retained %d snapshots)",
        len(rows), elapsed, len(store["snapshots"])
    )
    return {
        "skipped": False,
        "date": date_str,
        "holder_count": len(rows),
        "elapsed_s": round(elapsed, 2),
        "snapshots_retained": len(store["snapshots"]),
        "path": str(HOLDERS_STORE),
    }


def _key(h: dict[str, Any]) -> str:
    return f"{h.get('hotkey') or ''}|{h.get('coldkey') or ''}"


def _diff_snapshots(today: dict[str, Any], prior: dict[str, Any] | None) -> list[dict[str, Any]]:
    today_map = {_key(h): h for h in today.get("holders", [])}
    prior_map = {_key(h): h for h in (prior or {}).get("holders", [])} if prior else {}

    house = house_set()
    out: list[dict[str, Any]] = []
    keys = set(today_map.keys()) | set(prior_map.keys())
    for k in keys:
        t = today_map.get(k)
        p = prior_map.get(k)
        balance_now = _to_int((t or {}).get("balance_rao"))
        balance_prev = _to_int((p or {}).get("balance_rao"))
        if balance_now == 0 and balance_prev == 0:
            continue
        delta_rao = balance_now - balance_prev
        balance_as_tao_now = _to_int((t or {}).get("balance_as_tao_rao"))
        balance_as_tao_prev = _to_int((p or {}).get("balance_as_tao_rao"))
        hotkey = (t or p or {}).get("hotkey")
        coldkey = (t or p or {}).get("coldkey")
        out.append(
            {
                "hotkey": hotkey,
                "hotkey_name": (t or p or {}).get("hotkey_name"),
                "coldkey": coldkey,
                "is_house": is_house(coldkey, hotkey, house=house),
                "alpha_now": balance_now / RAO_PER_TAO,
                "alpha_prev": balance_prev / RAO_PER_TAO,
                "alpha_delta": delta_rao / RAO_PER_TAO,
                "alpha_as_tao_now": balance_as_tao_now / RAO_PER_TAO,
                "alpha_as_tao_delta": (balance_as_tao_now - balance_as_tao_prev) / RAO_PER_TAO,
                "subnet_rank": (t or p or {}).get("subnet_rank"),
                "is_new": p is None,
                "is_exited": t is None,
            }
        )
    return out


def get_movement(limit: int = 50) -> dict[str, Any]:
    """Top movers (by abs alpha delta) over the last 24h."""
    store = load_json(HOLDERS_STORE, {"snapshots": []})
    snapshots = (store or {}).get("snapshots") or []
    if not snapshots:
        return {"error": "No holder snapshots yet — POST /api/holders/sync"}
    today = snapshots[-1]
    prior = snapshots[-2] if len(snapshots) >= 2 else None

    diff = _diff_snapshots(today, prior)
    diff.sort(key=lambda r: abs(r["alpha_delta"]), reverse=True)
    movers = diff[: max(1, min(limit, 200))]

    inflows_alpha = sum(r["alpha_delta"] for r in diff if r["alpha_delta"] > 0)
    outflows_alpha = sum(-r["alpha_delta"] for r in diff if r["alpha_delta"] < 0)
    house_inflows_alpha = sum(
        r["alpha_delta"] for r in diff if r["alpha_delta"] > 0 and r.get("is_house")
    )
    house_outflows_alpha = sum(
        -r["alpha_delta"] for r in diff if r["alpha_delta"] < 0 and r.get("is_house")
    )
    new_positions = sum(1 for r in diff if r["is_new"])
    exited_positions = sum(1 for r in diff if r["is_exited"])

    return {
        "today_date": today.get("date"),
        "prior_date": (prior or {}).get("date"),
        "today_holder_count": today.get("holder_count"),
        "prior_holder_count": (prior or {}).get("holder_count"),
        "new_positions": new_positions,
        "exited_positions": exited_positions,
        "inflows_alpha": round(inflows_alpha, 6),
        "outflows_alpha": round(outflows_alpha, 6),
        "house_inflows_alpha": round(house_inflows_alpha, 6),
        "house_outflows_alpha": round(house_outflows_alpha, 6),
        "other_inflows_alpha": round(inflows_alpha - house_inflows_alpha, 6),
        "other_outflows_alpha": round(outflows_alpha - house_outflows_alpha, 6),
        "movers": movers,
    }


def get_our_movement(coldkey: str | None = None) -> dict[str, Any]:
    """Snapshot timeline filtered to our owner coldkey across stored snapshots."""
    if not coldkey:
        coldkey = (os.environ.get("TAOSTATS_OWNER_ID") or "").strip() or None
    if not coldkey:
        return {"error": "TAOSTATS_OWNER_ID not configured"}
    store = load_json(HOLDERS_STORE, {"snapshots": []})
    snapshots = (store or {}).get("snapshots") or []
    series: list[dict[str, Any]] = []
    for snap in snapshots:
        ours = [h for h in snap.get("holders", []) if h.get("coldkey") == coldkey]
        total_alpha = sum(_to_int(h.get("balance_rao")) for h in ours) / RAO_PER_TAO
        total_as_tao = sum(_to_int(h.get("balance_as_tao_rao")) for h in ours) / RAO_PER_TAO
        series.append(
            {
                "date": snap.get("date"),
                "alpha": round(total_alpha, 6),
                "alpha_as_tao": round(total_as_tao, 6),
                "positions": len(ours),
                "by_hotkey": [
                    {
                        "hotkey": h.get("hotkey"),
                        "hotkey_name": h.get("hotkey_name"),
                        "alpha": _to_int(h.get("balance_rao")) / RAO_PER_TAO,
                        "alpha_as_tao": _to_int(h.get("balance_as_tao_rao")) / RAO_PER_TAO,
                    }
                    for h in ours
                ],
            }
        )
    return {
        "coldkey": coldkey,
        "snapshots": series,
        "latest": series[-1] if series else None,
        "delta_24h_alpha": (
            round(series[-1]["alpha"] - series[-2]["alpha"], 6)
            if len(series) >= 2 else None
        ),
        "delta_24h_alpha_as_tao": (
            round(series[-1]["alpha_as_tao"] - series[-2]["alpha_as_tao"], 6)
            if len(series) >= 2 else None
        ),
    }
