"""
PROPOSED — hard rank tiers: top-32 take 75%, ranks 33-64 take 25%, 65+ get ZERO
(subtensor PR #3010, "Allocate TAO emissions across the top 64 subnets").

STATUS 2026-07-29: OPEN **DRAFT** PR by gzaentz (codex/tiered-subnet-emissions),
opened 2026-07-29 00:00 UTC, no reviews. Bumps spec 440 -> 441 in the diff, but a
draft PR is not a release; nothing is on finney. Lane = "Consider this".

WHAT CHANGES (subnet_emissions.rs, verified from the diff):

  Everything upstream is UNCHANGED — the demand share price*(1-burn), the v440
  Hill gate, and the emission-enabled filter all run exactly as today. The new
  step `apply_ranked_emission_tiers` is applied LAST, to the already-gated,
  already-renormalised share map:

      rank subnets by gated share, descending (ties -> ascending netuid)
      ranks  1-32 : share_i / sum(top32)   * 0.75
      ranks 33-64 : share_i / sum(33..64)  * 0.25
      ranks  65+  : 0
      (if there is no 2nd tier at all, tier 1 takes 100% so nothing is stranded)

  This is a HARD CLIFF where v440 gave a soft one. The Hill gate crushes
  below-bar subnets asymptotically but never to exactly zero; this zeroes rank 65
  outright and puts a 3x step at the rank-32/33 boundary.

SN21 READ: this is the single most consequential of the five open PRs for us.
SN21's gated rank is what decides everything — the tier multiplier is a step
function of rank, not of demand. Two distinct regimes:

  - rank <= 32  -> emission MULTIPLIED (0.75 spread over 32 instead of over the
                   whole 62-subnet emitting set)
  - rank 33-64  -> roughly held, possibly up (0.25 over 32 subnets)
  - rank >= 65  -> ZERO TAO emission. Not "crushed": zero.

Because the ranking runs on the POST-GATE share, and the gate already amplifies
demand differences ~3x, our position relative to the rank-64 line is the whole
question. score() reproduces the tiering so emission_share() answers it directly.
"""

from __future__ import annotations

from . import Mechanism, register
from .hill_gate_v440_2990 import _score as _gated_score

PR_URL = "https://github.com/RaoFoundation/subtensor/pull/3010"

TIER_SIZE = 32
PRIMARY_ALLOCATION = 0.75
SECONDARY_ALLOCATION = 0.25


def tiered_shares(state: dict) -> dict:
    """netuid -> post-tier emission share. Mirrors apply_ranked_emission_tiers."""
    gated = {s["netuid"]: max(0.0, _gated_score(s, state) or 0.0) for s in state["subnets"]}
    positive = [(n, w) for n, w in gated.items() if w > 0]
    # descending share, ties broken by ascending netuid — same ordering as the diff
    positive.sort(key=lambda nw: (-nw[1], nw[0]))

    cut1 = min(len(positive), TIER_SIZE)
    cut2 = min(len(positive), TIER_SIZE * 2)
    total1 = sum(w for _, w in positive[:cut1])
    total2 = sum(w for _, w in positive[cut1:cut2])
    has_tier2 = total2 > 0

    out = {n: 0.0 for n in gated}
    for rank, (netuid, w) in enumerate(positive):
        if rank < cut1:
            alloc = PRIMARY_ALLOCATION if has_tier2 else 1.0
            out[netuid] = (w / total1) * alloc if total1 > 0 else 0.0
        elif rank < cut2:
            out[netuid] = (w / total2) * SECONDARY_ALLOCATION if total2 > 0 else 0.0
        else:
            out[netuid] = 0.0
    return out


def gated_rank(state: dict, netuid: int | None = None) -> int | None:
    """A subnet's rank in the post-gate ordering the tiers are cut from (1-based)."""
    target = netuid if netuid is not None else state.get("netuid", 21)
    gated = {s["netuid"]: max(0.0, _gated_score(s, state) or 0.0) for s in state["subnets"]}
    positive = sorted(((n, w) for n, w in gated.items() if w > 0), key=lambda nw: (-nw[1], nw[0]))
    for i, (n, _) in enumerate(positive, start=1):
        if n == target:
            return i
    return None


def _score(sub: dict, state: dict) -> float:
    """Post-tier share. Already normalised to 1 across subnets, so
    emission_share()'s renormalisation is a no-op — which is what we want."""
    return tiered_shares(state).get(sub["netuid"], 0.0)


register(Mechanism(
    id="ranked_tiers_3010",
    label="PROPOSED #3010 — top-32 take 75%, 33-64 take 25%, 65+ ZERO",
    pr_url=PR_URL,
    activation_block=None,
    merged=False,
    stage="proposed",
    score=_score,
    notes=("OPEN DRAFT (gzaentz, 2026-07-29, no reviews). Applies hard rank "
           "tiers AFTER the v440 Hill gate: ranks 1-32 share 75%, 33-64 share "
           "25%, 65+ get exactly zero. Turns v440's soft top-k into a cliff. "
           "For SN21 the only question that matters is our POST-GATE rank vs "
           "the 32 and 64 lines — the multiplier is a step function of rank, "
           "not of demand."),
))
