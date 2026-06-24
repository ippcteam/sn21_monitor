"""
Lab runner — orchestrates a single lab run.

  1. pull live ChainState (lab/chain_pull.py)
  2. REPRODUCTION GATE (§4.3): model the incumbent SN21 emission share and compare
     it to the chain's ACTUAL per-block share (tao_in_emission). Pass iff the
     relative error is within tolerance. This is the credibility anchor — scenario
     results are flagged `trusted` only when the gate passes. A red gate is a valid,
     informative outcome: "the model can't yet rebuild reality — extract the source
     formula (Action 1) before acting", exactly as the doc requires.
  3. run scenarios S1..S5 for the selected mechanism (lab/scenarios.py)
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


def actual_sn21_share(state: dict) -> float | None:
    """SN21's real share of per-block TAO injection across all subnets — chain ground truth."""
    tot = sum((s.get("tao_in_emission") or 0.0) for s in state["subnets"])
    if tot <= 0:
        return None
    me = sn21(state)
    return (me.get("tao_in_emission") or 0.0) / tot


def reproduction_gate(state: dict, tolerance: float = DEFAULT_TOLERANCE) -> dict:
    inc = M.get("incumbent")
    modeled = M.emission_share(inc, state)
    actual = actual_sn21_share(state)
    rel_err = None
    passed = False
    if actual and actual > 0:
        rel_err = abs(modeled - actual) / actual
        passed = rel_err <= tolerance
    return {
        "mechanism": "incumbent",
        "modeled_share_pct": round(modeled * 100, 6),
        "actual_share_pct": round(actual * 100, 6) if actual else None,
        "relative_error": round(rel_err, 4) if rel_err is not None else None,
        "tolerance": tolerance,
        "passed": passed,
        "note": ("Modelled current emission matches the chain within tolerance — "
                 "scenarios are trustworthy." if passed else
                 "Modelled current emission does NOT match the chain — the incumbent "
                 "formula is incomplete (extract from v3.4.6-421 source, Action 1). "
                 "Treat scenario magnitudes as directional only."),
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
          f"(modeled {g['modeled_share_pct']}% vs actual {g['actual_share_pct']}%, "
          f"rel.err {g['relative_error']}, tol {g['tolerance']})")
    print(f"  {g['note']}")
    print(f"  trusted = {rec['trusted']}")
    for key in ("S1", "S2", "S3", "S4", "S5"):
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
