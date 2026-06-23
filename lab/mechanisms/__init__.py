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


# Populate the registry. Import side-effects register each mechanism.
from . import incumbent  # noqa: E402,F401
from . import root_reborn_v346_421  # noqa: E402,F401
