"""
Cross-sectional factor study — which subnet attributes track net TAO demand?

Step 2 of the valuation research. One row per subnet, ~16 operationalised factors,
DV = measured net non-owner TAO inflow (90d) from delegation_history — the binding
lever established in [[sn21-valuation-decomposition]]. Tests which of the demand
hypotheses actually correlate with inflow ACROSS the field, and — critically —
whether they survive controlling for the two structural confounders step 1 exposed:
FLOAT (total issued alpha) and AGE. Longevity/float drive everything, so an
uncontrolled correlation is almost meaningless.

Stats (numpy only): Spearman ρ (monotonic, robust to the heavy skews seen
throughout), plus PARTIAL Spearman controlling for [float, age] via rank-residual
OLS. A factor that keeps a significant partial ρ is a real candidate lever; one
that collapses was just a proxy for being old/big.

Qualitative hypotheses (#1 mining-output-is-product, #2 simplicity, #3 crypto-
adjacency, #4 revenue, #5 partnerships, #6 whitepaper) need an LLM coding pass over
summary/description/repo — those raw text fields are pulled into the CSV so the
follow-up pass can score them. This module covers the quantitative/structural set.

CLI:  python cross_section.py
Writes data/cross_section.csv and data/cross_section.json.
"""
from __future__ import annotations

import csv
import json
import logging
from datetime import datetime, timezone

import numpy as np

from collector import save_json
from config import DATA_DIR
from flow_events import build_flow_series, WINDOW_START  # noqa: F401
from movers_attribution import tf_query

logger = logging.getLogger(__name__)

CSV_PATH = DATA_DIR / "cross_section.csv"
JSON_PATH = DATA_DIR / "cross_section.json"
NETUID_SN21 = 21

# blocks→days (finney ~7200/day) for age
BLOCKS_PER_DAY = 7200.0

OVERVIEW_SQL = """
select sn_id, subnet_name, owner_coldkey_full,
       tao_in, alpha_in, total_alpha, alpha_out,
       circulating_alpha_now, circulating_alpha_increase_30_days,
       registration_block, "miner_burn_%" miner_burn, "alpha_burnt_%" alpha_burnt,
       avg_code_lines_30d, last_x_msg_days, last_discord_msg_days, twitter,
       gini, top_holder_amount, protocol_buy_pressure, month_price_change_perc,
       price, alpha_staked_30d, owner_deposits,
       last_30_days_manual_alpha_burns_in_tao, num_manual_burns_last_30_days,
       tao_in_emission, summary, description, repo_url
from materialized_overview_data where id != 0
"""


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def build_table() -> list[dict]:
    # 1) overview snapshot (one row/subnet)
    cols, rows = tf_query(OVERVIEW_SQL, timeout=180)
    ov = [dict(zip(cols, r)) for r in rows]

    # owner → subnet count (hypothesis #10: multiple complementary subnets per owner)
    owner_counts: dict[str, int] = {}
    for r in ov:
        ck = r.get("owner_coldkey_full")
        if ck:
            owner_counts[ck] = owner_counts.get(ck, 0) + 1

    # 2) DV: net non-owner TAO inflow over last 90 / 30 days
    series = build_flow_series()
    all_days = [o for d in series.values() for o in d]
    hi = max(all_days)

    def net_flow(nid: int, days: int, key: str = "nonowner") -> float:
        d = series.get(nid, {})
        return round(sum(v.get(key, 0.0) for o, v in d.items() if o > hi - days), 3)

    table = []
    for r in ov:
        try:
            nid = int(r["sn_id"])
        except (TypeError, ValueError):
            continue
        if nid == 0:
            continue
        total_alpha = _f(r["total_alpha"]) or 0.0
        reg_block = _f(r["registration_block"])
        top_holder = _f(r["top_holder_amount"])
        row = {
            "netuid": nid,
            "name": r["subnet_name"],
            # ── DV ──
            "net_flow_90d": net_flow(nid, 90),
            "net_flow_30d": net_flow(nid, 30),
            "owner_flow_90d": net_flow(nid, 90, "owner"),
            # ── structural controls ──
            "float_total": total_alpha,
            "age_days": round((8_514_000 - reg_block) / BLOCKS_PER_DAY, 1) if reg_block else None,
            # ── factors ──
            "tao_in": _f(r["tao_in"]),
            "float_growth_30d": _f(r["circulating_alpha_increase_30_days"]),
            "dev_codelines_30d": _f(r["avg_code_lines_30d"]),
            "x_days": _f(r["last_x_msg_days"]),          # lower = fresher
            "discord_days": _f(r["last_discord_msg_days"]),
            "has_twitter": 1 if r.get("twitter") else 0,
            "gini": _f(r["gini"]),
            "top_holder_share": (top_holder / total_alpha) if (top_holder and total_alpha) else None,
            "buy_pressure": _f(r["protocol_buy_pressure"]),
            "miner_burn": _f(r["miner_burn"]),
            "owner_buyback_tao_30d": _f(r["last_30_days_manual_alpha_burns_in_tao"]),
            "owner_deposits": _f(r["owner_deposits"]),
            "price_mom_30d": _f(r["month_price_change_perc"]),
            "owner_subnet_count": owner_counts.get(r.get("owner_coldkey_full"), 1),
            "is_emitting": 1 if (_f(r["tao_in_emission"]) or 0) > 0 else 0,
            # ── raw text for the later qualitative LLM pass ──
            "_summary": (r.get("summary") or "")[:300],
            "_repo": r.get("repo_url"),
        }
        table.append(row)
    return table


# ── stats ─────────────────────────────────────────────────────────────────────

def _rank(x: np.ndarray) -> np.ndarray:
    order = x.argsort()
    ranks = np.empty_like(order, dtype=float)
    ranks[order] = np.arange(len(x))
    # average ties
    _, inv, counts = np.unique(x, return_inverse=True, return_counts=True)
    sums = np.zeros(len(counts))
    np.add.at(sums, inv, ranks)
    return (sums / counts)[inv]


def _spearman(a: np.ndarray, b: np.ndarray) -> float:
    ra, rb = _rank(a), _rank(b)
    ra, rb = ra - ra.mean(), rb - rb.mean()
    d = np.sqrt((ra @ ra) * (rb @ rb))
    return float(ra @ rb / d) if d > 0 else 0.0


def _partial_spearman(a, b, controls: list[np.ndarray]) -> float:
    """Spearman of a,b after regressing each (rank-transformed) on the rank controls."""
    ra, rb = _rank(a), _rank(b)
    X = np.column_stack([np.ones(len(a))] + [_rank(c) for c in controls])
    def resid(y):
        beta, *_ = np.linalg.lstsq(X, y, rcond=None)
        return y - X @ beta
    rra, rrb = resid(ra), resid(rb)
    d = np.sqrt((rra @ rra) * (rrb @ rrb))
    return float(rra @ rrb / d) if d > 0 else 0.0


def analyze(table: list[dict], dv: str = "net_flow_90d") -> dict:
    factors = ["tao_in", "float_total", "age_days", "float_growth_30d", "dev_codelines_30d",
               "x_days", "discord_days", "has_twitter", "gini", "top_holder_share",
               "buy_pressure", "miner_burn", "owner_buyback_tao_30d", "owner_deposits",
               "price_mom_30d", "owner_subnet_count", "is_emitting"]
    # restrict to emitting subnets — zero-emission subnets have ~no live flow dynamics
    rows = [r for r in table if r["is_emitting"] == 1 and r.get(dv) is not None]
    n = len(rows)
    y = np.array([r[dv] for r in rows], float)

    def col(name):
        return np.array([r[name] if r.get(name) is not None else np.nan for r in rows], float)

    fl, ag = col("float_total"), col("age_days")
    results = []
    for f in factors:
        x = col(f)
        mask = ~(np.isnan(x) | np.isnan(y))
        if mask.sum() < 20:
            continue
        xm, ym = x[mask], y[mask]
        rho = _spearman(xm, ym)
        # partial controlling for float+age (skip when the factor IS a control)
        if f in ("float_total", "age_days"):
            prho = None
        else:
            cm = mask & ~np.isnan(fl) & ~np.isnan(ag)
            prho = _partial_spearman(x[cm], y[cm], [fl[cm], ag[cm]]) if cm.sum() >= 20 else None
        # crude significance: |rho| z-test, ρ·sqrt(n-1) ~ N(0,1)
        sig = abs(rho) * np.sqrt(mask.sum() - 1)
        results.append({"factor": f, "spearman": round(rho, 3),
                        "partial_float_age": round(prho, 3) if prho is not None else None,
                        "n": int(mask.sum()), "z": round(float(sig), 1)})
    results.sort(key=lambda d: -abs(d["partial_float_age"] if d["partial_float_age"] is not None else d["spearman"]))
    return {"dv": dv, "n_emitting": n, "factors_ranked": results}


def run() -> dict:
    logger.info("Cross-section: building factor table …")
    table = build_table()
    # write CSV (drop long text cols from the analysis JSON but keep in CSV)
    keys = [k for k in table[0] if not k.startswith("_")] + ["_summary", "_repo"]
    with open(CSV_PATH, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        w.writerows(table)
    analysis_90 = analyze(table, "net_flow_90d")
    analysis_30 = analyze(table, "net_flow_30d")
    sn = next((r for r in table if r["netuid"] == NETUID_SN21), None)
    out = {
        "computed_at_utc": datetime.now(timezone.utc).isoformat(),
        "n_subnets": len(table),
        "analysis_90d": analysis_90,
        "analysis_30d": analysis_30,
        "sn21": {k: v for k, v in sn.items() if not k.startswith("_")} if sn else None,
    }
    save_json(JSON_PATH, out)
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    out = run()
    print(json.dumps(out, indent=2))
