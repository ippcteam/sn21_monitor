#!/usr/bin/env python3
"""
Root Reborn (subtensor PR #2759) — SN21 risk models
=====================================================
Two models:
  A. Redemption overhang & cascade price impact  (risk R-C, primary)
  B. Two-way reflexivity sketch via Taoflow       (risk R-D, gated)

AMM assumption: constant-product pool  T * A = k,  spot price p = T / A
(TAO per alpha). Selling dA alpha:
    p1 / p0 = ( A0 / (A0 + dA) )**2 = ( 1 / (1 + x) )**2 ,  x = dA / A0
So price impact depends ONLY on the sell size as a fraction of the
alpha reserve. That makes the model robust even where absolute reserve
figures are uncertain — what matters is the ratio.

USAGE
-----
  python root_reborn_model.py            # run on baked-in last-known LIVE pool state
  python root_reborn_model.py --live     # pull fresh SN21 pool state from finney, then run

The pool-state inputs (alpha_reserve, alpha_price_tao, tao reserve) are
LIVE-BACKED: defaults below are the last on-chain pull, and --live refreshes
them from the same finney path market_sync.py / collector.py use.

The flow inputs (network_root_div_tao_day, sn21_weight_share,
accumulation_days, baseline_rootprop_sell_alpha_day) are NOT chain-readable in
the current RPC version (subnet(21) emission fields return 0). They remain
ESTIMATE / SCENARIO knobs — edit them or pass via fetch overrides.
"""

import math
import sys

# ----------------------------------------------------------------------
# INPUTS
#   pool block: LIVE-BACKED (see DEFAULTS_SOURCE); refresh with --live
#   flow block: ESTIMATE / SCENARIO — not chain-readable
# ----------------------------------------------------------------------
DEFAULTS_SOURCE = "finney all_subnets() @ block 8,432,852 · 2026-06-18"

INPUTS = {
    # --- SN21 AMM pool (LIVE-BACKED — refresh with --live) ---
    "alpha_reserve":            1_974_778.0,   # alpha_in of the SN21 pool      [LIVE]
    "alpha_price_tao":          0.00405200,    # spot = tao_in / alpha_in       [LIVE]
    "dereg_floor_tao":          0.0035,        # not a chain constant; SN21 +15.8% above, 17/128 subnets below [ASSUMPTION]

    # --- Root Reborn buy-flow into SN21 (ESTIMATE / SCENARIO — not chain-readable) ---
    "network_root_div_tao_day": 1500.0,        # TOTAL TAO/day recycled across ALL baskets [ESTIMATE]
    "sn21_weight_share":        0.01,          # SN21's aggregate share of all root baskets [SCENARIO]
    "accumulation_days":        30,            # days the basket builds before a cascade    [SCENARIO]

    # --- Today's baseline for comparison (ESTIMATE — not chain-readable) ---
    "baseline_rootprop_sell_alpha_day": 50.0,  # current daily root-prop alpha sold on SN21  [ESTIMATE]
}

NETUID_SN21 = 21


# ----------------------------------------------------------------------
# LIVE POOL FETCH  — same finney path as market_sync.py / collector.py
# ----------------------------------------------------------------------
def _to_float(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        for attr in ("tao", "rao"):
            v = getattr(x, attr, None)
            if v is not None:
                return float(v) / (1e9 if attr == "rao" else 1.0)
    return None


def fetch_live_pool(netuid: int = NETUID_SN21) -> dict:
    """Pull live pool state for `netuid` from finney. Returns the keys of INPUTS
    that are chain-derivable: alpha_reserve, alpha_price_tao (+ block, tao_in).
    Raises on failure so a --live run never silently falls back to stale values."""
    from collector import _configure_chain_ssl, NETWORK
    _configure_chain_ssl()
    import bittensor as bt

    st = bt.Subtensor(network=NETWORK, log_verbose=False)
    raw = st.all_subnets()
    try:
        block = int(st.get_current_block())
    except Exception:
        block = None

    for d in raw or []:
        nu = getattr(d, "netuid", None)
        if nu is None or int(nu) != netuid:
            continue
        tao_in = _to_float(getattr(d, "tao_in", None))
        alpha_in = _to_float(getattr(d, "alpha_in", None))
        if not (tao_in and alpha_in and alpha_in > 0):
            break
        return {
            "block": block,
            "alpha_reserve": alpha_in,
            "tao_reserve": tao_in,
            "alpha_price_tao": tao_in / alpha_in,
        }
    raise RuntimeError(f"netuid {netuid} pool not found / invalid in all_subnets()")


# ----------------------------------------------------------------------
# CORE AMM MATH
# ----------------------------------------------------------------------
def price_impact(x: float) -> float:
    """Fractional price change from selling x = (alpha sold / alpha reserve)."""
    return (1.0 / (1.0 + x)) ** 2 - 1.0

def overhang_alpha(div_day, share, price, days):
    """First-order accumulated basket position in SN21 alpha.
    Ignores buy-side slippage and basket compounding => slightly conservative."""
    tao_in_per_day = div_day * share
    alpha_per_day = tao_in_per_day / price
    return alpha_per_day * days, alpha_per_day, tao_in_per_day

def floor_breach_overhang_ratio(price, floor):
    """Overhang ratio x at which a FULL one-shot cascade pushes spot to the floor."""
    return math.sqrt(price / floor) - 1.0


# ----------------------------------------------------------------------
# REPORT
# ----------------------------------------------------------------------
def banner(t):
    print("\n" + "=" * 68 + f"\n{t}\n" + "=" * 68)

def run(cfg=INPUTS, source: str = DEFAULTS_SOURCE):
    A0 = cfg["alpha_reserve"]
    p0 = cfg["alpha_price_tao"]
    floor = cfg["dereg_floor_tao"]
    T0 = p0 * A0

    banner(f"POOL SNAPSHOT  (pool state: {source})")
    print(f"  alpha reserve A0        : {A0:,.0f}")
    print(f"  spot price p0           : {p0:.5f} TAO/alpha")
    print(f"  implied TAO reserve T0  : {T0:,.0f} TAO")
    print(f"  dereg floor             : {floor:.5f} TAO/alpha  ({(floor/p0-1)*100:+.1f}% from spot)")

    # ---- Accumulation ----
    P, a_day, tao_day = overhang_alpha(
        cfg["network_root_div_tao_day"], cfg["sn21_weight_share"], p0, cfg["accumulation_days"])
    x_over = P / A0
    banner(f"MODEL A — OVERHANG ACCUMULATED IN {cfg['accumulation_days']} DAYS "
           f"@ {cfg['sn21_weight_share']*100:.2f}% weight share  [flow inputs = ESTIMATE]")
    print(f"  daily buy-flow into SN21: {tao_day:,.1f} TAO/day  (~{a_day:,.0f} alpha/day)")
    print(f"  accumulated overhang    : {P:,.0f} alpha")
    print(f"  overhang / reserve (x)  : {x_over*100:.2f}%")

    # ---- Cascade impact ----
    banner("CASCADE PRICE IMPACT  (overhang sold back into pool over a short window)")
    print(f"  {'redeemed':>10} | {'alpha sold':>12} | {'x=sold/A0':>10} | {'price impact':>13} | {'spot after':>11} | breaches floor?")
    print("  " + "-" * 84)
    for f in (0.10, 0.25, 0.50, 1.00):
        sold = f * P
        x = sold / A0
        imp = price_impact(x)
        spot_after = p0 * (1 + imp)
        breach = "YES" if spot_after <= floor else "no"
        print(f"  {f*100:9.0f}% | {sold:12,.0f} | {x*100:9.2f}% | {imp*100:12.2f}% | {spot_after:11.5f} | {breach}")

    # ---- Baseline comparison ----
    banner("BASELINE COMPARISON  (today's smooth root-prop sell — ESTIMATE)")
    q = cfg["baseline_rootprop_sell_alpha_day"]
    x_base = q / A0
    imp_base = price_impact(x_base)
    print(f"  baseline daily sell     : {q:,.0f} alpha/day")
    print(f"  daily price impact      : {imp_base*100:.4f}%  (spread across ~7,200 blocks => negligible intraday)")
    full_cascade_alpha = P
    equiv_days = full_cascade_alpha / q if q else float('inf')
    print(f"  a FULL cascade ({full_cascade_alpha:,.0f} alpha) compresses ~{equiv_days:,.0f} days "
          f"of baseline selling into one window")

    # ---- Floor-breach analysis ----
    banner("FLOOR-BREACH ANALYSIS  (full one-shot cascade)")
    x_breach = floor_breach_overhang_ratio(p0, floor)
    print(f"  overhang ratio that breaches floor on full cascade : {x_breach*100:.2f}% of reserve")
    print(f"  {'weight share':>13} | {'alpha/day':>10} | {'x/day':>8} | days to breach-capable overhang")
    print("  " + "-" * 70)
    for s in (0.005, 0.01, 0.02, 0.05):
        a_d = cfg["network_root_div_tao_day"] * s / p0
        x_d = a_d / A0
        days = x_breach / x_d if x_d else float('inf')
        print(f"  {s*100:12.1f}% | {a_d:10,.0f} | {x_d*100:7.3f}% | {days:6.0f} days")

    # ---- Sensitivity grid: overhang ratio (days x share) ----
    banner("SENSITIVITY — OVERHANG RATIO x  (rows = days, cols = weight share)")
    shares = (0.005, 0.01, 0.02, 0.05)
    print("  days\\share | " + " | ".join(f"{s*100:5.1f}%" for s in shares))
    print("  " + "-" * 52)
    for d in (14, 30, 60, 90):
        cells = []
        for s in shares:
            P_ds, _, _ = overhang_alpha(cfg["network_root_div_tao_day"], s, p0, d)
            cells.append(f"{P_ds/A0*100:5.1f}%")
        print(f"  {d:9d} | " + " | ".join(cells))

    # ---- Model B: reflexivity (gated) ----
    banner("MODEL B — TWO-WAY REFLEXIVITY (DIRECTIONAL, GATED ON OPEN QUESTION Q1)")
    print("  If basket buys COUNT as Taoflow net inflow (Q1 = YES), buy-flow B raises")
    print("  emission share, which raises root dividend minted on SN21, which raises B:")
    print("      B_eff ~= B / (1 - e)      e = Taoflow elasticity of emission share to inflow")
    for e in (0.0, 0.2, 0.4):
        amp = 1.0 / (1.0 - e)
        print(f"      e={e:.1f}  =>  amplification {amp:.2f}x  (up-spiral AND down-spiral)")
    print("  e is UNKNOWN here. If Q1 = NO (buys excluded, like legacy root-claim swaps),")
    print("  amplification = 1.0x and reflexivity is muted. RESOLVE Q1 BEFORE MODELLING.")

    print(f"\n[pool state {'LIVE' if '--live' in source else 'last-known live'} · "
          f"flow inputs ESTIMATE/SCENARIO — see module docstring]")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    cfg = dict(INPUTS)
    source = DEFAULTS_SOURCE + " (baked-in defaults)"
    if "--live" in argv:
        print("Pulling live SN21 pool state from finney …")
        live = fetch_live_pool()
        cfg["alpha_reserve"] = live["alpha_reserve"]
        cfg["alpha_price_tao"] = live["alpha_price_tao"]
        blk = f"block {live['block']:,}" if live.get("block") else "block ?"
        source = f"--live finney all_subnets() @ {blk}"
        print(f"  live alpha_reserve = {live['alpha_reserve']:,.0f}")
        print(f"  live tao_reserve   = {live['tao_reserve']:,.0f}")
        print(f"  live spot price    = {live['alpha_price_tao']:.6f} TAO/alpha")
    run(cfg, source=source)


if __name__ == "__main__":
    main()
