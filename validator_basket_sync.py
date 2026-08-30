"""
SN21 validator-basket sync — which named network operators have SN21 α
staked to their hotkey.

Source: GET /api/dtao/validator/available/v1?netuid=21
Optional join: latest holders snapshot (nominator counts per hotkey).

This is the live dTAO basket (operators who accept SN21 stake), not a
Root Reborn allocation vector — that mechanism is not on mainnet.

Writes:
  data/validator_basket.json          — latest snapshot
  data/validator_basket_history.json  — one compact row/day, 90d
"""

from __future__ import annotations

import logging
import os
import time as _time
from datetime import datetime, timezone
from typing import Any

import requests

from collector import load_json, save_json
from config import DATA_DIR
from labels import house_set, is_house

logger = logging.getLogger(__name__)

TAOSTATS_API_BASE = os.environ.get("TAOSTATS_API_BASE", "https://api.taostats.io").rstrip("/")
AVAILABLE_PATH = "/api/dtao/validator/available/v1"
NETUID = int(os.environ.get("SN21_NETUID", "21"))
RAO_PER_TAO = 1_000_000_000
PAGE_SIZE = 200
MAX_429_RETRIES = 6
INTER_PAGE_SLEEP = 0.8

OUR_VALIDATOR_HOTKEY = (
    os.environ.get("OUR_VALIDATOR_HOTKEY")
    or "5GuiHBTfciFauoF1XuyvVuWYrQaS7LExrbsqV5EmDU2ibJEz"
).strip()

BASKET_STORE = DATA_DIR / "validator_basket.json"
BASKET_HISTORY_STORE = DATA_DIR / "validator_basket_history.json"
HISTORY_RETENTION_DAYS = 90


def _api_key() -> str | None:
    return (os.environ.get("TAOSTATS_API_KEY") or "").strip() or None


def _headers() -> dict[str, str]:
    key = _api_key()
    return {"Authorization": key, "Accept": "application/json"} if key else {}


def _ss58(v: Any) -> str | None:
    if isinstance(v, dict):
        return v.get("ss58") or None
    if isinstance(v, str) and v.strip():
        return v.strip()
    return None


def _short(addr: str | None, head: int = 8, tail: int = 4) -> str | None:
    if not addr:
        return None
    return f"{addr[:head]}…{addr[-tail:]}" if len(addr) > head + tail + 1 else addr


def _rao_to_alpha(v: Any) -> float:
    if v is None or v == "":
        return 0.0
    try:
        return int(v) / RAO_PER_TAO
    except (TypeError, ValueError):
        try:
            return float(v) / RAO_PER_TAO
        except (TypeError, ValueError):
            return 0.0


def _display_name(name: str | None, hotkey: str | None) -> str:
    cleaned = (name or "").strip()
    return cleaned or (_short(hotkey) or "unnamed")


def parse_available_row(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Normalise one Taostats `validator/available` row. None if no hotkey."""
    hotkey = _ss58(raw.get("address")) or _ss58(raw.get("hotkey"))
    if not hotkey:
        return None
    name = raw.get("name")
    if isinstance(name, str):
        name = name.strip() or None
    else:
        name = None
    return {
        "hotkey": hotkey,
        "hotkey_short": _short(hotkey),
        "name": name,
        "is_named": bool(name),
        "alpha": round(_rao_to_alpha(raw.get("hotkey_alpha")), 6),
    }


def index_holders_by_hotkey(holders: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Collapse a holders snapshot onto per-hotkey nominator counts."""
    out: dict[str, dict[str, Any]] = {}
    for h in holders:
        hk = h.get("hotkey")
        if not hk:
            continue
        rec = out.get(hk)
        if rec is None:
            rec = out[hk] = {"nominators": 0, "holder_alpha": 0.0}
        rec["nominators"] += 1
        try:
            rec["holder_alpha"] += int(h.get("balance_rao") or 0) / RAO_PER_TAO
        except (TypeError, ValueError):
            pass
    for rec in out.values():
        rec["holder_alpha"] = round(rec["holder_alpha"], 6)
    return out


def _load_holders_index() -> dict[str, dict[str, Any]]:
    try:
        from holders_sync import HOLDERS_STORE
    except Exception:
        return {}
    store = load_json(HOLDERS_STORE, {"snapshots": []})
    snaps = (store or {}).get("snapshots") or []
    if not snaps:
        return {}
    return index_holders_by_hotkey(snaps[-1].get("holders") or [])


def annotate(
    rows: list[dict[str, Any]],
    holders_by_hotkey: dict[str, dict[str, Any]] | None = None,
    house: set[str] | None = None,
    our_hotkey: str = OUR_VALIDATOR_HOTKEY,
) -> list[dict[str, Any]]:
    """Add house/ours flags, nominator counts, and share of SN21 basket α."""
    house = house if house is not None else house_set()
    holders_by_hotkey = holders_by_hotkey or {}
    total = sum(r["alpha"] for r in rows)
    out: list[dict[str, Any]] = []
    for r in rows:
        hk = r["hotkey"]
        hold = holders_by_hotkey.get(hk) or {}
        nominators = hold.get("nominators")
        out.append(
            {
                **r,
                "share_pct": round(100.0 * r["alpha"] / total, 4) if total else 0.0,
                "nominators": nominators if nominators is not None else None,
                "is_house": is_house(None, hk, house=house),
                "is_ours": hk == our_hotkey,
                "is_new": False,
                "is_exited": False,
                "alpha_delta": None,
            }
        )
    out.sort(key=lambda r: (-r["alpha"], r.get("name") or r["hotkey"]))
    return out


def diff_baskets(
    today: list[dict[str, Any]],
    prior: list[dict[str, Any]] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (annotated today, entered, exited). Prior may be None on first run."""
    prior_map = {r["hotkey"]: r for r in (prior or []) if r.get("hotkey")}
    today_keys = {r["hotkey"] for r in today}
    annotated: list[dict[str, Any]] = []
    entered: list[dict[str, Any]] = []
    for r in today:
        prev = prior_map.get(r["hotkey"])
        row = dict(r)
        if prior is not None and prev is None:
            row["is_new"] = True
            row["alpha_delta"] = round(row["alpha"], 6)
            entered.append(row)
        elif prev is not None:
            row["alpha_delta"] = round(row["alpha"] - float(prev.get("alpha") or 0.0), 6)
        annotated.append(row)

    exited: list[dict[str, Any]] = []
    if prior is not None:
        for prev in prior:
            if prev.get("hotkey") in today_keys:
                continue
            gone = dict(prev)
            gone["is_exited"] = True
            gone["is_new"] = False
            gone["alpha_delta"] = round(-float(prev.get("alpha") or 0.0), 6)
            exited.append(gone)
        exited.sort(key=lambda r: (-abs(r.get("alpha") or 0.0), r.get("name") or r.get("hotkey") or ""))
    return annotated, entered, exited


def summarise(
    validators: list[dict[str, Any]],
    entered: list[dict[str, Any]],
    exited: list[dict[str, Any]],
) -> dict[str, Any]:
    named = [v for v in validators if v.get("is_named")]
    return {
        "validator_count": len(validators),
        "named_count": len(named),
        "unnamed_count": len(validators) - len(named),
        "house_count": sum(1 for v in validators if v.get("is_house")),
        "total_alpha": round(sum(v["alpha"] for v in validators), 6),
        "named_alpha": round(sum(v["alpha"] for v in named), 6),
        "entered_count": len(entered),
        "exited_count": len(exited),
        "entered_names": [_display_name(v.get("name"), v.get("hotkey")) for v in entered],
        "exited_names": [_display_name(v.get("name"), v.get("hotkey")) for v in exited],
    }


def history_row(date_str: str, summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "date": date_str,
        "validator_count": summary["validator_count"],
        "named_count": summary["named_count"],
        "unnamed_count": summary["unnamed_count"],
        "total_alpha": summary["total_alpha"],
        "named_alpha": summary["named_alpha"],
        "entered": summary["entered_names"],
        "exited": summary["exited_names"],
    }


def build_snapshot(
    raw_rows: list[dict[str, Any]],
    *,
    holders_by_hotkey: dict[str, dict[str, Any]] | None = None,
    prior_validators: list[dict[str, Any]] | None = None,
    fetched_at: datetime | None = None,
    house: set[str] | None = None,
    our_hotkey: str = OUR_VALIDATOR_HOTKEY,
    holders_joined: bool = False,
) -> dict[str, Any]:
    """Pure snapshot builder — used by the sync and by tests."""
    parsed = [p for p in (parse_available_row(r) for r in raw_rows) if p]
    # Dedup by hotkey, keep the larger α if Taostats repeats a row.
    by_hk: dict[str, dict[str, Any]] = {}
    for p in parsed:
        prev = by_hk.get(p["hotkey"])
        if prev is None or p["alpha"] > prev["alpha"]:
            by_hk[p["hotkey"]] = p
    annotated = annotate(
        list(by_hk.values()),
        holders_by_hotkey=holders_by_hotkey,
        house=house,
        our_hotkey=our_hotkey,
    )
    validators, entered, exited = diff_baskets(annotated, prior_validators)
    summary = summarise(validators, entered, exited)
    now = fetched_at or datetime.now(timezone.utc)
    return {
        "date": now.strftime("%Y-%m-%d"),
        "fetched_at_utc": now.isoformat(),
        "source": "taostats",
        "api": {"base": TAOSTATS_API_BASE, "path": AVAILABLE_PATH, "netuid": NETUID},
        "holders_joined": holders_joined,
        "summary": summary,
        "validators": validators,
        "entered": entered,
        "exited": exited,
    }


def _fetch_available(session: requests.Session) -> list[dict[str, Any]]:
    url = f"{TAOSTATS_API_BASE}{AVAILABLE_PATH}"
    rows: list[dict[str, Any]] = []
    page = 1
    while True:
        params = {"netuid": NETUID, "limit": PAGE_SIZE, "page": page}
        body: dict[str, Any] | None = None
        for attempt in range(MAX_429_RETRIES):
            r = session.get(url, params=params, timeout=60)
            if r.status_code == 429:
                wait = min(2 ** attempt + 1.0, 30)
                logger.warning("Basket sync 429 on page %s; retry in %.1fs", page, wait)
                _time.sleep(wait)
                continue
            r.raise_for_status()
            body = r.json()
            break
        if body is None:
            r = session.get(url, params=params, timeout=60)
            r.raise_for_status()
            body = r.json()
        chunk = body.get("data") or []
        rows.extend(chunk)
        pag = body.get("pagination") or {}
        next_page = pag.get("next_page")
        total_pages = pag.get("total_pages") or 0
        if not chunk or not next_page or page >= total_pages:
            break
        page = int(next_page)
        if page > 20:
            break
        _time.sleep(INTER_PAGE_SLEEP)
    return rows


def _prior_validators() -> list[dict[str, Any]] | None:
    stored = load_json(BASKET_STORE, None)
    if isinstance(stored, dict) and stored.get("validators"):
        return list(stored["validators"])
    return None


def _write_history(date_str: str, summary: dict[str, Any]) -> int:
    hist = load_json(BASKET_HISTORY_STORE, [])
    if not isinstance(hist, list):
        hist = []
    hist = [r for r in hist if r.get("date") != date_str]
    hist.append(history_row(date_str, summary))
    hist.sort(key=lambda r: r.get("date") or "")
    if len(hist) > HISTORY_RETENTION_DAYS:
        hist = hist[-HISTORY_RETENTION_DAYS:]
    save_json(BASKET_HISTORY_STORE, hist)
    return len(hist)


def run_sync() -> dict[str, Any]:
    """Pull the SN21 validator basket and persist latest + today's history row."""
    if not _api_key():
        logger.warning("Basket sync skipped: TAOSTATS_API_KEY not set")
        return {"skipped": True, "reason": "missing TAOSTATS_API_KEY"}

    session = requests.Session()
    session.headers.update(_headers())
    raw = _fetch_available(session)
    holders_index = _load_holders_index()
    snapshot = build_snapshot(
        raw,
        holders_by_hotkey=holders_index,
        prior_validators=_prior_validators(),
        holders_joined=bool(holders_index),
    )
    save_json(BASKET_STORE, snapshot)
    retained = _write_history(snapshot["date"], snapshot["summary"])
    logger.info(
        "Basket sync: %d validators (%d named) on SN21; entered=%s exited=%s",
        snapshot["summary"]["validator_count"],
        snapshot["summary"]["named_count"],
        snapshot["summary"]["entered_count"],
        snapshot["summary"]["exited_count"],
    )
    return {
        "skipped": False,
        "date": snapshot["date"],
        "validator_count": snapshot["summary"]["validator_count"],
        "named_count": snapshot["summary"]["named_count"],
        "entered_count": snapshot["summary"]["entered_count"],
        "exited_count": snapshot["summary"]["exited_count"],
        "holders_joined": snapshot["holders_joined"],
        "history_rows": retained,
        "path": str(BASKET_STORE),
    }


def latest() -> dict[str, Any] | None:
    stored = load_json(BASKET_STORE, None)
    return stored if isinstance(stored, dict) else None


def history(days: int = 30) -> list[dict[str, Any]]:
    hist = load_json(BASKET_HISTORY_STORE, [])
    if not isinstance(hist, list):
        return []
    return hist[-max(1, min(days, HISTORY_RETENTION_DAYS)):]
