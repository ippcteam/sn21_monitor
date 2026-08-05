# SN21 — Miner-Burn Reduction: Conclusion & Recommendation

**Date:** 2 July 2026 · **Prepared for:** IPPC investors · **Status:** Pre-execution briefing

---

## Recommendation in one line

**Reduce SN21's miner-emission burn from ~74% to ≤20% (target 0%) in staged steps, and enforce ≥85% retention of freed rewards through a curated, vetted miner set — scoring policy we fully control.** (A public "stake-to-mine" entry gate modeled in the first draft is **withdrawn** after subnet-owner review — see §7.1.) On the live formula the plan projects **+7% to alpha price in 90 days / +14% in 180 at burn 20% (+12% / +23% at burn 0%)** versus holding, at no treasury cost. The just-merged emission change (PR #2800, §7.2) roughly **quadruples** those payoffs once node operators deploy it (+27% / +65% at burn 20%) and makes every step of the cut price-effective immediately — executing before competing subnets respond to the same change is the point of moving now. One defensive action is required regardless of the burn decision: **lock owner alpha before the same upgrade activates conviction-based ownership transfer** (§7.3).

---

## 1. What changed on the network

Bittensor's new emission mechanism ("Root Reborn") went live on mainnet ~24 June 2026. We verified its behaviour directly from the deployed source code and reproduced it against live chain data (our model now matches the chain within tolerance across all 63 emitting subnets, including SN21).

Under the new rules, each subnet's share of network TAO emission is:

> **share ∝ price × youth-allowance × (1 − miner burn)**

The last term is the decisive one for us. SN21 currently burns ~74% of miner rewards (declining from our 77.8% weight setting as the chain re-measures each cycle). The chain reads that burn every cycle and **cuts our emission share by exactly the same proportion — the forfeited emission goes to competing subnets.** The mechanism was explicitly designed to penalise subnets that withhold miner rewards; we are currently one of its principal targets.

Two facts we confirmed that correct earlier assumptions:

- **The burned rewards benefit no one.** The withheld alpha is destroyed by the protocol — the owner does not receive it. High burn is pure forfeiture.
- **The lever is exactly linear.** Cutting burn from 74% to 0% multiplies our emission share by ~3.8× (from 0.09% to 0.34% of network emission, i.e. TAO flowing into our pool rises from ~4.0 to ~15.1 TAO/day).

## 2. Why *how far* we cut matters more than *whether* we cut

Extra emission reaches our token's price through two different channels, and only one of them lifts the price:

1. **Below a protocol threshold**, extra emission enters the pool as *balanced liquidity* (TAO and alpha together at the current price). This deepens the pool — useful, but it does **not** move the price.
2. **Above the threshold** (~5.2 TAO/day for SN21 today), the protocol converts the excess into **direct market buys of our alpha every block**. This is the price-lifting channel — and SN21 only crosses the threshold once burn falls below roughly **50%**. *(Under the incoming spec-425 formula the crossing point rises to ~77% — essentially our current burn — making every cut price-effective from the first step; see §7.2.)*

This is why the standing advice to "significantly reduce the burn" is only half right: a cut from 74% to 50–65% captures more emission but converts essentially none of it into price. The price case is specifically for a **deep** cut.

The offsetting force is miner selling: cutting burn hands real miners more alpha, some of which gets sold. Because we control which miners we score, realized selling is a choice, not a risk we passively accept. Break-even is ~15% of the freed rewards sold per day.

## 3. Modelled price impact (180-day simulation, live chain inputs)

Alpha price versus holding the current 74% burn, at 90 / 180 days, across burn levels and the fraction of freed miner rewards that gets sold:

| Burn level | Miners sell 0% | Miners sell 15% | Miners sell 30% | Miners sell 100% |
|---|---|---|---|---|
| 65% | +0% / +0% | −0.4% / −0.7% | −0.7% / −1.4% | −2.4% / −4.6% |
| 50% | +2.0% / +3.8% | +1.0% / +1.8% | +0.0% / −0.2% | −4.4% / −8.6% |
| **20%** | **+9.6% / +19.0%** | **+7.1% / +13.5%** | +4.7% / +8.4% | −5.7% / −11.3% |
| **0%** | **+15.1% / +30.8%** | **+11.4% / +22.4%** | +7.9% / +14.7% | −6.5% / −13.1% |

Read: shallow cuts are dead weight; deep cuts with dump control (≤15–30% selling) deliver double-digit gains; uncontrolled dumping caps the downside at roughly −11%.

Additional effects at burn ≤20%:

- **TAO injection into our pool:** 4.0 → 12–15 TAO/day (≈4,400–5,500 TAO/year of protocol-driven inflow — currently the pool is bleeding ~1 TAO/day).
- **Owner emissions:** the owner's alpha allocation is protocol-fixed at 1,296/day regardless of burn — what rises is its **value**, in line with price.
- **Strategic positioning:** removes SN21 from the "high-withholding" category the new mechanism (and any future tightening of it) is designed to punish.
- **Timing:** the youth-allowance term is near its peak for SN21 and halves over ~30 months — the same cut made later buys structurally less. *(Superseded by §7.2: the merged upgrade removes this term entirely; the new and sharper timing argument is cutting before competing subnets respond to the same incentive.)*

## 4. The coupling: retention enforced through a curated miner set

*(Revised 3 July: the first draft coupled the cut to a public entry-stake gate. That element is withdrawn after external subnet-owner review — the reasoning and what replaces it are in §7.1. The retention mechanism below stands.)*

The table in §3 makes the whole price case conditional on one behavioural assumption — that miners sell no more than ~15–30% of their freed rewards. Rather than assume it, we enforce it. Bittensor has no chain-level rule for this, but it doesn't need one: **we control 100% of SN21's weight-setting** (every validator copies our weights), so miner-scoring policy *is* subnet policy. Two instruments, checked each weekly scoring epoch from on-chain data:

1. **Curated miner set.** The freed rewards are routed to vetted operators (including our own house miners) admitted under an explicit operating agreement. Who gets scored is already entirely our choice — this is standard subnet-owner discretion, not a new mechanism, and it involves no public "pay to mine" rule.
2. **Retention scoring.** A miner's weight is zeroed if its coldkey sells more than 15% of its freed rewards over the trailing week — measured with the per-coldkey flow monitoring we already run daily. This makes the §3 "miners sell 15%" row the *enforced* case, not the hoped-for one.

The chain sees none of this — our published burn, and therefore our emission share, is unaffected. Modelled impact on the **live** formula (S7 engine, retention-only; alpha price vs holding — see §7.2 for the much larger post-upgrade figures):

| Burn level | Retention | 90 days | 180 days | 180 days under exit-cascade stress* |
|---|---|---|---|---|
| 20% | none (miners sell all) | −5.7% | −11.3% | — |
| **20%** | **≥85% (the policy)** | **+7.1%** | **+13.5%** | **+9.6%** |
| 20% | 100% | +9.6% | +19.0% | — |
| 0% | ≥85% | +11.5% | +22.6% | +16.7% |
| 0% | 100% | +15.1% | +30.8% | — |

\* Stress case: 25% of miners' retained alpha dumped at day 90 — the soft-lock failure mode, since alpha unstaking has no unbonding period. Even then the plan at burn 20% ends 180 days clearly positive.

By day 180 at the burn-20% policy case, roughly **250,000 alpha (~13% of the pool's current alpha side) sits held** in retained miner rewards — a direct reduction of the float that our valuation work identified as SN21's structural weakness. Honest caveats: retention should never be tightened during a drawdown (that converts a soft hold into an exit trigger), and retention applied to miners' pre-existing reward flow is additional upside the model deliberately does not count.

## 5. Execution plan and guardrails

Our validator scores miners on a **weekly epoch**, so each burn adjustment lands with the weekly weight update; the chain re-measures the burn within ~1.5 hours of the new weights and the emission share follows immediately. That makes one step per week the natural cadence — full execution to ≤20% takes about **4–5 weeks**.

| Step (week) | Action | Gate to proceed |
|---|---|---|
| 0 (now) | **Lock owner alpha above the conviction-takeover threshold** (§7.3) and stand up lock monitoring — required before spec 425 deploys, independent of the burn decision | Owner hotkey holds the top conviction position with margin |
| 1 | **Brief the curated miner set** (operating agreement incl. ≥85% retention, effective from week 2 scoring) and cut burn 74% → ~64% at the next weekly weight update | Confirm emission share rises as modelled |
| 2–4 | Staged cuts of ~15 pts to ≤20%, one per weekly epoch | Retention compliance ≥85% of freed rewards per coldkey per week (enforced by scoring; daily flow monitoring already in place) |
| 5 | Optional final step to ~0% | Same retention gate; hold at 20% if compliance misbehaves |

**Guardrails:** deregistration-price headroom is currently ~33% (risk: low) and burn reduction *improves* it; the worst modelled outcomes are bounded — full non-compliance costs ~11% (and self-corrects, since non-compliant miners lose their score), and the exit-cascade stress case still ends positive. Everything is reversible at the next weekly weight update: the burn can be raised again and the miner policy adjusted without chain involvement. If spec 425 deploys mid-execution (our daily lab run now detects the flip automatically), the same schedule simply gets more valuable — no re-planning needed.

## 6. Basis of confidence

- Mechanism read directly from the deployed subtensor source (v3.4.9-424, runtime spec 422), not from documentation or third parties.
- Our emission model reproduces live chain emissions across all 63 emitting subnets (median error 13%, SN21 within tolerance).
- An earlier internal finding that suggested the burn cut might be ineffective ("SN21 already over-emits its burn level") was traced to a measurement gap in our tooling and is resolved — the chain applies exactly the burn it publishes.
- Simulations run daily against live chain state in our monitoring stack (Lab tab, scenarios S6 burn→price and S7 stake+retention coupling), so the projections above refresh automatically through execution.
- The stake/retention policy needs no new infrastructure: enforcement is the weight-setting we already control, and compliance is measured by the per-coldkey flow monitoring already running daily.

*Figures in §1–5 as of block 8,539,372 (3 July 2026); §7 figures same block. Projections are ceteris-paribus simulations of the emission mechanics — they exclude market-wide TAO moves and organic demand shifts, and should be read as the mechanical edge versus holding, not absolute price forecasts.*

---

## 7. Addendum (3 July 2026): external review and PR #2800

We circulated the 2 July draft to selected subnet owners. The feedback contained one warning and one lead; both checked out against the subtensor source and both change the plan — one element withdrawn, the rest strengthened.

### 7.1 The public entry-stake gate is withdrawn

The warning: the Opentensor Foundation (Const) has historically cut emissions from, or publicly discredited as "Ponzi", subnets whose incentive mechanisms force miners to buy and hold the subnet's own alpha — and subnets have died of that treatment. Our own risk register already carries discretionary emission-blocking as the #1 tail risk; publishing a "stake X alpha to mine" rule would paint the target on us ourselves. Three further reasons made this an easy call: our own flow research had already concluded the entry-stake's price pop (~8pp, one-time) is mechanical and not durable; the same network upgrade discussed below makes encouraging third parties to accumulate and lock our alpha actively dangerous (§7.3); and the retention rule — the load-bearing piece — never needed the stake gate. **What replaces it:** the curated-miner-set structure of §4, where retention is a condition of a private operating agreement rather than a published pay-to-play rule. Externally this presents as ordinary subnet-owner curation, which it is.

### 7.2 PR #2800 verified: the emission formula loses `root_prop` — a large net win for SN21

Merged into subtensor main on 30 June (runtime spec 425, **not yet deployed** by node operators — live chain still runs the current formula; our daily lab run now auto-detects the flip). Verified directly from the diff: the emission share becomes **price × (1 − miner burn)** — the youth-allowance (`root_prop`) term is removed from the share, while the liquidity-injection cap that creates the chain-buy price channel is untouched. Three consequences, computed from live chain state:

- **A deploy-day windfall with no action from us.** The emission-weighted average youth-allowance of competing subnets is ~0.27 versus our ~0.15 — removing the term re-levels the field in our favour. At our current burn, SN21's emission share goes from 0.080% to 0.142% (**1.78×**, TAO inflow 2.9 → 5.1/day) the moment the upgrade lands.
- **Every step of the cut becomes price-effective.** The chain-buy threshold moves from burn ≈ 0.59 to burn ≈ **0.77 — essentially our current level** — so under the new formula even the first staged cut starts converting emission into direct market buys of our alpha. The "shallow cuts buy depth, not price" caveat of §2 largely dissolves (deep cuts remain 4–5× better).
- **The projections in §4 roughly quadruple.** Re-running the same simulation under the new formula: burn 20% with ≥85% retention → **+27% at 90 days / +65% at 180** vs holding (+39% / +101% at burn 0%); the day-90 stress case stays strongly positive.

One honest moderator: with `root_prop` gone, **(1 − burn) becomes the only term any subnet controls** — 81 of 128 subnets currently burn, and they all face the same new incentive to cut. Our projections hold competitors at today's burns, so every competitor cut dilutes our gain. That replaces the old "youth allowance is fading" urgency with a sharper one: **the payoff belongs to whoever cuts first.** It also means the timing argument for starting the staged cuts now, on the live formula, is stronger than in the original draft.

### 7.3 New in the same PR: conviction-based ownership transfer — owner defense required

Spec 425 also activates, every epoch, a subnet-ownership reassignment: if total *lock-conviction* on a subnet reaches **10% of its outstanding alpha**, the subnet is over a year old (SN21 is), and any non-owner hotkey holds more matured conviction than the owner's hotkey, **ownership of the subnet transfers to that hotkey's coldkey**. Conviction accrues only from alpha explicitly *locked* on-chain (plain staking creates none) and matures over time. For SN21 the 10% threshold is currently **~357,000 alpha (~1,700 TAO, roughly $340k)** — an amount a motivated actor could accumulate and lock quietly. Actions, independent of the burn decision: **(a)** lock owner alpha above any plausible challenger before the upgrade deploys (owner emissions of 1,296 alpha/day make this cheap to maintain); **(b)** add third-party lock/conviction monitoring on SN21 to the daily scan; **(c)** never design miner policy around *locked* stake — retention holdings must stay as plain stake, which builds no conviction against us.
