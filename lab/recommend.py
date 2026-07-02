"""
Recommendation engine — turn the scenarios into ranked operator actions.

The operator goal is fixed and is the lens for everything here:

    MAXIMISE  alpha price  +  owner alpha
    AVOID     deregistration (price floor)  +  emission-blocking (triumvirate
              fake-mining throttle)

`build_recommendations(state, scenarios)` reads a ChainState plus the computed
S1..S5 results and returns: current standing, a risk register (the two risks to
avoid), and a ranked list of concrete actions — each tagged with its expected
effect on price and on owner alpha, the guardrail it respects, and a confidence.

Honest framing on burn (RESOLVED by Action 1 — subtensor coinbase source read;
magnitudes CONFIRMED 2026-07-02 once the gate counted the excess-TAO chain-buy leg):
lowering burn raises SN21's renormalised (1-b) network slice exactly linearly — the
old "effective burn" gap was a measurement artifact. The old worry — that burn routes
the miner allocation to the owner key — is FALSE: the coinbase BURNS withheld miner
incentive (destroyed/recycled via burn_subnet_alpha; the owner receives nothing).

Two magnitude corrections encoded here (2026-07-02):
1. OWNER ALPHA QUANTITY IS BURN-INDEPENDENT — alpha_out is 1/block for every subnet,
   so the 18% SubnetOwnerCut is a fixed ~1,296 alpha/day at ANY burn. Cutting burn
   raises the VALUE of that fixed alpha via price, not its amount. (An earlier
   version claimed the owner cut scales with the (1-b) slice — wrong.)
2. PRICE ONLY MOVES VIA CHAIN BUYS (S6). Liquidity injection adds both pool sides at
   spot; the direct price channel is the excess TAO above the injection cap
   (root_prop x alpha_emission), which today opens only once burn drops below ~0.5.
   Shallow cuts buy depth, not price — the price case is for DEEP cuts (b <= 0.2),
   staged, with realized miner dump kept below the S5 breakeven.
"""

from __future__ import annotations

from collector import load_json
from config import DATA_DIR
from .scenarios import (
    DEREG_FLOOR_TAO, DEREG_HEADROOM_MIN, MAX_WEEKLY_PRICE_IMPACT, _sn21,
)

WEIGHTS_STORE = DATA_DIR / "weights_scan.json"


def _price_standing(state: dict) -> dict:
    me = _sn21(state)
    spot = me.get("spot_price") or 0.0
    prices = sorted((s.get("spot_price") or 0.0) for s in state["subnets"] if s.get("spot_price"))
    n = len(prices)
    rank = sum(1 for p in prices if p < spot) + 1 if spot else None  # 1 = cheapest
    headroom = (spot / DEREG_FLOOR_TAO - 1.0) if spot else None
    n_below_floor = sum(1 for p in prices if p < DEREG_FLOOR_TAO)
    return {
        "spot": spot,
        "ema": me.get("ema_price"),
        "dereg_floor": DEREG_FLOOR_TAO,
        "headroom_pct": round(headroom * 100, 1) if headroom is not None else None,
        "price_rank_from_cheapest": rank,
        "n_priced": n,
        "n_below_floor": n_below_floor,
    }


def _scored_miners() -> int | None:
    """Best-effort count of miners actually being scored (legibility signal)."""
    w = load_json(WEIGHTS_STORE, {})
    try:
        vals = w.get("validators", []) or []
        return max((int(v.get("scored_miners") or 0) for v in vals), default=None)
    except (AttributeError, TypeError, ValueError):
        return None


def _dereg_risk(ps: dict) -> dict:
    h = ps.get("headroom_pct")
    if h is None:
        level = "unknown"
    elif h >= DEREG_HEADROOM_MIN * 100 * 2:
        level = "low"
    elif h >= DEREG_HEADROOM_MIN * 100:
        level = "medium"
    else:
        level = "high"
    return {
        "name": "Deregistration",
        "level": level,
        "detail": (f"Spot {ps['spot']:.6f} is {h:.1f}% above the assumed dereg floor "
                   f"{ps['dereg_floor']:.4f} ({ps['n_below_floor']}/{ps['n_priced']} subnets below it). "
                   f"Keep spot ≥ {DEREG_HEADROOM_MIN*100:.0f}% above the floor."
                   if h is not None else "No price data."),
    }


def _block_risk(b_now: float, scored: int | None) -> dict:
    if b_now <= 0.10:
        level = "low"
    elif b_now <= 0.40:
        level = "medium"
    else:
        level = "high"
    miners = f" {scored} miners scored." if scored else ""
    return {
        "name": "Emission-blocking (fake-mining throttle)",
        "level": level,
        "detail": (f"Current burn b={b_now:.2f}: the chain BURNS that share of miner alpha "
                   f"(destroyed/recycled — the owner does NOT receive it; its only emission is the "
                   f"separate 18% owner cut) AND, via the renormalised (1-burn) split, hands SN21's "
                   f"network emission slice to other subnets.{miners} Higher burn is the bad optic "
                   f"the triumvirate/Yuma throttle targets; lower burn reverses both costs."),
    }


def build_recommendations(state: dict, scenarios: dict) -> dict:
    b_now = state.get("sn21_miner_burn") or 0.0
    S2 = scenarios.get("S2", {}) or {}
    S3 = scenarios.get("S3", {}) or {}
    S4 = scenarios.get("S4", {}) or {}
    S5 = scenarios.get("S5", {}) or {}
    S6 = scenarios.get("S6", {}) or {}

    share_now = (S2.get("inputs") or {}).get("share_current_pct")
    share_b0 = (S2.get("inputs") or {}).get("share_no_burn_pct")
    # best 90/180-day price uplift vs holding, at the 15%-dump planning case (S6)
    s6_rows = [r for r in (S6.get("table") or []) if r.get("dump_frac") == 0.15]
    s6_best = max(s6_rows, key=lambda r: r["d90_vs_hold_pct"], default=None) if s6_rows else None
    s6_in = S6.get("inputs") or {}

    ps = _price_standing(state)
    scored = _scored_miners()
    risks = [_dereg_risk(ps), _block_risk(b_now, scored)]
    opt = S4.get("optimal") or {}
    s5_in = S5.get("inputs") or {}

    actions = []

    # 1 — Burn (master lever; aligns price + owner-alpha VALUE + legibility)
    if b_now > 0.001:
        target_b = s5_in.get("target_b")
        # safe single step from S5: largest sell_fraction keeping net pool flow >= 0
        safe_rows = [r for r in (S5.get("table") or []) if r.get("net_positive")]
        safe_dump = max((r["miner_sell_fraction"] for r in safe_rows), default=0.0)
        price_txt = ("↑ only once burn < ~0.5 (chain-buy threshold "
                     f"~{s6_in.get('chain_buy_threshold_tao_day')} TAO/day); "
                     f"best S6 case at 15% dump: {s6_best['d90_vs_hold_pct']:+.1f}% @90d / "
                     f"{s6_best['d180_vs_hold_pct']:+.1f}% @180d at b={s6_best['b']:.2f}"
                     if s6_best else
                     "↑ via chain buys only below the injection-cap threshold (S6)")
        actions.append({
            "priority": 1,
            "lever": "Burn rate",
            "action": (f"Reduce burn from b={b_now:.2f} DEEP (target ≤0.2, then 0) in staged "
                       f"steps — next step to b≈{target_b:.2f}. Shallow cuts (stopping above "
                       f"~0.5) add pool depth but ~zero price." if target_b is not None else
                       f"Reduce burn from b={b_now:.2f} deep toward 0 (price channel opens below ~0.5)."),
            "effect_price": price_txt,
            "effect_owner_alpha": (f"quantity FIXED at ~{s6_in.get('owner_alpha_day', 1296):,.0f}/day "
                                   "(18% cut is burn-independent); its VALUE rises with price"),
            "guardrail": (f"Emission-blocking risk ↓. Safe if miners dump ≤ "
                          f"~{safe_dump:.0%} of the freed alpha per S5 grid (fine-grained "
                          f"breakeven ~15%); route freed emission to an aligned miner set."),
            "confidence": "HIGH — source-read (run_coinbase.rs) + gate now reproduces SN21 within "
                          "tolerance once chain buys are counted; the (1−b) slice is exactly linear "
                          "and the owner captures none of the burn (destroyed).",
        })
    else:
        actions.append({
            "priority": 1,
            "lever": "Burn rate",
            "action": "Burn already ~0 — hold. The price-support and legibility levers are maxed.",
            "effect_price": "maxed", "effect_owner_alpha": "share at full (1−b)=1",
            "guardrail": "Emission-blocking risk already minimal.",
            "confidence": "HIGH",
        })

    # 2 — Extraction (realise owner alpha without breaching the dereg floor)
    if opt:
        actions.append({
            "priority": 2,
            "lever": "Extraction",
            "action": (f"Sell ≤ {opt.get('alpha_per_week'):,.0f} alpha/week "
                       f"({opt.get('weekly_sell_frac_of_reserve', 0)*100:.2f}% of reserve) "
                       f"→ ~{opt.get('realized_tao_per_week'):,.0f} TAO."),
            "effect_price": f"≤ {abs(opt.get('price_impact_pct', 0)):.2f}% weekly impact (capped)",
            "effect_owner_alpha": "converts owner alpha to TAO at the max safe rate",
            "guardrail": (f"Bound by {opt.get('binding_constraint')}; keeps spot "
                          f"≥ {DEREG_HEADROOM_MIN*100:.0f}% above the dereg floor."),
            "confidence": "MEASURED (constant-product slippage on live pool depth).",
        })

    # 3 — Guard the floor (only if dereg risk is not low)
    if risks[0]["level"] in ("medium", "high", "unknown"):
        actions.append({
            "priority": 3,
            "lever": "Dereg guard",
            "action": "Throttle extraction and/or add buy-side support to rebuild floor headroom "
                      "before reducing burn further.",
            "effect_price": "protects against floor breach",
            "effect_owner_alpha": "preserves the subnet (no emission if deregistered)",
            "guardrail": f"Dereg headroom currently {ps.get('headroom_pct')}%.",
            "confidence": "HIGH (floor breach zeroes everything).",
        })

    # Verdict
    decay = S3.get("inputs") or {}
    verdict_bits = []
    if b_now > 0.001:
        tgt = s5_in.get("target_b")
        verdict_bits.append(
            (f"reduce burn {b_now:.2f}→{tgt:.2f} now, staged on to ≤0.2 "
             f"(price channel opens below ~0.5)") if tgt is not None
            else "reduce burn deep (≤0.2; price channel opens below ~0.5)")
    if opt:
        verdict_bits.append(f"extract ≤{opt.get('alpha_per_week'):,.0f} alpha/wk")
    verdict = ("To grow price + owner alpha: " + ", ".join(verdict_bits) +
               f". Dereg headroom {ps.get('headroom_pct')}% ({risks[0]['level']}), "
               f"emission-blocking {risks[1]['level']}. "
               "Youth allowance (root_prop) is near peak now and fades slowly "
               f"(~{decay.get('root_prop_now')} → 30mo), so front-load while it's high.")

    return {
        "objective": "Maximise alpha price + owner alpha; avoid deregistration & emission-blocking.",
        "guardrails": {
            "dereg_floor_tao": DEREG_FLOOR_TAO,
            "dereg_headroom_min_pct": DEREG_HEADROOM_MIN * 100,
            "max_weekly_price_impact_pct": MAX_WEEKLY_PRICE_IMPACT * 100,
        },
        "standing": {
            "burn_b": round(b_now, 4),
            "emission_share_now_pct": share_now,
            "emission_share_no_burn_pct": share_b0,
            "owner_alpha_per_day": s6_in.get("owner_alpha_day"),   # fixed at every burn level
            "price_uplift_90d_pct_at_15pct_dump": s6_best["d90_vs_hold_pct"] if s6_best else None,
            "root_prop_now": (S3.get("inputs") or {}).get("root_prop_now"),
            **ps,
            "scored_miners": scored,
        },
        "risks": risks,
        "actions": actions,
        "verdict": verdict,
    }
