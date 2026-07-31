"""
SN21 validator weight-copy scanner — direct finney chain read.

Reads every validator's published weight vector straight from the chain
(`subtensor.weights(netuid=21)`), joins the metagraph (stake, vTrust, last
weight-set age, hot/coldkeys) and answers three questions the Taostats-driven
views can't:

  1. Burn status     — are validators assigning 100% to the subnet-owner UID
                       (no real miner scoring)? Who, and what fraction?
  2. Copy detection  — once validators publish differentiated vectors, which
                       ones track another validator's vector (copying) vs score
                       independently? Pairwise cosine similarity + source guess.
  3. Our position    — UID 64 (our validator): scoring breadth, vTrust, and the
                       full coldkey→stake wallet breakdown behind its hotkey,
                       cross-checked against on-chain TotalHotkeyAlpha.

Writes:
  data/weights_scan.json          — latest scan.
  data/weights_scan_history.json  — daily rows, 90d retention.
  data/validator_names.json       — hotkey→operator-name cache (Taostats).

Direct-chain like collector.py / backfill_chain.py; reuses the same SSL fix so
WebSocket verification works on minimal Render images.
"""

from __future__ import annotations

import logging
import math
import os
import threading
import time as _time
from datetime import datetime, timezone
from typing import Any

import requests

from collector import load_json, save_json, _configure_chain_ssl
from config import DATA_DIR
from labels import house_set, is_house

logger = logging.getLogger(__name__)

NETUID = 21
NETWORK = os.environ.get("SN21_WEIGHTS_NETWORK", "finney")
RAO_PER_TAO = 1_000_000_000

# Our validator. Derived from the chain where possible; env-overridable.
OUR_VALIDATOR_UID = int(os.environ.get("OUR_VALIDATOR_UID", "64"))
OUR_VALIDATOR_HOTKEY = (
    os.environ.get("OUR_VALIDATOR_HOTKEY")
    or "5GuiHBTfciFauoF1XuyvVuWYrQaS7LExrbsqV5EmDU2ibJEz"
)

SCAN_STORE = DATA_DIR / "weights_scan.json"
SCAN_HISTORY_STORE = DATA_DIR / "weights_scan_history.json"
NAMES_STORE = DATA_DIR / "validator_names.json"
HISTORY_RETENTION_DAYS = 90

# A validator counts as "burning" when ≥ this share of its weight sits on the
# owner UID. Burn-mode for the subnet when ≥ BURN_SUBNET_FRACTION of setters burn.
BURN_TARGET_SHARE = 0.98
BURN_SUBNET_FRACTION = 0.80

# Copy-verdict cosine thresholds (only meaningful once vectors differentiate).
COS_IDENTICAL = 0.999
COS_NEAR = 0.97
COS_SIMILAR = 0.85

# Taostats name enrichment.
TAOSTATS_API_BASE = os.environ.get("TAOSTATS_API_BASE", "https://api.taostats.io").rstrip("/")
STAKE_BALANCE_PATH = "/api/dtao/stake_balance/latest/v1"
NAME_TTL_SECONDS = 7 * 24 * 3600
NAME_MISS_TTL_SECONDS = 24 * 3600  # retry nameless/transient-miss hotkeys sooner
NAME_FETCH_SLEEP = 1.5
MAX_429_RETRIES = 6

CACHE_TTL_SECONDS = 60
_cache_lock = threading.Lock()
_cache: dict[str, Any] = {"fetched_at": 0.0, "payload": None}
_scan_lock = threading.Lock()


# ── small helpers ───────────────────────────────────────────────────────────


def _api_key() -> str | None:
    return (os.environ.get("TAOSTATS_API_KEY") or "").strip() or None


def _short(addr: str | None, head: int = 8, tail: int = 4) -> str | None:
    if not addr:
        return None
    return f"{addr[:head]}…{addr[-tail:]}" if len(addr) > head + tail + 1 else addr


def _ss58(v: Any) -> str | None:
    return v.get("ss58") if isinstance(v, dict) else v


def _cosine(a: list[float], b: list[float]) -> float:
    dot = na = nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    return dot / math.sqrt(na * nb)


# ── validator name cache (Taostats hotkey_name) ─────────────────────────────


def _load_names() -> dict[str, Any]:
    store = load_json(NAMES_STORE, {})
    return store if isinstance(store, dict) else {}


def _fetch_hotkey_name(session: requests.Session, hotkey: str) -> str | None:
    """One Taostats stake_balance read for a hotkey → its operator name."""
    url = f"{TAOSTATS_API_BASE}{STAKE_BALANCE_PATH}"
    params = {"netuid": NETUID, "hotkey": hotkey, "limit": 1, "order": "balance_desc"}
    for attempt in range(MAX_429_RETRIES):
        r = session.get(url, params=params, timeout=60)
        if r.status_code == 429:
            _time.sleep(min(2 ** attempt + 1.0, 30))
            continue
        if r.status_code != 200:
            return None
        data = r.json().get("data") or []
        if not data:
            return None
        return (data[0].get("hotkey_name") or "").strip() or None
    return None


def _resolve_names(hotkeys: list[str]) -> dict[str, str | None]:
    """Return hotkey→name, fetching only stale/missing ones from Taostats."""
    cache = _load_names()
    now = _time.time()
    out: dict[str, str | None] = {}
    stale = []
    for hk in hotkeys:
        rec = cache.get(hk)
        ttl = NAME_TTL_SECONDS if (rec and rec.get("name")) else NAME_MISS_TTL_SECONDS
        if rec and (now - rec.get("fetched_at", 0)) < ttl:
            out[hk] = rec.get("name")
        else:
            stale.append(hk)

    if stale and _api_key():
        session = requests.Session()
        session.headers.update({"Authorization": _api_key(), "Accept": "application/json"})
        for hk in stale:
            try:
                name = _fetch_hotkey_name(session, hk)
            except Exception:
                logger.exception("Name lookup failed for %s", hk)
                name = None
            cache[hk] = {"name": name, "fetched_at": now}
            out[hk] = name
            _time.sleep(NAME_FETCH_SLEEP)
        save_json(NAMES_STORE, cache)
    else:
        for hk in stale:
            out[hk] = (cache.get(hk) or {}).get("name")

    return out


# ── chain access ────────────────────────────────────────────────────────────


def _connect():
    from chain_compat import fetch_metagraph, get_subtensor

    st = get_subtensor(NETWORK)                 # bittensor 11 client
    mg = fetch_metagraph(NETUID, network=NETWORK, st=st)
    return st, mg


def _owner_uid(st, mg) -> tuple[int | None, str | None, str | None]:
    """(uid, hotkey, coldkey) of the subnet-owner hotkey, the burn target.
    The v11 metagraph carries both owner keys directly."""
    owner_hk = mg.owner_hotkey or None
    owner_ck = mg.owner_coldkey or None
    uid = None
    if owner_hk:
        for i, hk in enumerate(mg.hotkeys):
            if hk == owner_hk:
                uid = i
                break
    return uid, owner_hk, owner_ck


# ── core scan ───────────────────────────────────────────────────────────────


def run_scan() -> dict[str, Any]:
    """Read all validator weight vectors from chain and analyse copy/burn state."""
    with _scan_lock:
        st, mg = _connect()
        block = int(mg.block)
        n = len(mg.uids)

        owner_uid, owner_hk, owner_ck = _owner_uid(st, mg)

        # Our validator's on-chain coldkey — lets us recognise the owner UID as
        # ours even when its key isn't House-labelled (SubnetOwner == UID 64 ck).
        our_coldkey = None
        if 0 <= OUR_VALIDATOR_UID < n and mg.hotkeys[OUR_VALIDATOR_UID] == OUR_VALIDATOR_HOTKEY:
            our_coldkey = mg.coldkeys[OUR_VALIDATOR_UID]
        else:
            for i, hk in enumerate(mg.hotkeys):
                if hk == OUR_VALIDATOR_HOTKEY:
                    our_coldkey = mg.coldkeys[i]
                    break

        # Raw weight vectors, normalised to sum 1. bittensor 11 returns
        # {setter_uid: {target_uid: normalized_float}} (already 0..1 floats;
        # renormalise anyway so the invariant never depends on SDK behavior).
        raw = st.weights.weights(NETUID)
        vectors: dict[int, list[float]] = {}
        scored_counts: dict[int, int] = {}
        for uid, pairs in (raw or {}).items():
            v = [0.0] * n
            for t, w in dict(pairs).items():
                t = int(t)
                if 0 <= t < n:
                    v[t] = float(w)
            s = sum(v)
            if s > 0:
                v = [x / s for x in v]
            vectors[int(uid)] = v
            scored_counts[int(uid)] = sum(1 for x in v if x > 0)

        permit_uids = [i for i in range(n) if bool(mg.validator_permit[i])]
        setters = [u for u in permit_uids if u in vectors and scored_counts.get(u, 0) > 0]

        # Stake-weighted consensus vector across setters.
        consensus = [0.0] * n
        stake_by_uid = {u: float(mg.S[u]) for u in setters}
        stake_sum = sum(stake_by_uid.values()) or 1.0
        for u in setters:
            w = stake_by_uid[u]
            vec = vectors[u]
            for i in range(n):
                consensus[i] += w * vec[i]
        cs = sum(consensus) or 1.0
        consensus = [x / cs for x in consensus]

        # Burn detection: weight concentrated on the owner UID.
        def is_burning(u: int) -> bool:
            if owner_uid is None:
                return False
            return vectors[u][owner_uid] >= BURN_TARGET_SHARE

        n_burning = sum(1 for u in setters if is_burning(u))
        burn_fraction = round(n_burning / len(setters), 4) if setters else 0.0
        burn_mode = bool(setters) and burn_fraction >= BURN_SUBNET_FRACTION

        # Resolve names for all permit-holders (only ~12), so non-setters like
        # the owner UID are labelled too. Cached after first sight.
        names = _resolve_names([mg.hotkeys[u] for u in permit_uids])
        house = house_set()
        total_permit_stake = sum(float(mg.S[u]) for u in permit_uids) or 1.0

        # Pairwise cosine among setters.
        sim = {a: {} for a in setters}
        for i, a in enumerate(setters):
            for b in setters[i:]:
                c = round(_cosine(vectors[a], vectors[b]), 6)
                sim[a][b] = c
                sim[b][a] = c

        def copy_for(u: int) -> dict[str, Any]:
            others = [o for o in setters if o != u]
            if not others:
                return {"verdict": "solo", "nearest_uid": None, "cosine": None, "source_uid": None}
            nearest = max(others, key=lambda o: sim[u][o])
            c = sim[u][nearest]
            if burn_mode and is_burning(u):
                verdict = "burn"  # identical one-hot → no real copy signal
            elif c >= COS_IDENTICAL:
                verdict = "identical→copy"
            elif c >= COS_NEAR:
                verdict = "near-copy"
            elif c >= COS_SIMILAR:
                verdict = "similar"
            else:
                verdict = "independent"
            # Source guess: among the cluster ≥ COS_NEAR, the highest-stake member.
            cluster = [o for o in others if sim[u][o] >= COS_NEAR]
            source = None
            if verdict in ("identical→copy", "near-copy") and cluster:
                cand = max(cluster + [u], key=lambda o: float(mg.S[o]))
                source = cand if cand != u else nearest
            return {
                "verdict": verdict,
                "nearest_uid": nearest,
                "nearest_name": names.get(mg.hotkeys[nearest]),
                "cosine": c,
                "source_uid": source,
                "source_name": names.get(mg.hotkeys[source]) if source is not None else None,
            }

        validators = []
        for u in permit_uids:
            hk = mg.hotkeys[u]
            ck = mg.coldkeys[u]
            set_wt = u in setters
            vec = vectors.get(u)
            top_target = top_share = None
            if vec and sum(vec) > 0:
                top_target = max(range(n), key=lambda i: vec[i])
                top_share = round(vec[top_target], 6)
            validators.append(
                {
                    "uid": u,
                    "name": names.get(hk),
                    "hotkey": hk,
                    "hotkey_short": _short(hk),
                    "coldkey": ck,
                    "coldkey_short": _short(ck),
                    "is_house": is_house(ck, hk, house=house),
                    "is_ours": (
                        u == OUR_VALIDATOR_UID
                        or hk == OUR_VALIDATOR_HOTKEY
                        or (bool(our_coldkey) and ck == our_coldkey)
                    ),
                    "is_owner_uid": u == owner_uid,
                    "stake_alpha": round(float(mg.S[u]), 4),
                    "stake_pct": round(100 * float(mg.S[u]) / total_permit_stake, 4),
                    "vtrust": round(float(mg.validator_trust[u]), 6),
                    "dividends": round(float(mg.dividends[u]), 6),
                    "sets_weights": set_wt,
                    "scored_miners": scored_counts.get(u, 0),
                    "top_target_uid": top_target,
                    "top_target_share": top_share,
                    "is_burning": is_burning(u) if set_wt else False,
                    "cos_to_consensus": round(_cosine(vec, consensus), 6) if (set_wt and vec) else None,
                    "weight_set_age_blocks": block - int(mg.last_update[u]),
                    "copy": copy_for(u) if set_wt else None,
                }
            )

        validators.sort(key=lambda v: (-v["stake_alpha"], v["uid"]))

        our = next((v for v in validators if v["is_ours"] and v["sets_weights"]), None) \
            or next((v for v in validators if v["is_ours"]), None)

        payload = {
            "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
            "block": block,
            "network": NETWORK,
            "owner": {
                "uid": owner_uid,
                "name": names.get(owner_hk) if owner_hk else None,
                "hotkey": owner_hk,
                "hotkey_short": _short(owner_hk),
                "coldkey": owner_ck,
                "coldkey_short": _short(owner_ck),
                "is_ours": (
                    (bool(our_coldkey) and owner_ck == our_coldkey)
                    or (bool(owner_ck) and is_house(owner_ck, owner_hk, house=house))
                ),
                "incentive": round(float(mg.I[owner_uid]), 6) if owner_uid is not None else None,
            },
            "burn": {
                "is_burn_mode": burn_mode,
                "target_uid": owner_uid,
                "n_setters": len(setters),
                "n_permits": len(permit_uids),
                "n_burning": n_burning,
                "burn_fraction": burn_fraction,
            },
            "our_validator": {
                "uid": our["uid"] if our else OUR_VALIDATOR_UID,
                "name": our["name"] if our else None,
                "stake_alpha": our["stake_alpha"] if our else None,
                "stake_pct": our["stake_pct"] if our else None,
                "vtrust": our["vtrust"] if our else None,
                "scored_miners": our["scored_miners"] if our else None,
                "is_burning": our["is_burning"] if our else None,
                "weight_set_age_blocks": our["weight_set_age_blocks"] if our else None,
            } if our or True else None,
            "totals": {
                "permits": len(permit_uids),
                "setters": len(setters),
                "non_setters": [u for u in permit_uids if u not in setters],
            },
            "similarity": {
                "uids": setters,
                "matrix": [[sim[a][b] for b in setters] for a in setters],
            },
            "validators": validators,
        }

        save_json(SCAN_STORE, payload)
        _append_history(payload)

        with _cache_lock:
            _cache["payload"] = payload
            _cache["fetched_at"] = _time.time()

        logger.info(
            "Weights scan @ block %s: %d permits, %d setters, burn_mode=%s (%d/%d burning)",
            block, len(permit_uids), len(setters), burn_mode, n_burning, len(setters),
        )
        return payload


def _append_history(payload: dict[str, Any]) -> None:
    """One compact row per UTC day; keep 90 days."""
    hist = load_json(SCAN_HISTORY_STORE, [])
    if not isinstance(hist, list):
        hist = []
    today = datetime.now(timezone.utc).date().isoformat()
    row = {
        "date": today,
        "block": payload["block"],
        "is_burn_mode": payload["burn"]["is_burn_mode"],
        "burn_fraction": payload["burn"]["burn_fraction"],
        "n_setters": payload["burn"]["n_setters"],
        "n_burning": payload["burn"]["n_burning"],
        "our_scored_miners": (payload.get("our_validator") or {}).get("scored_miners"),
        "our_is_burning": (payload.get("our_validator") or {}).get("is_burning"),
        "copiers": sum(
            1 for v in payload["validators"]
            if v.get("copy") and v["copy"].get("verdict") in ("identical→copy", "near-copy")
        ),
        "independents": sum(
            1 for v in payload["validators"]
            if v.get("copy") and v["copy"].get("verdict") == "independent"
        ),
    }
    hist = [r for r in hist if r.get("date") != today]
    hist.append(row)
    if len(hist) > HISTORY_RETENTION_DAYS:
        hist = hist[-HISTORY_RETENTION_DAYS:]
    save_json(SCAN_HISTORY_STORE, hist)


def latest_scan() -> dict[str, Any] | None:
    with _cache_lock:
        if _cache["payload"] and (_time.time() - _cache["fetched_at"]) < CACHE_TTL_SECONDS:
            return _cache["payload"]
    stored = load_json(SCAN_STORE, None)
    return stored if isinstance(stored, dict) else None


def scan_history(days: int = 30) -> list[dict[str, Any]]:
    hist = load_json(SCAN_HISTORY_STORE, [])
    if not isinstance(hist, list):
        return []
    return hist[-max(1, min(days, HISTORY_RETENTION_DAYS)):]


# ── our-validator wallet identification ─────────────────────────────────────


def our_validator_wallets(hotkey: str | None = None) -> dict[str, Any]:
    """
    Full coldkey→stake breakdown behind our validator hotkey, from Taostats
    stake_balance, cross-checked against the on-chain TotalHotkeyAlpha for that
    hotkey so the wallet list is provably complete.
    """
    hk = hotkey or OUR_VALIDATOR_HOTKEY
    if not _api_key():
        return {"error": "TAOSTATS_API_KEY not set", "hotkey": hk}

    session = requests.Session()
    session.headers.update({"Authorization": _api_key(), "Accept": "application/json"})

    rows: list[dict[str, Any]] = []
    page = 1
    while True:
        url = f"{TAOSTATS_API_BASE}{STAKE_BALANCE_PATH}"
        params = {"netuid": NETUID, "hotkey": hk, "limit": 200, "page": page, "order": "balance_desc"}
        for attempt in range(MAX_429_RETRIES):
            r = session.get(url, params=params, timeout=120)
            if r.status_code == 429:
                _time.sleep(min(2 ** attempt + 1.0, 30))
                continue
            break
        if r.status_code != 200:
            return {"error": f"Taostats HTTP {r.status_code}", "hotkey": hk}
        body = r.json()
        data = body.get("data") or []
        rows.extend(data)
        pag = body.get("pagination") or {}
        nxt = pag.get("next_page")
        tp = pag.get("total_pages") or 0
        if not data or not nxt or page >= tp:
            break
        page = int(nxt)
        _time.sleep(0.5)

    house = house_set()
    total = 0.0
    wallets = []
    for row in rows:
        ck = _ss58(row.get("coldkey"))
        alpha = int(row.get("balance") or 0) / RAO_PER_TAO
        as_tao = int(row.get("balance_as_tao") or 0) / RAO_PER_TAO
        total += alpha
        wallets.append(
            {
                "coldkey": ck,
                "coldkey_short": _short(ck),
                "name": row.get("coldkey_name") or row.get("hotkey_name"),
                "alpha": round(alpha, 6),
                "as_tao": round(as_tao, 6),
                "is_house": is_house(ck, hk, house=house),
            }
        )
    for w in wallets:
        w["pct"] = round(100 * w["alpha"] / total, 4) if total else 0.0

    # On-chain cross-check.
    onchain_total = None
    cross_ok = None
    try:
        from chain_compat import bits, substrate

        with substrate() as sub:
            raw = bits(sub.query("SubtensorModule", "TotalHotkeyAlpha", [hk, NETUID]))
        onchain_total = round(raw / RAO_PER_TAO, 6) if raw is not None else None
        if onchain_total is not None:
            cross_ok = abs(onchain_total - total) <= max(1.0, 0.001 * onchain_total)
    except Exception:
        logger.exception("TotalHotkeyAlpha cross-check failed")

    return {
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "uid": OUR_VALIDATOR_UID,
        "hotkey": hk,
        "hotkey_short": _short(hk),
        "wallet_count": len(wallets),
        "total_alpha_staked": round(total, 6),
        "onchain_total_hotkey_alpha": onchain_total,
        "cross_check_ok": cross_ok,
        "wallets": wallets,
    }
