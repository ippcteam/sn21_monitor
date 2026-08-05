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
   (root_prop x alpha_emission), which opens once burn drops below the S6-computed
   threshold (chain_buy_threshold_b — moved up from ~0.5 to ~0.77 when the v430-432
   deploy removed root_prop from the share, so it now sits ABOVE typical burns).
   Shallow cuts buy depth, not price — the price case is for DEEP cuts (b <= 0.2),
   staged, with realized miner dump kept below the S5 breakeven.

Update 2026-07-20 (v430-432 deploys live, spec 432): the share formula is now
price x (1-MinerBurned) over emit-enabled subnets — root_prop is OUT of the share
(it still caps injection). MinerBurned recomputes every tempo, so burn moves take
effect the next tempo. The same deploy activated conviction-based ownership
transfer — see the priority-2 defense action.
"""

from __future__ import annotations

from collector import load_json
from config import DATA_DIR
from dereg_watch import DEREG_BUFFER_MIN, TIER_LABELS, load_dereg_state
from .scenarios import MAX_WEEKLY_PRICE_IMPACT, _sn21

WEIGHTS_STORE = DATA_DIR / "weights_scan.json"


def _price_standing(state: dict) -> dict:
    """Where SN21 sits on price — and, from the live dereg watch, where it sits in
    the prune QUEUE, which is the thing that actually kills subnets. Dereg ranks on
    the EMA price among non-immune subnets; there is no absolute floor to be above."""
    me = _sn21(state)
    spot = me.get("spot_price") or 0.0
    prices = sorted((s.get("spot_price") or 0.0) for s in state["subnets"] if s.get("spot_price"))
    rank = sum(1 for p in prices if p < spot) + 1 if spot else None  # 1 = cheapest

    d = load_dereg_state()
    return {
        "spot": spot,
        "ema": me.get("ema_price"),
        "price_rank_from_cheapest": rank,
        "n_priced": len(prices),
        # Live prune-queue position (None until dereg_watch has run).
        "dereg_tier": d.get("tier"),
        "subnets_below": d.get("subnets_below"),
        "n_prunable": d.get("n_prunable"),
        "dereg_floor_tao": d.get("floor_tao"),
        "dereg_floor_netuid": d.get("floor_netuid"),
        "dereg_guard_tao": d.get("guard_tao"),
        "drop_to_target_pct": d.get("drop_to_target_pct"),
        "runway_days": d.get("runway_days"),
        "days_per_prune": d.get("days_per_prune"),
        "buffer_places_lost_14d": (d.get("erosion") or {}).get("places_lost"),
        "dereg_checked_at": d.get("checked_at"),
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
    """Risk level tracks the live prune-queue tier, not a price threshold. The
    buffer is how many non-immune subnets have a lower EMA than ours: each new
    subnet registration dissolves exactly one of them, cheapest EMA first."""
    tier = ps.get("dereg_tier")
    if tier is None:
        return {
            "name": "Deregistration",
            "level": "unknown",
            "detail": "No live dereg data — run dereg_watch.py (refreshes every 2 days).",
        }
    level = {0: "low", 1: "low", 2: "medium", 3: "high", 4: "high", 5: "high"}[tier]
    # A fast-eroding buffer outranks a comfortable level: 36 -> 24 in 8 days (the
    # 2026-07-29 slide) is tier 0 the whole way down.
    lost = ps.get("buffer_places_lost_14d")
    if lost is not None and lost >= 8 and level == "low":
        level = "medium"
    detail = (
        f"{ps['subnets_below']} of {ps['n_prunable']} prunable subnets sit below our EMA "
        f"{ps['ema'] or 0:.6f} — {TIER_LABELS[tier]}. Next in line is netuid "
        f"{ps['dereg_floor_netuid']} @ {ps['dereg_floor_tao']:.6f} ({ps['drop_to_target_pct']}% "
        f"below us). At one prune every ~{ps['days_per_prune']} d that is ~{ps['runway_days']:.0f} d "
        f"of runway at this rank."
    )
    if lost is not None:
        direction = "lost" if lost >= 0 else "gained"
        detail += f" Buffer {direction} {abs(lost)} places in the last 14 d."
    return {"name": "Deregistration", "level": level, "detail": detail}


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
    S7 = scenarios.get("S7", {}) or {}

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

    # 1 — Burn (master lever; aligns price + owner-alpha VALUE + legibility).
    # Since the v430-432 deploy the share is price x (1-b) with NO root_prop and
    # MinerBurned recomputes EVERY TEMPO — a burn cut pays out the next tempo.
    if b_now > 0.001:
        target_b = s5_in.get("target_b")
        thr_b = s6_in.get("chain_buy_threshold_b")
        thr_txt = f"~{thr_b:.2f}" if thr_b is not None else "the S6 threshold"
        # safe single step from S5: largest sell_fraction keeping net pool flow >= 0
        safe_rows = [r for r in (S5.get("table") or []) if r.get("net_positive")]
        safe_dump = max((r["miner_sell_fraction"] for r in safe_rows), default=0.0)
        price_txt = (f"↑ once burn < {thr_txt} (chain-buy threshold "
                     f"~{s6_in.get('chain_buy_threshold_tao_day')} TAO/day); "
                     f"best S6 case at 15% dump: {s6_best['d90_vs_hold_pct']:+.1f}% @90d / "
                     f"{s6_best['d180_vs_hold_pct']:+.1f}% @180d at b={s6_best['b']:.2f}"
                     if s6_best else
                     "↑ via chain buys only below the injection-cap threshold (S6)")
        actions.append({
            "priority": 1,
            "lever": "Burn rate",
            "action": (f"Reduce burn from b={b_now:.2f} DEEP (target ≤0.2, then 0) in staged "
                       f"steps — next step to b≈{target_b:.2f}. Effect lands NEXT TEMPO "
                       f"(MinerBurned is per-tempo). Shallow cuts (stopping above "
                       f"{thr_txt}) add pool depth but ~zero price." if target_b is not None else
                       f"Reduce burn from b={b_now:.2f} deep toward 0 (price channel opens below {thr_txt}; "
                       "effect lands next tempo)."),
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

    # 2 — Conviction takeover defense (LIVE since the v430-432 deploys, 2026-07-13..16).
    # change_subnet_owner_if_needed runs every epoch: total rolled conviction >= 10%
    # of SubnetAlphaOut + subnet >= 1yr old + a non-owner hotkey out-convicts the
    # owner => ownership MOVES. SN21 verified 2026-07-20: age 2.1y (clause ARMED),
    # threshold ~359k alpha, ZERO HotkeyLock entries — nobody can seize it today,
    # but we hold no defensive conviction either.
    actions.append({
        "priority": 2,
        "lever": "Ownership defense (conviction)",
        "action": ("Build owner conviction NOW: enable the `owner_cut_auto_lock_enabled` "
                   "hyperparam (compounds the ~1,296 alpha/day owner cut into a conviction "
                   "lock every tempo) and/or lock a seed tranche of owner alpha "
                   "(btcli lock). Target: owner conviction comfortably above any "
                   "plausible challenger before total subnet conviction nears the "
                   "~359k-alpha (10% of SubnetAlphaOut) takeover threshold."),
        "effect_price": "neutral (locking removes no liquidity from the pool)",
        "effect_owner_alpha": "unchanged quantity; locked tranche unlocks ~50% per 90d if needed",
        "guardrail": ("Locked alpha is slow to exit (UnlockRate ~50%/90d) — size the seed "
                      "lock so planned extraction (action 3) still clears. Watch "
                      "HotkeyLock[21] for ANY third-party lock: that is the takeover "
                      "prep signal (stake_watch candidate)."),
        "confidence": "HIGH — source-read (staking/lock.rs change_subnet_owner_if_needed) "
                      "+ chain-verified: clause armed for SN21, zero locks exist today.",
    })

    # 2b — v435 collateral prep (PR #2953 merged 2026-07-21, deploy pending):
    # decide hyperparams BEFORE it lands so the curated-set policy switches to
    # the chain-native rail on day one.
    S8 = scenarios.get("S8", {}) or {}
    s8_in = S8.get("inputs") or {}
    if S8.get("summary") and not S8.get("error"):
        actions.append({
            "priority": 2,
            "lever": "v435 collateral prep (deploy pending)",
            "action": ("Pre-decide CollateralLockShare p≈0.75-0.9 and CollateralDrainRatio "
                       "k≈0.5 for SN21, and size min_locked floors for the curated set "
                       "(see S8). High p is miner-FRIENDLY for scored miners (recoverable "
                       f"in days at today's {s8_in.get('reg_cost_tao', 0.1):.2f}-TAO reg "
                       "cost) while squatters' share freezes forever and hotkey rotation "
                       "is blocked."),
            "effect_price": "mild ↑ — collateral is an AMM buy at registration; floors lock float",
            "effect_owner_alpha": "neutral (owner cut untouched); emission share formula unchanged",
            "guardrail": ("Do NOT set floors so high that scored miners' capture phase eats "
                          "the retention-policy allowance; announce policy with the burn "
                          "steps. Deploy trigger: v435 release tag / finney spec >= 435 "
                          "(lab watcher covers it)."),
            "confidence": "SOURCE-READ (collateral.rs @ main); numbers from S8 on live state.",
        })

    # 3 — Retention policy via curated miner set (couples with the burn cut; S7)
    # NOTE 2026-07-03: the PUBLIC entry-stake gate is WITHDRAWN (OTF has emission-cut /
    # FUDded "stake-to-mine" subnets as Ponzi, and spec-425 conviction makes third-party
    # alpha accumulation a takeover vector). Retention stays, enforced through curation.
    s7_rows = [r for r in (S7.get("table") or []) if r.get("retention") == 0.85]
    s7_plan = next((r for r in s7_rows if r.get("b") == 0.20), None) or \
              (max(s7_rows, key=lambda r: r["d90_vs_hold_pct"]) if s7_rows else None)
    if s7_plan and b_now > 0.001:
        actions.append({
            "priority": 3,
            "lever": "Miner retention via curated set",
            "action": ("Enforce ≥85% retention of freed rewards through a CURATED miner set "
                       "(private operating agreement; zero weight if a coldkey sells >15%/week — "
                       "per-coldkey flow monitoring already runs daily). NO public stake-to-mine "
                       "rule (withdrawn 2026-07-03: OTF Ponzi-pattern precedent + spec-425 "
                       "conviction risk). Brief the miner set with burn step 1."),
            "effect_price": (f"makes the S6 15%-dump row the ENFORCED case "
                             + (f"({s6_best['d90_vs_hold_pct']:+.1f}% @90d / "
                                f"{s6_best['d180_vs_hold_pct']:+.1f}% @180d at b={s6_best['b']:.2f})"
                                if s6_best else "")),
            "effect_owner_alpha": "retained rewards shrink circulating float; owner quantity "
                                  "unchanged, value tracks price",
            "guardrail": ("Never tighten retention in a drawdown (soft hold → exit trigger). "
                          "Miners hold PLAIN stake only — locked stake builds conviction, the "
                          "conviction-takeover vector that is NOW LIVE (v430-432)."),
            "confidence": "MODELED (S7/S6 engine) — enforcement is weight-setting we fully "
                          "control; no chain mechanism needed or wanted.",
        })

    # 3 — Extraction (realise owner alpha without breaching the dereg floor)
    if opt:
        actions.append({
            "priority": 4,
            "lever": "Extraction",
            "action": (f"Sell ≤ {opt.get('alpha_per_week'):,.0f} alpha/week "
                       f"({opt.get('weekly_sell_frac_of_reserve', 0)*100:.2f}% of reserve) "
                       f"→ ~{opt.get('realized_tao_per_week'):,.0f} TAO."),
            "effect_price": f"≤ {abs(opt.get('price_impact_pct', 0)):.2f}% weekly impact (capped)",
            "effect_owner_alpha": "converts owner alpha to TAO at the max safe rate",
            "guardrail": (f"Bound by {opt.get('binding_constraint')}; keeps at least "
                          f"{DEREG_BUFFER_MIN} subnets below us in the prune queue."),
            "confidence": "MEASURED (constant-product slippage on live pool depth).",
        })

    # 4 — Guard the rank (only if dereg risk is not low)
    if risks[0]["level"] in ("medium", "high", "unknown"):
        actions.append({
            "priority": 5,
            "lever": "Dereg guard",
            "action": "Stop extraction and stake TAO into the SN21 pool to rebuild the rank "
                      "buffer. The buy raises spot and the EMA follows within ~1 day "
                      "(~8-hour half-life) — see dereg_watch's defence table for sizing.",
            "effect_price": "raises spot directly, which IS the pruning metric",
            "effect_owner_alpha": "preserves the subnet (deregistration dissolves the pool)",
            "guardrail": (f"{ps.get('subnets_below')} subnets below us; "
                          f"{ps.get('drop_to_target_pct')}% to become the prune target."),
            "confidence": "HIGH (chain-simulated swap; deregistration zeroes everything).",
        })

    # Verdict
    verdict_bits = []
    thr_b = s6_in.get("chain_buy_threshold_b")
    thr_txt = (f"price channel {'ALREADY OPEN' if (thr_b is not None and b_now < thr_b) else 'opens'} "
               f"below b≈{thr_b:.2f}" if thr_b is not None
               else "price channel per S6 threshold")
    if b_now > 0.001:
        tgt = s5_in.get("target_b")
        verdict_bits.append(
            (f"reduce burn {b_now:.2f}→{tgt:.2f} now, staged on to ≤0.2 "
             f"({thr_txt}; effect lands next tempo)") if tgt is not None
            else f"reduce burn deep (≤0.2; {thr_txt})")
    verdict_bits.append("lock owner conviction (takeover clause LIVE + armed for SN21; "
                        "zero locks exist)")
    if s7_plan and b_now > 0.001:
        verdict_bits.append("enforce ≥85% retention via the curated miner set (S7; no public "
                            "stake gate) so the ≤15% dump gate is enforced, not assumed")
    if opt:
        verdict_bits.append(f"extract ≤{opt.get('alpha_per_week'):,.0f} alpha/wk")
    verdict = ("To grow price + owner alpha: " + ", ".join(verdict_bits) +
               f". Dereg buffer {ps.get('subnets_below')} subnets below us "
               f"(~{ps.get('runway_days')} d runway, {risks[0]['level']}), "
               f"emission-blocking {risks[1]['level']}. "
               "Share no longer decays with age (root_prop out of the share since "
               "v430-432); the aging effect is a widening chain-buy price channel.")

    return {
        "objective": "Maximise alpha price + owner alpha; avoid deregistration & emission-blocking.",
        "guardrails": {
            # Live, from dereg_watch — the floor moves as the field re-ranks.
            "dereg_floor_tao": ps.get("dereg_floor_tao"),
            "dereg_guard_tao": ps.get("dereg_guard_tao"),
            "dereg_buffer_min": DEREG_BUFFER_MIN,
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
