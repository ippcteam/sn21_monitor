"""
Current wallet balances for our owner, miner, and validator coldkeys.

Alpha is SN21 stake sitting on the coldkey. TAO and USD are the full wallet
(free TAO plus every stake, already marked to TAO by Taostats). A wallet's
balance lives on the coldkey, so the validator row is that hotkey's coldkey,
not the nominators staked onto it.

Storage: data/wallet_balances.json
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

import requests

from collector import load_json, save_json
from config import DATA_DIR
from labels import DEFAULT_HOUSE_KEYS
from stake_watch import OUR_VALIDATOR_HOTKEY, OWNER_SHARE_COLDKEY
from taostats_sync import _api_key, _headers, fetch_owner_balance
from taostats_v1 import PATH_METAGRAPH

logger = logging.getLogger(__name__)

WALLET_BALANCES_STORE = DATA_DIR / "wallet_balances.json"
NETUID = int(os.environ.get("SN21_NETUID", "21"))

TAOSTATS_API_BASE = os.environ.get("TAOSTATS_API_BASE", "https://api.taostats.io").rstrip("/")
METAGRAPH_LATEST_PATH = PATH_METAGRAPH


def _short(addr: str | None, head: int = 8, tail: int = 4) -> str | None:
    if not addr:
        return None
    return f"{addr[:head]}…{addr[-tail:]}" if len(addr) > head + tail + 1 else addr


def _ss58(v: Any) -> str | None:
    if isinstance(v, dict):
        return v.get("ss58")
    if isinstance(v, str) and v:
        return v
    return None


def miner_coldkeys() -> list[tuple[str, str]]:
    """(coldkey, note) for the in-house miner wallets, in label order."""
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for kind, ss58, note in DEFAULT_HOUSE_KEYS:
        if kind != "coldkey" or ss58 in seen:
            continue
        seen.add(ss58)
        out.append((ss58, note))
    return out


def validator_coldkey_from_records(
    neurons_rows: list[dict] | None,
    weights_validators: list[dict] | None,
    hotkey: str = OUR_VALIDATOR_HOTKEY,
) -> str | None:
    """Coldkey that registered our validator hotkey, from stored snapshots."""
    for row in reversed(neurons_rows or []):
        if row.get("hotkey") == hotkey and row.get("coldkey"):
            return row["coldkey"]
    for row in weights_validators or []:
        if row.get("hotkey") == hotkey and row.get("coldkey"):
            return row["coldkey"]
    return None


def resolve_validator_coldkey() -> str | None:
    """Env, then the latest neurons-daily row, then the weights scan."""
    env = (os.environ.get("OUR_VALIDATOR_COLDKEY") or "").strip()
    if env:
        return env
    from neurons_daily_sync import NEURONS_DAILY_STORE
    from weights_scan import SCAN_STORE

    daily = load_json(NEURONS_DAILY_STORE, {})
    rows = daily.get("rows") if isinstance(daily, dict) else None
    scan = load_json(SCAN_STORE, {})
    validators = scan.get("validators") if isinstance(scan, dict) else None
    return validator_coldkey_from_records(rows, validators)


def lookup_validator_coldkey(hotkey: str = OUR_VALIDATOR_HOTKEY) -> str | None:
    """
    One Taostats metagraph read filtered by hotkey.

    The filter is not guaranteed, so a row is accepted only when its hotkey
    matches. Anything else is ignored.
    """
    if not _api_key():
        return None
    session = requests.Session()
    session.headers.update(_headers())
    try:
        r = session.get(
            f"{TAOSTATS_API_BASE}{METAGRAPH_LATEST_PATH}",
            params={"netuid": NETUID, "hotkey": hotkey, "limit": 5},
            timeout=60,
        )
        r.raise_for_status()
        rows = (r.json() or {}).get("data") or []
    except Exception as e:
        logger.warning("Validator coldkey lookup failed: %s", e)
        return None
    for row in rows:
        if _ss58(row.get("hotkey")) == hotkey:
            return _ss58(row.get("coldkey"))
    return None


def wallet_targets(validator_coldkey: str | None) -> list[dict[str, Any]]:
    """Owner coldkey, each miner coldkey, then the validator coldkey."""
    targets: list[dict[str, Any]] = [
        {
            "role": "owner",
            "label": "Owner",
            "coldkey": OWNER_SHARE_COLDKEY,
            "detail": "owner-share coldkey",
        }
    ]
    for coldkey, note in miner_coldkeys():
        targets.append({
            "role": "miner",
            "label": "Miner",
            "coldkey": coldkey,
            "detail": note,
        })
    targets.append({
        "role": "validator",
        "label": "Validator",
        "coldkey": validator_coldkey,
        "hotkey": OUR_VALIDATOR_HOTKEY,
        "detail": "validator coldkey" if validator_coldkey else "coldkey not on file",
    })
    return targets


def summarise_balance(raw: dict[str, Any] | None, tao_usd: float | None) -> dict[str, Any]:
    """SN21 alpha plus the full wallet in TAO and USD. None when the fetch failed."""
    if not raw:
        return {
            "sn21_alpha": None,
            "sn21_tao": None,
            "free_tao": None,
            "total_tao": None,
            "usd": None,
            "change_24h_pct": None,
            "sn21_positions": None,
            "block_number": None,
        }
    alpha = 0.0
    alpha_tao = 0.0
    positions = 0
    for ab in raw.get("alpha_balances") or []:
        try:
            netuid = int(ab.get("netuid"))
        except (TypeError, ValueError):
            continue
        if netuid != NETUID:
            continue
        positions += 1
        if ab.get("alpha") is not None:
            alpha += float(ab["alpha"])
        if ab.get("alpha_as_tao") is not None:
            alpha_tao += float(ab["alpha_as_tao"])
    total = raw.get("balance_total_tao")
    ago = raw.get("balance_total_24hr_ago_tao")
    pct = None
    if total is not None and ago:
        pct = round((float(total) - float(ago)) / float(ago) * 100, 2)
    usd = round(float(total) * tao_usd, 2) if (total is not None and tao_usd) else None
    return {
        "sn21_alpha": round(alpha, 6),
        "sn21_tao": round(alpha_tao, 6),
        "free_tao": raw.get("balance_free_tao"),
        "total_tao": total,
        "usd": usd,
        "change_24h_pct": pct,
        "sn21_positions": positions,
        "block_number": raw.get("block_number"),
    }


def _blank_figures() -> dict[str, Any]:
    return summarise_balance(None, None)


def _sum_figures(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Sum wallets that actually returned a balance. Skips failed fetches."""
    present = [r for r in rows if r.get("total_tao") is not None or r.get("sn21_alpha") is not None]
    if not present:
        out = _blank_figures()
        out["n"] = 0
        return out

    def _sum(key: str) -> float | None:
        vals = [r[key] for r in present if r.get(key) is not None]
        if not vals:
            return None
        return round(sum(vals), 6 if key != "usd" else 2)

    out = {
        "sn21_alpha": _sum("sn21_alpha"),
        "sn21_tao": _sum("sn21_tao"),
        "free_tao": _sum("free_tao"),
        "total_tao": _sum("total_tao"),
        "usd": _sum("usd"),
        "n": len(present),
    }
    return out


def _tao_usd(prior: dict[str, Any]) -> float | None:
    from taostats_sync import TAOSTATS_STORE, fetch_tao_usd

    price = fetch_tao_usd()
    if price is not None:
        return price
    if prior.get("tao_price_usd") is not None:
        return prior.get("tao_price_usd")
    stored = load_json(TAOSTATS_STORE, {})
    if isinstance(stored, dict) and stored.get("tao_price_usd") is not None:
        return stored.get("tao_price_usd")
    from neurons_daily_sync import _latest_subnet_prices

    return _latest_subnet_prices().get("tao_price_usd")


def build_wallet_balances(
    *,
    fetch_balance=None,
    validator_coldkey: str | None = None,
    lookup_coldkey: bool = True,
) -> dict[str, Any]:
    """
    Fetch each coldkey and write the snapshot.

    A failed fetch keeps that coldkey's previous figures so one rate-limit
    does not blank the row.
    """
    prior = load_json(WALLET_BALANCES_STORE, {})
    if not isinstance(prior, dict):
        prior = {}
    prior_by_key = {
        (w.get("role"), w.get("coldkey")): w
        for w in (prior.get("wallets") or [])
        if w.get("coldkey")
    }

    if not _api_key():
        if prior.get("wallets"):
            prior["stale"] = True
            return prior
        return {"error": "TAOSTATS_API_KEY not set"}

    ck = validator_coldkey if validator_coldkey is not None else resolve_validator_coldkey()
    if not ck and lookup_coldkey:
        ck = lookup_validator_coldkey()

    fetch = fetch_balance or fetch_owner_balance
    tao_usd = _tao_usd(prior)
    now = datetime.now(timezone.utc).isoformat()
    wallets: list[dict[str, Any]] = []

    for target in wallet_targets(ck):
        coldkey = target.get("coldkey")
        row: dict[str, Any] = {
            "role": target["role"],
            "label": target["label"],
            "detail": target.get("detail"),
            "coldkey": coldkey,
            "coldkey_short": _short(coldkey),
            "hotkey": target.get("hotkey"),
            "fetched_at_utc": now,
            "stale": False,
            "error": None,
        }
        if not coldkey:
            row["error"] = "validator coldkey unknown"
            row.update(_blank_figures())
            wallets.append(row)
            continue
        raw = None
        try:
            raw = fetch(coldkey)
        except Exception as e:
            logger.warning("Balance fetch failed for %s: %s", coldkey[:12], e)
            row["error"] = str(e)
        figures = summarise_balance(raw, tao_usd)
        if figures["total_tao"] is None:
            previous = prior_by_key.get((target["role"], coldkey))
            if previous and previous.get("total_tao") is not None:
                for key in (
                    "sn21_alpha", "sn21_tao", "free_tao", "total_tao", "usd",
                    "change_24h_pct", "sn21_positions", "block_number",
                ):
                    figures[key] = previous.get(key)
                row["stale"] = True
                row["fetched_at_utc"] = previous.get("fetched_at_utc")
                row["error"] = row["error"] or "fetch failed; showing last balance"
            elif row["error"] is None:
                row["error"] = "no balance returned"
        row.update(figures)
        wallets.append(row)

    by_role = {
        role: _sum_figures([w for w in wallets if w["role"] == role])
        for role in ("owner", "miner", "validator")
    }
    seen: set[str] = set()
    unique = []
    for w in wallets:
        ck_ = w.get("coldkey")
        if not ck_ or ck_ in seen:
            continue
        if w.get("total_tao") is None and w.get("sn21_alpha") is None:
            continue
        seen.add(ck_)
        unique.append(w)

    snapshot = {
        "fetched_at_utc": now,
        "tao_price_usd": tao_usd,
        "netuid": NETUID,
        "validator_hotkey": OUR_VALIDATOR_HOTKEY,
        "wallets": wallets,
        "roles": by_role,
        "total": _sum_figures(unique),
    }
    save_json(WALLET_BALANCES_STORE, snapshot)
    logger.info(
        "Wallet balances: %d keys, total %.4f τ",
        snapshot["total"]["n"],
        snapshot["total"]["total_tao"] or 0.0,
    )
    return snapshot


def get_wallet_balances() -> dict[str, Any]:
    snap = load_json(WALLET_BALANCES_STORE, None)
    if not snap:
        return {"error": "No wallet balances yet — POST /api/wallets/balances/sync"}
    return snap
