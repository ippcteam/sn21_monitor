"""
V450 root-basket scanner — which root-network funds include SN21.

Root validators (netuid 0) can `set_root_weights` and send their *dividend
stream* (not principal) into subnet alphas. Cap 1/16 → at least 16
destinations. Empty vector = null strategy (dividends accrue in place).

Two signals, do not mix them:

  curated   — 21 is in the fund's weight vector (they chose it)
  leftover  — fund holds SN21 α but has no 21 weight (inventory, not a vote)

A leftover that starts curating is an *add*, not a leftover-clear.

Reads `BetaBasketRuntimeApi.get_all_validator_baskets` via the raw
substrate client (works on bittensor 11.0.0 — do not bump to 11.3).

Writes:
  data/root_baskets.json          — latest snapshot
  data/root_baskets_history.json  — one compact row/day, 90d
"""

from __future__ import annotations

import logging
import os
import threading
import time as _time
from datetime import datetime, timezone
from typing import Any

from collector import load_json, save_json
from config import DATA_DIR
from labels import house_set, is_house

logger = logging.getLogger(__name__)

NETUID = 21
NETWORK = "finney"
RAO_PER_TAO = 1_000_000_000
SS58_FORMAT = 42

OUR_VALIDATOR_HOTKEY = (
    os.environ.get("OUR_VALIDATOR_HOTKEY")
    or "5GuiHBTfciFauoF1XuyvVuWYrQaS7LExrbsqV5EmDU2ibJEz"
).strip()

SCAN_STORE = DATA_DIR / "root_baskets.json"
SCAN_HISTORY_STORE = DATA_DIR / "root_baskets_history.json"
HISTORY_RETENTION_DAYS = 90

# Significance — keep these thresholds (ported from SN21-adtao).
SHARE_MOVE_PP = 1.0          # 16→17 dest 1/N ≈ 0.37pp is noise
POSITION_MIN_TAO = 1.0       # |Δτ| floor
POSITION_MIN_PCT = 10.0      # |Δτ| / prior τ
NEW_LEFTOVER_MIN_TAO = 5.0   # first-seen leftover inventory

CACHE_TTL_SECONDS = 60
_cache_lock = threading.Lock()
_cache: dict[str, Any] = {"fetched_at": 0.0, "payload": None}
_scan_lock = threading.Lock()


# ── decode helpers ──────────────────────────────────────────────────────────


def _peel(v: Any) -> Any:
    """Unwrap ScaleObj.value and SCALE newtype 1-tuples/lists."""
    v = getattr(v, "value", v)
    while isinstance(v, (list, tuple)) and len(v) == 1:
        v = getattr(v[0], "value", v[0])
    return v


def _as_int(v: Any, default: int = 0) -> int:
    v = _peel(v)
    if v is None or v == "":
        return default
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _as_rao(v: Any) -> float:
    """TaoBalance / AlphaBalance newtypes are raw rao."""
    v = _peel(v)
    if v is None or v == "":
        return 0.0
    try:
        return float(v) / RAO_PER_TAO
    except (TypeError, ValueError):
        return 0.0


def _as_ss58(v: Any) -> str | None:
    v = _peel(v)
    if v is None:
        return None
    if isinstance(v, str) and v.strip():
        return v.strip()
    if isinstance(v, (bytes, bytearray)) and len(v) == 32:
        from scalecodec.utils.ss58 import ss58_encode

        return ss58_encode(bytes(v), SS58_FORMAT)
    if isinstance(v, (list, tuple)) and len(v) == 32 and all(isinstance(x, int) for x in v):
        from scalecodec.utils.ss58 import ss58_encode

        return ss58_encode(bytes(v), SS58_FORMAT)
    return None


def _short(addr: str | None, head: int = 8, tail: int = 4) -> str | None:
    if not addr:
        return None
    return f"{addr[:head]}…{addr[-tail:]}" if len(addr) > head + tail + 1 else addr


def _display_name(name: str | None, hotkey: str | None) -> str:
    cleaned = (name or "").strip()
    return cleaned or (_short(hotkey) or "unnamed")


# ── parse / classify ────────────────────────────────────────────────────────


def parse_weights(raw: Any) -> list[tuple[int, int]]:
    """`Vec<(NetUid, u16)>` → [(netuid, weight), …] dropping zero weights."""
    out: list[tuple[int, int]] = []
    for item in raw or []:
        item = _peel(item)
        if isinstance(item, dict):
            netuid = _as_int(item.get("netuid") if "netuid" in item else item.get(0))
            weight = _as_int(item.get("weight") if "weight" in item else item.get(1))
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            netuid = _as_int(item[0])
            weight = _as_int(item[1])
        else:
            continue
        if weight > 0:
            out.append((netuid, weight))
    return out


def parse_holdings(raw: Any) -> list[dict[str, Any]]:
    """BasketHolding rows → {netuid, alpha, spot_tao, realizable_tao}."""
    out: list[dict[str, Any]] = []
    for item in raw or []:
        item = _peel(item)
        if isinstance(item, dict):
            netuid = _as_int(item.get("netuid"))
            alpha = _as_rao(item.get("alpha"))
            spot = _as_rao(item.get("spot_tao"))
            real = _as_rao(item.get("realizable_tao"))
        elif isinstance(item, (list, tuple)) and len(item) >= 3:
            netuid = _as_int(item[0])
            alpha = _as_rao(item[1])
            spot = _as_rao(item[2] if len(item) == 3 else item[2])
            real = _as_rao(item[-1])
        else:
            continue
        out.append({
            "netuid": netuid,
            "alpha": alpha,
            "spot_tao": spot,
            "realizable_tao": real,
        })
    return out


def classify(
    weights: list[tuple[int, int]],
    holdings: list[dict[str, Any]],
    netuid: int = NETUID,
) -> dict[str, Any]:
    """
    Curated vs leftover for one fund. `kind` is 'curated', 'leftover', or None
    (no 21 signal). Share is the 21-weight fraction of the *stored* vector
    (0 when not curated). dests counts every non-zero destination including
    netuid 0 (hold as TAO).
    """
    dests = len(weights)
    w_sum = sum(w for _, w in weights)
    share = 0.0
    curated = False
    for n, w in weights:
        if n == netuid:
            curated = True
            share = (w / w_sum) if w_sum else 0.0
            break

    sn21_alpha = 0.0
    sn21_tao = 0.0
    for h in holdings:
        if h.get("netuid") == netuid:
            sn21_alpha += float(h.get("alpha") or 0.0)
            sn21_tao += float(h.get("realizable_tao") or 0.0)

    leftover = (not curated) and (sn21_tao > 0 or sn21_alpha > 0)
    kind = "curated" if curated else ("leftover" if leftover else None)
    return {
        "kind": kind,
        "choice": choice_for(kind, dests),
        "share": share,
        "share_pp": round(share * 100.0, 4),
        "dests": dests,
        "sn21_alpha": sn21_alpha,
        "sn21_tao": sn21_tao,
    }


def choice_for(kind: str | None, dests: int) -> str | None:
    """
    Active root-weight choice, distinct from leftover inventory.

    include — published a vector and put 21 in it
    exclude — published a vector and left 21 out
    none    — no custom vector (null strategy); leftover α is not a vote
    """
    if kind == "curated":
        return "include"
    if kind is None and dests <= 0:
        return None
    if dests > 0:
        return "exclude"
    if kind == "leftover":
        return "none"
    return None


def normalize_fund(raw: dict[str, Any], netuid: int = NETUID) -> dict[str, Any] | None:
    """One runtime BasketSummary → a flat row, or None if the hotkey is unreadable."""
    hotkey = _as_ss58(raw.get("hotkey"))
    if not hotkey:
        return None
    weights = parse_weights(raw.get("weights"))
    holdings = parse_holdings(raw.get("holdings"))
    sig = classify(weights, holdings, netuid=netuid)
    return {
        "hotkey": hotkey,
        "hotkey_short": _short(hotkey),
        "nav_tao": round(_as_rao(raw.get("nav_tao")), 6),
        "spot_nav_tao": round(_as_rao(raw.get("spot_nav_tao")), 6),
        "shares": _as_int(raw.get("shares")),
        "kind": sig["kind"],
        "choice": sig["choice"],
        "share": sig["share"],
        "share_pp": sig["share_pp"],
        "dests": sig["dests"],
        "sn21_alpha": round(sig["sn21_alpha"], 6),
        "sn21_tao": round(sig["sn21_tao"], 6),
    }


def funds_with_signal(funds: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [f for f in funds if f.get("kind") in ("curated", "leftover")]


# ── annotate / diff / significance ──────────────────────────────────────────


def annotate(
    funds: list[dict[str, Any]],
    names: dict[str, str | None] | None = None,
    house: set[str] | None = None,
    our_hotkey: str = OUR_VALIDATOR_HOTKEY,
) -> list[dict[str, Any]]:
    names = names or {}
    house = house if house is not None else house_set()
    out: list[dict[str, Any]] = []
    for f in funds:
        hk = f["hotkey"]
        name = names.get(hk)
        if isinstance(name, str):
            name = name.strip() or None
        else:
            name = None
        dests = int(f.get("dests") or 0)
        out.append({
            **f,
            "choice": f.get("choice") or choice_for(f.get("kind"), dests),
            "name": name,
            "is_house": is_house(None, hk, house=house),
            "is_ours": hk == our_hotkey,
            "share_pp_delta": None,
            "sn21_tao_delta": None,
            "reasons": [],
            "significant": False,
        })
    out.sort(key=lambda r: (
        {"include": 0, "exclude": 1, "none": 2}.get(r.get("choice"), 3),
        -(r.get("sn21_tao") or 0.0),
        r.get("name") or r["hotkey"],
    ))
    return out


def _position_pct(delta: float, prior_tao: float) -> float | None:
    if prior_tao <= 0:
        return None
    return abs(delta) / prior_tao * 100.0


def change_reasons(today: dict[str, Any] | None, prior: dict[str, Any] | None) -> list[str]:
    """
    Ordered reasons for one fund vs yesterday.

    A leftover that starts curating is `curated_add`, never leftover-clear.
    First-seen leftover is `leftover_new` (caller applies the 5τ floor).
    """
    t_kind = (today or {}).get("kind")
    p_kind = (prior or {}).get("kind")
    if today is None and prior is None:
        return []
    if today is None:
        return ["curated_drop"] if p_kind == "curated" else ["leftover_clear"]

    reasons: list[str] = []
    if t_kind == "curated" and p_kind != "curated":
        reasons.append("curated_add")
    elif t_kind != "curated" and p_kind == "curated":
        reasons.append("curated_drop")

    if t_kind == "leftover" and prior is None:
        reasons.append("leftover_new")

    if t_kind == "curated" and p_kind == "curated":
        share_delta = abs(float(today.get("share_pp") or 0) - float(prior.get("share_pp") or 0))
        if share_delta >= SHARE_MOVE_PP:
            reasons.append("share_move")

    if today is not None and prior is not None:
        delta = float(today.get("sn21_tao") or 0) - float(prior.get("sn21_tao") or 0)
        pct = _position_pct(delta, float(prior.get("sn21_tao") or 0))
        if abs(delta) >= POSITION_MIN_TAO and pct is not None and pct >= POSITION_MIN_PCT:
            reasons.append("position_move")

    return reasons


def is_significant(reasons: list[str], today: dict[str, Any] | None) -> bool:
    """Apply the leftover-new 5τ floor; add/drop always fire."""
    if "curated_add" in reasons or "curated_drop" in reasons:
        return True
    if "share_move" in reasons or "position_move" in reasons:
        return True
    if "leftover_new" in reasons:
        return float((today or {}).get("sn21_tao") or 0) >= NEW_LEFTOVER_MIN_TAO
    return False


def diff_funds(
    today: list[dict[str, Any]],
    prior: list[dict[str, Any]] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Return (annotated today, change records). `prior is None` is the first
    snapshot — census only, no significance.
    """
    prior_map = {r["hotkey"]: r for r in (prior or []) if r.get("hotkey")}
    today_keys = {r["hotkey"] for r in today}
    annotated: list[dict[str, Any]] = []
    changes: list[dict[str, Any]] = []

    for r in today:
        prev = prior_map.get(r["hotkey"])
        row = dict(r)
        if prior is None:
            row["share_pp_delta"] = None
            row["sn21_tao_delta"] = None
            row["reasons"] = []
            row["significant"] = False
        else:
            reasons = change_reasons(row, prev)
            share_delta = None
            tao_delta = None
            if prev is not None:
                share_delta = round(
                    float(row.get("share_pp") or 0) - float(prev.get("share_pp") or 0), 4
                )
                tao_delta = round(
                    float(row.get("sn21_tao") or 0) - float(prev.get("sn21_tao") or 0), 6
                )
            elif row.get("kind"):
                tao_delta = round(float(row.get("sn21_tao") or 0), 6)
            row["share_pp_delta"] = share_delta
            row["sn21_tao_delta"] = tao_delta
            row["reasons"] = reasons
            row["significant"] = is_significant(reasons, row)
            if reasons:
                changes.append(_change_record(row, prev, reasons))
        annotated.append(row)

    if prior is not None:
        for prev in prior:
            if prev.get("hotkey") in today_keys:
                continue
            reasons = change_reasons(None, prev)
            gone = dict(prev)
            gone["share_pp_delta"] = None
            gone["sn21_tao_delta"] = round(-float(prev.get("sn21_tao") or 0), 6)
            gone["reasons"] = reasons
            gone["significant"] = is_significant(reasons, None)
            changes.append(_change_record(gone, prev, reasons, gone=True))

    changes.sort(key=lambda c: (
        0 if "curated_add" in c["reasons"] else
        1 if "curated_drop" in c["reasons"] else 2,
        -(abs(c.get("sn21_tao_delta") or 0)),
        c.get("name") or c.get("hotkey") or "",
    ))
    return annotated, changes


def _change_record(
    row: dict[str, Any],
    prior: dict[str, Any] | None,
    reasons: list[str],
    gone: bool = False,
) -> dict[str, Any]:
    return {
        "hotkey": row.get("hotkey"),
        "hotkey_short": row.get("hotkey_short"),
        "name": row.get("name"),
        "kind": None if gone else row.get("kind"),
        "kind_prior": (prior or {}).get("kind"),
        "reasons": reasons,
        "share_pp": None if gone else row.get("share_pp"),
        "share_pp_delta": row.get("share_pp_delta"),
        "dests": None if gone else row.get("dests"),
        "sn21_tao": 0.0 if gone else row.get("sn21_tao"),
        "sn21_tao_delta": row.get("sn21_tao_delta"),
        "nav_tao": None if gone else row.get("nav_tao"),
        "significant": row.get("significant"),
        "is_house": row.get("is_house"),
        "is_ours": row.get("is_ours"),
    }


def summarise(
    funds: list[dict[str, Any]],
    changes: list[dict[str, Any]],
    *,
    is_baseline: bool,
    n_all_funds: int,
) -> dict[str, Any]:
    curating = [f for f in funds if f.get("kind") == "curated"]
    leftover = [f for f in funds if f.get("kind") == "leftover"]
    included = [f for f in funds if f.get("choice") == "include"]
    excluded = [f for f in funds if f.get("choice") == "exclude"]
    no_vector = [f for f in funds if f.get("choice") == "none"]
    sig = [c for c in changes if c.get("significant")]
    adds = [c for c in sig if "curated_add" in c["reasons"]]
    drops = [c for c in sig if "curated_drop" in c["reasons"]]
    return {
        "n_all_funds": n_all_funds,
        "n_curating": len(curating),
        "n_leftover": len(leftover),
        "n_included": len(included),
        "n_excluded": len(excluded),
        "n_no_vector": len(no_vector),
        "realizable_tao_21": round(sum(f.get("sn21_tao") or 0 for f in funds), 6),
        "curated_tao_21": round(sum(f.get("sn21_tao") or 0 for f in curating), 6),
        "n_significant": len(sig),
        "n_adds": len(adds),
        "n_drops": len(drops),
        "add_names": [_display_name(c.get("name"), c.get("hotkey")) for c in adds],
        "drop_names": [_display_name(c.get("name"), c.get("hotkey")) for c in drops],
        "is_baseline": is_baseline,
    }


def history_row(date_str: str, summary: dict[str, Any], block: int | None) -> dict[str, Any]:
    return {
        "date": date_str,
        "block": block,
        "n_curating": summary["n_curating"],
        "n_leftover": summary["n_leftover"],
        "realizable_tao_21": summary["realizable_tao_21"],
        "n_significant": summary["n_significant"],
        "adds": summary["add_names"],
        "drops": summary["drop_names"],
    }


def digest_payload(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    """Compact block for gather() / the Telegram composer."""
    if not snapshot or not isinstance(snapshot, dict) or not snapshot.get("summary"):
        return {"available": False}
    hydrate_snapshot(snapshot)
    s = snapshot["summary"]
    sig = [c for c in (snapshot.get("changes") or []) if c.get("significant")]
    return {
        "available": True,
        "is_baseline": bool(s.get("is_baseline")),
        "n_curating": s.get("n_curating") or 0,
        "n_leftover": s.get("n_leftover") or 0,
        "n_included": s.get("n_included") or s.get("n_curating") or 0,
        "n_excluded": s.get("n_excluded") or 0,
        "n_no_vector": s.get("n_no_vector") or 0,
        "realizable_tao_21": s.get("realizable_tao_21") or 0.0,
        "n_significant": s.get("n_significant") or 0,
        "adds": s.get("add_names") or [],
        "drops": s.get("drop_names") or [],
        "significant": [
            {
                "name": _display_name(c.get("name"), c.get("hotkey")),
                "reasons": c.get("reasons") or [],
                "kind": c.get("kind"),
                "share_pp": c.get("share_pp"),
                "share_pp_delta": c.get("share_pp_delta"),
                "sn21_tao": c.get("sn21_tao"),
                "sn21_tao_delta": c.get("sn21_tao_delta"),
            }
            for c in sig
        ],
    }


# ── snapshot builder (pure) ─────────────────────────────────────────────────


def build_snapshot(
    raw_funds: list[dict[str, Any]],
    *,
    prior_funds: list[dict[str, Any]] | None = None,
    names: dict[str, str | None] | None = None,
    house: set[str] | None = None,
    our_hotkey: str = OUR_VALIDATOR_HOTKEY,
    fetched_at: datetime | None = None,
    block: int | None = None,
    network: str = NETWORK,
) -> dict[str, Any]:
    parsed = [p for p in (normalize_fund(r) for r in raw_funds) if p]
    signal = funds_with_signal(parsed)
    annotated = annotate(signal, names=names, house=house, our_hotkey=our_hotkey)
    is_baseline = prior_funds is None
    funds, changes = diff_funds(annotated, prior_funds)
    summary = summarise(funds, changes, is_baseline=is_baseline, n_all_funds=len(parsed))
    now = fetched_at or datetime.now(timezone.utc)
    return {
        "date": now.strftime("%Y-%m-%d"),
        "fetched_at_utc": now.isoformat(),
        "block": block,
        "network": network,
        "source": "BetaBasketRuntimeApi.get_all_validator_baskets",
        "is_baseline": is_baseline,
        "summary": summary,
        "funds": funds,
        "changes": changes,
    }


# ── name join (cache only — no live Taostats; 60+ hotkeys would stall 09:18) ─


def _names_by_hotkey() -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    try:
        from weights_scan import NAMES_STORE
    except Exception:
        NAMES_STORE = DATA_DIR / "validator_names.json"
    cache = load_json(NAMES_STORE, {})
    if isinstance(cache, dict):
        for hk, rec in cache.items():
            if isinstance(rec, dict) and rec.get("name"):
                out[hk] = rec["name"]
    try:
        from validator_basket_sync import BASKET_STORE
    except Exception:
        BASKET_STORE = DATA_DIR / "validator_basket.json"
    basket = load_json(BASKET_STORE, {})
    if isinstance(basket, dict):
        for v in basket.get("validators") or []:
            hk = v.get("hotkey")
            name = (v.get("name") or "").strip() if isinstance(v.get("name"), str) else ""
            if hk and name and hk not in out:
                out[hk] = name
    return out


# ── chain read ──────────────────────────────────────────────────────────────


def _fetch_all_baskets() -> tuple[list[dict[str, Any]], int | None]:
    from chain_compat import substrate, unwrap

    with substrate() as sub:
        header = sub.get_block_header()
        raw_num = None
        if isinstance(header, dict):
            raw_num = (header.get("header") or header).get("number")
        block = int(raw_num) if raw_num is not None else None
        result = sub.runtime_call(
            "BetaBasketRuntimeApi", "get_all_validator_baskets", []
        )
        rows = unwrap(result) or []
        if not isinstance(rows, list):
            rows = [rows]
        return [r for r in rows if isinstance(r, dict)], block


def _prior_funds() -> list[dict[str, Any]] | None:
    stored = load_json(SCAN_STORE, None)
    if isinstance(stored, dict) and stored.get("funds") is not None:
        return list(stored["funds"])
    return None


def _write_history(date_str: str, summary: dict[str, Any], block: int | None) -> int:
    hist = load_json(SCAN_HISTORY_STORE, [])
    if not isinstance(hist, list):
        hist = []
    hist = [r for r in hist if r.get("date") != date_str]
    hist.append(history_row(date_str, summary, block))
    hist.sort(key=lambda r: r.get("date") or "")
    if len(hist) > HISTORY_RETENTION_DAYS:
        hist = hist[-HISTORY_RETENTION_DAYS:]
    save_json(SCAN_HISTORY_STORE, hist)
    return len(hist)


def run_scan() -> dict[str, Any]:
    """Fetch every root basket, persist the SN21-signal set, append today's history row."""
    with _scan_lock:
        raw, block = _fetch_all_baskets()
        snapshot = build_snapshot(
            raw,
            prior_funds=_prior_funds(),
            names=_names_by_hotkey(),
            house=house_set(),
        )
        snapshot["block"] = block
        save_json(SCAN_STORE, snapshot)
        _write_history(snapshot["date"], snapshot["summary"], block)
        with _cache_lock:
            _cache["payload"] = snapshot
            _cache["fetched_at"] = _time.time()
        s = snapshot["summary"]
        logger.info(
            "Root baskets @ block %s: %d funds, %d curating 21, %d leftover, "
            "τ21=%.4f, significant=%d (adds=%d drops=%d baseline=%s)",
            block, s["n_all_funds"], s["n_curating"], s["n_leftover"],
            s["realizable_tao_21"], s["n_significant"], s["n_adds"], s["n_drops"],
            s["is_baseline"],
        )
        return snapshot


def hydrate_snapshot(snapshot: dict[str, Any] | None) -> dict[str, Any] | None:
    """Fill include/exclude/none on snapshots taken before `choice` existed."""
    if not snapshot or not isinstance(snapshot, dict):
        return snapshot
    funds = snapshot.get("funds") or []
    for f in funds:
        if not f.get("choice"):
            f["choice"] = choice_for(f.get("kind"), int(f.get("dests") or 0))
    funds.sort(key=lambda r: (
        {"include": 0, "exclude": 1, "none": 2}.get(r.get("choice"), 3),
        -(r.get("sn21_tao") or 0.0),
        r.get("name") or r.get("hotkey") or "",
    ))
    snapshot["funds"] = funds
    s = snapshot.setdefault("summary", {})
    if s.get("n_excluded") is None or s.get("n_no_vector") is None:
        s["n_included"] = sum(1 for f in funds if f.get("choice") == "include")
        s["n_excluded"] = sum(1 for f in funds if f.get("choice") == "exclude")
        s["n_no_vector"] = sum(1 for f in funds if f.get("choice") == "none")
        if s.get("n_curating") is None:
            s["n_curating"] = s["n_included"]
        if s.get("n_leftover") is None:
            s["n_leftover"] = s["n_excluded"] + s["n_no_vector"]
    return snapshot


def latest_scan() -> dict[str, Any] | None:
    with _cache_lock:
        if _cache["payload"] and (_time.time() - _cache["fetched_at"]) < CACHE_TTL_SECONDS:
            return hydrate_snapshot(_cache["payload"])
    stored = load_json(SCAN_STORE, None)
    if not isinstance(stored, dict):
        return None
    hydrated = hydrate_snapshot(stored)
    with _cache_lock:
        _cache["payload"] = hydrated
        _cache["fetched_at"] = _time.time()
    return hydrated


def scan_history(days: int = 30) -> list[dict[str, Any]]:
    hist = load_json(SCAN_HISTORY_STORE, [])
    if not isinstance(hist, list):
        return []
    return hist[-max(1, min(days, HISTORY_RETENTION_DAYS)):]
