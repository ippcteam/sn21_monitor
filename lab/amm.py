"""
Shared AMM math for the SN21 lab.

Pool (current lab assumption):  T * A = k,  spot p = T / A  (TAO per alpha).
Selling dA alpha:
    p1 / p0 = ( A0 / (A0 + dA) )**2 = ( 1 / (1 + x) )**2 ,  x = dA / A0
So price impact depends ONLY on the sell size as a fraction of the alpha
reserve — robust even where absolute reserves are uncertain.

These functions were originally defined in root_reborn_model.py; they live here
now so both that script and the lab scenarios (S4 extraction, S5 dump-safety)
share one implementation. root_reborn_model.py imports them for back-compat.

TWO FLOORS (do not mix them) — docs/SN21_AMM_Floor_BIT_2026-08-20.md:

  * Dereg *selection* is an EMA-price RANK (`dereg_watch.py`). There is no
    chain constant at 0.0035 TAO/α.
  * AMM *price* floor (`plowest`) is residual TAO left in a constant-product
    pool after all outstanding α is sold. The SN29 d2tao BIT (Feb 2026,
    https://coldint.io/d2tao.pdf) proposes removing that floor so p and τ_in
    can both go to zero. No PR as of 2026-08-20. S4/S5 still use CPMM until
    a live curve is read from source.

`α_held` in the BIT is outstanding α outside the pool ≈ `alpha_issued`
from chain_pull. Live pools may already be PalSwap/balancer; the BIT
equations below are the PDF's claims against x·y=k, not a reproduction of
finney.
"""

from __future__ import annotations

import math
from typing import Any


def price_impact(x: float) -> float:
    """Fractional price change from selling x = (alpha sold / alpha reserve)."""
    return (1.0 / (1.0 + x)) ** 2 - 1.0


def buy_impact(y: float) -> float:
    """Fractional price change from buying with y = (tao spent / tao reserve).

    Buying adds TAO and removes alpha: p1/p0 = (1 + y)**2 (symmetric to a sell
    of the equivalent alpha). Used by the §4.6 symmetry property test."""
    return (1.0 + y) ** 2 - 1.0


def overhang_alpha(div_day: float, share: float, price: float, days: int):
    """First-order accumulated basket position in alpha.
    Returns (accumulated_alpha, alpha_per_day, tao_in_per_day).
    Ignores buy-side slippage and basket compounding => slightly conservative."""
    tao_in_per_day = div_day * share
    alpha_per_day = tao_in_per_day / price if price else 0.0
    return alpha_per_day * days, alpha_per_day, tao_in_per_day


def floor_breach_overhang_ratio(price: float, floor: float) -> float:
    """Overhang ratio x at which a FULL one-shot cascade pushes spot to the floor."""
    return math.sqrt(price / floor) - 1.0


def realized_tao_from_sell(alpha_sold: float, alpha_reserve: float, tao_reserve: float) -> float:
    """Exact constant-product proceeds (TAO) from selling `alpha_sold` into the pool.

    k = A0 * T0; after adding alpha: A1 = A0 + alpha_sold, T1 = k / A1.
    Realized TAO = T0 - T1. Captures slippage exactly (not the first-order
    approximation) — used by S4 to value weekly extraction."""
    if alpha_reserve <= 0 or tao_reserve <= 0 or alpha_sold <= 0:
        return 0.0
    k = alpha_reserve * tao_reserve
    a1 = alpha_reserve + alpha_sold
    t1 = k / a1
    return tao_reserve - t1


# ── Current CPMM residual floor + SN29 BIT claims (not live) ──────────────────


def locked_tao_cpmm(tao_in: float, alpha_in: float, alpha_held: float) -> float:
    """TAO still in the pool if every outstanding α is sold (constant-product).

    τ_locked = τ_in · α_in / (α_in + α_held). This is the 'safety net' the
    d2tao BIT wants to release to holders."""
    a0 = alpha_in + alpha_held
    if tao_in <= 0 or alpha_in <= 0 or a0 <= 0:
        return 0.0
    return tao_in * alpha_in / a0


def amm_price_floor_cpmm(tao_in: float, alpha_in: float, alpha_held: float) -> float:
    """Hard lower spot if all α is sold: plowest = τ_locked / α0 = τ_in · α_in / α0²."""
    a0 = alpha_in + alpha_held
    if a0 <= 0:
        return 0.0
    return locked_tao_cpmm(tao_in, alpha_in, alpha_held) / a0


def liquidation_price(tao_in: float, alpha_held: float) -> float:
    """Dereg liquidation vs remaining holders: p_liq = τ_in / α_held."""
    if tao_in <= 0 or alpha_held <= 0:
        return 0.0
    return tao_in / alpha_held


def d2tao_instant_price_factor(alpha_in: float, alpha_held: float) -> float:
    """BIT claimed instant reprice: p_new / p_old = 1 + 2 · α_in / α_held.

    Paper-only. They propose a slow ease-in; do not treat this as a candle.
    Returns math.inf if α_held is 0 (last-α corner).
    """
    if alpha_in < 0:
        return 0.0
    if alpha_held <= 0:
        return math.inf
    return 1.0 + 2.0 * alpha_in / alpha_held


def d2tao_new_spot(tao_in: float, alpha_in: float, alpha_held: float) -> float:
    """BIT eq. 11 at current reserves: τ_in/α_in + 2 · τ_in/α_held."""
    if tao_in <= 0:
        return 0.0
    if alpha_in <= 0 or alpha_held <= 0:
        return 0.0
    return tao_in / alpha_in + 2.0 * tao_in / alpha_held


def amm_floor_from_row(row: dict[str, Any]) -> dict[str, Any]:
    """Snapshot the two AMM quantities from a chain_pull subnet row.

    `alpha_issued` is treated as α_held (outstanding outside the pool).
    """
    alpha_in = float(row.get("alpha_in") or 0.0)
    tao_in = float(row.get("tao_in") or 0.0)
    alpha_held = float(row.get("alpha_issued") or 0.0)
    spot = (tao_in / alpha_in) if alpha_in > 0 else 0.0
    if row.get("spot_price"):
        spot = float(row["spot_price"])
    floor = amm_price_floor_cpmm(tao_in, alpha_in, alpha_held)
    factor = d2tao_instant_price_factor(alpha_in, alpha_held)
    return {
        "tao_in": tao_in,
        "alpha_in": alpha_in,
        "alpha_held": alpha_held,
        "alpha0": alpha_in + alpha_held,
        "spot": spot,
        "locked_tao": locked_tao_cpmm(tao_in, alpha_in, alpha_held),
        "plowest": floor,
        "p_liq": liquidation_price(tao_in, alpha_held),
        "floor_over_spot": (floor / spot) if spot > 0 else None,
        "instant_bit_factor": factor,
        "d2tao_new_spot": d2tao_new_spot(tao_in, alpha_in, alpha_held),
        # True only if the AMM floor is in the same order as spot — i.e. selling
        # cannot reach a typical prune band. SN21 has been false on every 2026
        # snapshot we have.
        "dereg_safe_hint": bool(spot > 0 and floor >= 0.5 * spot),
    }
