# SN21 Emission-Gate Risk Assessment — subtensor v440 (PR #2990)

**Date:** 2026-07-27  **Chain block modelled:** 8,715,829  **Status: LIVE on finney (confirmed).**

## TL;DR

A runtime change merged today (**RaoFoundation/subtensor PR #2990, "release-v440: emission gate"**, spec 440) inserts a **q-mass Hill gate** on top of the emission-share formula. It **concentrates TAO emission into the top ~12 subnets** and crushes everything below a demand "bar" toward zero.

**It is already executing on finney.** SN21's actual on-chain emission share has already collapsed to **0.0094% — a ~97% cut** from the **0.30%** the previous (un-gated) formula would give. The lab reproduces the *entire* 62-subnet distribution to **2.9% median error only with the gate applied** (158% error without it) — that is proof the gate is live, not proposed.

**Price is the dominant lever, but the defence is cheaper and more graduated than a first pass suggests** — and the owner's alpha cash-flow is NOT killed. See the "Defence" and "Is it dead" sections; the earlier "burn is dead / ~6,000 TAO minimum" framing was computed at the code-default `q=0.61` and is corrected below to the DEPLOYED `q≈0.77`.

## What the gate does (verified from source)

Old (live v432) share, per emit-enabled subnet:

    s_i = ema_price_i × (1 − MinerBurned_i)   /  Σ_j (…)

New (v440), gate applied on top and renormalised:

    e_i = gate(s_i) · s_i / Σ_j [ gate(s_j) · s_j ]
    gate(s) = s^h / (s^h + θ^h) = 1 / (1 + (θ/s)^h)

- **θ (EmissionGateBar)** = the **q-mass bar**: sort demand shares descending, accumulate until the running total first reaches `q`; θ is the share at that crossing. The subnets above θ collectively carry `q` of all demand.
- **q (EmissionBarQuantile)** default **0.61**, **h (EmissionGateExponent)** default **3** — both **root/sudo hyperparams (network-wide; we do NOT control them).**
- θ recomputes every **360 blocks**, sticky in between.
- `gate(θ) = ½` at the bar, `→1` well above, `→0` well below.

**Concentration multiplier is severe.** The PR's own unit test: two subnets at a 1:2 price ratio (linear shares ⅓ : ⅔) settle at **1/10 : 9/10** after the default gate. A 2× demand edge becomes a 9× emission edge.

## SN21's position (live, block 8,715,829)

| Metric | Value (deployed q≈0.77) |
|---|---|
| SN21 pre-gate demand share | 0.00300 → **rank 57/128** |
| Bar θ (deployed q≈0.77) | ~0.0107 |
| SN21 share ÷ θ | 0.28 (**below the bar**) |
| gate(SN21) | ~0.024 |
| **SN21 emission share, un-gated** | **0.300%** |
| **SN21 emission share, actual on-chain (gated)** | **0.0094%** |
| Effective cut | **≈ −97%** |

**How many subnets "clear the gate" (deployed q≈0.77, no hard cutoff — it's a smooth curve):** ~**24** at gate≥½ (the bar), ~**28** keep ≥50% of their old share, ~**44** retain ≥10% pass. (At the *code-default* q=0.61 these are 12 / 18 / 30 — the tighter bar I originally quoted in error. The live bar is looser.)

**Deployed-gate calibration:** fitting (q,h) to SN21's actual share reproduces the network at **median rel.err 0.029, 62/62 within tol** at **q≈0.77, h≈2.9** (h ≈ its default 3; q running ABOVE the 0.61 default — a looser bar than the code default, but SN21 at rank 57 is below it regardless).

**Winners (the concentration beneficiaries), old → new share:** SN64 Chutes 11.2%→17.3%, SN51 8.4%→12.9%, SN4 7.6%→11.6%, SN120 7.4%→11.4%, SN107 6.4%→9.6% (all ~+50%). Network-wide: **51 of ~69 subnets lose >50% of their share; only 18 keep ≥50%.** Rich-get-richer.

## Defence — cheaper and more graduated than a threshold (deployed q≈0.77)

The gate is a smooth Hill curve and SN21 sits on its **steep** section, so cheap moves compound. Pool depth **8,000 TAO / 2.04M α**.

**Lever 1 — cut burn to 0 (FREE).** Not dead at the deployed bar (that was only true at the tight q=0.61). Sweep:

| burn b | gate(SN21) | gated share | vs now |
|---|---|---|---|
| 0.45 (now) | 0.024 | 0.0097% | 1.0× |
| 0.25 | 0.058 | 0.031% | 3.3× |
| 0.00 | 0.124 | 0.089% | **9.3×** |

(Caveat: cutting burn frees miner alpha that can be dumped — pair with retention scoring, S7. Absolute share still small.)

**Lever 2 — treasury buy is a DIAL, not a 6k threshold** (costs are *after* burn→0, CPMM spot):

| Target | Extra buy |
|---|---|
| gate 0.10 ("back in the game") | **~0 TAO (burn cut alone gets there)** |
| gate 0.30 | ~1,700 TAO |
| gate 0.50 (the bar) | ~3,200 TAO |
| gate 0.90 (full pass) | ~8,400 TAO |

A buy only *holds* if real demand follows (EMA decays back otherwise) — a bridge, not a fix.

**q/h sweep (governance settings we don't control):** no setting restores SN21 at rank 57; the most lenient knob (h=1) still roughly halves us. But q,h are foundation sudo and the gate just gutted 51 subnets — softening is plausible; monitor.

## Is it "dead for us"? No — the gate hits price support, not the owner cut

The gate throttles the **TAO emission** (pool injection + chain buys = price support). It does **NOT** gate **alpha emission**: on-chain right now, 57 gated subnets — SN21 included — **still mint a full 1.0 α/block**, so the owner cut keeps accruing at full quantity. What died is the emission-funded price *pump*, not the ownership cash-flow. The gate forces SN21 onto an **organic-demand standard** — the same "demand follows substance" conclusion, now mechanically enforced. The risk is that continued α inflation with no emission-funded buy support is net downward price pressure unless real demand fills in.

## Strategy

### Defensive (realistic, recommended baseline)
1. **Cut burn toward 0 — free, ~9× emission, do it.** At the deployed bar SN21 is on the steep part of the Hill curve, so b:0.45→0 lifts gated share 0.0097%→0.089%. (Manage the freed-alpha dump via retention scoring, S7.) This is necessary-not-sufficient — absolute share is still small.
2. **Re-anchor the thesis to owner-alpha value via real demand/revenue.** Revenue-driven price is the durable path back above the bar; the gate enforces it mechanically.
3. **Re-baseline price-support projections to near-zero gated TAO emission** until SN21 climbs, but **do not write off owner-alpha accrual** — it continues at full rate.
4. **Watch conviction-takeover exposure** ([[sn21-conviction-ownership-risk]]): lower price → shifting AlphaOut/threshold dynamics. Re-check the tripwire.

### Maximal (aggressive, capital-gated, only if paired with a real catalyst)
- After burn→0, a treasury buy is a **dial**: ~1,700 TAO → gate 0.30, **~3,200 TAO → the bar (gate ½)**, ~8,400 TAO → 90% pass. **It only holds if a genuine demand/revenue catalyst sustains the price** — otherwise EMA decays and we fall back, capital spent. Thinning float / locking owner alpha (conviction auto-lock) raises price per unit demand more cheaply than fighting pool depth. **Commit to a credible top-tier push or don't spend.**

### The honest third option
- If there is no credible demand catalyst, the rational call may be to **stop subsidizing and harvest owner alpha passively** (or wind down). The gate makes an undifferentiated subnet structurally unrewarded — a real portfolio decision, not a foregone death.

## Lab / follow-up actions
- New reviewed mechanism module `lab/mechanisms/hill_gate_v440_2990.py` (registered). Modelled from source, calibrated to live, `stage="mainnet"`.
- **The lab's `LIVE_VERSION` is now mis-anchored** (still the un-gated `root_reborn_v425_2800`, whose reproduction error just jumped to 1.58 — the regression detector's trigger condition). **Recommend re-anchoring `LIVE_VERSION` to the gate and rebuilding S6/S7 around the gated (near-zero) channel** as the next PR. Not done here to avoid silently redefining every scenario under time pressure.
