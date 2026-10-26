"""
LIVE — per-subnet emission weights ("etao").

subtensor #3254 (spec 480, merged 2026-10-15) introduced the vector.
#3264 (spec 481, merged 2026-10-16) replaced the frozen per-subnet TAO weight
with root paid its live baseline off the top of the validator slot every block.
Release v481 published 2026-10-19. Confirmed on finney spec_version 481.

EMISSION SHARE: UNCHANGED. Pool injection (`root_proportion`, `tao_in`,
`alpha_in`, excess TAO) and `get_shares` (the v440 gate) do not read the
vector. `score()` is the live gate, so `emission_share()` matches today.

WHAT CHANGES is how one subnet's own `alpha_out` is divided each block:

    vector = [burn, recycle, owner, validator, miner]   # u64 parts of u64::MAX

    v1 rules (emission_weights.rs):
        burn = recycle = 0
        owner     <= 33%     (lease-created subnets: owner >= the 18% default)
        validator <= 50% and validator > r
        miner     >= 33%
        sum = 1

    r = V0 · x / (x + A)          x = root_tao · TaoWeight
                                  A = subnet alpha issuance
                                  V0 = default validator share (~41%)
    root_alpha       = r · alpha_out          # on every legal vector; V > r
    alpha_validators = (V − r) · alpha_out
    owner_alpha      = owner · alpha_out
    miner_alpha      = miner · alpha_out      # MinerBurned still withholds
                                              # (1 − b) of this bucket

Root's alpha does not move when the owner sets a legal vector. The owner
rate limit is one call per 50_400 blocks (~7 days); the first call is free.
"""

from __future__ import annotations

from . import Mechanism, register
from .hill_gate_v440_2990 import _score as _gate_score

PR_URL = "https://github.com/RaoFoundation/subtensor/pull/3264"
ACTIVATION_SPEC = 481

# u64::MAX. Every slot is an integer number of these parts.
ONE = 2**64 - 1
U16_MAX = 65535
# 12s blocks, same constant as lab/scenarios.py. 50_400 blocks = 7 days.
BLOCK_SECONDS = 12
OWNER_RATE_LIMIT_BLOCKS = 50_400

MAX_OWNER = (ONE * 33) // 100
MAX_VALIDATOR = (ONE * 50) // 100
MIN_MINER = (ONE * 33) // 100


def scale_u16(value: int) -> int:
    """Legacy u16/u16::MAX fraction, scaled the way the runtime seeds the vector."""
    return (int(value) * ONE) // U16_MAX


def default_weights(owner_u16: int = 11796) -> tuple[int, int, int, int, int]:
    """Canonical seed: [0, 0, owner, validator, miner], miner absorbs rounding.

    11796/65535 is the mainnet SubnetOwnerCut the migration seeded from
    (18%). Matches SN21's on-chain vector at spec 481."""
    owner = scale_u16(owner_u16)
    validator = (ONE - owner) // 2
    miner = ONE - owner - validator
    return (0, 0, owner, validator, miner)


def _share(parts: int) -> float:
    return parts / ONE


def _parts_from_share(share: float) -> int:
    """Truncate toward zero, matching `emission_share_to_parts`."""
    if share <= 0:
        return 0
    return min(ONE, int(share * ONE))


def baseline_root_share(state: dict, sub: dict) -> float:
    """r = V0 · x / (x + A). Zero when there is no weighted root TAO."""
    v0 = _share(default_weights()[3])
    root_tao = state.get("root_tao") or state.get("root_stake_tao") or 0.0
    tao_weight = state.get("tao_weight") or 0.0
    issued = sub.get("alpha_issued") or 0.0
    weighted = root_tao * tao_weight
    denom = weighted + issued
    if denom <= 0 or v0 <= 0:
        return 0.0
    return v0 * weighted / denom


def _owner_u16(state: dict) -> int:
    raw = state.get("owner_cut")
    if not raw:
        return 11796
    return int(round(float(raw) * U16_MAX))


def legal(weights: tuple[int, int, int, int, int], root_parts: int, *,
          leased: bool = False, min_owner: int | None = None) -> bool:
    """v1 acceptance, including V > r (the chain rejects V <= r)."""
    burn, recycle, owner, validator, miner = weights
    if burn != 0 or recycle != 0:
        return False
    if sum(weights) != ONE:
        return False
    if owner > MAX_OWNER or validator > MAX_VALIDATOR or miner < MIN_MINER:
        return False
    if validator <= root_parts:
        return False
    if leased and owner < (default_weights()[2] if min_owner is None else min_owner):
        return False
    return True


def _vector(owner: int, validator: int, miner: int) -> tuple[int, int, int, int, int]:
    return (0, 0, owner, validator, miner)


def corners(state: dict, sub: dict | None = None, *, leased: bool = False) -> list[dict]:
    """The legal corners that matter for an owner: hold, max owner (miners
    held, and miners at the floor), owner to zero with miners maximised,
    and the 50% validator cap.

    Each row is a full vector. `miner_paid_share` is the miner slot after
    MinerBurned withholds its fraction — that burn hyperparameter is NOT
    the miner slot, and changing the slot does not change it.
    """
    if sub is None:
        target = state.get("netuid", 21)
        sub = next(s for s in state["subnets"] if s["netuid"] == target)
    current = default_weights(_owner_u16(state))
    r = baseline_root_share(state, sub)
    root_parts = _parts_from_share(r)
    floor = root_parts + 1
    _, _, cur_o, cur_v, cur_m = current

    candidates: list[tuple[str, tuple[int, int, int, int, int]]] = []

    def add(name: str, owner: int, validator: int) -> None:
        # Miner absorbs the remainder so the vector sums to ONE.
        candidates.append((name, _vector(owner, validator, ONE - owner - validator)))

    add("hold (seeded default)", cur_o, cur_v)

    # Max owner, miner slot kept at today's ~41%. The cut comes out of validators.
    add("max owner, miner slot held", MAX_OWNER, ONE - MAX_OWNER - cur_m)

    # Max owner, miner at its 33% floor. Validator takes what is left (~34%).
    add("max owner, miner at floor", MAX_OWNER, ONE - MAX_OWNER - MIN_MINER)

    # Owner at its floor (0, or 18% if leased). Validator sits one part above
    # root's baseline, so the miner slot takes everything root does not.
    min_owner = default_weights()[2] if leased else 0
    add("owner at floor, miner maximised", min_owner, floor)

    # Owner cut removed and the validator slot pushed to its 50% cap.
    # Miner receives the other 50%. Illegal when the lease floor binds.
    add("owner at floor, validator at cap", min_owner, MAX_VALIDATOR)

    burn = sub.get("miner_burn")
    if sub.get("netuid") == state.get("netuid", 21):
        burn = state.get("sn21_miner_burn", burn)
    burn = 0.0 if burn is None else min(1.0, max(0.0, float(burn)))
    alpha_out = sub.get("alpha_out_emission") or 0.0
    spot = sub.get("spot_price") or sub.get("ema_price") or 0.0
    blocks_day = 86400.0 / BLOCK_SECONDS

    rows = []
    for name, weights in candidates:
        ok = legal(weights, root_parts, leased=leased)
        owner_s = _share(weights[2])
        validator_s = _share(weights[3])
        miner_s = _share(weights[4])
        root_paid = min(validator_s, r)
        rows.append({
            "name": name,
            "legal": ok,
            "owner": owner_s,
            "validator": validator_s,
            "miner": miner_s,
            "root": root_paid,
            "alpha_validators": max(0.0, validator_s - root_paid),
            "miner_paid_share": miner_s * (1.0 - burn),
            "owner_alpha_day": owner_s * alpha_out * blocks_day,
            "miner_alpha_day": miner_s * alpha_out * blocks_day,
            "miner_paid_alpha_day": miner_s * (1.0 - burn) * alpha_out * blocks_day,
            "owner_tao_day": owner_s * alpha_out * blocks_day * spot,
            "alpha_out_per_block": alpha_out,
            "spot": spot,
            "baseline_root_share": r,
            "miner_burn": burn,
        })
    return rows


register(Mechanism(
    id="emission_weights_v481_3264",
    label="LIVE #3264 etao — owner sets the alpha split; TAO share unchanged",
    pr_url=PR_URL,
    activation_block=None,   # activated by runtime spec 481, not a block height we pin
    merged=True,
    stage="mainnet",
    score=_gate_score,
    notes=("Spec 481 on finney (PR #3254 + #3264). Owners set "
           "[burn, recycle, owner, validator, miner] within owner≤33%, "
           "validator≤50% and above root's baseline, miner≥33%. Root is paid "
           "r = V0·root_prop off the top every block, so a legal set cannot "
           "move root's alpha. Pool injection and the v440 emission share are "
           "untouched. SN21's lever is its own owner/miner/validator split, "
           "once per 50400 blocks after the first call."),
))
