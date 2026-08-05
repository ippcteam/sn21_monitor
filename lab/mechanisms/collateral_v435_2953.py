"""
v435 — miner registration collateral (subtensor PR #2953). MERGED, NOT DEPLOYED.

Merged to RaoFoundation/subtensor main 2026-07-21 (spec_version 435); finney is
still spec 432 as of 2026-07-22 and no v433-435 release tag exists yet, so this
sits in the "Plan for this" lane.

EMISSION SHARE: UNCHANGED. `get_shares` (subnet_emissions.rs) has zero diff
v432→main — the share stays `price × (1 − MinerBurned)` over emit-enabled
subnets, so this module scores identically to the live mechanism. It is
registered so the change pipeline shows the deploy train and its stance.

WHAT CHANGES (subnets/collateral.rs + run_coinbase.rs hook, verified from
source):
  - Two per-subnet hyperparams: `CollateralLockShare` p ∈ [0,1) and
    `CollateralDrainRatio` k. With p>0 the (adaptive) registration cost splits:
    (1−p) burned exactly as today, p bought via the AMM and STAKED-AND-LOCKED
    to the registering (hotkey, coldkey) as miner collateral.
  - Per tempo, `settle_miner_collateral` releases min(k × incentive_earned,
    locked − min_locked) back to withdrawable stake — earned incentive is the
    ONLY exit; there is no direct withdrawal, ever.
  - The lock survives deregistration and credits the next registration of the
    same (hotkey, coldkey) at EMA-valued alpha, so real miners re-register for
    just the burn share. Bonded miners cannot hotkey-swap (identity rotation
    blocked); unstake/transfer guards keep the position covering the lock.
  - `min_locked` FLOOR (miner-set via set_min_collateral): incentive is
    CAPTURED into the lock while below the floor, and drain stops at it — a
    self-maintaining per-machine deposit that validators can require and score
    against. This is chain-native infrastructure for the curated-set retention
    policy (the withdrawn public stake-to-mine gate, now protocol-sanctioned).

SN21 read (S8 scenario quantifies): at today's 0.1 TAO reg cost the collateral
amounts are trivial for scored miners (payback < a day) — the teeth are (a) the
squatter/identity-rotation deterrent, and (b) the min_locked floor as the
enforcement rail for retention once v435 lands.
"""

from __future__ import annotations

from . import Mechanism, register
from .root_reborn_v425_2800 import _score as _live_score

PR_URL = "https://github.com/RaoFoundation/subtensor/pull/2953"


register(Mechanism(
    id="collateral_v435_2953",
    label="v435 miner collateral (share UNCHANGED)",
    pr_url=PR_URL,
    activation_block=None,
    merged=True,          # merged 2026-07-21; deploy pending -> testnet lane
    score=_live_score,    # get_shares has zero diff v432->main
    notes=("PR #2953 / spec 435 (merged, NOT deployed): registration splits "
           "into burned (1-p) + locked collateral p, unlocked only via earned "
           "incentive at ratio k; lock survives dereg, blocks hotkey swaps, "
           "and supports validator-required min_locked floors. Emission share "
           "formula untouched. Owner prep: choose p/k + floor policy (S8)."),
))
