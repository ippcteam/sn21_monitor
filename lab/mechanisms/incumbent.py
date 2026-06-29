"""
Incumbent (live) mechanism — for the §4.3 reproduction gate.

Models today's dynamic-TAO emission as price-weighted: a subnet's share of TAO
emission is proportional to its EMA (moving) price. This is the documented
conceptual mechanism; the reproduction gate (lab/runner.py) compares the modelled
SN21 share against the chain's ACTUAL per-block share (tao_in_emission) and reports
the error.

HONEST STATUS (measured live @ ~block 8,468,700): the chain's actual SN21 share
(~0.34%) does not match pure price-weighting (~0.29-0.45% depending on the subnet
set), and 60/128 subnets receive zero emission. So this incumbent model is
expected to MISS the tolerance until the exact formula is extracted from the
v3.4.6-421 subtensor source (Action 1 / G-9.1). That is the intended signal: a red
gate means "do not trust projections yet — read the source", per the doc. Do not
tune this to force a pass.
"""

from __future__ import annotations

from . import Mechanism, register

PR_URL = "https://github.com/opentensor/subtensor (live finney mechanism — confirm via Action 0)"


def _score(sub: dict, state: dict) -> float:
    """Price-weighted dynamic-TAO share. EMA price is the 'market salary'."""
    p = sub.get("ema_price") or sub.get("spot_price") or 0.0
    return max(0.0, float(p))


register(Mechanism(
    id="incumbent",
    label="Incumbent (price-weighted dynamic TAO)",
    pr_url=PR_URL,
    activation_block=None,
    stage="mainnet",  # this IS the live finney mechanism -> Go now
    score=_score,
    notes=("First-principles model of the live mechanism for the reproduction gate. "
           "Known to miss tolerance vs actual emission — flags that exact source "
           "formula extraction (Action 1) is still outstanding."),
))
