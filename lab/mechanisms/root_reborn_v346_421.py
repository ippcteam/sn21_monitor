"""
Root Reborn mechanism (subtensor v3.4.6-421 / PR #2759) — the three switches.

    emission_share_i  =  root_prop_i  x  price_i  x  (1 - miner_burn_i)
    root_prop_i       =  R / (R + A_i)        R = T_root x tao_weight

per the doc §1. A subnet's slice is this score normalised across all subnets.

Exact root_proportion (Action 1, subtensor block_step.rs:69 `root_proportion`):
  root_prop_i = (root_tao x tao_weight) / (root_tao x tao_weight + alpha_issuance_i)
  - root_tao      = SubnetTAO[0] (TAO in the ROOT pool; GLOBAL, same for all subnets)
  - tao_weight    = TaoWeight / 2**64 (live ~0.18)
  - alpha_issuance_i = SubnetAlphaIn_i + SubnetAlphaOut_i  (RAW alpha, NO price)
  The earlier `A = alpha_issued x ema_price` (TAO-valued) convention was WRONG —
  there is no price multiply, and the denominator uses AlphaIn+AlphaOut, not just
  alpha_out. Today alpha_issuance is ~uniform (~5.3M) across subnets, so root_prop
  is ~flat (~0.15) and barely affects relative shares — it matters as subnets'
  issuance diverges with age.

miner_burn:
  Only SN21's b is known (from the weight scan, state['sn21_miner_burn']). Other
  subnets are modelled at b=0 (best available). For SN21-centric scenarios (S2
  sweeps SN21's b, others fixed) this is exactly the right comparative.
"""

from __future__ import annotations

from . import Mechanism, register

PR_URL = "https://github.com/opentensor/subtensor/pull/2759"
ACTIVATION_BLOCK = None  # confirm via Action 0

def root_prop(sub: dict, state: dict) -> float:
    """Exact root_proportion(netuid): (root_tao x tao_weight) / (that + alpha_issuance).
    root_tao = SubnetTAO[0] (global); alpha_issuance = SubnetAlphaIn + SubnetAlphaOut
    (raw alpha, no price). Falls back to the legacy root_stake_tao only if root_tao
    is absent (e.g. an old snapshot)."""
    root_tao = state.get("root_tao")
    if root_tao is None:
        root_tao = state.get("root_stake_tao") or 0.0   # legacy fallback
    R = root_tao * (state.get("tao_weight") or 0.0)
    a = (sub.get("alpha_in") or 0.0) + (sub.get("alpha_issued") or 0.0)   # AlphaIn + AlphaOut
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
