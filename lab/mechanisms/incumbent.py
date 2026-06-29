"""
Incumbent (live) mechanism — for the §4.3 reproduction gate.

UPDATED after Action 1 (source read of subtensor `main`, coinbase pallet): the
live finney mechanism is NOT pure price-weighting — Root Reborn has SHIPPED. The
per-subnet TAO slice is `moving_price_i x root_proportion_i x (1 - MinerBurned_i)`,
renormalised across subnets (subnet_emissions.rs `get_shares`). So the incumbent
gate now models that same three-switch formula, using each subnet's OWN live burn.

Reproduction status (measured live @ ~block 8,512,300): pure price-weighting gave
rel.err ~0.55; the three-switch formula with PER-SUBNET burn closes that to ~0.34
(actual SN21 slice 0.204% vs modelled ~0.135%). Still outside the 0.15 tolerance —
the residual is the exact `root_proportion(netuid)` definition (RootProportion is
computed, not stored; our R/(R+A) proxy and A-unit convention are the next
refinement). A red gate still means "treat magnitudes as directional", but the
model now reproduces the dominant structure rather than the wrong shape.
"""

from __future__ import annotations

from . import Mechanism, register
from .root_reborn_v346_421 import root_prop

PR_URL = "https://github.com/opentensor/subtensor (live finney coinbase — Root Reborn shipped)"


def _score(sub: dict, state: dict) -> float:
    """Live three-switch share: moving_price x root_proportion x (1 - MinerBurned),
    each subnet using its OWN burn. EMA price is the 'market salary'."""
    p = sub.get("ema_price") or sub.get("spot_price") or 0.0
    if p <= 0:
        return 0.0
    if sub["netuid"] == state.get("netuid", 21):
        b = state.get("sn21_miner_burn", 0.0)
    else:
        b = sub.get("miner_burn", 0.0)
    return max(0.0, root_prop(sub, state) * float(p) * (1.0 - b))


register(Mechanism(
    id="incumbent",
    label="Incumbent (Root Reborn three-switch — live)",
    pr_url=PR_URL,
    activation_block=None,
    stage="mainnet",  # this IS the live finney mechanism -> Go now
    score=_score,
    notes=("Source-confirmed live mechanism: price x root_proportion x (1-burn), "
           "per-subnet, renormalised. Reproduces the dominant structure; residual "
           "error is the exact root_proportion formula (next refinement)."),
))
