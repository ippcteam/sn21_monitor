"""
PROPOSED — cap chain buys at the TAO value of UNBURNED miner emissions
(subtensor PR #3012, "Cap chain buys at unburned miner emissions").

STATUS 2026-07-29: OPEN **DRAFT** by gzaentz (codex/cap-chain-buys-miner-emissions),
opened 2026-07-29 01:45 UTC, no formal reviews but a live design argument in the
thread (see below). Not merged, not on finney. Lane = "Consider this".

EMISSION SHARE: UNCHANGED. get_shares is untouched — this PR edits
run_coinbase.rs / get_subnet_terms, i.e. what happens to a subnet's TAO AFTER its
share is decided. So it scores identically to the live v440 gate and is
registered to keep the change pipeline honest. The damage it does to us is
downstream of the share and is quantified by `chain_buy_cap` below.

WHAT CHANGES (get_subnet_terms, verified from the diff):

  Today, a mature subnet whose liquidity injection is capped spends the leftover
  ("excess TAO") buying its own alpha on its own pool — the chain buyback. That
  is unconditional buy pressure and it is a large fraction of SN21's realised
  emission (the lab already counts it: actual emission = tao_in + excess_tao).

  The PR caps it:

      participant_alpha = alpha_emission * (1 - owner_cut)   [if owner cut on]
      allocated_miner_alpha = participant_alpha * 0.5 * (1 - MinerBurned)
      chain_buy = min(excess_tao, allocated_miner_alpha * spot_price)

  TAO above the cap is still issued, but is redistributed across emitting subnets
  by emission weight into each subnet's BalancerTaoReservoir — held, NOT swapped.
  It creates no buy pressure and no price move in the block.

  At MinerBurned = 1.0 the cap is exactly ZERO: a fully-burning subnet gets no
  chain buy at all.

THE THREAD IS THE STORY. camfairchild (core dev) asked the exact right question:

    "Is this not doubling the miner burn penalty?"

and gzaentz conceded the mechanism does hit burning subnets twice, defending it
on equilibrium grounds:

    "the point is to stop chain buys from exceeding the miner emissions a sn
     actually pays out. so it can hit burning sns twice. we could cap buybacks at
     total miner emissions and get almost the same result, but including burn
     keeps the buyback tied to what miners actually receive"

So the double-penalty is ACKNOWLEDGED AND INTENTIONAL, and a burn-independent
variant (cap at total miner emissions) is explicitly on the table as an
alternative that "gets almost the same result".

SN21 READ — this is the one that bites us hardest of the four emission PRs.
We run a deliberately high miner burn (b = 0.45 live at block 8.73M, down from
0.60). Under v440 that b already multiplies our demand share by (1-b). This PR
multiplies our chain-buy leg by (1-b) A SECOND TIME. The two compound:

      share    ~ price * (1 - b)          [v440, live today]
      buy leg  ~ ...   * (1 - b)          [#3012, proposed]

Our burn lever was already the cheapest thing we control (memory: b=0 frees ~9x
under the gate). If #3012 lands, cutting b gets MORE valuable again, and holding
a high b becomes materially more expensive than the live model says. Note the
capped TAO is not destroyed — it sits in our reservoir and may be activated
later by the balancer — so this is a timing-and-price-support hit, not an
outright emission loss. But price support is precisely the channel the v440 gate
scores us on, which is what makes it compounding rather than merely annoying.
"""

from __future__ import annotations

from . import Mechanism, register
from .hill_gate_v440_2990 import _score as _gate_score

PR_URL = "https://github.com/RaoFoundation/subtensor/pull/3012"

MINER_SHARE = 0.5   # miners take half of participant alpha (validators the other half)


def chain_buy_cap(sub: dict, state: dict) -> float:
    """TAO value of the alpha actually paid to miners = the proposed cap.

    allocated_miner_alpha = alpha_emission * (1 - owner_cut) * 0.5 * (1 - burn)
    cap                   = allocated_miner_alpha * spot_price
    """
    alpha_em = sub.get("alpha_out_emission") or 0.0
    if alpha_em <= 0:
        return 0.0
    owner_cut = state.get("owner_cut", 0.0) or 0.0
    if sub["netuid"] == state.get("netuid", 21):
        b = state.get("sn21_miner_burn", 0.0)
    else:
        b = sub.get("miner_burn", 0.0) or 0.0
    b = min(1.0, max(0.0, b))
    price = sub.get("spot_price") or sub.get("ema_price") or 0.0
    return alpha_em * (1.0 - owner_cut) * MINER_SHARE * (1.0 - b) * price


def capped_chain_buy(sub: dict, state: dict) -> float:
    """What the chain buy becomes under #3012: min(today's excess_tao, cap)."""
    return min(sub.get("excess_tao_emission") or 0.0, chain_buy_cap(sub, state))


def reservoired_tao(sub: dict, state: dict) -> float:
    """TAO diverted from buy pressure into the balancer reservoir."""
    return max(0.0, (sub.get("excess_tao_emission") or 0.0) - chain_buy_cap(sub, state))


register(Mechanism(
    id="chain_buy_cap_3012",
    label="PROPOSED #3012 — chain buys capped at unburned miner emissions (share UNCHANGED)",
    pr_url=PR_URL,
    activation_block=None,
    merged=False,
    stage="proposed",
    score=_gate_score,   # get_shares untouched — scores as the live v440 gate
    notes=("OPEN DRAFT (gzaentz, 2026-07-29). Emission SHARE untouched; caps "
           "the chain-buy leg at alpha_emission*(1-owner_cut)*0.5*(1-burn)*price "
           "and reservoirs the remainder instead of swapping it. Core dev "
           "camfairchild flagged it 'doubling the miner burn penalty'; author "
           "conceded 'it can hit burning sns twice' and named a burn-independent "
           "variant as a near-equivalent alternative. SN21 runs b=0.45, so our "
           "buy leg would be multiplied by (1-b) a SECOND time on top of the "
           "v440 share term. Makes cutting b more valuable, not less."),
))
