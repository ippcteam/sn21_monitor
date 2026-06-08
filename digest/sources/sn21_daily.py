"""
SN21 daily digest source. Reads existing JSON stores (no new fetches) and
returns a structured `inputs` dict for the composer to narrate.

Reads:
  - subnet_daily.json     — pool / price / depth (Activity tab data)
  - holders_snapshots.json — up to 31 snapshots for 24h/7d/30d movers
  - taostats_owner_transfers.json — wallet balance + transfers
  - daily_log.json        — chain snapshot, emissions, our entitlement
  - neurons_daily.json    — per-UID daily, burn rate, validator/miner counts
  - wallet_labels.json    — via labels.house_set() for house tagging

Multi-window output:
  - `movers` (24h, today vs prior, per hotkey×coldkey position)
  - `movers_7d` (per coldkey aggregate, today vs ~7d ago)
  - `movers_30d` (per coldkey aggregate, today vs ~30d ago — graceful
    fallback to oldest snapshot until 30 days of data accumulate)
  - `trends` (per-metric today / -7d / -30d / pct deltas across all sources)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from collector import load_json
from config import DATA_DIR, DAILY_LOG
from labels import house_set, is_house
from ownership import next_tier_info

logger = logging.getLogger(__name__)

SUBNET_DAILY_STORE = DATA_DIR / "subnet_daily.json"
HOLDERS_STORE = DATA_DIR / "holders_snapshots.json"
TAOSTATS_STORE = DATA_DIR / "taostats_owner_transfers.json"
NEURONS_DAILY_STORE = DATA_DIR / "neurons_daily.json"
MARKET_STORE = DATA_DIR / "subnets_market.json"

RAO_PER_TAO = 1_000_000_000

# Names worth flagging as "validator brand" exits.
KNOWN_BRANDS = {
    "taostats",
    "tao.bot",
    "1t1b",
    "1t1b.ai",
    "datura",
    "openτensor",
    "open tensor",
    "otf",
    "polychain",
    "rizzo",
    "yuma",
    "crucible",
    "love",
}

# Threshold for "notable exit" (in alpha). Anything ≥ 1000 alpha or ≥ 5 τ-equiv.
NOTABLE_EXIT_ALPHA = 1000.0
NOTABLE_EXIT_TAO = 5.0

# Multi-window depth (per-coldkey movers).
WINDOW_DAYS = (7, 30)
TOP_MOVERS_PER_WINDOW = 10


def _pct(today: float | int | None, prior: float | int | None) -> float | None:
    if today is None or not prior:
        return None
    try:
        return round((today - prior) / prior * 100, 2)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _row_at_offset(rows: list[dict], days_ago: int) -> tuple[dict | None, int | None]:
    """
    Return (row, actual_days_ago) for the row closest to `days_ago` days
    behind the latest. Falls back to the oldest available row if the window
    extends beyond what's stored. Both rows must carry a `date` field.

    Defensive: returns (None, None) if `rows` is anything other than a non-empty
    list — keeps a misshapen JSON store from blowing up the whole digest.
    """
    if not isinstance(rows, list) or not rows:
        return None, None
    if days_ago <= 0:
        return rows[-1], 0
    if len(rows) <= days_ago:
        # Use the oldest; report the actual gap for honest labelling.
        oldest = rows[0]
        try:
            today = datetime.fromisoformat(rows[-1]["date"]).date()
            old = datetime.fromisoformat(oldest["date"]).date()
            return oldest, max(0, (today - old).days)
        except Exception:
            return oldest, len(rows) - 1
    return rows[-1 - days_ago], days_ago


def _neurons_daily_series(neurons_daily_store: Any) -> list[dict[str, Any]]:
    """
    Reduce per-UID-per-day rows ({"rows": [...]}) to one row per date for trends.
    Per-day fields kept: burn_rate_pct (subnet-level, same on all UID rows for
    a date) plus aggregate sums of mining / burned / validating alpha.
    Returns chronologically sorted list of {date, burn_rate_pct, total_*}.
    """
    rows = []
    if isinstance(neurons_daily_store, dict):
        rows = neurons_daily_store.get("rows") or []
    elif isinstance(neurons_daily_store, list):
        rows = neurons_daily_store  # legacy/local-only path
    if not isinstance(rows, list):
        return []

    by_date: dict[str, dict[str, Any]] = {}
    for r in rows:
        if not isinstance(r, dict):
            continue
        d = r.get("date")
        if not d:
            continue
        agg = by_date.setdefault(d, {
            "date": d,
            "burn_rate_pct": None,
            "total_mining_alpha": 0.0,
            "total_burned_alpha": 0.0,
            "total_validating_alpha": 0.0,
            "total_owner_alpha": 0.0,
        })
        if agg["burn_rate_pct"] is None and r.get("burn_rate_pct") is not None:
            try:
                agg["burn_rate_pct"] = float(r["burn_rate_pct"])
            except (TypeError, ValueError):
                pass
        for src, dst in [
            ("daily_mining_alpha", "total_mining_alpha"),
            ("daily_burned_alpha", "total_burned_alpha"),
            ("daily_validating_alpha", "total_validating_alpha"),
            ("daily_owner_alpha", "total_owner_alpha"),
        ]:
            try:
                v = float(r.get(src) or 0)
                agg[dst] += v
            except (TypeError, ValueError):
                pass

    return [by_date[k] for k in sorted(by_date.keys())]


def _label_brand(name: str | None) -> str | None:
    if not name:
        return None
    nl = name.strip().lower()
    for brand in KNOWN_BRANDS:
        if brand in nl:
            return brand
    return None


# ── Section builders ──────────────────────────────────────────────────────────

def _price_section(subnet_log: list[dict]) -> tuple[dict, list[str]]:
    """alpha / TAO price + 1d / 7d deltas."""
    if not subnet_log:
        return {}, ["subnet_daily missing"]
    today = subnet_log[-1] or {}
    prior = subnet_log[-2] if len(subnet_log) >= 2 else {}
    week = subnet_log[-8] if len(subnet_log) >= 8 else (subnet_log[0] if subnet_log else {})

    pool = today.get("pool") or {}
    pool_prior = (prior or {}).get("pool") or {}
    pool_week = (week or {}).get("pool") or {}

    alpha = pool.get("alpha_price_tao")
    alpha_prior = pool_prior.get("alpha_price_tao")
    alpha_week = pool_week.get("alpha_price_tao")

    # Pool API also returns its own change pct fields; prefer those if present.
    api_1d = pool.get("price_change_1d_pct")
    api_7d = pool.get("price_change_7d_pct")

    return {
        "alpha_price_tao": alpha,
        "alpha_price_usd": _alpha_usd(alpha, today),
        "alpha_1d_pct": api_1d if api_1d is not None else _pct(alpha, alpha_prior),
        "alpha_7d_pct": api_7d if api_7d is not None else _pct(alpha, alpha_week),
        "tao_price_usd": _tao_usd(today),
        "tao_1d_pct": _pct(_tao_usd(today), _tao_usd(prior)),
        "fear_greed_index": pool.get("fear_and_greed_index"),
        "fear_greed_label": pool.get("fear_and_greed_sentiment"),
    }, []


def _alpha_usd(alpha: float | None, row: dict) -> float | None:
    tao = _tao_usd(row)
    if alpha is None or tao is None:
        return None
    try:
        return round(float(alpha) * float(tao), 6)
    except (TypeError, ValueError):
        return None


def _tao_usd(row: dict | None) -> float | None:
    """Best-effort TAO/USD lookup from a subnet_daily row (pool may not carry it)."""
    if not row:
        return None
    pool = row.get("pool") or {}
    tao = pool.get("tao_price_usd")
    if tao is not None:
        return tao
    # Fall back: not present in subnet_daily; caller may supply via taostats store.
    return None


def _pool_section(subnet_log: list[dict]) -> dict:
    if not subnet_log:
        return {}
    pool = (subnet_log[-1] or {}).get("pool") or {}
    return {
        "buys_24h": pool.get("buys_24h"),
        "sells_24h": pool.get("sells_24h"),
        "buyers_24h": pool.get("buyers_24h"),
        "sellers_24h": pool.get("sellers_24h"),
        "alpha_buy_volume_24h": pool.get("alpha_buy_volume_24h"),
        "alpha_sell_volume_24h": pool.get("alpha_sell_volume_24h"),
        "tao_buy_volume_24h": pool.get("tao_buy_volume_24h"),
        "tao_sell_volume_24h": pool.get("tao_sell_volume_24h"),
        "liquidity_tao": pool.get("liquidity_tao"),
        "market_cap_tao": pool.get("market_cap_tao"),
        "rank": pool.get("rank"),
    }


def _movers_section() -> tuple[dict, list[str]]:
    """24h holder diff — top inflows, outflows, exits."""
    store = load_json(HOLDERS_STORE, {"snapshots": []}) or {}
    snapshots = store.get("snapshots") or []
    if len(snapshots) < 2:
        return {}, ["holders_snapshots missing prior day"]

    today = snapshots[-1]
    prior = snapshots[-2]

    house = house_set()
    today_map = {f"{h.get('hotkey') or ''}|{h.get('coldkey') or ''}": h
                 for h in (today.get("holders") or [])}
    prior_map = {f"{h.get('hotkey') or ''}|{h.get('coldkey') or ''}": h
                 for h in (prior.get("holders") or [])}

    rows: list[dict] = []
    inflows = outflows = h_in = h_out = 0.0
    new_n = exit_n = 0
    for k in set(today_map) | set(prior_map):
        t = today_map.get(k)
        p = prior_map.get(k)
        bal_now = int((t or {}).get("balance_rao") or 0)
        bal_prev = int((p or {}).get("balance_rao") or 0)
        if bal_now == 0 and bal_prev == 0:
            continue
        delta_alpha = (bal_now - bal_prev) / RAO_PER_TAO
        bal_tao_now = int((t or {}).get("balance_as_tao_rao") or 0)
        bal_tao_prev = int((p or {}).get("balance_as_tao_rao") or 0)
        delta_tao = (bal_tao_now - bal_tao_prev) / RAO_PER_TAO

        coldkey = (t or p or {}).get("coldkey")
        hotkey = (t or p or {}).get("hotkey")
        hk_name = (t or p or {}).get("hotkey_name")
        is_h = is_house(coldkey, hotkey, house=house)
        is_new = p is None
        is_exited = t is None

        rows.append({
            "hotkey": hotkey,
            "hotkey_name": hk_name,
            "coldkey": coldkey,
            "is_house": is_h,
            "is_new": is_new,
            "is_exited": is_exited,
            "alpha_now": bal_now / RAO_PER_TAO,
            "alpha_prev": bal_prev / RAO_PER_TAO,
            "alpha_delta": round(delta_alpha, 6),
            "alpha_as_tao_delta": round(delta_tao, 6),
            "brand": _label_brand(hk_name),
        })

        if delta_alpha > 0:
            inflows += delta_alpha
            if is_h: h_in += delta_alpha
        elif delta_alpha < 0:
            outflows += -delta_alpha
            if is_h: h_out += -delta_alpha
        if is_new: new_n += 1
        if is_exited: exit_n += 1

    by_size = sorted(rows, key=lambda r: abs(r["alpha_delta"]), reverse=True)
    top_inflows = [r for r in by_size if r["alpha_delta"] > 0][:5]
    top_outflows = [r for r in by_size if r["alpha_delta"] < 0][:5]
    notable_exits = [
        r for r in by_size
        if r["is_exited"] and (
            abs(r["alpha_delta"]) >= NOTABLE_EXIT_ALPHA
            or abs(r["alpha_as_tao_delta"]) >= NOTABLE_EXIT_TAO
        )
    ][:5]

    return {
        "today_date": today.get("date"),
        "prior_date": prior.get("date"),
        "today_holder_count": today.get("holder_count"),
        "prior_holder_count": prior.get("holder_count"),
        "new_positions": new_n,
        "exited_positions": exit_n,
        "inflows_alpha": round(inflows, 4),
        "outflows_alpha": round(outflows, 4),
        "house_inflows_alpha": round(h_in, 4),
        "house_outflows_alpha": round(h_out, 4),
        "top_inflows": top_inflows,
        "top_outflows": top_outflows,
        "notable_exits": notable_exits,
    }, []


def _owner_pool_section() -> dict:
    """Owner-coldkey alpha + wallet balance + 24h delta."""
    out: dict[str, Any] = {}

    # Wallet balance from taostats sync.
    taostats = load_json(TAOSTATS_STORE, {}) or {}
    wallet = taostats.get("balance") or {}
    if wallet:
        bal = wallet.get("balance_total_tao")
        bal_24 = wallet.get("balance_total_24hr_ago_tao")
        out["balance_total_tao"] = bal
        out["balance_24h_ago_tao"] = bal_24
        if bal is not None and bal_24:
            out["balance_change_24h_pct"] = round((bal - bal_24) / bal_24 * 100, 2)

    # Owner-pool alpha across last 2 holders snapshots, summed for our coldkey.
    owner_id = ((taostats.get("balance") or {}).get("address")
                or taostats.get("account_ss58"))
    if owner_id:
        store = load_json(HOLDERS_STORE, {"snapshots": []}) or {}
        snapshots = store.get("snapshots") or []
        def _sum(snap: dict) -> tuple[float, float]:
            ours = [h for h in (snap.get("holders") or []) if h.get("coldkey") == owner_id]
            a = sum(int(h.get("balance_rao") or 0) for h in ours) / RAO_PER_TAO
            t = sum(int(h.get("balance_as_tao_rao") or 0) for h in ours) / RAO_PER_TAO
            return a, t
        if snapshots:
            a_now, t_now = _sum(snapshots[-1])
            out["alpha_now"] = round(a_now, 6)
            out["alpha_as_tao_now"] = round(t_now, 6)
            if len(snapshots) >= 2:
                a_prev, t_prev = _sum(snapshots[-2])
                out["alpha_delta_24h"] = round(a_now - a_prev, 6)
                out["alpha_as_tao_delta_24h"] = round(t_now - t_prev, 6)

    return out


def _burn_section(subnet_log: list[dict], neurons_daily_series: list[dict]) -> dict:
    """Burn rate + miner/validator activity (from neurons_daily and subnet_daily)."""
    out: dict[str, Any] = {}
    if neurons_daily_series:
        latest = neurons_daily_series[-1] or {}
        out["burn_rate_pct"] = latest.get("burn_rate_pct")
        out["date"] = latest.get("date")
        out["miner_emission_alpha"] = latest.get("total_mining_alpha")
        out["miner_burned_alpha"] = latest.get("total_burned_alpha")
        out["validator_emission_alpha"] = latest.get("total_validating_alpha")

    if subnet_log:
        sub = (subnet_log[-1] or {}).get("subnet") or {}
        out["active_validators"] = sub.get("active_validators")
        out["active_miners"] = sub.get("active_miners")
        out["recycled_24h_tao"] = sub.get("recycled_24h_tao")
        out["incentive_burn"] = sub.get("incentive_burn")
        # Prefer subnet incentive_burn (live) over neurons_daily snapshot if both present.
        if out.get("burn_rate_pct") is None and sub.get("incentive_burn") is not None:
            try:
                out["burn_rate_pct"] = round(float(sub["incentive_burn"]) * 100, 2)
            except (TypeError, ValueError):
                pass
    return out


def _tier_section() -> dict:
    info = next_tier_info() or {}
    return {
        "current_rate_pct": _pct_to_pct(info.get("current_rate")),
        "next_tier_rate_pct": _pct_to_pct(info.get("next_rate")),
        "next_tier_date": info.get("next_date"),
        "days_to_next_tier": info.get("days_to_next"),
    }


def _pct_to_pct(v: Any) -> float | None:
    """Convert a 0..1 fractional rate to percent. Pass through if already > 1."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return round(f * 100, 4) if 0 <= f <= 1 else round(f, 4)


def _emissions_section(daily_log: list[dict]) -> dict:
    """Today's emissions + our entitled alpha; 1d delta."""
    if not daily_log:
        return {}
    latest = daily_log[-1] or {}
    prior = daily_log[-2] if len(daily_log) >= 2 else {}
    s = latest.get("subnet") or {}
    sp = (prior or {}).get("subnet") or {}
    return {
        "date": latest.get("date"),
        "total_alpha_emission": s.get("total_alpha_emission"),
        "owner_share_alpha": s.get("owner_share_alpha"),
        "our_entitled_alpha": s.get("our_entitled_alpha"),
        "our_entitled_alpha_1d_pct": _pct(
            s.get("our_entitled_alpha"), sp.get("our_entitled_alpha")
        ),
    }


# ── Multi-window trends (7d / 30d) ───────────────────────────────────────────

def _trend_row(rows: list[dict], extractor) -> dict[str, Any]:
    """
    Build a {today, d-7, d-30, 7d_pct, 30d_pct, window_actual_days_*}
    record from a list-of-dicts. `extractor(row)` pulls the metric value.
    """
    today_row = rows[-1] if rows else None
    today = extractor(today_row) if today_row else None

    d7_row, d7_actual = _row_at_offset(rows, 7)
    d30_row, d30_actual = _row_at_offset(rows, 30)
    d7 = extractor(d7_row) if d7_row else None
    d30 = extractor(d30_row) if d30_row else None

    return {
        "today": today,
        "d-7": d7,
        "d-30": d30,
        "7d_pct": _pct(today, d7),
        "30d_pct": _pct(today, d30),
        "7d_actual_days": d7_actual,
        "30d_actual_days": d30_actual,
    }


def _trends_section(subnet_log: list[dict], daily_log: list[dict],
                    neurons_daily_series: list[dict]) -> dict[str, Any]:
    """Per-metric 7d / 30d trends, drawing from whichever store has the longest history."""
    out: dict[str, Any] = {}

    # Alpha price τ — from subnet_daily
    out["alpha_price_tao"] = _trend_row(
        subnet_log,
        lambda r: ((r or {}).get("pool") or {}).get("alpha_price_tao"),
    )
    # TAO price USD — try subnet_daily.pool first, then daily_log.subnet
    out["tao_price_usd"] = _trend_row(
        subnet_log,
        lambda r: ((r or {}).get("pool") or {}).get("tao_price_usd")
                  or ((r or {}).get("subnet") or {}).get("tao_price_usd"),
    )
    if out["tao_price_usd"]["today"] is None:
        out["tao_price_usd"] = _trend_row(
            daily_log,
            lambda r: ((r or {}).get("subnet") or {}).get("tao_price_usd"),
        )

    # Holder count — from subnet_daily
    out["holder_count"] = _trend_row(
        subnet_log,
        lambda r: (r or {}).get("subnet_total_holders"),
    )

    # Pool depth + 24h volumes — from subnet_daily
    out["liquidity_tao"] = _trend_row(
        subnet_log,
        lambda r: ((r or {}).get("pool") or {}).get("liquidity_tao"),
    )
    out["alpha_buy_volume_24h"] = _trend_row(
        subnet_log,
        lambda r: ((r or {}).get("pool") or {}).get("alpha_buy_volume_24h"),
    )
    out["alpha_sell_volume_24h"] = _trend_row(
        subnet_log,
        lambda r: ((r or {}).get("pool") or {}).get("alpha_sell_volume_24h"),
    )

    # Burn rate — neurons_daily series, fall back to subnet incentive_burn ×100
    def _burn_x(r: dict | None) -> float | None:
        if not r:
            return None
        v = r.get("burn_rate_pct")
        if v is not None:
            try:
                return float(v)
            except (TypeError, ValueError):
                return None
        return None
    out["burn_rate_pct"] = _trend_row(neurons_daily_series or [], _burn_x)

    # Our entitled alpha — from daily_log
    out["our_entitled_alpha"] = _trend_row(
        daily_log,
        lambda r: ((r or {}).get("subnet") or {}).get("our_entitled_alpha"),
    )
    # Owner share alpha (the 18% pool gross)
    out["owner_share_alpha"] = _trend_row(
        daily_log,
        lambda r: ((r or {}).get("subnet") or {}).get("owner_share_alpha"),
    )

    out["windows"] = {
        "subnet_daily_rows": len(subnet_log),
        "daily_log_rows": len(daily_log),
        "neurons_daily_days": len(neurons_daily_series or []),
    }
    return out


# ── Per-coldkey multi-day movers (7d / 30d) ──────────────────────────────────

def _per_coldkey_balance(snapshot: dict) -> dict[str, dict[str, Any]]:
    """
    Aggregate a snapshot to one row per coldkey:
      {coldkey: {balance_rao, balance_as_tao_rao, positions, hotkey_names, hotkeys}}
    """
    out: dict[str, dict[str, Any]] = {}
    for h in (snapshot or {}).get("holders") or []:
        ck = h.get("coldkey")
        if not ck:
            continue
        cur = out.setdefault(ck, {
            "balance_rao": 0,
            "balance_as_tao_rao": 0,
            "positions": 0,
            "hotkey_names": [],
            "hotkeys": [],
        })
        cur["balance_rao"] += int(h.get("balance_rao") or 0)
        cur["balance_as_tao_rao"] += int(h.get("balance_as_tao_rao") or 0)
        cur["positions"] += 1
        if h.get("hotkey_name") and h["hotkey_name"] not in cur["hotkey_names"]:
            cur["hotkey_names"].append(h["hotkey_name"])
        if h.get("hotkey") and h["hotkey"] not in cur["hotkeys"]:
            cur["hotkeys"].append(h["hotkey"])
    return out


def _coldkey_movers_window(snapshots: list[dict], window_days: int,
                           house: set[str]) -> dict[str, Any]:
    """
    Top movers across a window, aggregated per coldkey. Falls back to oldest
    snapshot if `window_days` exceeds available history; the returned
    `actual_days` records what was actually used.
    """
    if not snapshots:
        return {"top": [], "actual_days": 0, "from_date": None, "to_date": None,
                "house_inflows_alpha": 0.0, "house_outflows_alpha": 0.0}

    today_snap = snapshots[-1]
    start_snap, actual_days = _row_at_offset(snapshots, window_days)
    if start_snap is None:
        start_snap = today_snap
        actual_days = 0

    today_map = _per_coldkey_balance(today_snap)
    start_map = _per_coldkey_balance(start_snap)

    rows: list[dict[str, Any]] = []
    house_in = house_out = 0.0
    for ck in set(today_map) | set(start_map):
        t = today_map.get(ck) or {}
        p = start_map.get(ck) or {}
        bal_now = int(t.get("balance_rao") or 0)
        bal_prev = int(p.get("balance_rao") or 0)
        if bal_now == 0 and bal_prev == 0:
            continue
        delta = (bal_now - bal_prev) / RAO_PER_TAO
        delta_tao = (int(t.get("balance_as_tao_rao") or 0)
                     - int(p.get("balance_as_tao_rao") or 0)) / RAO_PER_TAO

        names = (t.get("hotkey_names") or p.get("hotkey_names") or [])[:3]
        hotkeys = (t.get("hotkeys") or p.get("hotkeys") or [])
        is_h = any(hk in house for hk in hotkeys) or (ck in house)

        rows.append({
            "coldkey": ck,
            "is_house": is_h,
            "is_new": ck not in start_map,
            "is_exited": ck not in today_map,
            "positions_now": (t.get("positions") or 0),
            "positions_prev": (p.get("positions") or 0),
            "alpha_now": round(bal_now / RAO_PER_TAO, 4),
            "alpha_prev": round(bal_prev / RAO_PER_TAO, 4),
            "alpha_delta": round(delta, 4),
            "alpha_as_tao_delta": round(delta_tao, 4),
            "hotkey_names": names,
            "brand": _label_brand(" ".join(names) if names else None),
        })

        if delta > 0:
            if is_h: house_in += delta
        elif delta < 0:
            if is_h: house_out += -delta

    rows.sort(key=lambda r: abs(r["alpha_delta"]), reverse=True)

    return {
        "top": rows[:TOP_MOVERS_PER_WINDOW],
        "actual_days": actual_days or 0,
        "from_date": (start_snap or {}).get("date"),
        "to_date": (today_snap or {}).get("date"),
        "house_inflows_alpha": round(house_in, 4),
        "house_outflows_alpha": round(house_out, 4),
        "total_movers_considered": len(rows),
    }


# ── Flags / risks the LLM should weight ──────────────────────────────────────

def _flags(price: dict, movers: dict, owner: dict, burn: dict, market: dict | None = None) -> list[str]:
    flags: list[str] = []

    a_1d = price.get("alpha_1d_pct")
    if a_1d is not None and a_1d <= -5:
        flags.append(f"Alpha price down {a_1d:.2f}% in 24h")
    elif a_1d is not None and a_1d >= 5:
        flags.append(f"Alpha price up {a_1d:.2f}% in 24h")

    # Market-relative context: distinguish a real SN21 problem from a market-wide move.
    if market and market.get("available"):
        verdict = market.get("verdict")
        b = market.get("breadth") or {}
        s = market.get("sn21") or {}
        if verdict == "sn21_specific":
            flags.append(
                f"SN21-SPECIFIC weakness: SN21 in the bottom of the field "
                f"(move pctile {s.get('move_24h_percentile')}) while the market held "
                f"(median {b.get('median_move_24h_tao_pct')}% in TAO)"
            )
        elif verdict == "market_wide":
            flags.append(
                f"Market-wide move (not SN21-specific): {b.get('pct_up_24h')}% of subnets up, "
                f"median {b.get('median_move_24h_tao_pct')}% in TAO; SN21 in line"
            )

    if movers:
        h_out = movers.get("house_outflows_alpha") or 0
        if h_out > 0:
            flags.append(f"House outflows: {h_out:.2f} α (verify before public visibility)")
        notable = movers.get("notable_exits") or []
        brand_exits = [r for r in notable if r.get("brand")]
        if brand_exits:
            names = ", ".join(sorted({r["brand"] for r in brand_exits}))
            flags.append(f"Validator-brand exits: {names}")
        elif notable:
            flags.append(f"{len(notable)} notable EXITED position(s) ≥ 1000 α")

    if owner.get("alpha_delta_24h") is not None and owner["alpha_delta_24h"] < -10:
        flags.append(f"Owner-pool alpha fell {owner['alpha_delta_24h']:.2f} α in 24h")

    if burn.get("burn_rate_pct") is not None and burn["burn_rate_pct"] < 100:
        flags.append(f"Burn rate {burn['burn_rate_pct']:.2f}% — miners receiving alpha")

    return flags


def _market_section() -> dict[str, Any]:
    """
    SN21's alpha move relative to the whole field (from subnets_market.json).
    Answers "is it us or the market?" — the composer leads the price line with this.
    """
    market = load_json(MARKET_STORE, {}) or {}
    sn21 = market.get("sn21") or {}
    breadth = market.get("breadth") or {}
    cohorts = market.get("cohorts") or {}
    if not sn21:
        return {"available": False}

    verdict = sn21.get("verdict")
    plain = {
        "market_wide": "Market-wide move — SN21 fell roughly in line with the whole field; not SN21-specific.",
        "sn21_specific": "SN21-specific — SN21 lagged the field while the market held up. Investigate.",
        "outperforming": "SN21 outperformed the field today.",
        "inline": "SN21 moved roughly in line with the field.",
        "unknown": "Insufficient history to compare (need a prior day's prices).",
    }.get(verdict, "")

    return {
        "available": True,
        "date": market.get("date"),
        "verdict": verdict,
        "verdict_plain": plain,
        "sn21": sn21,
        "breadth": breadth,
        "top_decile": cohorts.get("top_decile"),
        "bottom_decile": cohorts.get("bottom_decile"),
    }


# ── Public entry point ────────────────────────────────────────────────────────

def gather() -> dict[str, Any]:
    """Pull everything needed for the SN21 daily digest. Pure read; no syncs."""
    subnet_log = load_json(SUBNET_DAILY_STORE, []) or []
    daily_log = load_json(DAILY_LOG, []) or []
    # neurons_daily.json is {"rows": [...]} on disk (per-UID-per-day).
    # Reduce to one row per date for trend / burn-rate computation.
    neurons_daily_raw = load_json(NEURONS_DAILY_STORE, {})
    neurons_daily_series = _neurons_daily_series(neurons_daily_raw)

    price, p_warn = _price_section(subnet_log)
    pool = _pool_section(subnet_log)
    movers, m_warn = _movers_section()
    owner = _owner_pool_section()
    burn = _burn_section(subnet_log, neurons_daily_series)
    tier = _tier_section()
    emissions = _emissions_section(daily_log)
    trends = _trends_section(subnet_log, daily_log, neurons_daily_series)
    market = _market_section()

    # Multi-window per-coldkey movers (7d, 30d).
    holders_store = load_json(HOLDERS_STORE, {"snapshots": []}) or {}
    snapshots = holders_store.get("snapshots") or []
    house = house_set()
    window_movers: dict[str, Any] = {}
    for w in WINDOW_DAYS:
        window_movers[f"movers_{w}d"] = _coldkey_movers_window(snapshots, w, house)

    # If subnet_log carries TAO USD via the daily log fallback, fold it in.
    if price.get("tao_price_usd") is None and daily_log:
        s = (daily_log[-1] or {}).get("subnet") or {}
        price["tao_price_usd"] = s.get("tao_price_usd")
        if price.get("alpha_price_usd") is None and price.get("alpha_price_tao") and price["tao_price_usd"]:
            price["alpha_price_usd"] = round(price["alpha_price_tao"] * price["tao_price_usd"], 6)

    today_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    stale = []
    stale.extend(p_warn)
    stale.extend(m_warn)
    if subnet_log and (subnet_log[-1] or {}).get("stale_fields"):
        stale.append(f"subnet_daily stale: {','.join(subnet_log[-1]['stale_fields'])}")

    out = {
        "kind": "sn21_daily",
        "date": today_iso,
        "price": price,
        "pool": pool,
        "movers": movers,
        "owner_pool": owner,
        "burn": burn,
        "emissions": emissions,
        "tier": tier,
        "trends": trends,
        "market": market,
        "stale_fields": stale,
    }
    out.update(window_movers)  # movers_7d, movers_30d
    out["flags"] = _flags(price, movers, owner, burn, market)
    return out
