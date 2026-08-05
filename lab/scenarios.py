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

from dereg_watch import DEREG_BUFFER_MIN, dereg_guard_tao
from .amm import price_impact, realized_tao_from_sell
from . import mechanisms as M
from .mechanisms import root_reborn_v346_421 as RR

BLOCK_SECONDS = 12

# ── Operator guardrails (the risks to avoid). ────────────────────────────────
# Dereg is NOT an absolute price floor — the chain prunes whichever non-immune
# subnet has the LOWEST EMA price when someone registers a new one, so the only
# meaningful guardrail is a RANK buffer. dereg_watch.py reads that live; the old
# DEREG_FLOOR_TAO = 0.0035 constant here was an unverified assumption and by
# 2026-07-29 sat ABOVE SN21's own EMA, scoring us against a number the chain
# never reads. Extraction now binds on dereg_guard_tao() — the price that still
# leaves DEREG_BUFFER_MIN subnets below us.
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


# ── S1 — superseded vs live formula (what the v430-432 deploy did to us) ─────
def s1_old_vs_new(state: dict) -> dict:
    old = M.get("incumbent")                # three-switch (pre 2026-07-14)
    new = M.get(M.LIVE_VERSION)             # price x (1-burn), live
    share_old = M.emission_share(old, state)
    share_new = M.emission_share(new, state)
    ratio = (share_new / share_old) if share_old > 0 else None
    return {
        "table": [
            {"mechanism": "three_switch_superseded", "sn21_emission_share_pct": round(share_old * 100, 5)},
            {"mechanism": "live_price_x_1mb", "sn21_emission_share_pct": round(share_new * 100, 5)},
        ],
        "inputs": {"b": state.get("sn21_miner_burn"), "block": state.get("block")},
        "summary": (
            f"At current burn b={state.get('sn21_miner_burn')}, the v430-432 deploy moved SN21's "
            f"modelled emission share from {share_old*100:.4f}% (three-switch) to "
            f"{share_new*100:.4f}% (live price x (1-b))" + (f" — {ratio:.2f}x." if ratio else ".")
        ),
        "trust_note": "Absolute owner emission needs the network TAO-emission anchor; "
                      "shares are robust. Old-formula number only as good as its reproduction fit.",
    }


# ── S2 — burn sweep → target b (decision D-Q) ────────────────────────────────
def s2_burn_sweep(state: dict, steps: int = 16) -> dict:
    new = M.get(M.LIVE_VERSION)
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
    new = M.get(M.LIVE_VERSION)
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
            f"{end['root_prop']:.4f} in {months} months. Since the v430-432 deploy the "
            f"SHARE no longer decays with root_prop (share_vs_now stays "
            f"{end['share_vs_now']}x — price x (1-b) only); the fade now only shrinks "
            f"the INJECTION CAP, shifting emission from liquidity injection to chain "
            f"buys (price channel widens as the subnet ages)."
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
    # keeping spot above the live dereg guard — the EMA that still leaves
    # DEREG_BUFFER_MIN subnets below us in the prune queue.
    f_impact = max_sell_frac_for_impact(MAX_WEEKLY_PRICE_IMPACT)
    guard = dereg_guard_tao()
    if guard is None:
        # dereg_watch has never run: bind on price impact alone rather than invent
        # a floor. Surfaced via binding_constraint so it is never silently assumed.
        f_floor = f_impact
    elif spot > 0 and guard < spot:
        # spot_after = spot * (1/(1+x))^2 >= guard  =>  x <= sqrt(spot/guard) - 1
        f_floor = math.sqrt(spot / guard) - 1.0
    else:
        f_floor = 0.0
    f_opt = max(0.0, min(f_impact, f_floor))
    opt_alpha = f_opt * A
    opt_tao = realized_tao_from_sell(opt_alpha, A, T)
    if guard is None:
        binding = "price-impact cap (no live dereg data — run dereg_watch)"
    elif f_impact <= f_floor:
        binding = "price-impact cap"
    else:
        binding = f"dereg rank guard ({DEREG_BUFFER_MIN}-subnet buffer)"
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
                   "dereg_guard": guard, "dereg_buffer_min": DEREG_BUFFER_MIN,
                   "max_weekly_impact": MAX_WEEKLY_PRICE_IMPACT},
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
    new = M.get(M.LIVE_VERSION)
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
    new = M.get(M.LIVE_VERSION)
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
            # LIVE share (v430-432): price x (1-b) only — root_prop removed from
            # the share (PR #2800); rp still governs the injection cap below.
            w21 = ema * (1.0 - b)
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
    # burn level b* below which SN21's TAO/day exceeds the cap (live share, no rp):
    # share* = cap/(block_emission*blocks_day); w* = share*·d_rest/(1−share*); b* = 1−w*/ema
    ema0 = me.get("ema_price") or spot0
    share_star = cap_tao_day / (block_emission * blocks_day)
    threshold_b = None
    if 0 < share_star < 1 and ema0 > 0:
        w_star = share_star * d_rest / (1.0 - share_star)
        threshold_b = max(0.0, min(1.0, 1.0 - w_star / ema0))
    best = max((r for r in rows if r["dump_frac"] == 0.15), key=lambda r: r["d90_vs_hold_pct"],
               default=None)
    owner_alpha_day = owner_cut * alpha_out_day
    return {
        "table": rows,
        "inputs": {"b_now": round(b_now, 4), "block_emission_tao": round(block_emission, 6),
                   "chain_buy_threshold_tao_day": round(cap_tao_day, 2),
                   "chain_buy_threshold_b": round(threshold_b, 4) if threshold_b is not None else None,
                   "owner_alpha_day": round(owner_alpha_day, 0), "days": days},
        "summary": (
            f"Price only moves via CHAIN BUYS, which open once SN21's TAO emission exceeds "
            f"the injection cap (~{cap_tao_day:.1f} TAO/day"
            + (f", i.e. burn below ~{threshold_b:.2f}" if threshold_b is not None else "")
            + (" — ALREADY OPEN at the current burn" if threshold_b is not None and b_now < threshold_b else "")
            + ") — cuts that stop above that add balanced liquidity (depth, not price). "
            + (f"Best 90-day price vs holding, at 15% realized dump: {best['d90_vs_hold_pct']:+.1f}% "
               f"at b={best['b']:.2f} ({best['d180_vs_hold_pct']:+.1f}% at 180d). " if best else "")
            + f"Owner alpha stays capped at {owner_alpha_day:,.0f}/day at every burn level — the "
              f"owner gain from cutting burn is the VALUE of that fixed alpha via price."
        ),
    }


# ── S7 — burn cut × miner stake + retention policy ───────────────────────────
def s7_stake_retention(state: dict,
                       burns=(0.50, 0.20, 0.0),
                       retentions=(0.0, 0.50, 0.85, 1.0),
                       stake_weeks: float = 4.0, entry_days: int = 28,
                       stress_day: int = 90, stress_exit_frac: float = 0.25,
                       stress_days: int = 7,
                       days: int = 180, ema_tc_days: float = 7.0) -> dict:
    """S6's burn→price simulation with a validator-enforced miner-stake policy
    coupled to the cut (there is no chain-native miner-stake gate — we enforce
    it through weight-setting, which we fully control):

      ENTRY STAKE — scored miners must hold `stake_weeks` of expected rewards in
      SN21 alpha. Aggregate requirement = stake_weeks×7 × miner_pool_day × (1−b)
      (per-miner size × miner count cancels). Bought through the AMM over the
      `entry_days` roll-out (phased with the staged cut) → a one-time price-UP
      flow that also thins the pool's alpha side.

      RETENTION SCORING — weight multiplier zeroes miners whose coldkey sells
      more than (1−r) of the freed rewards → realized dump is capped at (1−r)
      BY POLICY rather than by hope. In pool-flow terms a retention floor r is
      identical to S6 at dump_frac = 1−r; what the policy adds is (a) the entry
      buy leg, (b) enforceability of the dump assumption, (c) a quantified
      soft-lock failure mode:

      STRESS — alpha unstaking has NO unbonding period, so the lock is only as
      strong as the seat's value. At `stress_day` a `stress_exit_frac` of the
      locked stock (entry principal + retained rewards) unstakes and market-
      sells over `stress_days` — the exit-cascade tail case.

    Conservative by construction: retention applied to the PRE-EXISTING
    (1−b_now) reward flow is NOT counted (that selling is ambient in the hold
    baseline), and exiting miners' stakes are dumped, not resold to entrants."""
    new = M.get(M.LIVE_VERSION)
    me = _sn21(state)
    b_now = state.get("sn21_miner_burn") or 0.0
    blocks_day = 86400.0 / BLOCK_SECONDS
    block_emission = sum(((s.get("tao_in_emission") or 0.0) +
                          (s.get("excess_tao_emission") or 0.0)) for s in state["subnets"])
    d_rest = sum(max(0.0, new.score(s, state)) for s in state["subnets"]
                 if s["netuid"] != state.get("netuid", 21))
    root_tao = state.get("root_tao") or state.get("root_stake_tao") or 0.0
    tw = root_tao * (state.get("tao_weight") or 0.0)
    owner_cut = state.get("owner_cut") or 0.18
    alpha_emission = me.get("alpha_out_emission") or 1.0
    alpha_out_day = alpha_emission * blocks_day
    miner_pool_day = 0.5 * (1.0 - owner_cut) * alpha_out_day

    if not (me.get("alpha_in") and me.get("tao_in") and block_emission > 0 and d_rest > 0):
        return {"error": "S7 needs pool reserves, per-subnet emission (incl. excess) and root_tao"}

    def simulate(b: float, r: float, entry: bool = True, stress: bool = False):
        A, T = me["alpha_in"], me["tao_in"]
        ema = me.get("ema_price") or (T / A)
        issuance = (me.get("alpha_in") or 0.0) + (me.get("alpha_issued") or 0.0)
        k_ema = 1.0 - math.exp(-1.0 / ema_tc_days)
        agg_stake = stake_weeks * 7.0 * miner_pool_day * (1.0 - b) if entry else 0.0
        entry_daily = agg_stake / entry_days if entry_days else 0.0
        locked = 0.0   # entry principal + retained freed rewards (staked, off-pool)
        entry_tao = 0.0
        stress_sell_daily = 0.0
        traj = []
        for d in range(days + 1):
            spot = T / A
            traj.append(spot)
            rp = tw / (tw + issuance) if (tw + issuance) > 0 else 0.0
            # LIVE share (v430-432): price x (1-b) only — root_prop removed from
            # the share (PR #2800); rp still governs the injection cap below.
            w21 = ema * (1.0 - b)
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
            if d < entry_days and entry_daily > 0:  # entry-stake buys: alpha out of pool
                dA = min(entry_daily, 0.10 * A)
                cost = (A * T) / (A - dA) - T
                A -= dA
                T += cost
                locked += dA
                entry_tao += cost
            freed = miner_pool_day * max(0.0, b_now - b)
            dump = freed * (1.0 - r)              # policy caps selling of freed rewards
            locked += freed * r
            if stress:
                if d == stress_day:
                    stress_sell_daily = stress_exit_frac * locked / stress_days
                if stress_day <= d < stress_day + stress_days:
                    dump += stress_sell_daily
                    locked -= stress_sell_daily
            if dump > 0:                          # sells: alpha in, TAO out
                T = (A * T) / (A + dump)
                A += dump
            issuance += alpha_out_day + inj_alpha
            ema += k_ema * (min(T / A, 1.0) - ema)
        return traj, locked, entry_tao

    base, _, _ = simulate(b_now, 1.0, entry=False)  # hold baseline == S6's
    A0 = me["alpha_in"]
    rows = []
    for b in sorted(set(round(b, 4) for b in burns), reverse=True):
        for r in retentions:
            tr, locked, entry_tao = simulate(b, r)
            tr_ne, _, _ = simulate(b, r, entry=False)       # isolate the entry-buy leg
            st, _, _ = simulate(b, r, stress=True)
            agg_stake = stake_weeks * 7.0 * miner_pool_day * (1.0 - b)
            d90 = min(90, days)
            rows.append({
                "b": b, "retention": r,
                "entry_stake_alpha": round(agg_stake, 0),
                "entry_stake_pct_of_reserve": round(agg_stake / A0 * 100, 2),
                "entry_tao_cost": round(entry_tao, 1),
                "d30_vs_hold_pct": round((tr[min(30, days)] / base[min(30, days)] - 1) * 100, 2),
                "d90_vs_hold_pct": round((tr[d90] / base[d90] - 1) * 100, 2),
                "d180_vs_hold_pct": round((tr[days] / base[days] - 1) * 100, 2),
                "entry_leg_d90_pp": round((tr[d90] / base[d90] - tr_ne[d90] / base[d90]) * 100, 2),
                "locked_alpha_d180": round(locked, 0),
                "stress_d180_vs_hold_pct": round((st[days] / base[days] - 1) * 100, 2),
            })
    plan = next((x for x in rows if x["b"] == 0.20 and x["retention"] == 0.85), None) or \
           (rows[-1] if rows else None)
    return {
        "table": rows,
        "inputs": {"b_now": round(b_now, 4), "stake_weeks": stake_weeks,
                   "entry_days": entry_days, "stress_day": stress_day,
                   "stress_exit_frac": stress_exit_frac,
                   "miner_pool_alpha_day": round(miner_pool_day, 0),
                   "pool_alpha_reserve": round(A0, 0), "days": days},
        "summary": (
            (f"Coupling the cut with a {stake_weeks:.0f}-week entry stake "
             f"(~{plan['entry_stake_alpha']:,.0f} alpha aggregate, "
             f"{plan['entry_stake_pct_of_reserve']:.1f}% of the pool's alpha side) and "
             f"retention-weighted scoring at r=0.85 gives {plan['d90_vs_hold_pct']:+.1f}% @90d / "
             f"{plan['d180_vs_hold_pct']:+.1f}% @180d vs holding at b={plan['b']:.2f} — the entry "
             f"buys contribute {plan['entry_leg_d90_pp']:+.1f}pp of that; the rest is S6's "
             f"burn effect with the ≤15% dump gate now ENFORCED by scoring, not assumed. "
             f"Locked float by d180: ~{plan['locked_alpha_d180']:,.0f} alpha. Soft-lock stress "
             f"({stress_exit_frac:.0%} of locked stock dumped at d{stress_day}): "
             f"{plan['stress_d180_vs_hold_pct']:+.1f}% @180d — the exit-cascade tail case. "
             if plan else "") +
            "Retention on the pre-existing reward flow is upside NOT counted here (conservative)."
        ),
    }


# ── S8 — v435 miner-registration collateral policy (PR #2953, deploy pending) ─
def s8_collateral(state: dict,
                  lock_shares=(0.25, 0.50, 0.75, 0.90),
                  drain_ratios=(0.1, 0.5, 1.0),
                  floor_weeks=(1.0, 4.0),
                  n_scored_miners: int = 3,
                  tier_share_within_real: float = 0.0183) -> dict:
    """Economics of the v435 collateral hyperparams (p = CollateralLockShare,
    k = CollateralDrainRatio) for SN21, plus min_locked floor sizing for the
    curated miner set. Share formula is untouched by v435 — this scenario is
    about miner-side economics and float locking, not the emission split.

    `tier_share_within_real` is a top-tier miner's slice of the REAL-miner
    incentive (excluding the owner/burn UID): measured 0.73% of the full
    incentive vector at b=0.60 on 2026-07-21 -> 0.0073/0.399 ~= 0.0183 within
    the real-miner share. Scaling by today's (1-b) keeps per-miner earnings
    honest at any burn level (~21 alpha/day now, ~54 at b=0) — the incentive
    vector spreads across ~165 scored UIDs, not just the curated set."""
    me = _sn21(state)
    ema = me.get("ema_price") or me.get("spot_price") or 0.0
    reg_cost_tao = state.get("sn21_reg_cost_tao")
    if not ema or reg_cost_tao is None:
        return {"error": "S8 needs ema price and sn21_reg_cost_tao in state"}

    blocks_day = 86400.0 / BLOCK_SECONDS
    owner_cut = state.get("owner_cut") or 0.18
    alpha_out_day = (me.get("alpha_out_emission") or 1.0) * blocks_day
    miner_pool_day = 0.5 * (1.0 - owner_cut) * alpha_out_day
    b = state.get("sn21_miner_burn") or 0.0
    real_miner_day = (1.0 - b) * miner_pool_day
    per_miner_day = tier_share_within_real * real_miner_day

    reg_cost_alpha = reg_cost_tao / ema if ema > 0 else 0.0
    rows = []
    for p in lock_shares:
        locked = p * reg_cost_alpha
        for k in drain_ratios:
            drain_day = k * per_miner_day
            rows.append({
                "p_lock_share": p,
                "k_drain_ratio": k,
                "locked_alpha_per_reg": round(locked, 2),
                "burned_alpha_per_reg": round((1 - p) * reg_cost_alpha, 2),
                "scored_miner_payback_days": (
                    round(locked / drain_day, 2) if drain_day > 0 else None),
                # an unscored miner earns no incentive: p stays frozen forever
                "squatter_frozen_alpha": round(locked, 2),
            })

    # min_locked floor sizing: N weeks of a scored miner's rewards, held as a
    # self-maintaining deposit (incentive fills shortfall, drain stops at it).
    floors = []
    for w in floor_weeks:
        floor = w * 7 * per_miner_day
        floors.append({
            "floor_weeks_of_rewards": w,
            "floor_alpha_per_miner": round(floor, 0),
            "fill_days_from_zero": round(w * 7, 1),  # capture = 100% of incentive
            "set_locked_float_alpha": round(floor * n_scored_miners, 0),
            "pct_of_pool_alpha": (
                round(100 * floor * n_scored_miners / me["alpha_in"], 2)
                if me.get("alpha_in") else None),
        })

    return {
        "table": rows,
        "floors": floors,
        "inputs": {"reg_cost_tao": reg_cost_tao,
                   "reg_cost_alpha": round(reg_cost_alpha, 2),
                   "per_scored_miner_alpha_day": round(per_miner_day, 1),
                   "b": round(b, 4), "n_scored_miners": n_scored_miners},
        "summary": (
            f"v435 collateral (deploy pending): at today's {reg_cost_tao:.2f}-TAO reg cost "
            f"(~{reg_cost_alpha:.0f} α), even p=0.9 collateral pays back in "
            f"<{max(r['scored_miner_payback_days'] or 0 for r in rows):.1f} days for a scored "
            f"miner earning ~{per_miner_day:.0f} α/day (rises with every burn cut) — "
            f"negligible friction for the curated "
            f"set, while squatters' locked share stays frozen forever and hotkey rotation is "
            f"blocked. The REAL lever is the min_locked floor: a 4-week floor "
            f"(~{floors[-1]['floor_alpha_per_miner']:,.0f} α x {n_scored_miners} miners = "
            f"{floors[-1]['set_locked_float_alpha']:,.0f} α locked, "
            f"{floors[-1]['pct_of_pool_alpha']}% of pool alpha) gives the retention policy a "
            f"chain-native, self-maintaining enforcement rail — set p high (0.75-0.9, "
            f"miner-friendly since it's recoverable), k moderate (0.5), floors via the "
            f"operating agreement once v435 deploys."
        ),
    }


ALL = {
    "S1": s1_old_vs_new,
    "S2": s2_burn_sweep,
    "S3": s3_decay,
    "S4": s4_extraction,
    "S5": s5_dump_safety,
    "S6": s6_burn_price,
    "S7": s7_stake_retention,
    "S8": s8_collateral,
}


def run_all(state: dict) -> dict:
    out = {}
    for key, fn in ALL.items():
        try:
            out[key] = fn(state)
        except Exception as e:  # noqa: BLE001
            out[key] = {"error": f"{type(e).__name__}: {e}"}
    return out
