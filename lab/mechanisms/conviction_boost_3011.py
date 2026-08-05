"""
PROPOSED — conviction-adjusted emission gate, EmissionConvictionBoost lambda
(subtensor PR #3011, "feat: conviction-adjusted emission gate").

STATUS 2026-07-29: OPEN, non-draft, by Kaizen0304, opened 2026-07-29 00:08 UTC,
no reviews. Not merged, not on finney. Lane = "Consider this".

WHAT CHANGES (subnet_emissions.rs apply_gate + lib.rs storage, from the diff):

  The v440 gate argument only. The base demand share s_i = price*(1-burn) and the
  q-mass bar theta are BOTH still computed from the raw share — nothing about the
  bar or the pre-gate weight moves. What changes is what the Hill function is
  evaluated at:

      C_i        = min(1, total_conviction_i / SubnetAlphaOut_i)     [cached]
      s_eff_i    = s_i * (1 + lambda * C_i)
      gate_i     = 1 / (1 + (theta / s_eff_i)^h)          <- s_eff, not s
      weight_i   = gate_i * s_i                            <- raw s again
      e_i        = weight_i / sum_j(weight_j)

  So conviction buys you GATE CLEARANCE, not demand. A fully-locked subnet
  (C=1) is evaluated at (1+lambda)x its real share when deciding how much of the
  gate it clears; a zero-demand subnet still scores zero because the base weight
  is untouched (the PR is explicit about this).

  New sudo hyperparam: EmissionConvictionBoost lambda, DEFAULT 0, range [0, 8],
  set via sudo_set_emission_conviction_boost (admin-utils call index 102).
  lambda = 0 reproduces v440 EXACTLY. New map EmissionConvictionRatio caches C
  per subnet, refreshed on the 360-block bar cadence, and only while lambda > 0.

SN21 READ: this is the FIRST proposal in the v425-v440 train that hands a
below-bar subnet a lever that is not price. We are deep below theta, so gate(s)
is tiny and the derivative of emission w.r.t. gate clearance is large. Conviction
is alpha we (or our backers) lock — and per the conviction-takeover work we
already know SN21 has ZERO locks today, so C_SN21 = 0 and this PR as-shipped
does literally nothing for us at any lambda.

That cuts both ways and it is the important read:
  - As drafted with lambda=0 default: NO-OP. Even if merged and deployed, it
    changes nothing until the Triumvirate sets lambda by sudo.
  - If lambda is ever set > 0 and we still hold no locks: we get RELATIVELY
    WORSE, because every subnet that DOES lock clears more gate than us and the
    renormalisation is zero-sum.
  - If we lock: the same C that arms a conviction TAKEOVER against us (see the
    conviction-ownership-risk work) also buys emission. The lock we were
    treating purely as a defensive cost acquires a yield.

score() takes lambda from state['_conviction_lambda'] (default 0) and C from
each subnet's 'conviction_ratio' key (default 0 — chain_pull does not pull locks
yet, so the honest baseline is "nobody is locked", which is also the SN21 truth).
"""

from __future__ import annotations

from . import Mechanism, register
from .hill_gate_v440_2990 import _h, _linear_share, emission_bar, gate

PR_URL = "https://github.com/RaoFoundation/subtensor/pull/3011"

DEFAULT_LAMBDA = 0.0   # EmissionConvictionBoost on-chain default — gate unchanged
MAX_LAMBDA = 8.0       # enforced range in sudo_set_emission_conviction_boost


def _conviction_ratio(sub: dict, state: dict) -> float:
    """C_i in [0,1]. SN21's can be swept via state['sn21_conviction_ratio']."""
    if sub["netuid"] == state.get("netuid", 21) and "sn21_conviction_ratio" in state:
        return min(1.0, max(0.0, state["sn21_conviction_ratio"]))
    return min(1.0, max(0.0, sub.get("conviction_ratio", 0.0) or 0.0))


def _score(sub: dict, state: dict) -> float:
    """gate(s_eff) * s — clearance from s_eff, weight from raw s."""
    s = _linear_share(sub, state)
    if s <= 0:
        return 0.0
    tot = sum(_linear_share(x, state) for x in state["subnets"])
    if tot <= 0:
        return 0.0
    s_norm = s / tot

    lam = state.get("_conviction_lambda", DEFAULT_LAMBDA)
    s_eff = s_norm * (1.0 + lam * _conviction_ratio(sub, state)) if lam > 0 else s_norm

    theta = emission_bar(state)
    return gate(s_eff, theta, _h(state)) * s_norm


register(Mechanism(
    id="conviction_boost_3011",
    label="PROPOSED #3011 — conviction boost lambda on the gate (default 0 = no-op)",
    pr_url=PR_URL,
    activation_block=None,
    merged=False,
    stage="proposed",
    score=_score,
    notes=("OPEN, no reviews (Kaizen0304, 2026-07-29). Adds sudo hyperparam "
           "EmissionConvictionBoost lambda in [0,8], DEFAULT 0. Gate is "
           "evaluated at s*(1+lambda*C) where C = conviction/alpha_out capped "
           "at 1; base weight and the bar keep using raw s. lambda=0 reproduces "
           "v440 exactly, so shipping it is a no-op until sudo sets lambda. "
           "SN21 holds ZERO locks -> C=0 -> we gain nothing and lose relative "
           "ground to lockers if lambda is ever turned on. First non-price "
           "lever offered to a below-bar subnet."),
))
