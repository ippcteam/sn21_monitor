"""
Flow event-study harness — does a discrete event cause DURABLE net TAO inflow?

Step 1 of the valuation research established that SN21's binding lever is *net TAO
inflow*, not the daily price pump that movers_attribution.py studies. This module
re-asks the attribution question with flow as the dependent variable, using a
proper event-study counterfactual (abnormal flow vs each subnet's own baseline).

WHY this is not a rerun of movers_attribution:
  - movers DV  = a ±20% daily PRICE move (transient, tautological with volume).
  - flow DV    = signed net TAO STAKED into the subnet (the thing that must rise,
                 and STAY, to climb the alpha-value ranks).
  A buyback can create sticky flow without ever printing a 20% candle — invisible
  to movers, visible here.

DATA (taoflute open Grafana→Postgres, see [[taoflute-data-source]]):
  - delegation_history (153k rows, 2025-07-27→): signed stake ops. amount = TAO(rao),
    action DELEGATE/UNDELEGATE, netuid, delegate_name ("Owner17" ⇒ owner), is_transfer.
    Aggregated server-side into a daily net-flow series per subnet, split owner/non-owner.
    Transfers (is_transfer) are EXCLUDED — they move stake between holders, not into the pool.
  - materialized_news: datable events (manual_burn, miner_burn, emissions_recovered,
    registrations, large_repo_commit, sno_staking, …) per subnet per day.

METHOD (classic event study, applied to flow):
  For each event (subnet s, day E):
    baseline μ_s, σ_s  = mean/sd of s's daily net flow over the whole window.
    abnormal flow AF_t = flow_t − μ_s.
    pre[-3..-1] (leakage), day[0], post CAF[+1..+7] (cumulative abnormal flow).
  Aggregate CAF across all events of a type; report raw-TAO mean, a standardized
  z (CAF / (σ_s·√h)) for cross-subnet comparability, %positive, and a t-stat vs 0.
  Null: AF is de-meaned, so E[CAF]=0 — a significant positive mean ⇒ the event
  predicts above-baseline inflow. The DV is NON-OWNER net flow by default, so an
  owner action (burn/stake) is tested for whether it catalyses OUTSIDE demand,
  not merely for moving the owner's own stake (which would be circular).

CLI:  python flow_events.py [run|sn21]
Writes data/flow_events.json.
"""
from __future__ import annotations

import json
import logging
import math
import os
from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Any

from collector import load_json, save_json  # noqa: F401  (save_json used)
from config import DATA_DIR
from movers_attribution import tf_query  # reuse the courteous read-only client

logger = logging.getLogger(__name__)

STORE = DATA_DIR / "flow_events.json"
NETUID_SN21 = 21

# delegation_history starts here; align everything to it.
WINDOW_START = os.environ.get("FLOW_WINDOW_START", "2025-07-27")

# event-study windows (trading days relative to event day E=0)
PRE = (-3, -1)      # leakage / anticipation
POST = (1, 7)       # durable response
POST_LONG = (1, 21) # does it persist three weeks?

# event types worth testing for a *catalytic* (non-owner) flow response.
# (sno_staking / sno_alpha_transfer_in_tao are owner buys — tested separately as
#  the buyback-catalyst question, since using them with non-owner DV is the cleanest
#  test of "does the owner buying make others buy?".)
EVENT_KEYS = [
    "manual_burn", "miner_burn", "emissions_recovered",
    "registrations", "large_repo_commit", "name_change", "twitter_change",
]
OWNER_BUY_KEYS = ["sno_staking", "sno_alpha_transfer_in_tao"]


# ── helpers ───────────────────────────────────────────────────────────────────

def _od(s: str) -> int:
    y, m, d = map(int, s[:10].split("-"))
    return date(y, m, d).toordinal()


def _tf_rows(sql: str) -> list[dict[str, Any]]:
    cols, rows = tf_query(sql, timeout=180)
    return [dict(zip(cols, r)) for r in rows]


def _mean(xs): return sum(xs) / len(xs) if xs else 0.0
def _sd(xs):
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


# ── 1) build the daily net-flow series (server-side aggregation) ──────────────

def build_flow_series() -> dict[int, dict[int, dict[str, float]]]:
    """{netuid: {ordinal: {'net':TAO, 'owner':TAO, 'nonowner':TAO}}}, transfers excluded."""
    sql = f"""
    select (json->>'netuid')::int netuid,
           (created_on::date)::text dt,
           sum(case when json->>'action'='DELEGATE'   then  (json->>'amount')::numeric
                    when json->>'action'='UNDELEGATE' then -(json->>'amount')::numeric
                    else 0 end)/1e9 net_tao,
           sum(case when lower(coalesce(json->>'delegate_name','')) like 'owner%' then
                      case when json->>'action'='DELEGATE'   then  (json->>'amount')::numeric
                           when json->>'action'='UNDELEGATE' then -(json->>'amount')::numeric
                           else 0 end
                    else 0 end)/1e9 owner_tao
    from delegation_history
    where coalesce((json->>'is_transfer')::boolean, false) = false
      and created_on >= date '{WINDOW_START}'
    group by 1, 2
    """
    series: dict[int, dict[int, dict[str, float]]] = defaultdict(dict)
    for r in _tf_rows(sql):
        nid = r["netuid"]
        if nid is None:
            continue
        o = _od(r["dt"])
        net = float(r["net_tao"] or 0.0)
        owner = float(r["owner_tao"] or 0.0)
        series[int(nid)][o] = {"net": net, "owner": owner, "nonowner": net - owner}
    return series

# CAUTION (verified 2026-06-29): the `owner` bucket (delegate_name like 'owner%') does
# NOT mean "owner BUYING". For SN21 it is dominated by owner-SHARE EMISSION auto-staking
# (hotkey "Owner21": a daily, monotonically-growing DELEGATE = compounding reward, each
# paired with an is_transfer UNDELEGATE that moves it out). Do NOT read `owner` > 0 as a
# market buy or "owner support". The DVs used by the study are `nonowner`, which excludes
# this, so the event-study / cross-section results are unaffected — but never cite the
# `owner` series as evidence of buyback/commitment. See [[sn21-owner-share-stake-watch]].


def _densify(days: dict[int, dict[str, float]], lo: int, hi: int, key: str) -> dict[int, float]:
    """Fill every ordinal in [lo,hi] with the flow value (0 = no staking activity)."""
    return {o: days.get(o, {}).get(key, 0.0) for o in range(lo, hi + 1)}


# ── 2) events ─────────────────────────────────────────────────────────────────

def build_events() -> dict[str, list[tuple[int, int]]]:
    """{event_key: [(netuid, ordinal), …]} from materialized_news within the window."""
    keys = EVENT_KEYS + OWNER_BUY_KEYS
    in_list = ",".join(f"'{k}'" for k in keys)
    sql = f"""
    select subnet_id netuid, (created_on::date)::text dt, key
    from materialized_news
    where created_on >= date '{WINDOW_START}' and key in ({in_list})
    group by 1,2,3
    """
    ev: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for r in _tf_rows(sql):
        if r["netuid"] is None:
            continue
        ev[r["key"]].append((int(r["netuid"]), _od(r["dt"])))
    return ev


# ── 3) the event study ────────────────────────────────────────────────────────

def _study_one(series, events, dv: str, pre=PRE, post=POST) -> dict[str, Any]:
    """Aggregate abnormal-flow response across one event list. DV ∈ net|owner|nonowner."""
    caf_raw, caf_z, pre_raw, day0_raw = [], [], [], []
    used = 0
    for nid, E in events:
        days = series.get(nid)
        if not days:
            continue
        os_ = sorted(days)
        lo, hi = os_[0], os_[-1]
        # need full post window inside the subnet's observed range
        if E + post[1] > hi or E + pre[0] < lo:
            continue
        dense = _densify(days, lo, hi, dv)
        vals = list(dense.values())
        mu, sd = _mean(vals), _sd(vals)
        if sd <= 0:
            continue
        af = {o: v - mu for o, v in dense.items()}
        pre_af = _mean([af[o] for o in range(E + pre[0], E + pre[1] + 1)])
        day0 = af[E]
        post_caf = sum(af[o] for o in range(E + post[0], E + post[1] + 1))
        h = post[1] - post[0] + 1
        caf_raw.append(post_caf)
        caf_z.append(post_caf / (sd * math.sqrt(h)))
        pre_raw.append(pre_af)
        day0_raw.append(day0)
        used += 1
    if used < 5:
        return {"n": used, "note": "too few events for a read (<5)"}
    mz, sz = _mean(caf_z), _sd(caf_z)
    t = mz / (sz / math.sqrt(used)) if sz > 0 else None
    return {
        "n": used,
        "pre_af_tao_mean": round(_mean(pre_raw), 2),
        "event_day_af_tao_mean": round(_mean(day0_raw), 2),
        "post_caf_tao_mean": round(_mean(caf_raw), 2),
        "post_caf_tao_median": round(sorted(caf_raw)[len(caf_raw) // 2], 2),
        "post_caf_z_mean": round(mz, 3),
        "pct_positive": round(100.0 * sum(1 for x in caf_raw if x > 0) / used, 1),
        "t_stat": round(t, 2) if t is not None else None,
        "significant": (t is not None and abs(t) >= 2.0),
        "directional_positive": (t is not None and t >= 2.0),
    }


def placebo(series, n: int = 1500, seed: int = 7) -> dict[str, Any]:
    """Calibration: random (subnet, day) pseudo-events. A sound harness returns t≈0.
    Run every time so a real signal can be judged against this null band, and so the
    right-skew in pct_positive (≈60% under the null) is never mistaken for signal."""
    import random
    rng = random.Random(seed)
    subs = [s for s in series if len(series[s]) > 40]
    fake = []
    for _ in range(n):
        s = rng.choice(subs)
        os_ = sorted(series[s])
        fake.append((s, rng.randint(os_[0] + 5, os_[-1] - 25)))
    out = {}
    for label, post in (("post7", POST), ("post21", POST_LONG)):
        r = _study_one(series, fake, dv="nonowner", post=post)
        out[label] = {"t_stat": r.get("t_stat"), "z_mean": r.get("post_caf_z_mean"),
                      "pct_positive": r.get("pct_positive")}
    return out


def run(post_long: bool = True) -> dict[str, Any]:
    logger.info("Flow event study: building flow series + events from taoflute …")
    series = build_flow_series()
    events = build_events()

    # quick field stats
    n_sub = len(series)
    sn21_days = series.get(NETUID_SN21, {})

    results: dict[str, Any] = {}
    for key in EVENT_KEYS:
        ev = events.get(key, [])
        r7 = _study_one(series, ev, dv="nonowner", post=POST)
        if post_long:
            r21 = _study_one(series, ev, dv="nonowner", post=POST_LONG)
            r7["post21_caf_z_mean"] = r21.get("post_caf_z_mean")
            r7["post21_t_stat"] = r21.get("t_stat")
        results[key] = r7

    # buyback catalyst: owner-buy events, DV = NON-OWNER flow (do others follow?)
    owner_events = [e for k in OWNER_BUY_KEYS for e in events.get(k, [])]
    catalyst = _study_one(series, owner_events, dv="nonowner", post=POST)
    catalyst_self = _study_one(series, owner_events, dv="owner", post=POST)
    catalyst["_self_owner_flow"] = catalyst_self

    out = {
        "computed_at_utc": datetime.now(timezone.utc).isoformat(),
        "window_start": WINDOW_START,
        "dv": "non-owner net TAO flow (abnormal vs subnet baseline)",
        "windows": {"pre": PRE, "post": POST, "post_long": POST_LONG},
        "n_subnets_with_flow": n_sub,
        "events_by_type": {k: len(v) for k, v in events.items()},
        "results": results,
        "buyback_catalyst": catalyst,
        "placebo_null_band": placebo(series),
        "verdict": _verdict(results, catalyst),
    }
    save_json(STORE, out)
    return out


def _verdict(results: dict, catalyst: dict) -> str:
    drivers = [k for k, r in results.items() if r.get("directional_positive")]
    cat = catalyst.get("directional_positive")
    parts = []
    if drivers:
        parts.append("durable non-owner inflow follows: " + ", ".join(drivers))
    else:
        parts.append("no on-chain event type produced significant durable non-owner inflow")
    parts.append("owner-buy DOES catalyse outside demand"
                 if cat else "owner-buy does NOT catalyse outside demand (flow reverts / stays self-funded)")
    return "; ".join(parts) + "."


# ── SN21 lens ─────────────────────────────────────────────────────────────────

def sn21_lens() -> dict[str, Any]:
    """SN21's own flow profile + the events it has had, for eyeballing."""
    series = build_flow_series()
    events = build_events()
    days = series.get(NETUID_SN21, {})
    if not days:
        return {"note": "no SN21 flow rows"}
    os_ = sorted(days)
    net = [days[o]["net"] for o in os_]
    owner = [days[o]["owner"] for o in os_]
    sn_events = {k: [o for (nid, o) in v if nid == NETUID_SN21] for k, v in events.items()}
    return {
        "n_days_active": len(os_),
        "net_tao_total": round(sum(net), 1),
        "net_tao_daily_mean": round(_mean(net), 3),
        "net_tao_daily_sd": round(_sd(net), 3),
        "owner_tao_total": round(sum(owner), 1),
        "nonowner_tao_total": round(sum(net) - sum(owner), 1),
        "best_day_tao": round(max(net), 1),
        "worst_day_tao": round(min(net), 1),
        "events": {k: len(v) for k, v in sn_events.items() if v},
    }


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cmd = sys.argv[1] if len(sys.argv) > 1 else "run"
    if cmd == "sn21":
        print(json.dumps(sn21_lens(), indent=2))
    else:
        print(json.dumps(run(), indent=2))
