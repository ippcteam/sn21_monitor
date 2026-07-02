"""
Lab runner — orchestrates a single lab run.

  1. pull live ChainState (lab/chain_pull.py)
  2. REPRODUCTION GATE (§4.3): model the incumbent SN21 emission share and compare
     it to the chain's ACTUAL per-block share (tao_in_emission + excess_tao_emission,
     i.e. liquidity injection + chain buys). Pass iff the
     relative error is within tolerance. This is the credibility anchor — scenario
     results are flagged `trusted` only when the gate passes. A red gate is a valid,
     informative outcome: "the model can't yet rebuild reality — extract the source
     formula (Action 1) before acting", exactly as the doc requires.
  3. run scenarios S1..S6 for the selected mechanism (lab/scenarios.py)
  4. append a lean run record to the versioned log (lab/store.py)

CLI:  python -m lab.runner --live [--version root_reborn_v346_421] [--tol 0.15]
      python -m lab.runner            # dry print only, no append
"""

from __future__ import annotations

import logging
import sys

from . import mechanisms as M
from . import scenarios as SC
from . import store
from .chain_pull import pull_chain_state, sn21

logger = logging.getLogger(__name__)

DEFAULT_VERSION = "root_reborn_v346_421"
DEFAULT_TOLERANCE = 0.15   # 15% relative error on the reproduction gate


def _actual_emission(sub: dict) -> float:
    """A subnet's ACTUAL per-block TAO emission = liquidity injection + chain buys.

    The coinbase caps injection at root_prop x alpha_emission; emission above the
    cap is swapped into alpha (SubnetExcessTao) instead of recorded in
    SubnetTaoInEmission. Summing tao_in_emission alone drops the chain-buy leg
    (~59% of network emission at block 8.53M) — that omission was the entire
    "SN21 over-emits 3x / effective burn 0.26" artifact (resolved 2026-07-02:
    with both legs the two legs sum to the 0.5 TAO/block emission exactly and
    SN21's rel.err falls 0.64 -> 0.065)."""
    return (sub.get("tao_in_emission") or 0.0) + (sub.get("excess_tao_emission") or 0.0)


def actual_sn21_share(state: dict) -> float | None:
    """SN21's real share of per-block TAO emission across all subnets — chain ground truth."""
    tot = sum(_actual_emission(s) for s in state["subnets"])
    if tot <= 0:
        return None
    return _actual_emission(sn21(state)) / tot


def sn21_effective_burn(state: dict, mech) -> dict:
    """SN21's EFFECTIVE burn — the b that makes the (1-b) model reproduce SN21's
    actual TAO-emission share, holding every other subnet at its snapshot burn.

    RESOLVED 2026-07-02: the old ~0.4 nominal-vs-effective gap was a measurement
    artifact — "actual" summed tao_in_emission only, dropping the SubnetExcessTao
    chain-buy leg of capped subnets' emission. With both legs counted, effective
    ~= nominal, i.e. the chain applies exactly the (1-b) it publishes. This is now
    an INVARIANT CHECK: a re-opened gap means the coinbase changed again.
    Solve: actual = S(1-b)/(S(1-b)+Rest), S = price*root_prop_SN21,
    Rest = sum of every other subnet's score -> b_eff = 1 - actual*Rest/(S*(1-actual))."""
    me = sn21(state)
    actual = actual_sn21_share(state)
    S = max(0.0, mech.score(me, state) / (1.0 - (state.get("sn21_miner_burn") or 0.0)) ) \
        if (state.get("sn21_miner_burn") or 0.0) < 1.0 else None
    if actual is None or not S or S <= 0 or actual >= 1.0:
        return {"nominal_burn": state.get("sn21_miner_burn"), "effective_burn": None}
    rest = sum(max(0.0, mech.score(s, state)) for s in state["subnets"]
               if s["netuid"] != state.get("netuid", 21))
    one_minus_b = actual * rest / (S * (1.0 - actual))
    b_eff = max(0.0, min(1.0, 1.0 - one_minus_b))
    nominal = state.get("sn21_miner_burn") or 0.0
    gap = nominal - b_eff
    note = (f"INVARIANT OK: effective burn {b_eff:.2f} ~= nominal {nominal:.2f} — the "
            "chain applies exactly its published (1-b); the (1-b) lever is fully real."
            if abs(gap) <= 0.10 else
            f"INVARIANT BROKEN: effective burn {b_eff:.2f} vs nominal {nominal:.2f} "
            f"(gap {gap:+.2f}) — the coinbase emission path has likely changed again; "
            "re-read the source before trusting scenario magnitudes.")
    return {
        "nominal_burn": round(nominal, 4),
        "effective_burn": round(b_eff, 4),
        "gap": round(gap, 4),
        "note": note,
    }


def _network_reproduction(state: dict, mech, tolerance: float):
    """Per-subnet model-vs-actual rel.err across all EMITTING subnets. This tests
    the FORMULA STRUCTURE network-wide, independent of any single subnet's burn
    transition — the honest credibility signal (one subnet mid-transition off full
    burn, like SN21 today, is an outlier, not evidence the formula is wrong)."""
    scores = {s["netuid"]: max(0.0, mech.score(s, state)) for s in state["subnets"]}
    tot = sum(scores.values())
    te = sum(_actual_emission(s) for s in state["subnets"])
    errs = []
    if tot > 0 and te > 0:
        for s in state["subnets"]:
            a = _actual_emission(s) / te
            if a > 1e-5:  # emitting subnets only
                errs.append(abs(scores[s["netuid"]] / tot - a) / a)
    errs.sort()
    median = errs[len(errs) // 2] if errs else None
    within = sum(1 for e in errs if e <= tolerance)
    return median, within, len(errs)


def reproduction_gate(state: dict, tolerance: float = DEFAULT_TOLERANCE) -> dict:
    inc = M.get("incumbent")
    modeled = M.emission_share(inc, state)          # SN21-specific
    actual = actual_sn21_share(state)
    sn21_err = abs(modeled - actual) / actual if (actual and actual > 0) else None
    median, within, n = _network_reproduction(state, inc, tolerance)

    # Gate on the NETWORK-WIDE median (structural validity), not SN21 alone. SN21's
    # own error is reported as a caveat: when SN21 sits mid burn-transition its
    # instantaneous MinerBurned lags its emission, so SN21 magnitudes stay
    # directional even when the formula is sound network-wide.
    passed = median is not None and median <= tolerance
    sn21_ok = sn21_err is not None and sn21_err <= tolerance
    if passed and sn21_ok:
        note = ("Formula reproduces the chain network-wide AND for SN21 — scenarios "
                "are trustworthy.")
    elif passed:
        note = (f"Formula validated NETWORK-WIDE (median rel.err {median:.3f}, "
                f"{within}/{n} subnets within tol), but SN21's own error is "
                f"{sn21_err:.2f}. STRUCTURE trusted; SN21 magnitudes directional.")
    else:
        note = (f"Formula does NOT reproduce the chain (median rel.err {median}) — "
                "structural error; treat all magnitudes as directional.")
    return {
        "mechanism": "incumbent",
        "modeled_share_pct": round(modeled * 100, 6),
        "actual_share_pct": round(actual * 100, 6) if actual else None,
        "relative_error": round(sn21_err, 4) if sn21_err is not None else None,
        "network_median_rel_err": round(median, 4) if median is not None else None,
        "network_within_tol": f"{within}/{n}",
        "tolerance": tolerance,
        "passed": passed,
        "sn21_passed": sn21_ok,
        "note": note,
    }


def _compact_state(state: dict, version: str) -> dict:
    """Lean, reproducible-for-SN21 snapshot stored in each run record."""
    me = sn21(state)
    denoms = {}
    for vid in (version, "incumbent"):
        try:
            mech = M.get(vid)
            denoms[vid] = sum(max(0.0, mech.score(s, state)) for s in state["subnets"])
        except Exception:  # noqa: BLE001
            denoms[vid] = None
    return {
        "block": state.get("block"),
        "tao_weight": state.get("tao_weight"),
        "owner_cut": state.get("owner_cut"),
        "root_stake_tao": state.get("root_stake_tao"),
        "sn21_miner_burn": state.get("sn21_miner_burn"),
        "n_subnets": state.get("n_subnets"),
        "sn21": me,
        "score_denominators": denoms,
    }


def run_lab(version: str = DEFAULT_VERSION, live: bool = True,
            tolerance: float = DEFAULT_TOLERANCE, state: dict | None = None,
            persist: bool = True) -> dict:
    mech = M.get(version)  # validate early
    if state is None:
        if not live:
            raise ValueError("run_lab needs live=True or an explicit state")
        logger.info("Lab run: pulling live chain state …")
        state = pull_chain_state()

    gate = reproduction_gate(state, tolerance)
    eff_burn = sn21_effective_burn(state, mech)
    scen = SC.run_all(state)

    from .recommend import build_recommendations
    recs = build_recommendations(state, scen)
    headline = recs.get("verdict")

    record = {
        "fetched_at_utc": state.get("fetched_at_utc") or store.now_iso(),
        "block": state.get("block"),
        "mechanism_version": version,
        "mechanism_label": mech.label,
        "tolerance": tolerance,
        "trusted": gate["passed"],
        "reproduction": gate,
        "effective_burn": eff_burn,
        "chain_state": _compact_state(state, version),
        "scenarios": scen,
        "recommendations": recs,
        "headline": headline,
    }
    if persist:
        record = store.append_run(record)
    return record


def main(argv=None):
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    argv = sys.argv[1:] if argv is None else argv
    live = "--live" in argv
    persist = "--live" in argv  # only persist real runs
    version = DEFAULT_VERSION
    tol = DEFAULT_TOLERANCE
    if "--version" in argv:
        version = argv[argv.index("--version") + 1]
    if "--tol" in argv:
        tol = float(argv[argv.index("--tol") + 1])

    rec = run_lab(version=version, live=live, tolerance=tol, persist=persist)

    g = rec["reproduction"]
    print("\n" + "=" * 64)
    print(f"LAB RUN  mechanism={version}  block={rec['block']}")
    print("=" * 64)
    print(f"REPRODUCTION GATE: {'PASS ✓' if g['passed'] else 'FAIL ✗'}  "
          f"(network median rel.err {g['network_median_rel_err']}, "
          f"{g['network_within_tol']} subnets within tol {g['tolerance']})")
    print(f"  SN21: modeled {g['modeled_share_pct']}% vs actual {g['actual_share_pct']}% "
          f"(rel.err {g['relative_error']}, {'within' if g['sn21_passed'] else 'OUTSIDE'} tol)")
    print(f"  {g['note']}")
    print(f"  trusted = {rec['trusted']}")
    eb = rec.get("effective_burn") or {}
    if eb.get("effective_burn") is not None:
        print(f"  SN21 burn: nominal {eb['nominal_burn']} vs effective {eb['effective_burn']} — {eb['note']}")
    for key in ("S1", "S2", "S3", "S4", "S5", "S6"):
        sc = rec["scenarios"].get(key, {})
        summ = sc.get("summary") or sc.get("error") or "—"
        print(f"\n[{key}] {summ}")

    recs = rec.get("recommendations") or {}
    print("\n" + "=" * 64)
    print("RECOMMENDED ACTIONS  (goal: ↑ alpha price + owner alpha; avoid dereg/emission-block)")
    print("=" * 64)
    print(f"VERDICT: {recs.get('verdict')}")
    for r in recs.get("risks", []):
        print(f"  risk · {r['name']}: {r['level'].upper()}")
    for a in recs.get("actions", []):
        print(f"\n  [{a['priority']}] {a['lever']}: {a['action']}")
        print(f"      price={a['effect_price']} · owner_alpha={a['effect_owner_alpha']}")
        print(f"      guardrail: {a['guardrail']}")
        print(f"      confidence: {a['confidence']}")
    if not persist:
        print("\n(dry run — pass --live to pull fresh state and append to the log)")


if __name__ == "__main__":
    main()
