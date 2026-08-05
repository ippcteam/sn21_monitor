"""
Root Reborn v2 (subtensor PR #2800 lineage) — root_prop REMOVED. **LIVE ON FINNEY.**

    emission_share_i  =  price_i  x  (1 - miner_burn_i)        [emit-enabled subnets]

Deployment history: the price x (1-MinerBurned) share shipped in PR #2781
(merged 2026-06-22, with #2779 as the price-share base); PR #2800 ("Enforce
conviction", merged 2026-06-30) then removed root_prop from the SHARE. The
whole train deployed to finney in the v430–v432 runtime releases
(2026-07-13..16; repo moved to RaoFoundation/subtensor). VERIFIED LIVE
2026-07-20 @ block ~8,665,500, spec_version 432:

  - `MinerBurned` storage populated for all subnets: 67 subnets > 0.5,
    ~44 at exactly 1.0 — those receive ZERO TAO emission (actual
    tao_in+excess = 0 on chain). SN21's MinerBurned = 0.602.
  - v432 `get_shares` (subnet_emissions.rs) = EMA-price share weighted by
    (1 - MinerBurned), renormalised; if every subnet's weight is zero it
    falls back to unweighted price shares (not modelled — never observed).
  - Emit-DISABLED subnets (SubnetEmissionEnabled=false, default off for new
    registrations per #2787) are zeroed and the emission renormalised over
    enabled subnets — modelled here via the row's `emission_enabled`.
  - `MinerBurned` = the fraction of a tempo's incentive emission whose
    recipient hotkey is owned by the subnet-owner coldkey (or is
    SubnetOwnerHotkey), recycled OR burned — recomputed every tempo
    (run_coinbase.rs), so a burn change takes effect the very next tempo.
  - The INJECTION CAP is root_prop x alpha_emission (run_coinbase.rs), with
    emission above the cap swapped into alpha (chain buys). The price channel
    and its threshold mechanics survive; root_prop is gone from the share only.

The same #2800 ACTIVATED conviction-based subnet-ownership transfer
(change_subnet_owner_if_needed, staking/lock.rs): if total rolled conviction on
a subnet >= 10% of SubnetAlphaOut, the subnet is >= 1 year old, and a non-owner
hotkey out-convicts the owner, OWNERSHIP MOVES to that hotkey's coldkey.
Conviction accrues only from explicitly LOCKED stake (do_lock_stake); plain
stake creates none. SN21 status 2026-07-20: age 2.1y (clause ARMED), takeover
threshold ~359k alpha, ZERO HotkeyLock entries exist — nobody can take it today
but we hold no defensive lock. Defenses: lock owner alpha (btcli lock), and/or
the `owner_cut_auto_lock_enabled` hyperparam (default false) which compounds
the owner cut into a conviction lock every tempo.
"""

from __future__ import annotations

from . import Mechanism, register

PR_URL = "https://github.com/RaoFoundation/subtensor/pull/2800"
ACTIVATION_BLOCK = 8_640_000  # ~v430 deploy window (2026-07-14); spec 432 by 07-16


def _score(sub: dict, state: dict) -> float:
    if not sub.get("emission_enabled", True):
        return 0.0
    price = sub.get("ema_price") or sub.get("spot_price") or 0.0
    if price <= 0:
        return 0.0
    if sub["netuid"] == state.get("netuid", 21):
        b = state.get("sn21_miner_burn", 0.0)
    else:
        b = sub.get("miner_burn", 0.0)
    return price * (1.0 - b)


register(Mechanism(
    id="root_reborn_v425_2800",
    label="Root Reborn v2 (price x (1-burn)) — LIVE",
    pr_url=PR_URL,
    activation_block=ACTIVATION_BLOCK,
    merged=True,
    stage="mainnet",  # verified live: spec 432, MinerBurned populated, fits chain
    score=_score,
    notes=("LIVE finney mechanism since the v430-v432 deploys (Jul 13-16 2026): "
           "share = price x (1-MinerBurned) over emit-enabled subnets, no "
           "root_prop. MinerBurned recomputes every tempo, so burn moves "
           "emission next tempo. ~44 full-burn subnets already at ZERO. "
           "Injection cap (root_prop x alpha_emission) unchanged. Same PR "
           "activated conviction ownership transfer — SN21 clause armed, no "
           "locks held; owner lock defense required."),
))
