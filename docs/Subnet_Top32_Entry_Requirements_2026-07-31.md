# What it takes to launch into the top group under v440

**Date:** 2026-07-31  **Backdrop:** live demand distribution at block 8,715,990 (2026-07-27), TAO = $198.6
**Question:** DSV-backed new subnet taking over an existing slot — what technical and commercial
criteria must it hit to land and hold a position that still earns emission under the v440 gate?

**Model caveat, stated up front:** these figures come from `hill_gate_v440_2990` against the
2026-07-27 state snapshot. Per CHANGELOG 2026-07-29, that mechanism reproduces the network to
median rel.err **0.207 (27/62 within tol)** — directional, not exact. Treat every number here as a
**band and a ranking**, not a quote. The *shape* of the answer (thresholds, which levers dominate,
orders of magnitude) is robust; the third significant figure is not.

---

## TL;DR

1. **The gate reads one number: `ema_price × (1 − miner_burn)`.** Revenue, VC backing, profitability,
   partnerships and growth rate are not inputs. They matter only as the funding and credibility
   behind sustained TAO buy-pressure on your own alpha. The buyback contract is not a feature
   alongside the commercial story — it is the only channel through which the commercial story
   reaches the chain.
2. **Entry price is $150k–$300k/month of *actual buying*, sustained.** Below that you never cross,
   at any horizon. Cumulative to the bar: **$0.6M–$2.4M**; to a defensible top-12 seat: **$1.2M–$5.5M**.
3. **Above the bar the gate pays for itself.** Emission inflow scales superlinearly with price;
   sell pressure scales linearly. At gate 0.9 the position runs a surplus at any plausible
   sell-through. This is a **one-off siege cost, not a burn rate** — which is the correct framing
   for the DSV conversation.
4. **Miner burn must be 0 and stay 0.** Burn ≥ 50% makes the bar unreachable at any realistic budget.
5. **Sell-through (σ) is the design lever that only exists at genesis.** Moving σ from 60% → 25%
   cuts the monthly requirement ~2.2×. Vesting, collateral floors and locked owner/investor alpha
   are worth more than the VC round.

---

## 1. The formula, and what it does and does not reward

Per emit-enabled subnet, every tempo:

```
s_i    = ema_price_i × (1 − miner_burn_i)          # demand share, normalised over emit-enabled set
θ      = q-mass bar: sort s descending, accumulate until cum ≥ q; θ is the share at the crossing
gate(s)= 1 / (1 + (θ/s)^h)                          # ½ at the bar, →1 above, →0 below
e_i    = gate(s_i)·s_i / Σ_j gate(s_j)·s_j          # final emission share
```

Live hyperparams read from finney 2026-07-29: **q = 0.75, h = 3.0**. Both are root/sudo — we do not
control them, and q has already moved once (0.61 default → 0.75 live).

There are exactly **two** inputs a subnet owner controls: `ema_price` and `miner_burn`. Everything
in a business plan must terminate in one of those two or it does not affect emission.

## 2. Where the bar sits (2026-07-27)

| | Value |
|---|---|
| θ (q-mass bar) | **0.01160** demand share |
| Bar price at zero burn | **0.00861 TAO/α** (≈ $1.71/α) |
| Emit-enabled subnets | 70 of 128 registered |
| Subnets at gate ≥ 0.5 | **~22–24** |
| Rank 32 | gate ≈ 0.25 — a **75% haircut**. "Top 32" is the edge of the cliff, not safety |

Network TAO emission is 0.5 TAO/block = **3,600 TAO/day** total.

| Target | Price needed | ×bar | Rank | Emission share | Gross TAO/day |
|---|---|---|---|---|---|
| gate 0.25 | 0.00574 | 0.69× | ~32 | 0.19% | 7 TAO ($1.4k) |
| **gate 0.50 (the bar)** | **0.00828** | **1.00×** | **~23** | **0.75%** | **27 TAO ($5.3k)** |
| gate 0.90 | 0.01790 | 2.16× | ~12 | 2.87% | 103 TAO ($20.5k) |
| gate 0.99 | 0.04039 | 4.88× | ~6 | ~8% | ~290 TAO ($58k) |

**Empirical comparables — thin-float subnets and the pool depth they hold:**

| Subnet | Pool alpha | Pool TAO | Price | gate |
|---|---|---|---|---|
| SN105 | 600k α | 5,034 ($1.0M) | 0.00861 | **0.50 — exactly at the bar** |
| SN96 | 316k α | 3,652 ($0.73M) | 0.01180 | 0.72 |
| SN15 | 464k α | 9,307 ($1.85M) | 0.01928 | 0.92 |
| SN107 | 308k α | 15,212 ($3.02M) | 0.04695 | 0.99 |
| *SN21 (us)* | *2.04M α* | *8,000 ($1.6M)* | *0.0039* | *0.024* |

SN21 holds **more TAO than SN15**, which sits at gate 0.92, and is at gate 0.024 — because price is
`TAO ÷ alpha` and our float is 4.4× larger. Capital does not set your position; **capital ÷ float** does.

## 3. Technical requirements

1. **Miner burn = 0, permanently.** Burn multiplies your demand share directly. At $300k/month of
   buying and σ = 40%:

   | burn | outcome |
   |---|---|
   | 0% | clears bar month 3, ends at gate 0.999 |
   | 25% | clears bar month 7, ends at gate 0.963 |
   | 50% | **never clears**, ends at gate 0.254 |
   | 75% | **never clears**, ends at gate 0.027 |

   Design the emission mechanism with no burn lever at all, or it will eventually get used.

2. **Emission enabled at genesis.** 58 of 128 registered subnets are emit-disabled and sit at gate 0
   structurally. A fumbled start call is a total loss.

3. **Sell-through (σ) is the escape-velocity determinant.** Minimum *flat* monthly buyback that
   ever clears the bar within 24 months:

   | Sell-through | Minimum sustained buyback |
   |---|---|
   | 25% (aggressive vesting + collateral) | **$97k/month** |
   | 40% | **$144k/month** |
   | 60% (typical) | **$215k/month** |
   | 80% (mercenary miners) | **$295k/month** |

   Below these you *never* cross — pool alpha accumulates faster than you buy, indefinitely. Long
   miner/validator vesting, collateral floors (the v435 pattern, see [[sn21-daily-stream-im]]) and
   locked owner/investor alpha are the cheapest capital in the whole plan.

4. **Buy continuously, not in lumps.** The gate reads `ema_price` (~8h half-life). A one-day spike
   with no follow-through retains **12.5% of its effect after 24h and 0.2% after 72h**. Per-transaction
   buyback triggers are close to ideal; monthly block purchases are close to worthless.

5. **Bought alpha must be locked or burned, never recycled.** Alpha used to pay contributors
   re-enters float and you pay for the same price level twice.

6. **Immunity is 120 days**, and deregistration is decided on `SubnetMovingPrice` — the *same* EMA the
   gate reads ([[sn21-dereg-floor-mechanics]]). One metric governs both survival and revenue, and you
   get ~4 protected months to cross. That window matches the timelines in §4, with little slack.

## 4. Commercial requirements

Fresh slot (60k α, minimal pool) simulated against the fixed live distribution. Cell = month the bar
is crossed @ cumulative capital spent:

| Flat buyback | σ=60% | σ=40% | σ=25% |
|---|---|---|---|
| $100k/mo | never | never | m21 @ $2.1M |
| $200k/mo | never | **m7 @ $1.4M** | m3 @ $0.6M |
| $300k/mo | m8 @ $2.4M | m3 @ $0.9M | m2 @ $0.6M |
| $500k/mo | m3 @ $1.5M | m1 @ $0.5M | m1 @ $0.5M |

**Requirement range:**

| | Cross the bar (gate 0.5) | Hold top-12 (gate 0.9) |
|---|---|---|
| Sustained buy rate | **$150k–$300k/month** | **$300k–$600k/month during ascent** |
| Cumulative capital | **$0.6M–$2.4M** | **$1.2M–$5.5M** |
| Timeline | 3–8 months | 6–18 months |

**Above the bar the position self-funds.** Steady-state net external TAO needed to *hold* a level
(this is float-independent — alpha mints at 1/block for every subnet regardless of pool size):

| Level | σ=40% | σ=60% | σ=80% |
|---|---|---|---|
| gate 0.5 | −$18k/mo (surplus) | +$53k/mo | +$124k/mo |
| gate 0.9 | **−$309k/mo (surplus)** | **−$155k/mo (surplus)** | ~$0 |

Emission inflow scales superlinearly with price while sell pressure scales linearly — the
rich-get-richer mechanic, working for you once inside. At gate 0.9 the seat yields ~**$7.5M/yr** of
gross TAO emission plus ~**$1.7M/yr** of owner-cut alpha (18% of 7,200 α/day at that price).

**A ~$3–5M seat acquisition with a self-funding terminal state — not an indefinite subsidy.**

## 5. Assessment of the proposed conditions

**Well-targeted:**
- **Contractual per-transaction buybacks, verifiable on chain.** Correct instrument, correct cadence
  (matches the EMA), and genuinely differentiated — almost nothing in the ecosystem has this.
- **Accelerating revenue.** The shape fits the cost curve: expensive ascent, self-funding after.
- **Profitability.** What makes a 30%+ buyback payout survivable at all.

**Insufficient as stated:**
- **$1M VC.** Roughly one attempt at the bar at σ = 40% with nothing held back; if it falls back, EMA
  decays and the capital is gone. **Raise $3–5M**, framed as seat acquisition.
- **"Six figures monthly revenue."** Too wide to be a criterion. At $100k/mo revenue with a 30% payout
  you buy $30k/month — never crosses, at any σ. The binding constraint is the **buyback dollar**, not
  the revenue dollar. Requires either revenue at the top of six figures ($400–500k/mo) at 30% payout,
  or a 70–100% payout for the first 6–9 months with VC covering opex, or VC bridging the ascent directly.
- **50% MoM for 18 months.** The model compounds this to $197M/month, i.e. the projection does no work
  past ~month 9. Underwrite the first 9 months only — which is also all the ascent needs.

**Missing:**
- **A genesis float/vesting design.** Worth more than the VC round and unavailable after launch.
- **A payout floor, not a percentage.** Contract a minimum $/month (e.g. $200k) with the percentage as
  upside. A percentage of early revenue sits below escape velocity exactly when it matters most.
- **Bar-inflation headroom.** θ is a moving target. If rival demand rises 50% — plausible if several
  funded teams run this same play — the escape threshold goes **$144k → $251k/month**; at 2× it is
  $367k. Budget 1.5×.
- **q/h governance risk.** A single root call reprices the entire plan in either direction. q already
  moved 0.61 → 0.75. Non-diversifiable; name it in the risk section rather than model it.

**On partnering with top-32 subnets (Hippius, LeadPoet et al.):** zero direct gate benefit, and TAO
spent on their services is TAO leaving your pool. The value is credibility, distribution and making
the revenue story legible to buyers. Worth doing — but it must not appear in the emissions model.

## 6. How this compares to fixing SN21

Deep float and thin float fail in different directions, and it is worth being precise about which:

| | SN21 (2.04M α, 8,000 TAO) | Fresh slot (thin) |
|---|---|---|
| One-off CPMM buy to reach the bar (at burn 0) | **3,621 TAO ($0.72M)** | ~86 TAO ($17k) |
| One-off buy to reach gate 0.9 | 9,092 TAO ($1.81M) | ~268 TAO ($53k) |
| Passive price decay from daily alpha mint | ~0.18%/day | ~6%/day |
| Ongoing hold cost | identical — set by σ, not by float | identical |

**Thin float is cheap to lift and decays fast; deep float is expensive to lift and holds well.** The
ongoing cost is the same for both. So the new subnet's advantage over fixing SN21 is *not* capital
efficiency on the lift — SN21's ascent is only ~$0.72M once burn is cut to 0. The real advantages are:

1. **σ is designable at genesis and effectively fixed thereafter.** SN21 cannot retrofit vesting onto
   an existing miner base; a new subnet can build collateral and vesting in from block 0.
2. **A revenue engine contractually bound to buybacks** funds the hold. SN21 has no demand catalyst —
   which is the actual finding of [[sn21-qualitative-drivers]]: demand follows substance, and a buy
   without substance decays back.
3. **120 days of dereg immunity** to establish the position.

That comparison cuts both ways and should be presented honestly to DSV: **SN21's lift is cheap; what
SN21 lacks is something to hold it up.** The case for a new subnet rests on the revenue contract and
the genesis float design, not on the entry price.

## 7. Headline for the DSV conversation

> $3–5M of committed buy over 9–15 months, of which ~$1.5–2.5M is the ascent, buys a top-12 seat
> worth ~$9M/yr gross that self-funds thereafter — conditional on zero miner burn and a genesis
> float design that keeps sell-through under 40%.

## 8. Follow-up

- Register these as a `lab/` scenario so the numbers refresh against live chain state rather than the
  2026-07-27 snapshot, and re-run once `hill_gate_v440_2990` clears its reproduction tolerance.
- Re-run §2 and §4 whenever `gate_q` / `gate_h` / `gate_theta` move on chain (`chain_pull` reads all
  three); a q change invalidates every threshold here.
- Track θ drift over the next 60 days to size the bar-inflation headroom empirically rather than by
  the ×1.25/×1.5/×2 sensitivity used above.
