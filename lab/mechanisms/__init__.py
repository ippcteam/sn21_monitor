"""
Versioned, reviewed emission mechanisms.

Each mechanism is a pure scoring function. A subnet's emission_share is its score
divided by the sum of all subnets' scores (emission is RELATIVE — §4.1). Mechanisms
are registered in REGISTRY by a stable version id; a new proposed Bittensor change
becomes a new module here, hand-written from the PR diff and reviewed before it is
trusted (the watcher only drafts a stub — see lab/watcher.py).

A mechanism's `score(subnet_row, state) -> float` reads the per-subnet primitives
pulled by lab/chain_pull.py plus global state (tao_weight, root_stake, the SN21
miner-burn). SN21's burn is read from `state['sn21_miner_burn']`, so a scenario can
sweep b simply by recomputing on a state copy with a different value.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass
class Mechanism:
    id: str
    label: str
    pr_url: str
    activation_block: int | None
    score: Callable[[dict, dict], float]
    notes: str
    merged: bool | None = None   # source PR merged into subtensor? None = unknown
    stage: str | None = None     # explicit lifecycle override; else derived (see deploy_stage)


# Lifecycle → our evaluation stance. The three lanes the operator decides across:
#   proposed  (open PR, not merged)        -> Consider this  (model it, don't act)
#   testnet   (merged, not yet mainnet)    -> Plan for this  (real; prep our response)
#   mainnet   (activated on finney)        -> Go now         (live; act on the recs)
STAGE_STANCE = {
    "proposed": "Consider this",
    "testnet": "Plan for this",
    "mainnet": "Go now",
}


def deploy_stage(mech: "Mechanism", current_block: int | None = None) -> str:
    """Where this change lives in the deploy pipeline. Explicit `stage` wins; else
    derive from activation_block + the merged-PR heuristic (the chosen testnet signal):
      - activation_block set and reached on finney   -> mainnet
      - activation_block set but still in the future  -> testnet (confirmed, scheduled)
      - no activation_block but the PR is merged       -> testnet (merged-PR heuristic)
      - otherwise                                       -> proposed
    """
    if mech.stage in STAGE_STANCE:
        return mech.stage
    ab = mech.activation_block
    if ab is not None:
        if current_block is not None and ab <= current_block:
            return "mainnet"
        return "testnet"
    if mech.merged:
        return "testnet"
    return "proposed"


def stance_for(stage: str) -> str:
    return STAGE_STANCE.get(stage, "Consider this")


REGISTRY: dict[str, Mechanism] = {}


def register(m: Mechanism) -> Mechanism:
    REGISTRY[m.id] = m
    return m


def emission_share(mech: Mechanism, state: dict, netuid: int | None = None) -> float:
    """SN21's slice = its score / sum of all subnets' scores under this mechanism."""
    target = netuid if netuid is not None else state.get("netuid", 21)
    scores = {s["netuid"]: (mech.score(s, state) or 0.0) for s in state["subnets"]}
    total = sum(v for v in scores.values() if v > 0)
    if total <= 0:
        return 0.0
    return max(0.0, scores.get(target, 0.0)) / total


def get(version: str) -> Mechanism:
    if version not in REGISTRY:
        raise KeyError(f"unknown mechanism '{version}' — known: {sorted(REGISTRY)}")
    return REGISTRY[version]


# The mechanism verified to be live on finney — the reproduction gate anchors on
# this and scenarios model it. Flipped from the three-switch incumbent on
# 2026-07-20 after the v430-v432 runtime deploys (spec 432 live; the spec-425
# detector confirmed price x (1-burn) now fits the chain best).
#
# Flipped again 2026-07-29 to the v440 gate. The un-gated v432 formula had been
# failing its own reproduction gate since the gate went live at block ~8,715,000
# (network median rel.err 1.78, 6/62 subnets within tolerance, SN21 modeled 64x
# its actual share) — the runner was printing "REGRESSION DETECTOR" every run.
# Measured against live state at block ~8,728,000 with q/h READ FROM CHAIN:
#
#     root_reborn_v425_2800   median rel.err 1.783   6/62 within   SN21 off by 64.0x
#     hill_gate_v440_2990     median rel.err 0.207  27/62 within   SN21 off by 0.33x
#
# NOTE: the gate mechanism is far better but still does NOT clear the 0.15
# tolerance, so magnitudes stay DIRECTIONAL and there is residual model error to
# chase (candidates: the emit-enabled set, the MinerBurned basis, the excess-TAO
# leg). An earlier calibration reported rel.err 0.024 by FITTING (q,h) to SN21's
# own share — circular, and it hid this gap. Revert by restoring the line below.
LIVE_VERSION = "hill_gate_v440_2990"

# Populate the registry. Import side-effects register each mechanism.
from . import incumbent  # noqa: E402,F401
from . import root_reborn_v346_421  # noqa: E402,F401
from . import root_reborn_v425_2800  # noqa: E402,F401
from . import collateral_v435_2953  # noqa: E402,F401
from . import hill_gate_v440_2990  # noqa: E402,F401
# Open PRs from the 2026-07-28/29 burst — all proposals, none merged.
from . import ranked_tiers_3010  # noqa: E402,F401
from . import conviction_boost_3011  # noqa: E402,F401
from . import chain_buy_cap_3012  # noqa: E402,F401
from . import q_raise_3013  # noqa: E402,F401
