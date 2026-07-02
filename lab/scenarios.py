"""
Scenarios S1..S5 (§4.4) — pure functions over a ChainState.

Each returns a JSON-safe dict: `table` (rows to chart/tabulate), `summary`
(plain-language, per the doc's "no math background" requirement), and `inputs`
(what it was computed from). None of these mutate the ChainState — b-sweeps run
on shallow copies.

What runs on existing data vs. what the new pulls unlock:
  S2 burn sweep, S4 extraction, S5 dump-safety  — spot price + burn (always ran)
  S1 old-vs-new, S3 decay                        — need root_prop (new data layer)
"""

from __future__ import annotations

import copy
import math

from .amm import price_impact, realized_tao_from_sell
from . import mechanisms as M
from .mechanisms import root_reborn_v346_421 as RR

BLOCK_SECONDS = 12

# ── Operator guardrails (the risks to avoid). Tune via env/source confirmation. ──
DEREG_FLOOR_TAO = 0.0035          # assumed deregistration price floor (R-C; confirm)
DEREG_HEADROOM_MIN = 0.15         # want spot >= 15% above the floor
MAX_WEEKLY_PRICE_IMPACT = 0.02    # cap a single week's extraction at 2% price impact


def max_sell_frac_for_impact(max_impact: float) -> float:
    """Largest sell (fraction of alpha reserve) whose price impact stays within
    max_impact: (1/(1+x))^2 - 1 >= -max_impact  =>  x <= 1/sqrt(1-max_impact) - 1."""
    if max_impact <= 0 or max_impact >= 1:
        return 0.0
    return 1.0 / math.sqrt(1.0 - max_impact) - 1.0


def _sn21(state: dict) -> dict:
    return next(s for s in state["subnets"] if s["netuid"] == state.get("netuid", 21))


def _state_with_b(state: dict, b: float) -> dict:
    s = copy.copy(state)
    s["sn21_miner_burn"] = b
    return s


def _blocks_per_day(state: dict) -> float:
    tempo = (_sn21(state).get("tempo") or 360)
    # emission accrues per block; tempo is the scoring cadence. Use seconds/block.
    return 86400.0 / BLOCK_SECONDS


# ── S1 — old vs new at activation ────────────────────────────────────────────
def s1_old_vs_new(state: dict) -> dict:
    inc = M.get("incumbent")
    new = M.get("root_reborn_v346_421")
    share_old = M.emission_share(inc, state)
    share_new = M.emission_share(new, state)
    ratio = (share_new / share_old) if share_old > 0 else None
    return {
        "table": [
            {"mechanism": "incumbent", "sn21_emission_share_pct": round(share_old * 100, 5)},
            {"mechanism": "root_reborn", "sn21_emission_share_pct": round(share_new * 100, 5)},
        ],
        "inputs": {"b": state.get("sn21_miner_burn"), "block": state.get("block")},
        "summary": (
            f"At current burn b={state.get('sn21_miner_burn')}, SN21's modelled emission "
            f"share goes from {share_old*100:.4f}% (incumbent) to {share_new*100:.4f}% "
            f"(Root Reborn)" + (f" — {ratio:.2f}x." if ratio else ".")
        ),
        "trust_note": "Absolute owner emission needs the network TAO-emission anchor; "
                      "shares are robust. Incumbent number only as good as the reproduction gate.",
    }


# ── S2 — burn sweep → target b (decision D-Q) ────────────────────────────────
def s2_burn_sweep(state: dict, steps: int = 16) -> dict:
    new = M.get("root_reborn_v346_421")
    b_now = state.get("sn21_miner_burn") or 0.0
    share_now = M.emission_share(new, _state_with_b(state, b_now))
    share_b0 = M.emission_share(new, _state_with_b(state, 0.0))  # un-burned maximum
    rows = []
    for i in range(steps + 1):
        b = i / steps
        share = M.emission_share(new, _state_with_b(state, b))
        rows.append({
            "b": round(b, 4),
            "sn21_emission_share_pct": round(share * 100, 6),
            # robust at b=1 (where share_now may be 0): always index off the b=0 max
            "share_vs_no_burn": round(share / share_b0, 4) if share_b0 > 0 else None,
            "share_vs_current": round(share / share_now, 4) if share_now > 0 else None,
        })
    return {
        "table": rows,
        "inputs": {"b_current": round(b_now, 4),
                   "share_current_pct": round(share_now * 100, 6),
                   "share_no_burn_pct": round(share_b0 * 100, 6)},
        "summary": (
            f"Owner emission scales with (1-b). At the current burn b={b_now:.2f} SN21's "
            f"emission share is {share_now*100:.4f}%; un-burned (b=0) it would be "
            f"{share_b0*100:.4f}% — the full recoverable slice. The curve is the input to "
            f"the target-burn decision (D-Q)."
        ),
    }


# ── S3 — youth-allowance decay ───────────────────────────────────────────────
def s3_decay(state: dict, months: int = 30, ref_burn: float = 0.0) -> dict:
    """Isolates the root_prop (youth-allowance) fade. Computed at a FIXED reference
    burn (default b=0) so the structural decay isn't masked by today's burn —
    today SN21 is at full burn, which would zero every share."""
    new = M.get("root_reborn_v346_421")
    base = _state_with_b(state, ref_burn)
    me = _sn21(base)
    alpha_per_block = me.get("alpha_out_emission") or 0.0
    alpha_per_day = alpha_per_block * (86400.0 / BLOCK_SECONDS)
    A0 = me.get("alpha_issued") or 0.0
    share_now = M.emission_share(new, base)
    rows = []
    for m in range(0, months + 1):
        A = A0 + alpha_per_day * 30 * m
        proj = copy.deepcopy(base)
        pm = _sn21(proj)
        pm["alpha_issued"] = A
        rp = RR.root_prop(pm, proj)
        share = M.emission_share(new, proj)
        rows.append({
            "month": m,
            "alpha_issued": round(A, 0),
            "root_prop": round(rp, 5),
            "sn21_emission_share_pct": round(share * 100, 6),
            "share_vs_now": round(share / share_now, 4) if share_now > 0 else None,
        })
    end = rows[-1]
    rp_now = RR.root_prop(me, base)
    return {
        "table": rows,
        "inputs": {"A0": round(A0, 0), "alpha_per_day": round(alpha_per_day, 1),
                   "root_prop_now": round(rp_now, 5), "ref_burn": ref_burn},
        "summary": (
            f"At the current issuance (~{alpha_per_day:,.0f} alpha/day) and a reference "
            f"burn b={ref_burn:.2f}, SN21's root_prop fades from {rp_now:.4f} now to "
            f"{end['root_prop']:.4f} in {months} months — emission share to "
            f"{end['share_vs_now']}x today. The runway-shape input to the financial "
            f"model (R-M)."
        ),
    }


# ── S4 — extraction / slippage ───────────────────────────────────────────────
def s4_extraction(state: dict, weekly_fracs=(0.005, 0.01, 0.02, 0.05, 0.10)) -> dict:
    me = _sn21(state)
    A = me.get("alpha_in") or 0.0          # pool alpha reserve
    T = me.get("tao_in") or 0.0            # pool TAO reserve
    spot = me.get("spot_price") or 0.0
    rows = []
    for f in weekly_fracs:
        sold = f * A
        realized = realized_tao_from_sell(sold, A, T)
        x = sold / A if A else 0.0
        rows.append({
            "weekly_sell_frac_of_reserve": round(f, 4),
            "alpha_sold": round(sold, 0),
            "realized_tao": round(realized, 2),
            "avg_price": round(realized / sold, 8) if sold else None,
            "price_impact_pct": round(price_impact(x) * 100, 3),
        })
    # Max safe weekly extraction: largest sell within the price-impact guardrail AND
    # keeping spot above the dereg floor + headroom margin.
    f_impact = max_sell_frac_for_impact(MAX_WEEKLY_PRICE_IMPACT)
    floor_target = DEREG_FLOOR_TAO * (1.0 + DEREG_HEADROOM_MIN)
    if spot > 0 and floor_target < spot:
        # spot_after = spot * (1/(1+x))^2 >= floor_target  =>  x <= sqrt(spot/floor_target) - 1
        f_floor = math.sqrt(spot / floor_target) - 1.0
    else:
        f_floor = 0.0
    f_opt = max(0.0, min(f_impact, f_floor))
    opt_alpha = f_opt * A
    opt_tao = realized_tao_from_sell(opt_alpha, A, T)
    binding = "price-impact cap" if f_impact <= f_floor else "dereg-floor headroom"
    optimal = {
        "weekly_sell_frac_of_reserve": round(f_opt, 5),
        "alpha_per_week": round(opt_alpha, 0),
        "realized_tao_per_week": round(opt_tao, 2),
        "price_impact_pct": round(price_impact(f_opt) * 100, 3),
        "binding_constraint": binding,
        "spot_after": round(spot * (1 + price_impact(f_opt)), 8),
    }
    return {
        "table": rows,
        "optimal": optimal,
        "inputs": {"pool_alpha": round(A, 0), "pool_tao": round(T, 0), "spot": round(spot, 8),
                   "dereg_floor": DEREG_FLOOR_TAO, "max_weekly_impact": MAX_WEEKLY_PRICE_IMPACT},
        "summary": (
            f"Pool depth {A:,.0f} alpha / {T:,.0f} TAO. Max SAFE weekly extraction is "
            f"~{opt_alpha:,.0f} alpha ({f_opt*100:.2f}% of reserve) → ~{opt_tao:,.0f} TAO at "
            f"{optimal['price_impact_pct']:.2f}% impact (bound by {binding}). Reducing the burn "
            f"(S2) deepens the pool and raises this ceiling — the reflexive lever in §2."
        ),
    }


# ── S5 — dump safety at lower burn ───────────────────────────────────────────
def s5_dump_safety(state: dict, target_b: float | None = None, step: float = 0.10,
                   sell_fracs=(0.0, 0.25, 0.5, 0.75, 1.0)) -> dict:
    """Is the NEXT burn REDUCTION safe? At a lower burn miners receive more alpha;
    net daily TAO flow into the pool = extra emission-driven TAO injection - extra
    miner sell pressure (alpha dumped, valued at price). Sweep the fraction of the
    extra miner alpha that gets dumped; the crossover is the safe-step signal.

    target_b defaults to one `step` BELOW the current burn (a reduction), so the
    scenario is always direction-correct regardless of where the operator is today."""
    new = M.get("root_reborn_v346_421")
    me = _sn21(state)
    A = me.get("alpha_in") or 0.0
    T = me.get("tao_in") or 0.0
    price = me.get("spot_price") or 0.0
    b_now = state.get("sn21_miner_burn") or 0.0
    if target_b is None:
        target_b = max(0.0, b_now - step)
    blocks_day = 86400.0 / BLOCK_SECONDS

    share_now = M.emission_share(new, _state_with_b(state, b_now))
    share_tgt = M.emission_share(new, _state_with_b(state, target_b))
    extra_share = max(0.0, share_tgt - share_now)

    # network-wide daily TAO injection (sum of per-block tao_in_emission across subnets)
    net_tao_inj_day = sum((s.get("tao_in_emission") or 0.0) for s in state["subnets"]) * blocks_day
    extra_injection_tao_day = extra_share * net_tao_inj_day

    # extra miner alpha/day freed by un-burning (scales with the burn reduction)
    alpha_day = (me.get("alpha_out_emission") or 0.0) * blocks_day
    extra_miner_alpha_day = alpha_day * max(0.0, (b_now - target_b))

    rows = []
    for sf in sell_fracs:
        dumped = extra_miner_alpha_day * sf
        sell_tao_day = dumped * price          # TAO/day of sell pressure
        net_tao_day = extra_injection_tao_day - sell_tao_day
        rows.append({
            "miner_sell_fraction": round(sf, 3),
            "extra_miner_alpha_dumped_day": round(dumped, 0),
            "extra_injection_tao_day": round(extra_injection_tao_day, 2),
            "sell_pressure_tao_day": round(sell_tao_day, 2),
            "net_tao_day": round(net_tao_day, 2),
            "net_positive": net_tao_day >= 0,
        })
    safe = [r for r in rows if r["net_positive"]]
    max_safe_sf = max((r["miner_sell_fraction"] for r in safe), default=0.0)
    return {
        "table": rows,
        "inputs": {"target_b": target_b, "b_now": round(b_now, 4),
                   "share_now_pct": round(share_now * 100, 6),
                   "share_target_pct": round(share_tgt * 100, 6),
                   "extra_injection_tao_day": round(extra_injection_tao_day, 2)},
        "summary": (
            f"Cutting burn {b_now:.2f}->{target_b:.2f} raises SN21's emission share "
            f"{share_now*100:.4f}%->{share_tgt*100:.4f}% (~{extra_injection_tao_day:,.0f} "
            f"extra TAO/day into the pool). Net pool flow stays positive while miners dump "
            f"up to ~{max_safe_sf:.0%} of the extra alpha — the safe-step input (R-Q)."
        ),
    }


# ── S6 — burn → alpha-price trajectory ───────────────────────────────────────
def s6_burn_price(state: dict,
                  burns=(0.778, None, 0.65, 0.50, 0.35, 0.20, 0.10, 0.0),
                  dump_fracs=(0.0, 0.15, 0.30, 0.50, 1.0),
                  days: int = 180, ema_tc_days: float = 7.0) -> dict:
    """Simulate SN21's alpha price at candidate MinerBurned levels x miner-dump
    fractions, using the exact v3.4.8+ coinbase split (run_coinbase.rs):

      - a subnet's block TAO emission = share x block_emission, where share is the
        renormalised ema_price x root_prop x (1-b) (the mechanism model);
      - liquidity injection is CAPPED at root_prop x alpha_emission; injection adds
        BOTH sides of the pool at spot (deepens, does not move price);
      - emission above the cap becomes excess TAO -> CHAIN BUYS (swaps TAO for
        alpha), which move price UP. This is the only direct price channel, and it
        only opens once emission exceeds the cap (b below ~0.5 today);
      - freed miner alpha (vs the CURRENT chain burn) x dump_frac is sold into the
        pool daily (price DOWN);
      - reflexive loop: ema_price follows spot (~ema_tc_days), share follows ema;
        root_prop decays as issuance grows.

    `None` in burns is replaced by the current chain burn (the hold baseline).
    All trajectories are ceteris paribus (no organic flows) — read them as
    RELATIVE to the hold-current baseline, not absolute forecasts."""
    new = M.get("root_reborn_v346_421")
    me = _sn21(state)
    b_now = state.get("sn21_miner_burn") or 0.0
    blocks_day = 86400.0 / BLOCK_SECONDS
    # actual network block emission = injection + chain-buy legs (0.5 TAO/block live)
    block_emission = sum(((s.get("tao_in_emission") or 0.0) +
                          (s.get("excess_tao_emission") or 0.0)) for s in state["subnets"])
    # cross-subnet denominator excluding SN21 (others held at snapshot)
    d_rest = sum(max(0.0, new.score(s, state)) for s in state["subnets"]
                 if s["netuid"] != state.get("netuid", 21))
    root_tao = state.get("root_tao") or state.get("root_stake_tao") or 0.0
    tw = root_tao * (state.get("tao_weight") or 0.0)
    owner_cut = state.get("owner_cut") or 0.18
    alpha_emission = me.get("alpha_out_emission") or 1.0
    alpha_out_day = alpha_emission * blocks_day
    # miner incentive pool: alpha_out minus owner cut, 50% miner split
    miner_pool_day = 0.5 * (1.0 - owner_cut) * alpha_out_day

    if not (me.get("alpha_in") and me.get("tao_in") and block_emission > 0 and d_rest > 0):
        return {"error": "S6 needs pool reserves, per-subnet emission (incl. excess) and root_tao"}

    def simulate(b: float, dump_frac: float) -> list[float]:
        A, T = me["alpha_in"], me["tao_in"]
        ema = me.get("ema_price") or (T / A)
        issuance = (me.get("alpha_in") or 0.0) + (me.get("alpha_issued") or 0.0)
        k_ema = 1.0 - math.exp(-1.0 / ema_tc_days)
        traj = []
        for _ in range(days + 1):
            spot = T / A
            traj.append(spot)
            rp = tw / (tw + issuance) if (tw + issuance) > 0 else 0.0
            w21 = ema * rp * (1.0 - b)
            share = w21 / (d_rest + w21)
            tao_day = share * block_emission * blocks_day
            cap_alpha_day = rp * alpha_emission * blocks_day
            alpha_needed = tao_day / spot if spot > 0 else 0.0
            inj_alpha = min(alpha_needed, cap_alpha_day)
            inj_tao = inj_alpha * spot if alpha_needed > cap_alpha_day else tao_day
            buy_tao = max(0.0, tao_day - inj_tao)
            T += inj_tao
            A += inj_alpha
            if buy_tao > 0:                       # chain buys: TAO in, alpha out
                A = (A * T) / (T + buy_tao)
                T += buy_tao
            dump = miner_pool_day * max(0.0, b_now - b) * dump_frac
            if dump > 0:                          # miner sells: alpha in, TAO out
                T = (A * T) / (A + dump)
                A += dump
            issuance += alpha_out_day + inj_alpha
            ema += k_ema * (min(T / A, 1.0) - ema)
        return traj

    burns = [b_now if b is None else b for b in burns]
    base = simulate(b_now, 0.0)
    rows = []
    for b in sorted(set(round(b, 4) for b in burns), reverse=True):
        for f in dump_fracs:
            tr = simulate(b, f)
            rows.append({
                "b": b, "dump_frac": f,
                "d30_vs_hold_pct": round((tr[min(30, days)] / base[min(30, days)] - 1) * 100, 2),
                "d90_vs_hold_pct": round((tr[min(90, days)] / base[min(90, days)] - 1) * 100, 2),
                "d180_vs_hold_pct": round((tr[days] / base[days] - 1) * 100, 2),
            })
    # today's chain-buy threshold: emission above cap_tao opens the price channel
    spot0 = me["tao_in"] / me["alpha_in"]
    rp0 = tw / (tw + (me.get("alpha_in") or 0.0) + (me.get("alpha_issued") or 0.0))
    cap_tao_day = rp0 * alpha_emission * blocks_day * spot0
    best = max((r for r in rows if r["dump_frac"] == 0.15), key=lambda r: r["d90_vs_hold_pct"],
               default=None)
    owner_alpha_day = owner_cut * alpha_out_day
    return {
        "table": rows,
        "inputs": {"b_now": round(b_now, 4), "block_emission_tao": round(block_emission, 6),
                   "chain_buy_threshold_tao_day": round(cap_tao_day, 2),
                   "owner_alpha_day": round(owner_alpha_day, 0), "days": days},
        "summary": (
            f"Price only moves via CHAIN BUYS, which open once SN21's TAO emission exceeds "
            f"the injection cap (~{cap_tao_day:.1f} TAO/day, i.e. burn below ~0.5 today) — "
            f"cuts that stop above that add balanced liquidity (depth, not price). "
            + (f"Best 90-day price vs holding, at 15% realized dump: {best['d90_vs_hold_pct']:+.1f}% "
               f"at b={best['b']:.2f} ({best['d180_vs_hold_pct']:+.1f}% at 180d). " if best else "")
            + f"Owner alpha stays capped at {owner_alpha_day:,.0f}/day at every burn level — the "
              f"owner gain from cutting burn is the VALUE of that fixed alpha via price."
        ),
    }


ALL = {
    "S1": s1_old_vs_new,
    "S2": s2_burn_sweep,
    "S3": s3_decay,
    "S4": s4_extraction,
    "S5": s5_dump_safety,
    "S6": s6_burn_price,
}


def run_all(state: dict) -> dict:
    out = {}
    for key, fn in ALL.items():
        try:
            out[key] = fn(state)
        except Exception as e:  # noqa: BLE001
            out[key] = {"error": f"{type(e).__name__}: {e}"}
    return out
