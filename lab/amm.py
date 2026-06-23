"""
Shared constant-product AMM math for the SN21 lab.

Pool:  T * A = k,  spot price p = T / A  (TAO per alpha).
Selling dA alpha:
    p1 / p0 = ( A0 / (A0 + dA) )**2 = ( 1 / (1 + x) )**2 ,  x = dA / A0
So price impact depends ONLY on the sell size as a fraction of the alpha
reserve — robust even where absolute reserves are uncertain.

These functions were originally defined in root_reborn_model.py; they live here
now so both that script and the lab scenarios (S4 extraction, S5 dump-safety)
share one implementation. root_reborn_model.py imports them for back-compat.
"""

from __future__ import annotations

import math


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
