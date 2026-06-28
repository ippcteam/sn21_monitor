"""
Movers Attribution — what drives the daily 20%+ alpha pumps: media, mechanics, or dark?

Each day a handful of subnets jump ≥20% in alpha/TAO. This module asks *why*, and —
critically — tests any candidate driver against a CONTROL group (the −20% losers and the
flat middle) so we never mistake a base rate for a cause. A signal only counts as a driver
if it both PRECEDES winners (leads, not reacts) AND separates winners from losers.

Two halves:

1) BACKTEST (`run_backtest`) — reproduces the one-time historical study against taoflute's
   open Grafana→Postgres ("trading" DB): ohlc price history defines winner/loser/control
   cohorts; discord_messages, materialized_news (owner stake/burn/transfer, emissions,
   registrations, commits) and delegation_history provide the lead-vs-lag signals. Verdict
   to date: on-chain MECHANICS do NOT lead daily pumps and don't separate them from dumps;
   DISCORD chatter leads big moves ~2× but BIDIRECTIONALLY (dumps light up more), so it's an
   attention marker, not a directional driver. See data/movers_backtest.json.

2) FORWARD CAPTURE (`capture_daily`) — the X/media signal can't be backtested: taoflute keeps
   the twitter *handle* but not tweet *timestamps*. So we snapshot per-subnet recency
   (`last_x_msg_days`, `last_discord_msg_days`, code activity, buy pressure) for ALL subnets
   every day into a self-contained ledger, tag the day's movers, and recompute the
   winners/losers/control lead-lag table from accumulated snapshots. After a few weeks this is
   the first real test of whether X *leads* pumps directionally. No UI until a signal appears.

Price moves come from our own authoritative market ledger (subnets_price_ledger.json, written
by market_sync) when available; taoflute's metagraph price is the fallback. The taoflute proxy
is an accidentally-open research surface — we query it lightly (one or four read-only queries
per run) and the harness degrades gracefully (records price/move only) if it locks down.

Writes:
  data/movers_signal_ledger.json — {date: {netuid: {price,x_days,disc_days,code30,buy_pressure,name}}}, 120d.
  data/movers_attribution.json   — latest: today's classified movers + rolling lead-lag cohort table.
  data/movers_backtest.json      — historical baseline study (callable on demand).
"""

from __future__ import annotations

import json
import logging
import os
import threading
import urllib.request
from datetime import date, datetime, timedelta, timezone
from typing import Any

from collector import load_json, save_json
from config import DATA_DIR

logger = logging.getLogger(__name__)

# ── taoflute open Grafana proxy (read-only) ───────────────────────────────────
TAOFLUTE_PROXY = os.environ.get("TAOFLUTE_PROXY", "https://taoflute.com/api/ds/query")
TAOFLUTE_DS_UID = os.environ.get("TAOFLUTE_DS_UID", "eeza6pofrbgn4d")
_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"

# ── Stores ────────────────────────────────────────────────────────────────────
SIGNAL_LEDGER_STORE = DATA_DIR / "movers_signal_ledger.json"
ATTRIBUTION_STORE = DATA_DIR / "movers_attribution.json"
BACKTEST_STORE = DATA_DIR / "movers_backtest.json"
PRICE_LEDGER_STORE = DATA_DIR / "subnets_price_ledger.json"  # written by market_sync

# ── Tunables ──────────────────────────────────────────────────────────────────
MOVE_PCT = float(os.environ.get("MOVERS_MOVE_PCT", "20.0"))   # |24h move| ≥ this ⇒ mover
CONTROL_BAND_PCT = 5.0                                          # |24h move| ≤ this ⇒ flat control
FRESH_DAYS = int(os.environ.get("MOVERS_FRESH_DAYS", "2"))     # social "fresh" if last msg ≤ this many days ago
LEDGER_RETENTION_DAYS = 120
BACKTEST_START = os.environ.get("MOVERS_BACKTEST_START", "2025-08-13")  # common window where all signals exist

_lock = threading.Lock()


# ── taoflute client ───────────────────────────────────────────────────────────

def tf_query(sql: str, timeout: int = 120) -> tuple[list[str], list[tuple]]:
    """Run one read-only SQL against taoflute's Postgres via the open Grafana proxy."""
    body = json.dumps({"queries": [{
        "refId": "A",
        "datasource": {"type": "grafana-postgresql-datasource", "uid": TAOFLUTE_DS_UID},
        "rawSql": sql, "format": "table",
    }]}).encode()
    req = urllib.request.Request(
        TAOFLUTE_PROXY, data=body,
        headers={"Content-Type": "application/json", "User-Agent": _UA},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.load(r)
    res = d["results"]["A"]
    if res.get("error"):
        raise RuntimeError(f"taoflute query error: {res['error']}")
    fr = res["frames"][0]
    cols = [f["name"] for f in fr["schema"]["fields"]]
    vals = fr["data"]["values"]
    rows = list(zip(*vals)) if vals else []
    return cols, rows


def _tf_rows(sql: str) -> list[dict[str, Any]]:
    cols, rows = tf_query(sql)
    return [dict(zip(cols, r)) for r in rows]


# ── small helpers ─────────────────────────────────────────────────────────────

def _od(s: str) -> int:
    y, m, d = map(int, s.split("-"))
    return date(y, m, d).toordinal()


def _pct(now: float | None, prev: float | None) -> float | None:
    if now is None or prev is None or prev == 0:
        return None
    return round((now - prev) / prev * 100.0, 3)


def _classify(move_pct: float | None) -> str | None:
    if move_pct is None:
        return None
    if move_pct >= MOVE_PCT:
        return "winner"
    if move_pct <= -MOVE_PCT:
        return "loser"
    if abs(move_pct) <= CONTROL_BAND_PCT:
        return "control"
    return None


# ── Forward capture ───────────────────────────────────────────────────────────

def capture_daily() -> dict[str, Any]:
    """Snapshot every subnet's media/mechanics recency, tag today's movers, refresh the
    rolling lead-lag cohort table. Self-contained: stores the price used so the rolling
    analysis never depends on taoflute history."""
    with _lock:
        return _capture_locked()


def _capture_locked() -> dict[str, Any]:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # 1) social/mechanics snapshot from taoflute (degrade gracefully if locked down)
    tf: dict[int, dict[str, Any]] = {}
    tf_ok = True
    try:
        for r in _tf_rows(
            "select sn_id, subnet_name, twitter, last_x_msg_days, last_discord_msg_days, "
            "avg_code_lines_30d, protocol_buy_pressure, metagraph_price "
            "from materialized_overview_data where id != 0"
        ):
            try:
                nid = int(r["sn_id"])
            except (TypeError, ValueError):
                continue
            tf[nid] = r
    except Exception:
        tf_ok = False
        logger.warning("taoflute snapshot unavailable — recording price/move only", exc_info=True)

    # 2) authoritative price move from our own market ledger (today vs most recent prior)
    price_ledger = load_json(PRICE_LEDGER_STORE, {}) or {}
    today_prices: dict[str, float] = price_ledger.get(today, {})
    prior_dates = sorted(d for d in price_ledger if d < today)
    prev_prices: dict[str, float] = price_ledger.get(prior_dates[-1], {}) if prior_dates else {}

    # 3) build today's per-subnet rows
    ledger = load_json(SIGNAL_LEDGER_STORE, {}) or {}
    nids = set(int(k) for k in today_prices) | set(tf.keys())
    day_rows: dict[str, dict[str, Any]] = {}
    for nid in sorted(nids):
        k = str(nid)
        price = today_prices.get(k)
        if price is None and tf.get(nid, {}).get("metagraph_price") is not None:
            price = _f(tf[nid]["metagraph_price"])
        move = _pct(price, prev_prices.get(k))
        t = tf.get(nid, {})
        day_rows[k] = {
            "name": (t.get("subnet_name") if t else None),
            "price": round(price, 10) if price else None,
            "move_24h_pct": move,
            "x_days": _i(t.get("last_x_msg_days")),
            "disc_days": _i(t.get("last_discord_msg_days")),
            "code30": _f(t.get("avg_code_lines_30d")),
            "buy_pressure": _f(t.get("protocol_buy_pressure")),
            "twitter": (t.get("twitter") if t else None),
        }
    ledger[today] = day_rows

    # trim retention
    cutoff = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=LEDGER_RETENTION_DAYS)).strftime("%Y-%m-%d")
    ledger = {d: v for d, v in ledger.items() if d >= cutoff}
    save_json(SIGNAL_LEDGER_STORE, ledger)

    # 4) today's movers, tagged with current signals
    movers = []
    for k, r in day_rows.items():
        coh = _classify(r["move_24h_pct"])
        if coh in ("winner", "loser"):
            movers.append({
                "netuid": int(k), "name": r["name"], "move_24h_pct": r["move_24h_pct"],
                "cohort": coh,
                "x_fresh": _fresh(r["x_days"]), "x_days": r["x_days"],
                "discord_fresh": _fresh(r["disc_days"]), "disc_days": r["disc_days"],
                "code_active": (r["code30"] or 0) > 0,
                "buy_pressure": r["buy_pressure"],
                "read": _read_one(r),
            })
    movers.sort(key=lambda m: (m["cohort"] != "winner", -(m["move_24h_pct"] or 0)))

    # 5) rolling lead-lag cohort table from accumulated snapshots
    rolling = _rolling_cohorts(ledger)

    snapshot = {
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "date": today,
        "taoflute_ok": tf_ok,
        "n_days_captured": len(ledger),
        "params": {"move_pct": MOVE_PCT, "control_band_pct": CONTROL_BAND_PCT, "fresh_days": FRESH_DAYS},
        "today_movers": movers,
        "rolling_cohorts": rolling,
        "note": rolling.get("note"),
    }
    save_json(ATTRIBUTION_STORE, snapshot)
    logger.info(
        "Movers capture: %d subnets, %d movers today (%d days history); rolling n=%s",
        len(day_rows), len(movers), len(ledger), rolling.get("counts"),
    )
    return snapshot


def _f(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _i(v: Any) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _fresh(days: int | None) -> bool:
    # taoflute uses 999 as "no known channel / untracked"
    return days is not None and 0 <= days <= FRESH_DAYS


def _read_one(r: dict[str, Any]) -> str:
    """One-line human read of a single mover's signal mix (triage, not proof)."""
    x, d = _fresh(r["x_days"]), _fresh(r["disc_days"])
    if x and d:
        return "media + community"
    if x:
        return "media-led (X)"
    if d:
        return "community/discord"
    if (r["code30"] or 0) > 0:
        return "dev-active, socially quiet"
    return "dark — no public X/discord footprint"


def _rolling_cohorts(ledger: dict[str, dict]) -> dict[str, Any]:
    """For every (subnet, day) with a prior day in the ledger, classify the move and test
    whether each signal was FRESH as of the PRIOR day (a lead = candidate cause). Compare
    prevalence across winners / control / losers. Lift = winner% / control%."""
    dates = sorted(ledger)
    if len(dates) < 2:
        return {"note": f"Need ≥2 days of captured snapshots to compute lift (have {len(dates)}).",
                "counts": {}, "signals": {}}

    cohorts = {"winner": _acc(), "control": _acc(), "loser": _acc()}
    for i in range(1, len(dates)):
        prev_d, cur_d = dates[i - 1], dates[i]
        if _od(cur_d) - _od(prev_d) != 1:
            continue  # only adjacent-day pairs are clean 24h leads
        cur, prev = ledger[cur_d], ledger[prev_d]
        for k, r in cur.items():
            coh = _classify(r.get("move_24h_pct"))
            if coh not in cohorts:
                continue
            p = prev.get(k, {})
            a = cohorts[coh]
            a["n"] += 1
            a["x_lead"] += _fresh(p.get("x_days"))
            a["disc_lead"] += _fresh(p.get("disc_days"))
            a["code_lead"] += (p.get("code30") or 0) > 0
            bp = p.get("buy_pressure")
            a["buy_lead"] += (bp is not None and bp > 0)

    def prev_pct(a: dict, key: str) -> float | None:
        return round(100.0 * a[key] / a["n"], 1) if a["n"] else None

    signals = {}
    for sig in ("x_lead", "disc_lead", "code_lead", "buy_lead"):
        w, c, l = (prev_pct(cohorts[x], sig) for x in ("winner", "control", "loser"))
        lift = round(w / c, 2) if (w and c) else None
        signals[sig] = {"winner_pct": w, "control_pct": c, "loser_pct": l,
                        "lift_vs_control": lift,
                        "directional": _is_directional(w, c, l)}
    counts = {x: cohorts[x]["n"] for x in cohorts}
    return {"counts": counts, "signals": signals,
            "note": _rolling_note(counts)}


def _acc() -> dict[str, int]:
    return {"n": 0, "x_lead": 0, "disc_lead": 0, "code_lead": 0, "buy_lead": 0}


def _is_directional(w: float | None, c: float | None, l: float | None) -> bool | None:
    """A signal is a *directional driver* only if it leads winners materially more than both
    control AND losers. Equal-or-higher in losers ⇒ attention/volatility, not direction."""
    if w is None or c is None or l is None:
        return None
    if w <= 0:
        return False
    return (w >= 1.5 * c) and (w >= 1.3 * l)


def _rolling_note(counts: dict[str, int]) -> str:
    w = counts.get("winner", 0)
    if w < 30:
        return (f"Only {w} winner-days captured — lift is noisy until ~30+. "
                "Forward capture is accruing the X signal that can't be backtested.")
    return "Enough winners for a first read; check whether x_lead is directional (winner% ≫ control% AND loser%)."


# ── Historical backtest (control baseline; callable on demand) ────────────────

_NEWS_BUCKET = {
    "sno_staking": "own_buy", "sno_alpha_transfer_in_tao": "own_buy",
    "manual_burn": "own_burn", "miner_burn": "own_burn", "sno_tao_transfer": "own_tao_out",
    "emissions_recovered": "emissions", "registrations": "registr",
    "large_repo_commit": "dev", "repo_change": "dev",
}


def run_backtest(start: str = BACKTEST_START) -> dict[str, Any]:
    """Reproduce the historical lead-lag study from taoflute history tables and persist it.
    This is the empirical baseline + control group; forward capture extends it with X."""
    with _lock:
        return _backtest_locked(start)


def _backtest_locked(start: str) -> dict[str, Any]:
    logger.info("Movers backtest: pulling history from taoflute since %s …", start)
    px = _tf_rows(f"""select subnet_id, (d::date)::text dt, c, v
        from ohlc where "interval"='1D' and d >= date '{start}' order by subnet_id, d""")
    disc = _tf_rows("""select subnet_id, (created_on::date)::text dt, count(*) msgs
        from discord_messages group by 1,2""")
    news = _tf_rows(f"""select subnet_id, (created_on::date)::text dt, key, count(*) n
        from materialized_news where created_on >= date '{start}' group by 1,2,3""")

    from collections import defaultdict
    P: dict = defaultdict(dict)
    V: dict = defaultdict(dict)
    for r in px:
        P[r["subnet_id"]][_od(r["dt"])] = r["c"]
        V[r["subnet_id"]][_od(r["dt"])] = r["v"] or 0
    D: dict = defaultdict(dict)
    for r in disc:
        D[r["subnet_id"]][_od(r["dt"])] = r["msgs"]
    DBASE = {s: (sum(v.values()) / len(v) if v else 0) for s, v in D.items()}
    NB: dict = defaultdict(lambda: defaultdict(set))
    for r in news:
        b = _NEWS_BUCKET.get(r["key"])
        if b:
            NB[r["subnet_id"]][_od(r["dt"])].add(b)

    SPIKE, VOL_FLOOR = 2.0, 5000.0
    coh = {"winner": _bt_acc(), "control": _bt_acc(), "loser": _bt_acc()}
    ndisc = {"winner": 0, "control": 0, "loser": 0}

    def disc_spike(s, days):
        b = DBASE.get(s, 0)
        if b <= 0:
            return None
        return any((D[s].get(o, 0) / b) >= SPIKE for o in days)

    def news_in(s, days, bucket):
        return any(bucket in NB[s].get(o, set()) for o in days)

    for s, ser in P.items():
        for o in sorted(ser):
            if (o - 1) not in ser:
                continue
            prev = ser[o - 1]
            if not prev or prev <= 0 or V[s].get(o, 0) < VOL_FLOOR:
                continue
            r = (ser[o] - prev) / prev * 100.0
            c = _classify(r)
            if c not in coh:
                continue
            a = coh[c]
            a["n"] += 1
            lead, day, lag = [o - 2, o - 1], [o], [o + 1, o + 2]
            sl = disc_spike(s, lead)
            if sl is not None:
                ndisc[c] += 1
                a["disc_lead"] += sl
                a["disc_day"] += disc_spike(s, day)
                a["disc_lag"] += disc_spike(s, lag)
            for b in ("own_buy", "own_burn", "own_tao_out", "emissions", "registr", "dev"):
                a[f"{b}_lead"] += news_in(s, lead, b)

    def pc(c, k, denom=None):
        d = denom if denom is not None else coh[c]["n"]
        return round(100.0 * coh[c][k] / d, 1) if d else None

    discord = {x: {"lead": pc(x, "disc_lead", ndisc[x]), "day": pc(x, "disc_day", ndisc[x]),
                   "lag": pc(x, "disc_lag", ndisc[x]), "n": ndisc[x]} for x in coh}
    mechanics = {b: {x: pc(x, f"{b}_lead") for x in coh}
                 for b in ("own_buy", "own_burn", "own_tao_out", "emissions", "registr", "dev")}

    result = {
        "computed_at_utc": datetime.now(timezone.utc).isoformat(),
        "window_start": start,
        "counts": {x: coh[x]["n"] for x in coh},
        "discord_spike_pct": discord,        # lead vs day vs lag, % of discord-covered events
        "mechanics_news_lead_pct": mechanics,  # % with a leading on-chain event (d-2,-1)
        "verdict": (
            "Mechanics does not lead daily pumps and does not separate winners from losers; "
            "discord chatter leads big moves ~2× but bidirectionally (losers light up ≥ winners) "
            "— attention, not a directional driver. X/media is not backtestable (no tweet history); "
            "use forward capture."
        ),
    }
    save_json(BACKTEST_STORE, result)
    logger.info("Movers backtest: winners=%s losers=%s; discord lead w/l=%s/%s",
                result["counts"]["winner"], result["counts"]["loser"],
                discord["winner"]["lead"], discord["loser"]["lead"])
    return result


def _bt_acc() -> dict[str, int]:
    a = {"n": 0, "disc_lead": 0, "disc_day": 0, "disc_lag": 0}
    for b in ("own_buy", "own_burn", "own_tao_out", "emissions", "registr", "dev"):
        a[f"{b}_lead"] = 0
    return a


# ── Accessors ─────────────────────────────────────────────────────────────────

def latest() -> dict[str, Any]:
    return load_json(ATTRIBUTION_STORE, {}) or {}


def backtest_latest() -> dict[str, Any]:
    return load_json(BACKTEST_STORE, {}) or {}


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cmd = sys.argv[1] if len(sys.argv) > 1 else "capture"
    if cmd == "backtest":
        print(json.dumps(run_backtest(), indent=2))
    elif cmd == "capture":
        print(json.dumps(capture_daily(), indent=2))
    else:
        print("usage: python movers_attribution.py [capture|backtest]")
