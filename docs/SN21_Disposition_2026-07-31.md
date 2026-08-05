# SN21 disposition under v440 — what the position is actually worth, and what to do with it

**Date:** 2026-07-31
**Basis:** `dereg_watch` 2026-07-29 (block 8,728,328), state snapshot 2026-07-27 (block 8,715,990),
`owner_ledger`, `stake_watch` 2026-07-09, `conviction_watch` 2026-07-21. TAO = $198.6.
**Companion:** [Subnet_Top32_Entry_Requirements_2026-07-31.md](Subnet_Top32_Entry_Requirements_2026-07-31.md)

**Model caveat:** gate figures come from `hill_gate_v440_2990`, which reproduces the network to
median rel.err 0.207 (27/62 within tol) per CHANGELOG 2026-07-29. Bands and rankings are robust;
third significant figures are not.

---

## TL;DR

1. **SN21 cannot be bought over the bar out of business revenue.** At $2k/month of buyback capacity
   we are **108× short** of the $215k/month escape threshold. One month's buying moves price −2.3%
   (i.e. it is swamped by the drift). This is arithmetic, not pessimism.
2. **The position is smaller than previously stated.** Our entitlement to the owner cut is **25%**,
   not 100% — **324 α/day, ≈$6.4k/month**, plus a ~32,615 α stake worth ≈$21.5k. Earlier working
   quoted the gross owner cut as ours and was 4× too high (see "Corrections").
3. **There is one free lever left and it has not been pulled.** Burn is still 0.45. Cutting to 0
   takes emission share 0.0075% → 0.0753% — **10×, at zero cost**. It is price support to the pool
   (+891 TAO/yr on a 7,369 TAO pool, ≈+12%/yr), not income; we capture it via float share and via
   uplift on the 324 α/day flow.
4. **The binding constraint is float, and it is permanent.** 3.55M α issued and rising ~7,200/day.
   That caps alpha APY at 61% today, ~35% in a year — the worst in any comparable set. It is the
   reason nobody stakes, and it can never be reversed.
5. **The urgent problem is the bleed, not the gate.** Pool TAO −7.9%, pool alpha +8.6%, EMA price
   −16.3%, all in the two days 07-27 → 07-29.
6. **Recommendation: harvest, don't climb.** Cut burn to 0, harvest the owner-cut entitlement at a
   chosen rate, stop spending on an ascent we cannot fund, and move growth ambition to a slot where
   float is still a design decision.

---

## 1. Corrections to earlier working

Two numbers in the 2026-07-30 analysis were wrong in a direction that flattered the position:

| Claim | Corrected |
|---|---|
| "Owner cut is worth $15–30k/month to us" | Our **entitlement rate is 0.25** (`owner_ledger`, last 22 entries). Gross owner cut is 1,296 α/day; **ours is 324 α/day ≈ $6.4k/month** at current price. |
| "Burn→0 is worth +$14.5k/month" | It is **+2.44 TAO/day of pool inflow**, i.e. price support shared pro-rata across the float — not income. Real, but we capture ~1% of it directly plus the uplift on our α flow. |

**`owner_ledger.json` was last updated 2026-04-10** — stale by ~3.5 months. The 25% entitlement rate
should be re-confirmed before any decision rests on it. **This is the first diligence item.**

## 2. What the position is worth today

| | Value |
|---|---|
| Price | 0.00333 TAO/α = **$0.661/α** |
| Float (α issued) | **3,568,900** |
| Float market cap | ~$2.35M |
| Our stake (`stake_watch`, 07-09) | 32,615 α ≈ **$21.5k** — **0.91% of float** |
| Our owner-cut flow (25% of 1,296 α/day) | 324 α/day ≈ **$6.4k/month** ≈ $78k/yr |
| Gate position | 0.019 (rank 57) — emission 0.0075% = 0.27 TAO/day |
| Dereg | tier 0 "clear", 20 prunable below → **~150 days buffer** |

**Set against a lift-to-bar cost of $850k–$1.2M.** The disproportion is the whole analysis: we would
spend 130–180× the annual cash flow to lift an asset in which we hold under 1% of the float.

## 3. The free lever: burn 0.45 → 0

| | emission share | TAO/day | pool inflow |
|---|---|---|---|
| burn 0.45 (now) | 0.0075% | 0.27 | ~$1.6k/month equivalent |
| burn 0.00 | 0.0753% | 2.71 | ~$16.1k/month equivalent |

Gate 0.019 → 0.103, rank 57 → 42. **Does not clear the bar**, but it is a 10× improvement for zero
capital, and it is 8× the entire monthly buyback budget. **Caveat:** cutting burn frees miner alpha
that can be dumped — pair with retention scoring (S7) or the freed supply lands straight in the pool.

**Do this regardless of which disposition is chosen.** It is free and it is currently unpulled.

## 4. Why nobody stakes — it is float, not the gate

Alpha emission is **ungated**: every subnet mints 1 α/block whatever the gate does. So staking yield
in alpha terms is unrelated to gate position:

| Subnet | Float (α issued) | gate | Alpha APY |
|---|---|---|---|
| SN15 | 1.16M | 0.92 | **186%** |
| SN107 | 1.27M | 0.99 | 169% |
| SN105 | 1.84M | 0.50 (at the bar) | 117% |
| SN13 | 2.44M | 0.36 (below the bar) | 88% |
| SN64 | 3.18M | 0.998 | 68% |
| **SN21** | **3.55M** | **0.019** | **61%** |

SN64 sits at gate 0.998 and yields **less** than SN13 at gate 0.36. **Float sets yield; the gate does
not.** SN21 offers the worst yield in the set because it has the largest float — and that would be
true at any gate position.

The staking pitch fails because **both** halves are true at once: the nominal yield is the lowest
available, *and* the gate removed the emission-funded buying that used to offset dilution, so the
real TAO-denominated return is negative. Fixing the gate fixes only the second half.

**Projection:** SN21 at +1yr → 6.18M α issued → **35% APY**. A fresh slot at 3 months → **718%**.
Even at 12 months a fresh slot (82%) beats SN21's *current* yield. This gap widens every day and
cannot be closed by any action available to us.

## 5. The bleed

07-27 → 07-29, two days:

| | 07-27 | 07-29 | change |
|---|---|---|---|
| Pool TAO | 8,000 | 7,369 | **−7.9%** |
| Pool alpha | 2,039,742 | 2,214,533 | **+8.6%** |
| EMA price | 0.00403 | 0.00337 | **−16.3%** |

Both jaws closing at once: TAO leaving, alpha accumulating. θ also fell 0.0116 → 0.0091 (−21.8%) over
the same window, so the network is repricing broadly — this is not purely idiosyncratic. Two days
across two data sources is an observation, not a trend, but **it is the number to watch daily**, ahead
of anything gate-related. Injecting capital into a pool leaking at this rate is the classic error.

## 6. Options

### A — Harvest (recommended)
Cut burn to 0. Harvest the owner-cut entitlement at a chosen rate. Spend nothing on the ascent.

| Harvest rate | Yield (at 25% entitlement) | Price cost |
|---|---|---|
| 25% | ~$1.6k/month | −0.9%/month |
| 50% | ~$3.2k/month | −1.9%/month |
| 100% | ~$6.4k/month | −3.7%/month |

*(price costs are for the gross owner cut; harvesting only our 25% is proportionally gentler)*

Accepts a below-bar position. Preserves the ~150-day dereg buffer while the growth decision is made
elsewhere. Costs nothing and forecloses nothing.

### B — Fund the lift ($850k–$1.2M)
Buys a position at the bar. **Rejected on current facts:** we hold 0.91% of float, so ~99% of the
value created accrues to third parties; and per [[sn21-qualitative-drivers]] a buy without a demand
catalyst decays back via the EMA, so the capital is spent and the position is not held.

### C — Inject a new business into SN21 as a takeover
Analysed separately — see §7 stub below. Turns on one measurable unknown: **combined our + DSV
ownership of the 3.55M float.** Break-even is 24–34% depending on legacy overhang; our own measured
holding is 0.91%.

### D — Wind down
Not required yet. The 150-day buffer means this is not forced, and option A dominates it (harvesting
costs nothing and keeps the option open).

## 7. Recommendation

**Take option A now**, unconditionally: cut burn to 0 (free, 10×, unpulled), pair with retention
scoring, and set a harvest rate. Then decide growth on a separate track.

The v440 risk doc's "honest third option" — stop subsidising and harvest — is now the supported call
for SN21 on the numbers. The growth ambition belongs where float is still a design decision. That
conclusion is the same one [[sn21-qualitative-drivers]] reached from a completely different direction:
demand follows substance, and there is no substance here to buy.

## 8. Open items

1. **Re-confirm the 25% entitlement rate** — `owner_ledger.json` is stale since 2026-04-10. Every
   cash-flow number here scales linearly with it.
2. **Measure combined our + DSV float ownership** — the single input that decides option C.
   `holders_sync.py` exists; run it and label DSV coldkeys in `wallet_labels.json`.
3. **Daily bleed monitor** — pool TAO, pool alpha and EMA, with an alert on the 7-day trend. The
   150-day dereg buffer is a function of price and erodes as price falls.
4. **Pull the burn lever and measure** — this is the one action with a known, free, 10× payoff, and
   it doubles as a live test of the gate model's calibration.
