"""
Daily SN21 bot watch — rescore suspected flow bots against our own clips.

Runs with the morning collection. Each pass:

  1. Pulls SN21 stake/unstake trades (Taostats) and appends them to a local tape.
  2. Rescores every watched coldkey from that tape: flatness, size, hold time,
     whether it buys after our buys, and what its sells line up with.
  3. Upgrades or degrades confidence. A coldkey quiet for several days steps down.
  4. Looks for a recycled key: one signature goes quiet and a new coldkey with
     the same hotkey, sizes, and hold shows up.

"Our" wallet is the clip buyer we want the crowd to react to (Siam's coldkey
by default). Override with BOT_WATCH_OURS, a comma-separated SS58 list.

Stores:
  data/bot_watch.json         — the map (wallets, replacements, our-move replies)
  data/bot_watch_trades.json  — trade tape, 21 days

Sell trigger for each of a wallet's sells, first match:
  same_block_own_buy   sold in the same block it bought (maker fade)
  after_our_sell       our wallet sold in the previous ~6 minutes
  after_our_buy        our wallet bought in the previous ~6 minutes (sold into our bid)
  timer_after_own_buy  sold after its own buy, with neither of our prints in between
"""

from __future__ import annotations

import logging
import os
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from statistics import median
from typing import Any

import requests

from collector import load_json, save_json
from config import DATA_DIR

logger = logging.getLogger(__name__)

TAOSTATS_API_BASE = os.environ.get("TAOSTATS_API_BASE", "https://api.taostats.io").rstrip("/")
STAKE_EVENTS_PATH = "/v1/subnets/stake-events"
NETUID = int(os.environ.get("SN21_NETUID", "21"))

# The clip wallet the crowd has been answering. Not a house miner key.
DEFAULT_OURS = "5DDDdanXMyBAf17hH5R8wMT3Ma44R8XGK5WxHquYNi5551gu"

BOT_WATCH_STORE = DATA_DIR / "bot_watch.json"
BOT_WATCH_TAPE = DATA_DIR / "bot_watch_trades.json"

TAPE_DAYS = 21
SCORE_DAYS = 14
HISTORY_DAYS = 90
MIN_TAO = 3.0
OUR_MOVE_MIN_TAO = 5.0
RESPONSE_BEFORE = 3       # blocks; a buy this far ahead of us still counts
RESPONSE_AFTER = 30       # blocks ≈ 6 minutes
BLOCK_SECONDS = 12
QUIET_STEP_DAYS = 3
QUIET_FLOOR_DAYS = 6
ROUND_TOL = 0.05

RANK = {"low": 0, "medium": 1, "high": 2}
RANK_NAME = {v: k for k, v in RANK.items()}


def our_coldkeys() -> list[str]:
    raw = os.environ.get("BOT_WATCH_OURS", DEFAULT_OURS)
    return [p.strip() for p in raw.split(",") if p.strip()]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _dt(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _round5(tao: float) -> int | None:
    if tao < 4.5:
        return None
    bucket = round(tao / 5) * 5
    if abs(tao - bucket) <= ROUND_TOL:
        return int(bucket)
    return None


def _api_key() -> str | None:
    return (os.environ.get("TAOSTATS_API_KEY") or "").strip() or None


def _headers() -> dict[str, str]:
    key = _api_key()
    return {"Authorization": key, "Accept": "application/json"} if key else {}


def _get(session: requests.Session, params: dict[str, Any]) -> dict[str, Any]:
    url = f"{TAOSTATS_API_BASE}{STAKE_EVENTS_PATH}"
    for attempt in range(6):
        r = session.get(url, params=params, timeout=90)
        if r.status_code == 429:
            time.sleep(min(2 ** attempt, 30))
            continue
        r.raise_for_status()
        return r.json()
    r = session.get(url, params=params, timeout=90)
    r.raise_for_status()
    return r.json()


def fetch_trades(start: datetime, end: datetime) -> list[dict[str, Any]]:
    """SN21 stake and unstake trades of at least MIN_TAO, oldest first."""
    session = requests.Session()
    session.headers.update(_headers())
    out: list[dict[str, Any]] = []
    page = 1
    while page <= 40:
        payload = _get(session, {
            "netuid": NETUID,
            "trades_only": "true",
            "timestamp_start": int(start.timestamp()),
            "timestamp_end": int(end.timestamp()),
            "amount_min": int(MIN_TAO * 1_000_000_000),
            "limit": 200,
            "page": page,
            "order_by": "timestamp",
            "order_dir": "asc",
        })
        batch = payload.get("data") or []
        for e in batch:
            out.append({
                "ts": e["timestamp"].replace(".000Z", "Z"),
                "block": int(e["block_number"]),
                "action": e["action"],
                "tao": int(e["amount"]) / 1_000_000_000,
                "ck": e["coldkey"],
                "hk": e.get("hotkey_name") or "",
            })
        if len(batch) < 200:
            break
        page += 1
        time.sleep(0.3)
    return out


def _event_key(e: dict[str, Any]) -> tuple:
    return (e["block"], e["ck"], e["action"], round(float(e["tao"]), 4), e["ts"])


def merge_tape(existing: list[dict], fresh: list[dict], *, now: datetime) -> list[dict]:
    seen = {_event_key(e) for e in existing}
    merged = list(existing)
    for e in fresh:
        k = _event_key(e)
        if k not in seen:
            seen.add(k)
            merged.append(e)
    cutoff = now - timedelta(days=TAPE_DAYS)
    kept = [e for e in merged if _dt(e["ts"]) >= cutoff]
    kept.sort(key=lambda e: (e["block"], e["ts"], e["ck"]))
    return kept


def _size_modes(buys: list[dict]) -> list[int]:
    counts: Counter[int] = Counter()
    for b in buys:
        bucket = _round5(float(b["tao"]))
        if bucket is not None:
            counts[bucket] += 1
    return [size for size, _n in counts.most_common(3)]


def _hold_median_s(events: list[dict]) -> int | None:
    """FIFO match of buys to later sells. Median seconds the matched lot was open."""
    lots: list[list] = []
    holds: list[float] = []
    for e in events:
        if e["action"] == "stake":
            lots.append([float(e["tao"]), e])
            continue
        left = float(e["tao"])
        while left > 0.05 and lots:
            take = min(lots[0][0], left)
            if take > 0.5:
                holds.append((_dt(e["ts"]) - _dt(lots[0][1]["ts"])).total_seconds())
            lots[0][0] -= take
            left -= take
            if lots[0][0] <= 0.05:
                lots.pop(0)
    if not holds:
        return None
    return int(median(holds))


def _family(buys: int, round_frac: float | None, hold_s: int | None,
            same_block_frac: float, sell_tao: float, buy_tao: float) -> str:
    if buys >= 4 and same_block_frac >= 0.6:
        return "same_block_fade"
    if (round_frac or 0) >= 0.7 and hold_s is not None and hold_s <= 20 * 60 and buys >= 3:
        return "round_clip_fast"
    if (round_frac or 0) >= 0.7 and hold_s is not None and hold_s <= 8 * 3600 and buys >= 2:
        return "round_clip_slow"
    if sell_tao < 1 and buys >= 3 and buy_tao >= 30:
        return "accumulator"
    return "unclassified"


def _is_suspect(profile: dict) -> bool:
    if profile["family"] == "unclassified":
        return False
    if profile["family"] == "accumulator":
        return True
    flat = profile["flatness"]
    return (
        profile["n"] >= 4
        and profile["gross"] >= 40
        and flat is not None
        and flat <= 0.2
    )


def _classify_sell(sell: dict, own_buys: list[dict], our_buys: list[dict],
                   our_sells: list[dict]) -> str:
    own_before = [b for b in own_buys if b["block"] <= sell["block"]]
    if any(b["block"] == sell["block"] for b in own_before):
        return "same_block_own_buy"
    open_from = own_before[-1]["block"] if own_before else sell["block"] - 10_000
    best: tuple[int, int, str] | None = None
    ranked = {"after_our_sell": 0, "after_our_buy": 1}
    for kind, group in (("after_our_sell", our_sells), ("after_our_buy", our_buys)):
        for other in group:
            lag = sell["block"] - other["block"]
            if open_from < other["block"] <= sell["block"] and 0 <= lag <= RESPONSE_AFTER:
                cand = (lag, ranked[kind], kind)
                if best is None or cand < best:
                    best = cand
    if best is not None:
        return best[2]
    if own_before:
        return "timer_after_own_buy"
    return "unexplained"


def _profile(ck: str, events: list[dict], our_buys: list[dict], our_sells: list[dict],
             now: datetime) -> dict[str, Any]:
    events = sorted(events, key=lambda e: (e["block"], e["ts"]))
    buys = [e for e in events if e["action"] == "stake"]
    sells = [e for e in events if e["action"] == "unstake"]
    buy_tao = sum(float(e["tao"]) for e in buys)
    sell_tao = sum(float(e["tao"]) for e in sells)
    gross = buy_tao + sell_tao
    round_buys = sum(1 for e in buys if _round5(float(e["tao"])) is not None)
    same_block = sum(1 for b in buys if any(s["block"] == b["block"] for s in sells))
    hold_s = _hold_median_s(events)
    hks = Counter((e.get("hk") or "") for e in events)
    hk = hks.most_common(1)[0][0] if hks else ""
    first = _dt(events[0]["ts"]) if events else None
    last = _dt(events[-1]["ts"]) if events else None

    triggers = [
        _classify_sell(s, buys, our_buys, our_sells) for s in sells
    ]
    trigger_counts = dict(Counter(triggers))
    dominant = Counter(triggers).most_common(1)[0][0] if triggers else None

    # Count an our-clip the wallet could still have been answering: up to ~6 min
    # before its first trade in the window. Clips from before it existed stay out.
    life_from = (events[0]["block"] - RESPONSE_AFTER) if events else 0
    our_buys_in_life = [b for b in our_buys if b["block"] >= life_from] if events else []
    our_sells_in_life = [s for s in our_sells if s["block"] >= life_from] if events else []

    follow_lags: list[int] = []
    for ob in our_buys_in_life:
        lags = [
            b["block"] - ob["block"] for b in buys
            if -RESPONSE_BEFORE <= b["block"] - ob["block"] <= RESPONSE_AFTER
        ]
        if lags:
            follow_lags.append(min(lags, key=abs))
    sell_after_lags: list[int] = []
    for osell in our_sells_in_life:
        lags = [
            s["block"] - osell["block"] for s in sells
            if 0 <= s["block"] - osell["block"] <= RESPONSE_AFTER
        ]
        if lags:
            sell_after_lags.append(min(lags))

    days = sorted({_dt(e["ts"]).date().isoformat() for e in events})
    round_frac = (round_buys / len(buys)) if buys else None
    same_frac = (same_block / len(buys)) if buys else 0.0
    family = _family(len(buys), round_frac, hold_s, same_frac, sell_tao, buy_tao)
    return {
        "coldkey": ck,
        "n": len(events),
        "buys": len(buys),
        "sells": len(sells),
        "buy_tao": round(buy_tao, 2),
        "sell_tao": round(sell_tao, 2),
        "net_tao": round(buy_tao - sell_tao, 2),
        "gross": round(gross, 2),
        "flatness": round(abs(buy_tao - sell_tao) / gross, 3) if gross else None,
        "round_frac": round(round_frac, 2) if round_frac is not None else None,
        "same_block_frac": round(same_frac, 2),
        "hold_median_s": hold_s,
        "hotkey": hk,
        "sizes": _size_modes(buys),
        "family": family,
        "first_seen": _iso(first) if first else None,
        "last_seen": _iso(last) if last else None,
        "days_active": len(days),
        "active_days": days,
        "days_since_last": (now.date() - last.date()).days if last else None,
        "sell_trigger": dominant,
        "sell_trigger_counts": trigger_counts,
        "follow_hits": len(follow_lags),
        "follow_of": len(our_buys_in_life),
        "follow_lags": follow_lags,
        "sell_after_our_sell_hits": len(sell_after_lags),
        "sell_after_our_sell_of": len(our_sells_in_life),
        "sell_after_lags": sell_after_lags,
    }


def _score(p: dict) -> int:
    score = 0
    flat = p["flatness"]
    if flat is not None and flat <= 0.08:
        score += 25
    elif flat is not None and flat <= 0.15:
        score += 15
    if p["n"] >= 15:
        score += 20
    elif p["n"] >= 8:
        score += 12
    elif p["n"] >= 4:
        score += 6
    if p["days_active"] >= 3:
        score += 15
    elif p["days_active"] >= 2:
        score += 8
    if p["follow_hits"] >= 2 and p["follow_of"] and p["follow_hits"] / p["follow_of"] >= 0.25:
        score += 15
    counts = p["sell_trigger_counts"]
    sells = p["sells"]
    if sells >= 3 and p["sell_trigger"]:
        share = counts.get(p["sell_trigger"], 0) / sells
        if share >= 0.5:
            score += 15
    quiet = p["days_since_last"]
    if quiet is not None and quiet >= QUIET_STEP_DAYS:
        score -= 25
    if quiet is not None and quiet >= QUIET_FLOOR_DAYS:
        score -= 20
    return max(0, min(100, score))


def _confidence(score: int, days_since_last: int | None) -> str:
    if score >= 70:
        label = "high"
    elif score >= 45:
        label = "medium"
    else:
        label = "low"
    if days_since_last is None:
        return "low"
    if days_since_last >= QUIET_FLOOR_DAYS:
        return "low"
    if days_since_last >= QUIET_STEP_DAYS and label == "high":
        return "medium"
    return label


def _delta(prior: dict | None, confidence: str, score: int) -> str:
    if not prior:
        return "new"
    old = prior.get("confidence") or "low"
    if RANK[confidence] > RANK.get(old, 0):
        return "upgraded"
    if RANK[confidence] < RANK.get(old, 0):
        return "degraded"
    old_score = prior.get("confidence_score")
    if isinstance(old_score, (int, float)):
        if score - old_score >= 12:
            return "upgraded"
        if old_score - score >= 12:
            return "degraded"
    return "unchanged"


def _jaccard(a: list[int], b: list[int]) -> float:
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 1.0
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _replacements(profiles: dict[str, dict]) -> list[dict[str, Any]]:
    """Quiet signature matched to a coldkey that started as the old one stopped."""
    quiet = [
        p for p in profiles.values()
        if p["family"] != "unclassified"
        and p["n"] >= 4
        and (p["days_since_last"] or 0) >= QUIET_STEP_DAYS
    ]
    fresh = [
        p for p in profiles.values()
        if p["family"] != "unclassified"
        and p["n"] >= 4
        and p["first_seen"]
        and (p["days_since_last"] or 0) < QUIET_STEP_DAYS
    ]
    pairs: list[tuple[float, dict, dict]] = []
    for old in quiet:
        old_days = set(old["active_days"])
        for new in fresh:
            if new["coldkey"] == old["coldkey"] or new["family"] != old["family"]:
                continue
            if (new["hotkey"] or "") != (old["hotkey"] or ""):
                continue
            overlap = old_days & set(new["active_days"])
            # One shared day is a handover. More than that is two wallets running together.
            if len(overlap) > 1:
                continue
            if new["first_seen"][:10] < old["first_seen"][:10]:
                continue
            sim = _jaccard(old["sizes"], new["sizes"])
            if old["family"] != "same_block_fade" and sim < 0.34:
                continue
            pairs.append((sim, old, new))
    pairs.sort(key=lambda t: -t[0])
    used_old: set[str] = set()
    used_new: set[str] = set()
    out = []
    for sim, old, new in pairs:
        if old["coldkey"] in used_old or new["coldkey"] in used_new:
            continue
        used_old.add(old["coldkey"])
        used_new.add(new["coldkey"])
        out.append({
            "retired": old["coldkey"],
            "successor": new["coldkey"],
            "family": old["family"],
            "hotkey": old["hotkey"],
            "similarity": round(sim, 2),
            "reason": (
                f"{old['family']} on {old['hotkey'] or 'an unnamed hotkey'} went quiet "
                f"after {old['last_seen'][:10]}; {new['coldkey'][:8]}… started "
                f"{new['first_seen'][:10]} with the same sizes"
            ),
        })
    return out


def _behaviour(p: dict) -> str:
    sizes = "/".join(str(s) for s in p["sizes"]) or "odd"
    where = p["hotkey"] or "an unnamed hotkey"
    bits = [f"Buys {sizes}τ on {where}."]
    if p["follow_of"]:
        lag = int(median(p["follow_lags"])) if p["follow_lags"] else None
        lag_txt = f", median lag {lag} blocks" if lag is not None else ""
        bits.append(
            f"Bought after {p['follow_hits']} of {p['follow_of']} our clips{lag_txt}."
        )
    counts = p["sell_trigger_counts"]
    if p["sells"] and p["sell_trigger"]:
        n = counts.get(p["sell_trigger"], 0)
        hold = p["hold_median_s"]
        hold_txt = f" (~{max(1, round((hold or 0) / 60))} min hold)" if hold else ""
        label = {
            "same_block_own_buy": "Sells in the same block it buys",
            "after_our_sell": "Sells within 6 min of our sell",
            "after_our_buy": "Sells within 6 min of our buy",
            "timer_after_own_buy": f"Sells on a timer after its own buy{hold_txt}",
            "unexplained": "Sells with no nearby trigger",
        }[p["sell_trigger"]]
        bits.append(f"{label} ({n} of {p['sells']} sells).")
    elif p["sells"] == 0 and p["buys"]:
        bits.append("Has not sold in this window.")
    if p["sell_after_our_sell_of"]:
        bits.append(
            f"Sold after {p['sell_after_our_sell_hits']} of "
            f"{p['sell_after_our_sell_of']} our sells."
        )
    return " ".join(bits)


def _our_moves(events: list[dict], ours: set[str], tracked: set[str]) -> list[dict]:
    moves = [
        e for e in events
        if e["ck"] in ours and float(e["tao"]) >= OUR_MOVE_MIN_TAO
    ]
    out = []
    for m in moves:
        reply = [
            e for e in events
            if e["ck"] not in ours
            and -RESPONSE_BEFORE <= e["block"] - m["block"] <= RESPONSE_AFTER
            and not (e["action"] == "unstake" and e["block"] < m["block"])
        ]
        # Buys may lead us by a few blocks. Sells only count at or after our print.
        if m["action"] == "stake":
            reply_buys = [e for e in reply if e["action"] == "stake"]
            reply_sells = [e for e in reply if e["action"] == "unstake" and e["block"] >= m["block"]]
        else:
            reply_buys = [e for e in reply if e["action"] == "stake" and e["block"] >= m["block"]]
            reply_sells = [e for e in reply if e["action"] == "unstake" and e["block"] >= m["block"]]
        wallets = []
        for e in reply_buys + reply_sells:
            if e["ck"] not in tracked:
                continue
            wallets.append({
                "coldkey": e["ck"],
                "action": e["action"],
                "tao": round(float(e["tao"]), 2),
                "lag_blocks": e["block"] - m["block"],
            })
        wallets.sort(key=lambda w: -w["tao"])
        out.append({
            "ts": m["ts"],
            "block": m["block"],
            "action": m["action"],
            "tao": round(float(m["tao"]), 2),
            "hotkey": m.get("hk") or "",
            "reply_buy_tao": round(sum(float(e["tao"]) for e in reply_buys), 1),
            "reply_sell_tao": round(sum(float(e["tao"]) for e in reply_sells), 1),
            "reply_wallets": wallets[:12],
        })
    return out[-60:]


def _expectation(moves: list[dict], profiles: dict[str, dict]) -> dict[str, Any]:
    buys = [m for m in moves if m["action"] == "stake"]
    sells = [m for m in moves if m["action"] == "unstake"]

    def med(rows: list[dict], key: str) -> float | None:
        if not rows:
            return None
        return round(float(median([r[key] for r in rows])), 1)

    buyers = []
    sellers = []
    for p in profiles.values():
        if p["follow_hits"]:
            buyers.append({
                "coldkey": p["coldkey"],
                "hits": p["follow_hits"],
                "of": p["follow_of"],
                "median_lag_blocks": int(median(p["follow_lags"])),
            })
        if p["sell_after_our_sell_hits"]:
            sellers.append({
                "coldkey": p["coldkey"],
                "hits": p["sell_after_our_sell_hits"],
                "of": p["sell_after_our_sell_of"],
                "median_lag_blocks": int(median(p["sell_after_lags"])),
            })
    buyers.sort(key=lambda r: (-r["hits"], r["median_lag_blocks"]))
    sellers.sort(key=lambda r: (-r["hits"], r["median_lag_blocks"]))
    return {
        "our_buys": len(buys),
        "our_sells": len(sells),
        "median_reply_buy_tao": med(buys, "reply_buy_tao"),
        "median_reply_sell_tao_after_our_buy": med(buys, "reply_sell_tao"),
        "median_reply_sell_tao_after_our_sell": med(sells, "reply_sell_tao"),
        "wallets_that_buy_after_us": buyers[:12],
        "wallets_that_sell_when_we_sell": sellers[:12],
    }


def analyse(
    events: list[dict],
    ours: list[str],
    *,
    now: datetime,
    seed_coldkeys: list[str] | None = None,
    prior_wallets: dict[str, dict] | None = None,
) -> dict[str, Any]:
    """Pure pass over a trade tape. No network, no disk."""
    ours_set = set(ours)
    seeds = set(seed_coldkeys or [])
    prior = prior_wallets or {}
    window_start = now - timedelta(days=SCORE_DAYS)
    window = [e for e in events if _dt(e["ts"]) >= window_start]
    by_ck: dict[str, list] = defaultdict(list)
    for e in window:
        by_ck[e["ck"]].append(e)

    our_buys = [
        e for e in window
        if e["ck"] in ours_set and e["action"] == "stake" and float(e["tao"]) >= OUR_MOVE_MIN_TAO
    ]
    our_sells = [
        e for e in window
        if e["ck"] in ours_set and e["action"] == "unstake" and float(e["tao"]) >= OUR_MOVE_MIN_TAO
    ]

    profiles: dict[str, dict] = {}
    for ck, ev in by_ck.items():
        if ck in ours_set:
            continue
        profiles[ck] = _profile(ck, ev, our_buys, our_sells, now)

    # Seeds and previously watched keys stay on the map after they go quiet,
    # so a silent week can degrade them instead of deleting them.
    for ck in seeds | set(prior):
        if ck in ours_set or ck in profiles:
            continue
        empty = _profile(ck, [], our_buys, our_sells, now)
        last = (prior.get(ck) or {}).get("last_seen")
        if last:
            empty["last_seen"] = last
            empty["days_since_last"] = (now.date() - _dt(last).date()).days
            empty["family"] = (prior.get(ck) or {}).get("family") or "unclassified"
            empty["hotkey"] = (prior.get(ck) or {}).get("hotkey") or ""
            empty["sizes"] = (prior.get(ck) or {}).get("sizes") or []
        profiles[ck] = empty

    tracked_keys = {
        ck for ck, p in profiles.items()
        if ck in seeds or ck in prior or _is_suspect(p)
    }
    profiles = {ck: profiles[ck] for ck in tracked_keys}

    replacements = _replacements(profiles)
    retired = {r["retired"] for r in replacements}
    successor = {r["successor"]: r["retired"] for r in replacements}

    wallets: dict[str, dict] = {}
    for ck, p in profiles.items():
        score = _score(p)
        days_quiet = p["days_since_last"]
        quiet_days = p["days_since_last"]
        if quiet_days is None and p["n"] == 0:
            quiet_days = 999
        confidence = _confidence(score, quiet_days)
        if ck in retired:
            confidence = RANK_NAME[max(0, RANK[confidence] - 1)]
        status = "recycled_out" if ck in retired else ("quiet" if (days_quiet or 0) >= QUIET_STEP_DAYS or p["n"] == 0 else "active")
        row = {
            "coldkey": ck,
            "family": p["family"],
            "confidence": confidence,
            "confidence_score": score,
            "confidence_delta": _delta(prior.get(ck), confidence, score),
            "status": status,
            "replaced": successor.get(ck),
            "hotkey": p["hotkey"],
            "sizes": p["sizes"],
            "buy_tao": p["buy_tao"],
            "sell_tao": p["sell_tao"],
            "net_tao": p["net_tao"],
            "flatness": p["flatness"],
            "hold_median_s": p["hold_median_s"],
            "first_seen": p["first_seen"],
            "last_seen": p["last_seen"],
            "days_active": p["days_active"],
            "days_since_last": p["days_since_last"],
            "follow_hits": p["follow_hits"],
            "follow_of": p["follow_of"],
            "sell_trigger": p["sell_trigger"],
            "sell_trigger_counts": p["sell_trigger_counts"],
            "sell_after_our_sell_hits": p["sell_after_our_sell_hits"],
            "sell_after_our_sell_of": p["sell_after_our_sell_of"],
            "behaviour": _behaviour(p),
        }
        # Keep the lag lists off the public row; behaviour() already consumed them.
        wallets[ck] = row

    moves = _our_moves(window, ours_set, set(wallets))
    return {
        "wallets": wallets,
        "replacements": replacements,
        "our_moves": moves,
        "expectation": _expectation(moves, profiles),
        "window_start": _iso(window_start),
        "window_end": _iso(now),
    }


def _upsert_history(history: list[dict], row: dict) -> list[dict]:
    kept = [h for h in history if h.get("date") != row["date"]]
    kept.append(row)
    return kept[-HISTORY_DAYS:]


def run_bot_watch(
    *,
    events: list[dict] | None = None,
    seed_coldkeys: list[str] | None = None,
    ours: list[str] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """One daily pass. Pass `events` to skip the network (tests, replays)."""
    now = now or _now()
    ours = ours if ours is not None else our_coldkeys()
    if seed_coldkeys is None:
        from labels import bot_set
        seed_coldkeys = sorted(bot_set())

    prior_doc = load_json(BOT_WATCH_STORE, {})
    prior_wallets = prior_doc.get("wallets") or {}

    if events is None:
        if not _api_key():
            logger.warning("Bot watch skipped: TAOSTATS_API_KEY not set")
            return {"skipped": True, "reason": "missing TAOSTATS_API_KEY"}
        tape = load_json(BOT_WATCH_TAPE, [])
        start = now - timedelta(days=SCORE_DAYS)
        if tape:
            start = max(start, _dt(tape[-1]["ts"]) - timedelta(hours=2))
        try:
            fresh = fetch_trades(start, now)
        except Exception:
            logger.exception("Bot watch fetch failed; scoring the tape on disk")
            fresh = []
        events = merge_tape(tape if isinstance(tape, list) else [], fresh, now=now)
        save_json(BOT_WATCH_TAPE, events)
    else:
        events = merge_tape([], events, now=now)

    scored = analyse(
        events, ours, now=now,
        seed_coldkeys=seed_coldkeys,
        prior_wallets=prior_wallets if isinstance(prior_wallets, dict) else {},
    )
    wallets = scored["wallets"]
    day = now.date().isoformat()
    history_row = {
        "date": day,
        "ran_at": _iso(now),
        "active": sum(1 for w in wallets.values() if w["status"] == "active"),
        "high": sum(1 for w in wallets.values() if w["confidence"] == "high"),
        "upgraded": [ck for ck, w in wallets.items() if w["confidence_delta"] == "upgraded"],
        "degraded": [ck for ck, w in wallets.items() if w["confidence_delta"] == "degraded"],
        "new": [ck for ck, w in wallets.items() if w["confidence_delta"] == "new"],
        "recycled": scored["replacements"],
    }
    doc = {
        "updated_at": _iso(now),
        "ours": ours,
        "window_start": scored["window_start"],
        "window_end": scored["window_end"],
        "expectation": scored["expectation"],
        "replacements": scored["replacements"],
        "wallets": wallets,
        "our_moves": scored["our_moves"],
        "history": _upsert_history(list(prior_doc.get("history") or []), history_row),
    }
    save_json(BOT_WATCH_STORE, doc)
    logger.info(
        "Bot watch: %d wallets (%d high, %d active) · our buys %s · upgraded %d · degraded %d · recycled %d",
        len(wallets),
        history_row["high"],
        history_row["active"],
        scored["expectation"]["our_buys"],
        len(history_row["upgraded"]),
        len(history_row["degraded"]),
        len(scored["replacements"]),
    )
    return doc


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = run_bot_watch()
    exp = result.get("expectation") or {}
    print(
        f"wallets={len(result.get('wallets') or {})} "
        f"our_buys={exp.get('our_buys')} "
        f"median_reply_buy={exp.get('median_reply_buy_tao')} "
        f"median_reply_sell_after_our_sell={exp.get('median_reply_sell_tao_after_our_sell')}"
    )
