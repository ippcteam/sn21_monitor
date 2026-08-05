"""
PROPOSED — raise the emission bar quantile q from 0.61 to 0.8073
(subtensor PR #3013, "Raise emission gate bar quantile from 0.61 to 0.8073").

STATUS 2026-07-29: OPEN, non-draft, by ap-choji, opened 2026-07-29 10:24 UTC —
the newest of the five. No reviews. Not merged. Lane = "Consider this", with a
large caveat below.

WHAT THE DIFF ACTUALLY DOES: it edits `DefaultEmissionBarQuantile` in lib.rs and
bumps spec 440 -> 441. That default is only read when the storage item has never
been written. Core dev mcjkula said so on the PR itself:

    "the current quantile is 0.75 ... you are changing the default value here
     (which won't do much). If we would want to change the quantile in the
     current runtime the Triumvirate just needs to change it with the
     `sudo_set_emission_bar_quantile` call. So no PR/code change needed."

So THE CODE CHANGE IS NEAR-IRRELEVANT — but the POLICY it argues for is not, and
it needs no PR at all. q is a sudo dial that can move any time, without a runtime
upgrade, without a release, without warning. That is the real finding here: our
single largest emission parameter is a one-extrinsic change by the Triumvirate.

Note also that mcjkula's live q = 0.75 corroborates our own calibration, which
fitted q ~ 0.77 to SN21's actual on-chain share (hill_gate_v440_2990.LIVE_Q).
Independent confirmation the lab's gate reproduction is anchored correctly.

WHAT RAISING q DOES: theta is the share at which the sorted cumulative demand
distribution first reaches q. Raising q walks the bar DOWN the sorted list to a
SMALLER share, which makes the gate LOOSER — more subnets sit at or above the
bar. The PR's stated target is theta ~0.441%, "around rank 64, 24 of 62 enabled
subnets gated". The PR's own updated unit test shows the direction cleanly: at
q=0.61 a 1:2 price pair settles 1/10 : 9/10; at q=0.8073 the same pair settles
9/41 : 32/41 — materially LESS concentrated.

SN21 READ: raising q is GOOD for us and is the cheapest possible relief — it
requires no action by us at all, only a sudo call by someone else. We are deep
below the bar, so any move of theta toward us multiplies gate(s_SN21). Whether it
is enough depends on where we land relative to theta=0.441%; score() answers that
against live state, and state['_gate_q'] sweeps it.

score() is the v440 gate with q overridden — a pure hyperparameter change, which
is exactly why this is a mechanism variant and not new machinery.
"""

from __future__ import annotations

from . import Mechanism, register
from .hill_gate_v440_2990 import _score as _gate_score

PR_URL = "https://github.com/RaoFoundation/subtensor/pull/3013"

PROPOSED_Q = 0.8073   # the PR's new DefaultEmissionBarQuantile
LIVE_Q_PER_CORE_DEV = 0.75   # mcjkula on the PR thread, 2026-07-29 — since
                             # CONFIRMED by reading EmissionBarQuantile on finney


def _score(sub: dict, state: dict) -> float:
    """v440 gate evaluated at the proposed q, unless the caller is sweeping."""
    if "_gate_q" in state:
        return _gate_score(sub, state)
    return _gate_score(sub, {**state, "_gate_q": PROPOSED_Q})


register(Mechanism(
    id="q_raise_3013",
    label="PROPOSED #3013 — emission bar quantile q 0.61 -> 0.8073 (LOOSER gate)",
    pr_url=PR_URL,
    activation_block=None,
    merged=False,
    stage="proposed",
    score=_score,
    notes=("OPEN, no reviews (ap-choji, 2026-07-29). Edits only the DEFAULT q "
           "in lib.rs; live q is a storage value we now READ (0.75 on finney, "
           "as core dev mcjkula said), so the diff itself is near-inert. The "
           "policy is what matters and it needs NO PR: q moves by a single "
           "sudo_set_emission_bar_quantile call. Raising q walks theta DOWN to "
           "a smaller share = looser gate = more emission for below-bar subnets "
           "like SN21. Cheapest relief available to us, and entirely out of our "
           "hands. Equally: q can be LOWERED the same way, with no warning."),
))
