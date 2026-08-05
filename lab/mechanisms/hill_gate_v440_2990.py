"""
v440 — q-mass Hill EMISSION GATE (subtensor PR #2990). Runtime spec 440.

Merged to RaoFoundation/subtensor main 2026-07-27 (PR #2990, "release-v440:
emission gate"); release-v441 (#2994) immediately bumps spec 440->441 "so the
train can cut a new stable after mainnet executes", i.e. v440 is the upgrade
being pushed to finney now. Treat as "Plan for this" turning "Go now" the moment
the chain reports spec_version 440 (the runner's reproduction gate will confirm).

WHAT CHANGES (verified from source — subnet_emissions.rs get_shares, lib.rs
storage, admin-utils/misc setters):

  Pre-gate demand share (UNCHANGED from live v432):
      s_i = ema_price_i * (1 - MinerBurned_i)  / sum_j(...)   [emit-enabled only]

  NEW gate applied on top, then renormalised:
      e_i = gate(s_i) * s_i / sum_j( gate(s_j) * s_j )

      gate(s) = s^h / (s^h + theta^h) = 1 / (1 + (theta/s)^h)

  theta (EmissionGateBar) = the q-MASS BAR: sort the demand shares s_i
  descending, accumulate until the running cumulative first reaches
  EmissionBarQuantile q; theta is the share at that crossing. Subnets ABOVE the
  bar collectively carry q of demand. Recomputed every EMISSION_BAR_UPDATE_INTERVAL
  = 360 blocks and sticky in between (per-block price wiggle can't flap the
  boundary). theta=0 (never computed) disables the gate.

  Hyperparams (sudo-settable, ranges enforced on-chain):
      q = EmissionBarQuantile  default 0.61   (0,1)
      h = EmissionGateExponent default 3      [1,8]  — cliff sharpness at the bar

  gate(theta)=1/2 exactly at the bar; ~1 well above it; ~0 well below it. Effect:
  a SOFT TOP-K. The default q=0.61 lands theta near the uniform share
  (1/active_subnets, ~rank 32 on the Jul-2026 distribution) — everything below
  the bar has its emission crushed toward zero, everything above is boosted on
  renormalisation. The concentration multiplier is severe: the PR's own unit test
  shows two subnets at a 1:2 EMA-price ratio (linear shares 1/3 : 2/3) settle at
  1/10 : 9/10 after the default gate. A 2x demand edge becomes a 9x emission edge.

SN21 READ: SN21 sits in the bottom third of the price distribution (price
percentile ~30, and price*(1-b) pushes it lower still with b~0.60), i.e. DEEP
BELOW the q-mass bar. Under the gate its already-small linear share is multiplied
by gate(s_SN21) << 1 — a large emission cut on top of the burn. S9 quantifies the
exact factor against live state and sweeps q/h; the price-first defense (get SN21
ABOVE the bar) dominates the burn lever once the gate is live.

The gate is DISTRIBUTION-dependent (theta is a property of every subnet's share),
so score() computes theta from `state` on each call — O(N log N), fine for ~128
subnets. Set state['_gate_q'] / state['_gate_h'] to sweep the hyperparams; absent,
the on-chain defaults are used.
"""

from __future__ import annotations

from . import Mechanism, register

PR_URL = "https://github.com/RaoFoundation/subtensor/pull/2990"
ACTIVATION_BLOCK = 8_715_000  # CONFIRMED LIVE on finney by block 8,715,829 (see below)

DEFAULT_Q = 0.61   # EmissionBarQuantile on-chain default (lib.rs)
DEFAULT_H = 3.0    # EmissionGateExponent on-chain default (lib.rs)
BAR_UPDATE_INTERVAL = 360

# q, h and theta are READ FROM CHAIN, not fitted (2026-07-29). They are plain
# storage items — `EmissionBarQuantile`, `EmissionGateExponent`, `EmissionGateBar`
# — pulled into ChainState by chain_pull as gate_q / gate_h / gate_theta.
#
# The earlier calibration FITTED (q,h) to SN21's observed on-chain share and got
# q~0.77, h~2.9, reproducing the network to median rel.err 0.029. The chain in
# fact runs q=0.75, h=3.0 exactly (confirmed on finney 2026-07-29, and by core dev
# mcjkula on PR #3013). The fit was close enough to validate the gate's SHAPE, but
# there was never a reason to infer a value that can simply be read — and a fitted
# constant silently goes stale the moment a root call moves the real one.
#
# These constants remain only as the fallback for a state with no chain read.
LIVE_Q = 0.75      # EmissionBarQuantile, read from finney 2026-07-29
LIVE_H = 3.0       # EmissionGateExponent, read from finney 2026-07-29


def _q(state: dict) -> float:
    """Gate quantile: explicit sweep override > chain read > last-known live."""
    if "_gate_q" in state:
        return state["_gate_q"]
    return state.get("gate_q") or LIVE_Q


def _h(state: dict) -> float:
    """Gate exponent: explicit sweep override > chain read > last-known live."""
    if "_gate_h" in state:
        return state["_gate_h"]
    return state.get("gate_h") or LIVE_H


def _linear_share(sub: dict, state: dict) -> float:
    """Pre-gate demand share numerator = ema_price * (1 - burn), emit-enabled only.
    Identical basis to the live v432 mechanism (root_reborn_v425_2800)."""
    if not sub.get("emission_enabled", True):
        return 0.0
    price = sub.get("ema_price") or sub.get("spot_price") or 0.0
    if price <= 0:
        return 0.0
    if sub["netuid"] == state.get("netuid", 21):
        b = state.get("sn21_miner_burn", 0.0)
    else:
        b = sub.get("miner_burn", 0.0)
    return max(0.0, price * (1.0 - b))


def _normalized_shares(state: dict) -> dict:
    """s_i over emit-enabled subnets, summing to 1 (the distribution theta bins)."""
    raw = {s["netuid"]: _linear_share(s, state) for s in state["subnets"]}
    tot = sum(raw.values())
    if tot <= 0:
        return {}
    return {n: w / tot for n, w in raw.items()}


def emission_bar(state: dict) -> float:
    """theta — the q-mass bar over the current demand distribution.

    When the caller is NOT sweeping q, prefer the chain's own last-computed bar
    (`EmissionGateBar`, recomputed every 360 blocks): it is the exact value the
    coinbase gated on, with no dependence on our reconstruction of the share
    distribution. A sweep (`_gate_q`) must recompute, since the whole point is to
    ask what theta WOULD be at a different quantile."""
    if "_gate_q" not in state and state.get("gate_theta"):
        return state["gate_theta"]
    q = _q(state)
    shares = sorted(_normalized_shares(state).values(), reverse=True)
    cumulative = 0.0
    theta = 0.0
    for s in shares:
        cumulative += s
        theta = s
        if cumulative >= q:
            break
    return theta


def gate(s: float, theta: float, h: float) -> float:
    """Hill gate 1/(1+(theta/s)^h). 1/2 at the bar, ->1 above, ->0 below."""
    if s <= 0 or theta <= 0:
        return 0.0 if s <= 0 else 1.0
    return 1.0 / (1.0 + (theta / s) ** h)


def _score(sub: dict, state: dict) -> float:
    """Gated weight gate(s_i)*s_i (emission_share renormalises it to e_i)."""
    s = _linear_share(sub, state)
    if s <= 0:
        return 0.0
    # theta is over normalised shares; the per-subnet s here is un-normalised but
    # the gate ratio theta/s is scale-covariant only if both use the same basis.
    # Normalise this subnet's share the same way theta was computed.
    tot = sum(_linear_share(x, state) for x in state["subnets"])
    if tot <= 0:
        return 0.0
    s_norm = s / tot
    theta = emission_bar(state)
    return gate(s_norm, theta, _h(state)) * s_norm


register(Mechanism(
    id="hill_gate_v440_2990",
    label="v440 q-mass Hill emission gate (CONCENTRATES) — LIVE",
    pr_url=PR_URL,
    activation_block=ACTIVATION_BLOCK,
    merged=True,          # merged to main 2026-07-27; CONFIRMED live on finney
    stage="mainnet",      # reproduction 62/62 within tol at calibrated q,h — it's live
    score=_score,
    notes=("PR #2990 / spec 440 (merged 2026-07-27): on top of the live "
           "price*(1-burn) demand share, a Hill gate 1/(1+(theta/s)^h) with theta "
           "the q-mass bar (q=0.61, h=3 defaults) crushes emission for every subnet "
           "below the bar and boosts those above. Soft top-k ~rank 32. SN21 (price "
           "pct ~30, b~0.60) sits DEEP below the bar -> large emission cut. Defense "
           "is price-first: lift SN21's demand share above theta. See S9."),
))
