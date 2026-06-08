"""
Market context — daily all-subnets alpha-price scan.

Pulls every subnet's AMM reserves in a SINGLE finney chain call
(`subtensor.all_subnets()`), computes each subnet's alpha price in TAO
(`tao_in / alpha_in` — the same ratio collector.py uses for SN21), and ranks
SN21 against the whole field so the digest can answer the only question that
matters when alpha falls: *is this SN21, or is it the market?*

Why alpha-in-TAO (not USD) for the peer comparison: alpha/USD moves whenever
TAO moves, so a TAO selloff paints every subnet red and triggers false alarms.
Alpha/TAO strips the common TAO factor out and isolates subnet-relative
performance — exactly the signal we want. We keep USD for absolute-wealth context.

Writes:
  data/subnets_market.json         — latest full snapshot (per-subnet + breadth + SN21 + cohorts).
  data/subnets_market_history.json — one compact row/day, 365d retention (drives SN21 rank-over-time).
  data/subnets_price_ledger.json   — {date: {netuid: alpha_price_tao}}, 14d window, for 24h/7d deltas.

Direct-chain like collector.py / weights_scan.py; reuses the same SSL fix so the
WebSocket chain connection verifies on minimal Render images.

Fallback (not implemented): if a future SDK rename breaks all_subnets(), the same
per-subnet reserves are available via Taostats /api/dtao/pool/latest/v1 (see subnet_scan.py).
"""

from __future__ import annotations

import logging
import math
import os
import threading
from datetime import datetime, timedelta, timezone
from typing import Any

from collector import _configure_chain_ssl, get_tao_price_usd, load_json, save_json
from config import DATA_DIR

logger = logging.getLogger(__name__)

NETUID_SN21 = 21
NETWORK = os.environ.get("SN21_MARKET_NETWORK", "finney")

MARKET_STORE = DATA_DIR / "subnets_market.json"
MARKET_HISTORY_STORE = DATA_DIR / "subnets_market_history.json"
PRICE_LEDGER_STORE = DATA_DIR / "subnets_price_ledger.json"

HISTORY_RETENTION_DAYS = 365
LEDGER_RETENTION_DAYS = 14

# ── Verdict thresholds (tunable) ──────────────────────────────────────────────
# "market_wide": the field fell as a whole and SN21 moved with it.
MARKET_DOWN_PCT = -2.0          # market median 24h move this negative ⇒ a real market-wide drop
MARKET_BAND_PCT = 1.5           # SN21 within ±this of the median ⇒ "in line with the market"
# "sn21_specific": SN21 in the bottom of the move distribution while the market held.
SN21_LAG_PERCENTILE = 25.0      # SN21 in the bottom quartile of moves …
MARKET_HELD_PCT = -0.5          # … while the market median was ~flat-or-up
OUTPERFORM_PCT = 2.0            # SN21 this far above median ⇒ "outperforming"

_scan_lock = threading.Lock()


# ── small helpers ─────────────────────────────────────────────────────────────

def _to_float(v: Any) -> float | None:
    """Coerce a chain value (Balance, int rao, float, str) to a whole-unit float."""
    if v is None:
        return None
    # bittensor Balance exposes .tao (whole units); fall back to float().
    t = getattr(v, "tao", None)
    if t is not None:
        try:
            return float(t)
        except (TypeError, ValueError):
            pass
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _subnet_name(d: Any) -> str | None:
    for attr in ("subnet_name", "name"):
        v = getattr(d, attr, None)
        if isinstance(v, bytes):
            try:
                v = v.decode("utf-8", "ignore")
            except Exception:
                v = None
        if v:
            s = str(v).strip()
            if s:
                return s
    return None


def _pct_change(now: float | None, prev: float | None) -> float | None:
    if now is None or prev is None or prev == 0:
        return None
    return round((now - prev) / prev * 100.0, 4)


def _percentile_rank(values: list[float], x: float) -> float:
    """Percentile of x within values: share of values ≤ x, as 0–100."""
    if not values:
        return 0.0
    le = sum(1 for v in values if v <= x)
    return round(le / len(values) * 100.0, 2)


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    s = sorted(values)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2.0


def _price_decile(price: float, sorted_desc: list[float]) -> int:
    """1 = top 10% (highest prices) … 10 = bottom 10%."""
    if not sorted_desc:
        return 10
    # rank: 1-based position when sorted high→low (count of prices strictly greater + 1)
    rank = sum(1 for p in sorted_desc if p > price) + 1
    return max(1, min(10, math.ceil(rank / len(sorted_desc) * 10)))


# ── Ledger (for deltas across days) ───────────────────────────────────────────

def _ledger_ref_date(ledger: dict[str, Any], today: str, lag_days: int) -> str | None:
    """Most recent ledger date on/before (today − lag_days), excluding today."""
    target = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=lag_days)).strftime("%Y-%m-%d")
    candidates = sorted(d for d in ledger if d < today and d <= target)
    if candidates:
        return candidates[-1]
    # For 24h (lag 1): if no date ≤ target, fall back to the latest prior date present.
    if lag_days <= 1:
        priors = sorted(d for d in ledger if d < today)
        return priors[-1] if priors else None
    return None


# ── Public entry point ────────────────────────────────────────────────────────

def run_sync() -> dict[str, Any]:
    """Pull all-subnet prices, compute movement/cohorts/verdict, persist. Returns the snapshot."""
    with _scan_lock:
        return _run_sync_locked()


def _run_sync_locked() -> dict[str, Any]:
    _configure_chain_ssl()
    import bittensor as bt

    logger.info("Market scan: pulling all subnets from %s …", NETWORK)
    st = bt.Subtensor(network=NETWORK, log_verbose=False)
    raw = st.all_subnets()
    try:
        block = int(st.get_current_block())
    except Exception:
        block = None

    tao_usd = get_tao_price_usd()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # ── Per-subnet price from reserves ───────────────────────────────────────
    rows: list[dict[str, Any]] = []
    for d in raw or []:
        netuid = getattr(d, "netuid", None)
        if netuid is None:
            continue
        netuid = int(netuid)
        if netuid == 0:  # root has no alpha pool
            continue
        tao_in = _to_float(getattr(d, "tao_in", None))
        alpha_in = _to_float(getattr(d, "alpha_in", None))
        price_tao = (tao_in / alpha_in) if (tao_in and alpha_in and alpha_in > 0) else None
        if price_tao is None or price_tao <= 0:
            continue
        rows.append({
            "netuid": netuid,
            "name": _subnet_name(d),
            "alpha_price_tao": round(price_tao, 8),
            "alpha_price_usd": round(price_tao * tao_usd, 8) if tao_usd else None,
            "tao_in": round(tao_in, 4),
            "alpha_in": round(alpha_in, 4),
        })

    if not rows:
        logger.error("Market scan: no subnets with a valid pool — aborting without overwrite")
        return load_json(MARKET_STORE, {}) or {}

    # ── Deltas vs ledger ─────────────────────────────────────────────────────
    ledger = load_json(PRICE_LEDGER_STORE, {}) or {}
    ref_24h = _ledger_ref_date(ledger, today, 1)
    ref_7d = _ledger_ref_date(ledger, today, 7)
    prev_24h = ledger.get(ref_24h, {}) if ref_24h else {}
    prev_7d = ledger.get(ref_7d, {}) if ref_7d else {}

    for r in rows:
        key = str(r["netuid"])
        p_now = r["alpha_price_tao"]
        r["move_24h_tao_pct"] = _pct_change(p_now, prev_24h.get(key))
        r["move_7d_tao_pct"] = _pct_change(p_now, prev_7d.get(key))
        # USD 24h move folds in TAO's own move (absolute-wealth view).
        usd_now = r["alpha_price_usd"]
        prev_usd = (prev_24h.get(key) * tao_usd) if (prev_24h.get(key) and tao_usd) else None
        r["move_24h_usd_pct"] = _pct_change(usd_now, prev_usd)

    # ── Cohorts, percentiles, breadth ────────────────────────────────────────
    prices = [r["alpha_price_tao"] for r in rows]
    prices_desc = sorted(prices, reverse=True)
    moves = [r["move_24h_tao_pct"] for r in rows if r["move_24h_tao_pct"] is not None]

    for r in rows:
        r["price_decile"] = _price_decile(r["alpha_price_tao"], prices_desc)
        r["price_percentile"] = _percentile_rank(prices, r["alpha_price_tao"])
        r["move_24h_percentile"] = (
            _percentile_rank(moves, r["move_24h_tao_pct"])
            if (moves and r["move_24h_tao_pct"] is not None) else None
        )

    median_move = _median(moves)
    n_up = sum(1 for m in moves if m > 0)
    n_down = sum(1 for m in moves if m < 0)
    best = max((r for r in rows if r["move_24h_tao_pct"] is not None),
               key=lambda r: r["move_24h_tao_pct"], default=None)
    worst = min((r for r in rows if r["move_24h_tao_pct"] is not None),
                key=lambda r: r["move_24h_tao_pct"], default=None)

    def _mini(r: dict | None) -> dict | None:
        if not r:
            return None
        return {"netuid": r["netuid"], "name": r["name"], "move_24h_tao_pct": r["move_24h_tao_pct"]}

    breadth = {
        "n_subnets": len(rows),
        "n_with_move": len(moves),
        "n_up_24h": n_up,
        "n_down_24h": n_down,
        "pct_up_24h": round(n_up / len(moves) * 100.0, 1) if moves else None,
        "median_move_24h_tao_pct": round(median_move, 4) if median_move is not None else None,
        "best": _mini(best),
        "worst": _mini(worst),
    }

    # ── Cohort summaries (top / bottom decile, full market) ──────────────────
    def _cohort(members: list[dict]) -> dict[str, Any]:
        ms = [m["move_24h_tao_pct"] for m in members if m["move_24h_tao_pct"] is not None]
        ps = [m["alpha_price_tao"] for m in members]
        med = _median(ms)
        return {
            "n": len(members),
            "price_floor_tao": round(min(ps), 8) if ps else None,
            "median_move_24h_tao_pct": round(med, 4) if med is not None else None,
            "members": sorted(m["netuid"] for m in members),
        }

    top_decile = [r for r in rows if r["price_decile"] == 1]
    bottom_decile = [r for r in rows if r["price_decile"] == 10]
    cohorts = {
        "top_decile": _cohort(top_decile),
        "bottom_decile": _cohort(bottom_decile),
        "market": _cohort(rows),
    }

    # ── SN21 standing + verdict ──────────────────────────────────────────────
    sn21_row = next((r for r in rows if r["netuid"] == NETUID_SN21), None)
    sn21 = None
    if sn21_row:
        move = sn21_row["move_24h_tao_pct"]
        vs_median = (round(move - median_move, 4)
                     if (move is not None and median_move is not None) else None)
        sn21 = {
            "netuid": NETUID_SN21,
            "alpha_price_tao": sn21_row["alpha_price_tao"],
            "alpha_price_usd": sn21_row["alpha_price_usd"],
            "move_24h_tao_pct": move,
            "move_24h_usd_pct": sn21_row["move_24h_usd_pct"],
            "move_7d_tao_pct": sn21_row["move_7d_tao_pct"],
            "price_decile": sn21_row["price_decile"],
            "price_percentile": sn21_row["price_percentile"],
            "move_24h_percentile": sn21_row["move_24h_percentile"],
            "vs_median_24h_tao_pct": vs_median,
            "verdict": _verdict(move, median_move, sn21_row["move_24h_percentile"], vs_median),
        }

    snapshot = {
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "date": today,
        "block": block,
        "tao_price_usd": tao_usd,
        "subnets": sorted(rows, key=lambda r: r["alpha_price_tao"], reverse=True),
        "breadth": breadth,
        "cohorts": cohorts,
        "sn21": sn21,
    }

    _persist(snapshot, ledger, today, block, tao_usd)
    logger.info(
        "Market scan: %d subnets, median 24h %s%%, SN21 verdict=%s",
        len(rows),
        breadth["median_move_24h_tao_pct"],
        (sn21 or {}).get("verdict"),
    )
    return snapshot


def _verdict(move: float | None, median: float | None,
             move_pctile: float | None, vs_median: float | None) -> str:
    """Classify SN21's day relative to the field. Order matters."""
    if move is None or median is None or vs_median is None:
        return "unknown"
    if vs_median >= OUTPERFORM_PCT:
        return "outperforming"
    if move_pctile is not None and move_pctile <= SN21_LAG_PERCENTILE and median >= MARKET_HELD_PCT:
        return "sn21_specific"
    if median <= MARKET_DOWN_PCT and abs(vs_median) <= MARKET_BAND_PCT:
        return "market_wide"
    return "inline"


# ── Persistence ───────────────────────────────────────────────────────────────

def _persist(snapshot: dict, ledger: dict, today: str, block: int | None, tao_usd: float | None) -> None:
    save_json(MARKET_STORE, snapshot)

    # Price ledger: today's per-netuid price; trim to LEDGER_RETENTION_DAYS.
    ledger[today] = {str(r["netuid"]): r["alpha_price_tao"] for r in snapshot["subnets"]}
    cutoff = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=LEDGER_RETENTION_DAYS)).strftime("%Y-%m-%d")
    ledger = {d: v for d, v in ledger.items() if d >= cutoff}
    save_json(PRICE_LEDGER_STORE, ledger)

    # Compact daily history row (replace same-date), trim to HISTORY_RETENTION_DAYS.
    sn21 = snapshot.get("sn21") or {}
    breadth = snapshot["breadth"]
    row = {
        "date": today,
        "block": block,
        "tao_price_usd": tao_usd,
        "n_subnets": breadth["n_subnets"],
        "pct_up_24h": breadth["pct_up_24h"],
        "median_move_24h_tao_pct": breadth["median_move_24h_tao_pct"],
        "sn21_alpha_price_tao": sn21.get("alpha_price_tao"),
        "sn21_alpha_price_usd": sn21.get("alpha_price_usd"),
        "sn21_price_percentile": sn21.get("price_percentile"),
        "sn21_move_24h_tao_pct": sn21.get("move_24h_tao_pct"),
        "sn21_move_24h_percentile": sn21.get("move_24h_percentile"),
        "sn21_verdict": sn21.get("verdict"),
    }
    history = load_json(MARKET_HISTORY_STORE, []) or []
    history = [h for h in history if h.get("date") != today]
    history.append(row)
    history.sort(key=lambda h: h["date"])
    h_cutoff = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=HISTORY_RETENTION_DAYS)).strftime("%Y-%m-%d")
    history = [h for h in history if h["date"] >= h_cutoff]
    save_json(MARKET_HISTORY_STORE, history)


def latest() -> dict[str, Any]:
    return load_json(MARKET_STORE, {}) or {}


def history(days: int = 30) -> list[dict[str, Any]]:
    rows = load_json(MARKET_HISTORY_STORE, []) or []
    if days and days > 0:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
        rows = [r for r in rows if r.get("date", "") >= cutoff]
    return rows
