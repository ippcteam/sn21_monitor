"""
Root Reborn mechanism (subtensor v3.4.6-421 / PR #2759) — the three switches.

    emission_share_i  =  root_prop_i  x  price_i  x  (1 - miner_burn_i)
    root_prop_i       =  R / (R + A_i)        R = T_root x tao_weight

per the doc §1. A subnet's slice is this score normalised across all subnets.

Unit choice for A (CONFIRM against source — G-9.1):
  A_i is valued in TAO as `alpha_issued_i x ema_price_i` so it is unit-consistent
  with R (TAO). Under this choice SN21's root_prop is ~0.99 today (young, little
  alpha issued relative to root weight) — matching the doc's "youth allowance near
  its peak now". A raw-alpha convention (A = alpha_issued) gives a much lower
  root_prop; which the chain actually uses is the Action-1 source question. The
  convention is a module constant so it can be flipped when the source is read.

miner_burn:
  Only SN21's b is known (from the weight scan, state['sn21_miner_burn']). Other
  subnets are modelled at b=0 (best available). For SN21-centric scenarios (S2
  sweeps SN21's b, others fixed) this is exactly the right comparative.
"""

from __future__ import annotations

from . import Mechanism, register

PR_URL = "https://github.com/opentensor/subtensor/pull/2759"
ACTIVATION_BLOCK = None  # confirm via Action 0

# A-unit convention: True => A valued in TAO (alpha_issued x price); False => raw alpha.
VALUE_A_IN_TAO = True


def root_prop(sub: dict, state: dict) -> float:
    """R / (R + A) for one subnet."""
    R = (state.get("root_stake_tao") or 0.0) * (state.get("tao_weight") or 0.0)
    a = sub.get("alpha_issued") or 0.0
    if VALUE_A_IN_TAO:
        a = a * (sub.get("ema_price") or sub.get("spot_price") or 0.0)
    denom = R + a
    return (R / denom) if denom > 0 else 0.0


def _score(sub: dict, state: dict) -> float:
    price = sub.get("ema_price") or sub.get("spot_price") or 0.0
    if price <= 0:
        return 0.0
    # SN21's burn comes from state so scenarios can sweep it; every OTHER subnet
    # uses its own live MinerBurned (confirmed live; 81/128 subnets burn), so the
    # renormalised share is correct rather than assuming competitors burn nothing.
    if sub["netuid"] == state.get("netuid", 21):
        b = state.get("sn21_miner_burn", 0.0)
    else:
        b = sub.get("miner_burn", 0.0)
    return root_prop(sub, state) * price * (1.0 - b)


register(Mechanism(
    id="root_reborn_v346_421",
    label="Root Reborn (root_prop x price x (1-burn))",
    pr_url=PR_URL,
    activation_block=ACTIVATION_BLOCK,
    merged=True,  # shipped in release v3.4.6-421; mainnet activation block still unconfirmed
    score=_score,
    notes=("The doc's three-switch model. root_prop front-loads emission to young "
           "subnets; price couples emission to market salary; (1-b) is the "
           "attendance gate SN21 has dimmed to its current burn. A-unit convention "
           "and activation block pending source confirmation (G-9.1, Action 0)."),
))
