# Root Reborn (PR #2759) — SN21 Risk Assessment & Models

**Version:** v0.6
**Date:** 2026-06-18
**Subject:** subtensor PR #2759 "Root Reborn" — impact on SN21 as subnet owner
**Proposal status:** Open against devnet-ready. Authored by unconst (Const). Not on testnet or mainnet. No deployment timeline announced. Security items unresolved.
**Assessment status:** Living document. Pool-state inputs are **live** (refreshable via `root_reborn_model.py --live --write-doc`, see §6); flow inputs remain estimates — see §3.0 before citing any figure.

---

## 1. Executive summary

**Mandate note (read first).** This assessment optimises for **one objective: maximise and protect SN21**. That is deliberately *not* the objective the proposal's author optimises for. Const's incentive is the network aggregate — total TAO revenue, sum-of-subnet-prices, validator-class realignment. A change can be unambiguously good for the network and simultaneously neutral-to-negative for any individual subnet, because the aggregate gains are **distributional** and accrue to selected subnets. Const's public case for Root Reborn (net sell pressure off, prices up, revenue up, institutional on-ramp) is a strong *network* case; none of it is a *per-subnet* guarantee. Where his framing operates at the aggregate level, we discount it to the SN21 level and ask only: does this protect or grow *our* alpha, *our* floor, *our* emission share? Everything below is filtered through that single question.

The mechanic that protects SN21 is intact: **the auto-sell on our root proportion is unchanged**. Gross sell-side pressure is identical before and after. Everything Root Reborn adds is on the *buy* side and is *conditional on winning root-validator basket weight*.

The trade for a subnet owner is therefore not "buy pressure vs. today." It is:

> **Buy pressure now (smooth, while we hold favour) in exchange for a redemption overhang (lumpy, on a trigger we don't control), validator-relationship dependency, and two-way reflexivity.**

For a subnet positioned to compete on legible real demand — which is the AdTAO thesis — this is a game we would rather be inside than outside, **but only under one assumption: that root validators select subnets on merit.** That assumption is doing heavy lifting. If validators instead select on what retains their stake — low-variance, deep-liquidity subnets where the buy→hold→redeem round-trip loses little to slippage — then selection correlates with *incumbency*, not *value* (R-J below). A thin, young, near-floor subnet with real demand can lose to a deep mediocre incumbent. So the v0.1 framing ("Root Reborn rewards exactly what AdTAO is built to demonstrate") now carries a caveat: it rewards demand *only if the jury grades on demand*.

It is a *managed exposure*, not a gift. It introduces one genuinely new tail risk (R-C) that compounds badly with Conviction's lockups, and one structural bias against our profile (R-J). The headline modelled result: **a favoured SN21 that accumulates ~5–6 weeks of basket weight, then suffers a full redemption, can breach the dereg-relevant floor in a single cascade.** *Now re-run on live pool state (§3 reference run; §6 carries the live-refreshable figures): with spot ~14–16% above the 0.0035 floor, the breach threshold is ~37–41 days at 1% weight share — so the 30-day case lands a few percent above the floor and "5–6 weeks" sits at the edge of the breach band, not inside it. Direction holds; the trigger is slightly further out than v0.4 implied.*

**Validator-archetype lens (frames R-B, R-C, R-E, R-J).** Three behaviours, increasing harm: *neutral* — allocates on merit (the assumption our upside relies on); *biased* — favours own/allied subnets (R-E; partially self-correcting via yield, **except** it does not discipline targeted starvation of a competitor — R-B); *predatory* — inflates own subnet's apparent yield, herds yield-chasing stake into his basket, accumulates a large escrow position in his alpha, then triggers a cascade (engineered R-C, enabled by the self-deal vector the PR's §7 admits is unguarded). The conservation invariant (Σ owed == BasketPrincipal) means a predatory validator cannot directly abscond with staker principal — the live mechanism is herding + self-dealing buy-flow capture + mass-redemption cascade, plus dumping his own personal holdings.

---

## 2. Prioritised risk register

Prioritised by (likelihood × impact to **SN21 specifically**). "SO-specific" = arises from our position as subnet owner, not general protocol/governance concern.

| ID | Risk | Tier | SO-specific | Trigger |
|----|------|------|-------------|---------|
| R-C | Redemption overhang / cascade volatility | **P1** | Yes | Concentrated redemption of an accumulated basket position |
| R-D | Two-way reflexivity via Taoflow | **P1** | Yes | Loss of basket favour while emission share is coupled to inflow |
| R-E | Validator oligopoly → relationship dependency / pay-to-play | **P2** | Yes | Stake concentration (live root-stake top-4 **55%**, top-10 **80%**; see §6 — earlier "~91%" was a different metric) |
| R-B | Targeted starvation by competitor-aligned validators | **P2** | Yes | A competitor controls / influences significant root stake |
| R-J | Adverse selection toward liquid / incumbent subnets | **P2** | Yes | Validators select on stake-retention (low slippage) not merit |
| R-K | Yield-optics / momentum bias | **P2** | Yes | Displayed yield is mark-to-market; stakers chase it → favours pumps over builders |
| R-A | Relative-position erosion | **P3** | Yes | Peers win weight; SN21 stays at status quo |
| R-F | Threshold squeeze near the 0.0035 floor | **P3** | Conditional | SN21 near dereg threshold while favoured peers are boosted |
| R-G | Technical / implementation flaws | **P4** | Partial | Mostly pre-mainnet; dissolve bug matters only at wind-down |
| R-I | Rushed process / timeline uncertainty | **P4** | No | Off-chain review; convergent opposition (see note) |
| R-H | Neutrality removal → buy-flow pool shrinkage | **P4** | Partial | Root TAO exits rather than accept forced allocation |

### P1 — Critical

**R-C — Redemption overhang / cascade volatility.**
Today root's relationship to SN21 is a smooth, predictable mechanical trickle of sells. Under Root Reborn, winning basket weight means an escrow accumulates a *standing position in our alpha*. That is supportive while it builds — but `root_claim_on_subnet` lets stakers redeem on demand, and redemption swaps that basket alpha **back to TAO through our AMM**. So we would be trading a smooth predictable sell for: buy pressure now, plus a lumpy, correlated sell *overhang* that fires on triggers we don't control.
**Refined characterisation (v0.3).** The buy flow is neither "hot money" nor "patient capital" — it sits between. A large aligned validator is plausibly a *steadier* holder than today's retail churn in normal conditions (lowering base volatility). But the **redemption trigger lives at the staker layer, not the validator layer**: an aligned validator can hold his thesis while his nominators redeem en masse on fear or a better basket elsewhere. Net effect is a *shape change* in our volatility — **lower base volatility in exchange for a fatter tail** (correlated mass redemption). We are not paid for that tail; it is the cost of the buy-side support.
**Empirical precedent (not theoretical).** Off-protocol basket allocators already demonstrate the failure mode: in SN76's Feb-2026 flash event, automated indexes mechanically rebalanced into a price spike at up to ~97% slippage / ~80% drawdown. The mechanism that hurt them — mechanical allocation against a thin pool — is the same one R-C describes, and SN21's pool profile is on the vulnerable side of it.
**Compounds with Conviction:** our own emissions are auto-locked (constrained ability to defend price), while the basket overhang in our alpha can exit freely. Asymmetric. *Modelled in §3.1.*
**Engineered variant (predatory archetype):** the overhang need not be incidental. A validator who inflates his own subnet's apparent yield herds yield-chasing stake into his basket, accumulating an oversized escrow position, then triggers the cascade — using the self-deal vector (buying into shallow pools he LPs into) that the PR's §7 admits is currently unguarded. The conservation invariant (Σ owed == BasketPrincipal) prevents him *directly* taking staker principal; the harm is the herding + buy-flow capture + mass redemption, plus dumping his own personal holdings alongside.
**Coordinated-trigger variant (v0.4):** beyond ambient fear, there is a *visible, intentional* cascade trigger. A validator who publicly cuts SN21 weight after a price rise effectively signals his stakers to claim (leaving rewards in-basket now exposes them to a correction). The public basket transparency we logged as a **governance positive under R-E doubles as a cascade-coordination channel here** — both readings hold simultaneously. The redemption trigger is therefore partly a communications event a third party controls, not only a market event.

**R-D — Two-way reflexivity via Taoflow.**
Basket buys are TAO flowing into our pool. Under flow-based emissions, inflow plausibly lifts emission share → more alpha minted → bigger root dividend on SN21 → more buy flow. Flywheel up. It runs in reverse identically: lose favour → basket sells *and* emission share contracts simultaneously — a self-reinforcing double hit on the way down.
**[GAP — Q1]** Whether the protocol's Taoflow accounting counts escrow-basket buys as subnet inflow is unconfirmed. The legacy root-claim swap was *explicitly excluded* from flow math. If basket buys are also excluded, reflexivity is muted; if they count, it is amplified. **Resolve before building any strategy on winning weight.** *Sketched in §3.2.*

### P2 — High

**R-E — Validator oligopoly / relationship dependency / pay-to-play.**
"Court the validator set" collapses into "court three or four specific entities" given documented stake concentration. That is a fragile position where one soured relationship is an existential allocation event, not a marginal one. It also sets up a pay-to-play arms race — subnets pressured to court big validators for funding. This directly tensions the standing discipline that **AdTAO operating costs must never depend on Bittensor income**: if defending our own alpha starts requiring recurring relationship spend or implicit quid-pro-quo, that is a new cost category and a reputationally messy one to be seen participating in. The common rebuttal — a *biased* validator's stakers will unstake if his favoured subnets underperform — is only partially true: it self-corrects broad mediocrity but not targeted starvation (see R-B), because the rest of the basket can mask one deliberately zeroed competitor.
**Partial temper (v0.3).** Validator-curated alpha baskets *already exist off-protocol* — Mentat Minds runs themed subnet index baskets (Sum-of-Subnets, Mentat 5/15, Protected Alpha) and Crucible operates a principal-protected Smart Allocator as a top validator. So the discretion R-E fears is largely *already here*, just opaque. Root Reborn's on-chain basket transparency (the `betaBasket_*` RPC views expose composition and NAV per validator) is plausibly *better* governance than the off-chain status quo: the real choice is transparent-discretion vs. opaque-discretion, not neutral vs. discretion. This lowers R-E's novelty, not its concentration danger — the oligopoly and pay-to-play dynamics persist regardless of transparency.

**R-B — Targeted starvation by a competitor-aligned validator.**
The weaponised form of R-E. A coordinated group can zero SN21 out of every basket. The PR frames this as "a feature if the subnet is bad, a bug if it's targeted abuse of an honest competitor" — and ships **no on-chain remediation**, relying entirely on root-validator-set decentralisation. Accountability-via-yield does *not* discipline this case: a bloc deliberately starving a competitor can still deliver fine returns from everything else in the basket, so their stakers have no reason to leave.
**[GAP — Q2]** Whether any entity controlling significant root stake views AdTAO as a competitor. This single variable decides whether R-B is theoretical or live for us.

**R-J — Adverse selection toward liquid / incumbent subnets.** *Evidence-backed; promoted from theoretical in v0.2.*
Validators must retain stake, so they are pulled toward subnets where the buy→hold→redeem round-trip is cheap — i.e. **deep liquidity and low NAV variance**. That criterion correlates with *large incumbents*, not *best subnets*: a validator can buy $100 of emissions and redeem ~$95 with little slippage, making such subnets a "safe bet" for stake-retention regardless of underlying AI value. This is a Goodhart divergence — the metric validators actually optimise (stable NAV) is not the metric the network claims to reward (productive work). **It is adverse for SN21 specifically:** a young, near-floor subnet with comparatively thin pools is exactly the high-variance, slippage-heavy profile that gets *underweighted despite real demand*.
**Confirmed in the wild:** the existing off-protocol allocators already behave exactly this way. Mentat's published "risk ladder" explicitly tells users to hold back when a pool is thin or a subnet is under 48 hours old — i.e. the allocators *screen out* precisely SN21's profile — and SN76's flash event showed mechanical rebalancing into a thin pool producing ~97% slippage. So this is not a hypothesised bias; it is documented allocator behaviour we would be subject to. It weakens the optimistic R-A framing: Root Reborn rewards legible demand only if validators grade on merit; the observed behaviour is that they grade on liquidity to protect principal, so a thin productive newcomer loses to a deep mediocre incumbent.
*Counter (logged for fairness):* if safe-but-low-growth baskets underperform genuine performers over a long horizon, yield-accountability could eventually correct the bias. The incumbency tilt is real short-to-medium term; the equilibrium is contestable.

**R-K — Yield-optics / momentum bias.** *Added v0.4. A second selection axis, distinct from R-J.*
A validator's *displayed* yield is marked-to-market on the alpha sitting unclaimed in their basket, so price movement on held positions drives the number stakers shop on. Because stakers chase displayed yield, this pulls validators toward subnets with strong recent *price action* — ephemeral pumps — and away from subnets that build steadily with flat or weak price action, **especially those carrying sell pressure from funding their own development**. This is a different axis from R-J and can point the opposite way: a thin pumping SN is *bad* on R-J (liquidity) but *good* on R-K (optics) short-term.
**Why this is the harder of the two for us:** SN21 loses on both axes — thin *and* not engineered for price action — but the "mitigations" conflict. R-J says deepen liquidity; R-K says manufacture visible price action. The second is a game we are constitutionally barred from playing: it cuts directly against the integrity discipline (no manufactured signals) and the rule that **AdTAO operating costs never depend on Bittensor income**. The honest builder with real costs is precisely the profile the optics game punishes. We cannot out-pump an extractor without becoming one.
**Severity is conditional (see Q6):** R-K bites hard only if validator yield is surfaced as mark-to-market NAV. If wallets/Taostats surface *realised* (claimed-TAO) yield instead, the distortion is muted. The measurement choice is unmade and materially sets this risk's weight.
**Secondary effect — claim-timing noise:** displayed yield also depends on *when a validator's stakers happened to claim* relative to price swings — two validators with identical strategies can show different yields purely from claim timing outside their control. This further corrodes the "accountability-via-yield" rebuttal that Const's case and the R-E/R-B counters lean on: if displayed yield is partly timing noise, it is a noisier merit signal than supporters assume.
*Source caveat:* drawn from a single practitioner opinion; the specific subnet examples cited (relative price paths of named SNs) are not independently verified and the assumption that stakers uniformly chase displayed yield is asserted, not proven. The *mechanism* is sound; the *magnitude* is unproven.

### P3 — Medium

**R-A — Relative-position erosion.** We don't get worse in absolute terms; we get *left behind*. If peers win weight and we don't, they get tighter floors while we sit at today's eroding status quo. Soft, slow, but real.

**R-F — Threshold squeeze near the dereg floor.** Root buy-flow concentrating on favoured subnets lifts *their* Taoflow metrics, pushing marginal subnets down the productive-subnet ranking. If SN21 is ever near the dereg threshold and unweighted, favoured competitors getting boosted raises the bar we must clear — an indirect squeeze even with our absolute sell-side unchanged.

### P4 — Lower / contextual

**R-G — Technical / implementation.** The PR's own §7 and the automated Skeptic review flag high-severity items: unbounded fan-out in the coinbase (DoS), unbounded migration state scans, unbounded weight vectors without caps, and a **dissolve-logic flaw that pays current shares instead of owed principals**. None are economically live for a healthy operating subnet — but the dissolve bug would misallocate value to our *stakers* if SN21 were ever wound down before it is fixed.

**R-I — Rushed process / timeline uncertainty.** Reviewed off-chain before a runtime upgrade rather than formal on-chain vote; criticised as fast. Affects *certainty*, not direction. *Recalibrated again (v0.3) — two opposing forces now weighed:* (1) multiple credible commentators (@AlgodTrading, FlowSniper, the independent archetype critique) converge **unprompted** on the same governance thesis, which lowers clean-merge probability and raises the chance of modification; against (2) **founder conviction is high** — Const frames this as the deferred original post-dTAO design with on-chain plumbing already present, philosophically load-bearing (root optimises TAO revenue as the symmetric counterpart to subnet validators optimising commodities). That conviction *raises* ship-probability and partially offsets the opposition. His "25 lines of code" minimisation is contradicted by the PR's own §7 hardening list (unbounded fan-out, migration scans, dissolve fix, slippage guards) — the redirect is small, the safe version is not. **Net: likely to ship in a modified form, with guards added** — and the guards (self-deal caps, rate-limit) are ones we would want. Plan for "when, modified," not "if."

**R-H — Neutrality removal → buy-flow pool shrinkage.** *Reframed in v0.2.* Root was the network's *opt-out* from allocation — the place to hold pure TAO and decline to pick. Root Reborn removes passive neutrality entirely: even doing nothing means your validator's basket. Beyond the manager-risk on our own root holdings (trivially mitigated by redeeming often), the second-order effect on SN21 is the one that matters: some root TAO may **exit root rather than accept forced allocation**, shrinking the dividend pool that feeds *all* baskets — i.e. shrinking the very buy-flow our upside depends on. The size of this is unknown and depends on how sticky root stake is once neutrality is gone. **[GAP — Q4]**

---

## 3. Quantitative models

### 3.0 Inputs — pool state now LIVE; flow inputs still estimates

The model (`root_reborn_model.py`, companion file) reduces cleanly because under a constant-product AMM the price impact of a sell depends **only on the sell size as a fraction of the alpha reserve**:

```
p1 / p0 = ( 1 / (1 + x) )^2 ,   x = (alpha sold) / (alpha reserve)
```

This makes the *shape* of the result robust even where absolute reserves are uncertain.

**[D1 — pool state RESOLVED, 2026-06-18]** Live SN21 pool pulled from finney (`subtensor.all_subnets()`, the same path `market_sync.py`/`collector.py` use) at **block 8,432,852**:

| Input | Old placeholder | **Live value** | Note |
|-------|-----------------|----------------|------|
| alpha reserve `A0` | 2,000,000 | **1,974,778** | placeholder was within 1.3% |
| spot price `p0` | 0.0040 | **0.0040520 TAO/alpha** | placeholder within 1.3% |
| implied TAO reserve `T0` | 8,000 | **8,002 TAO** | `tao_in` of the pool |
| dereg floor | 0.0035 | **0.0035 (kept)** | not a chain constant — see §3.1; SN21 sits **+15.8% above** it, and 17 of 128 priced subnets are below it |

**The placeholders were materially accurate, so the v0.3 model results stand essentially unchanged** (re-run below). Still estimates / scenario knobs, *not* resolved by chain state: `network_root_div_tao_day` (1,500), `sn21_weight_share` (1%), `accumulation_days` (30), `baseline_rootprop_sell_alpha_day` (50). These are network-aggregate or forward-looking and could not be cleanly read on-chain in this RPC version (`subnet(21)` emission fields return 0). **[D1 remainder]** still open: derive real root-dividend recycle rate and SN21 baseline root-prop sell.

### 3.1 Model A — Redemption overhang & cascade (R-C)

*Figures below re-run on LIVE pool state (block 8,432,852); see §3.0.*

**Accumulation.** At 1% weight share, SN21 receives ~15 TAO/day of basket buy-flow (~3,702 alpha/day). Over 30 days the escrow holds **~111,056 alpha = 5.62% of the pool reserve.**

**Cascade impact** — that overhang sold back into the pool over a short window:

| Redeemed | x = sold/reserve | Price impact | Spot after | Breaches floor (0.0035)? |
|----------|------------------|--------------|------------|------------------|
| 10% | 0.56% | −1.12% | 0.00401 | no |
| 25% | 1.41% | −2.75% | 0.00394 | no |
| 50% | 2.81% | −5.40% | 0.00383 | no |
| 100% | 5.62% | −10.37% | 0.00363 | **no (+3.8% above floor)** |

**Live-data note (softens the v0.3 headline).** Because live spot sits **+15.8% above the 0.0035 floor** (vs the 12.5% assumed in v0.3), the 30-day / 1%-share full cascade now lands at **0.00363 — ~3.8% clear of the floor, not through it.** The single-cascade floor breach is therefore *not* reached at the headline 30-day/1% scenario; it needs ~41 days at 1% share (see below). The exec-summary "~5–6 weeks then a full redemption can breach the floor" remains directionally correct (5–6 weeks ≈ 35–42 days) but is at the *edge* of, not inside, the breach band at current pool depth.

**Baseline contrast.** Today's smooth root-prop sell (~50 alpha/day, *still an estimate*) is **−0.005%/day**, spread across ~7,200 blocks → negligible intraday. A full cascade of the accumulated overhang compresses **~2,221 days of baseline selling into one window.** That is the asymmetry, quantified: the danger was never the gross sell rate — it is the *timing concentration* a redeemable escrow creates.

**Floor-breach analysis (full one-shot cascade).** With live spot **15.8% above** the floor, an overhang of **7.60% of reserve** breaches the floor if fully redeemed at once (up from 6.90% — higher because spot has more headroom). Days of accumulation to reach that, by weight share:

| Weight share | alpha/day | Days to breach-capable overhang |
|--------------|-----------|----------------------------------|
| 0.5% | 1,851 | **81 days** |
| 1.0% | 3,702 | **41 days** |
| 2.0% | 7,404 | **20 days** |
| 5.0% | 18,509 | **8 days** |

**Read this carefully:** the *more favour* SN21 wins, the *faster* a breach-capable overhang accumulates. Winning big is not unambiguously good — it builds a larger spring. At 2% share, just 20 days of favour creates a position that, if dumped, takes spot through the floor.

**Overhang sensitivity (x, rows = days, cols = weight share):**

| days \ share | 0.5% | 1.0% | 2.0% | 5.0% |
|--------------|------|------|------|------|
| 14 | 1.3% | 2.6% | 5.2% | 13.1% |
| 30 | 2.8% | 5.6% | 11.2% | 28.1% |
| 60 | 5.6% | 11.2% | 22.5% | 56.2% |
| 90 | 8.4% | 16.9% | 33.8% | 84.4% |

**Interpretation.** The realistic path is *gradual appreciation during accumulation, then exposure to a sharp drawdown on a redemption trigger*. This is path-dependent and the downside is concentrated. The defensive posture writes itself: monitor the standing basket position in SN21 alpha as a first-class risk metric, and treat large accumulated overhang from a single validator as concentration risk, not a win.

### 3.2 Model B — Two-way reflexivity (R-D), directional only

If basket buys **count** as Taoflow net inflow (Q1 = YES), buy-flow `B` raises emission share, which raises the root dividend minted on SN21, which raises `B`:

```
B_eff ≈ B / (1 − e)      e = Taoflow elasticity of emission share to net inflow
```

| e (elasticity) | Amplification | Applies to |
|----------------|---------------|------------|
| 0.0 | 1.00× | up-spiral **and** down-spiral |
| 0.2 | 1.25× | up-spiral **and** down-spiral |
| 0.4 | 1.67× | up-spiral **and** down-spiral |

`e` is unknown here and must be estimated from Taoflow behaviour. If Q1 = NO (buys excluded, like legacy root-claim swaps), amplification = 1.0× and reflexivity is muted. **This model is not usable until Q1 is resolved** — it is included to show the *structure* of the amplification, both directions, not to produce a number.

### 3.3 What the models do NOT capture

- Buy-side slippage during accumulation (overhang is slightly overstated → conservative for R-C sizing).
- Basket *compounding* (alpha emissions on the escrow position + price appreciation) — grows the overhang faster than the linear estimate.
- Correlated cross-subnet cascades (a market-wide redemption hits many pools at once; LP and arbitrage behaviour not modelled).
- MEV / front-running of published rebalances (depends on the unset root `WeightsRateLimit`).
- Conviction lockup interaction beyond the qualitative asymmetry note.

---

## 4. Open questions / decisions required

- **[Q1 — blocks R-D]** Do escrow-basket buys count as Taoflow net inflow? (Legacy root-claim swaps were excluded.) Determines whether reflexivity amplifies or is muted.
- **[Q2 — blocks R-B severity]** Does any entity controlling significant root stake view AdTAO/SN21 as a competitor? Decides theoretical vs. live.
- **[Q3]** What is the chosen root `WeightsRateLimit` (hourly / daily / weekly)? Currently `u64::MAX` (disabled); sudo must set it. Governs rebalance cadence, MEV surface, and how fast favour can be withdrawn (faster withdrawal = sharper R-C trigger).
- **[Q4 — sizes R-H]** How sticky is root stake once passive neutrality is removed? Outflow shrinks the dividend pool feeding all baskets — and therefore our own potential buy-flow.
- **[Q5 — PARTIALLY RESOLVED 2026-06-18, see §6]** Does SN21's current pool depth clear the screens existing allocators *already* apply? **Live answer: SN21 sits mid-pack on liquidity** — TAO depth (`tao_in` = 8,002) ranks **69 / 128** priced subnets (~54th percentile, ~1.05× the field median) and is **~4× below the top-liquidity decile** (≥33,910 TAO). We are *not* a deep "safe bet"; we are exactly the median-and-thinner profile that retention-minded allocators underweight. Subnet-age and root-claim-flow screen inputs not yet measured.
- **[Q6 — sizes R-K]** How is validator yield surfaced — mark-to-market NAV (includes unclaimed basket price swings) or realised claimed-TAO only? NAV-based surfacing makes the momentum/optics bias bite hard; realised-only mutes it. **Not chain-derivable** — gated on the PR/UI design.
- **[D1 — pool state DONE 2026-06-18]** Model inputs replaced with live SN21 pool state (§3.0) and re-run (§3.1); placeholders were within ~1.3%, so results stand. *Remainder:* root-dividend recycle rate and baseline root-prop sell still estimates.
- **[D2]** Decide whether to actively pursue root-validator weight or stay neutral — given §3.1 shows winning *more* builds a larger overhang spring.
- **[D3 — informed by §6]** Live depth confirms SN21 is in the "underweighted despite demand" band on the R-J screen (mid-pack, not a deep safe-bet). The deepen-liquidity question is therefore *live*, not hypothetical.

> **Not answerable from existing SN21 chain values** (flagged so they are not mistaken for open data gaps): **Q1** (does Taoflow count basket buys — proposal semantics), **Q2** (does any root-stake holder view AdTAO as a competitor — off-chain intent; on-chain we can only size *whose* stake is large, see §6), **Q3** (chosen root `WeightsRateLimit` — currently `u64::MAX`, unset by sudo), **Q4** (root-stake stickiness once neutrality is removed — forward behavioural), **Q6** (yield surfacing). These depend on the PR text or future governance, not present chain state.

---

## 5. Recommended monitoring metrics (sn21_monitor)

Once/if Root Reborn reaches testnet, add to the dashboard:

1. **Standing basket position in SN21 alpha**, per root validator (via `betaBasket_getValidatorBasket`) — the R-C overhang, broken out by counterparty so concentration is visible.
2. **Overhang ratio** = standing position / current alpha reserve, with floor-breach threshold line (the 6.90% figure recomputed on live reserves).
3. **Net root flow on SN21** = basket buys − root-prop sells, daily.
4. **Weight-share rank** among subnets (R-A relative position) and distance to the marginal productive-subnet cutoff (R-F).
5. **Validator concentration** of our buy-flow — flag if any single validator > N% of our basket support.

---

## 6. Live SN21 values (connector pull)

Pulled via the project's finney path (`subtensor.all_subnets()` + root metagraph), the same connectors that feed `market_sync.py` / `weights_scan.py`. TAO-denominated to strip TAO's own market move. The figures block below is **auto-generated** — refresh it with `python root_reborn_model.py --live --write-doc`. The interpretation that follows is maintained by hand.

<!-- BEGIN live-figures (auto-generated by root_reborn_model.py --write-doc — do not edit by hand) -->
*Source: live finney all_subnets() @ block 8,433,046 · generated 2026-06-18 09:42 UTC. Regenerate with `python root_reborn_model.py --live --write-doc`. Flow inputs (root-dividend recycle, weight share, baseline sell) are ESTIMATE/SCENARIO — not chain-readable.*

**Pool state (LIVE):**

| Metric | Value |
|--------|-------|
| alpha reserve `A0` | 1,987,200 |
| TAO reserve `T0` (`tao_in`) | 7,952 TAO |
| spot price `p0` | 0.0040015 TAO/alpha |
| dereg floor (assumption) | 0.00350 TAO/alpha (+14.3% headroom) |

**Liquidity & relative position (LIVE — R-J / Q5 / R-A / R-F):**

| Metric | Value |
|--------|-------|
| TAO-depth rank | 68 / 128 priced subnets (~53th pct, 1.05× median 7,576 TAO) |
| top-liquidity decile threshold | ≥ 33,909 TAO — SN21 NOT in top decile |
| price rank | 35 / 128 (~27th pct, median 0.005760) |
| floor proximity | spot **+14.3%** above 0.0035; 16 / 128 subnets below it |

**Root-stake concentration (LIVE — R-E / Q2):**

Root subnet (netuid 0): **64 neurons, ~5,470,913 TAO** total. top-1 18.5% · top-3 44.7% · **top-4 55.3%** · top-5 60.3% · **top-10 80.4%**.

**Cascade impact** — 30-day overhang at 1.0% weight share (~15.0 TAO/day → 112,458 alpha = 5.66% of reserve), sold back over a short window:

| Redeemed | x = sold/reserve | Price impact | Spot after | Breaches floor (0.0035)? |
|----------|------------------|--------------|------------|------------------|
| 10% | 0.57% | -1.12% | 0.00396 | no |
| 25% | 1.41% | -2.77% | 0.00389 | no |
| 50% | 2.83% | -5.43% | 0.00378 | no |
| 100% | 5.66% | -10.43% | 0.00358 | no (+2.4% above floor) |

**Floor-breach analysis (full one-shot cascade).** Overhang of **6.92% of reserve** breaches the floor if fully redeemed at once. Days of accumulation to reach that, by weight share:

| Weight share | alpha/day | Days to breach-capable overhang |
|--------------|-----------|----------------------------------|
| 0.5% | 1,874 | **73 days** |
| 1.0% | 3,749 | **37 days** |
| 2.0% | 7,497 | **18 days** |
| 5.0% | 18,743 | **7 days** |

<!-- END live-figures -->

**Interpretation (manual — reads the block above; exact figures drift block-to-block).**
- **R-J / Q5 / D3 — liquidity:** TAO-depth rank is mid-pack (~mid-50s percentile, ~1× the field median) and **~4× below the top-liquidity decile**. → we are the *underweighted-despite-demand* profile, not a deep safe-bet.
- **R-A — relative position:** price rank is bottom-third (~27th pct); SN21 alpha is cheaper than ~70%+ of the field. Below-median position, room for relative erosion.
- **R-F — floor proximity:** spot sits ~14–16% above the 0.0035 dereg-relevant floor, with ~15–17 of ~128 subnets below it. Not near-floor today, but not comfortably clear.
- **R-E / Q2 — concentration:** live *root-stake* top-4 ≈ **55%** (top-10 ≈ 80%), **not the ~91%** the register cites — that figure is a different/derived metric. "Court 4–5 entities" still holds (top-5 ≈ 60%). **Q2 remains off-chain** — chain shows *who is large*, not *who is hostile*.

*Caveat:* single-block snapshot; re-pull before citing. `network_root_div_tao_day` and SN21 baseline root-prop sell were not cleanly chain-readable in this RPC version and remain estimates.

## Changelog

- **v0.6 (2026-06-18)** — **Made §6 self-updating.** `root_reborn_model.py` now fetches the market context (liquidity rank, price rank, root-stake concentration) alongside pool state and can regenerate the §6 figures block in place via `--write-doc` (delimited by `<!-- BEGIN/END live-figures -->`). One command — `python root_reborn_model.py --live --write-doc` — refreshes every chain-derived figure; interpretive prose stays hand-maintained. Softened drift-prone exact figures in the exec summary and §6 interpretation to ranges so they survive block-to-block movement (§3 is now framed as the fixed reference run; §6 carries the live numbers).
- **v0.5 (2026-06-18)** — **Live SN21 values pulled via connectors** (finney `all_subnets()` + root metagraph, block 8,432,852). Added **§6** (live pool state, liquidity/price rank, root-stake concentration). **Resolved D1's pool-state half** — placeholders (2.0M reserve / 0.0040 spot) were within ~1.3% of live (1.975M / 0.0040520), so §3 results stand; re-ran §3.1 tables on live state. **Softened the headline:** at live spot (+15.8% above floor, vs 12.5% assumed) the 30-day/1%-share full cascade lands +3.8% *above* the 0.0035 floor — single-cascade breach needs ~41 days at 1% share (was 37), so "5–6 weeks then breach" is at the *edge* of, not inside, the breach band. **Partially resolved Q5/D3** (SN21 liquidity rank 69/128, ~median, ~4× below top decile → underweighted-despite-demand profile confirmed). **Tempered R-E** (live root-stake top-4 = 55%, not 91%). Flagged Q1/Q2/Q3/Q4/Q6 as *not* answerable from chain state. Flow inputs (root-dividend recycle, baseline root-prop sell) remain estimates — not cleanly chain-readable in this RPC version.
- **v0.4 (2026-06-17)** — Incorporated practitioner opinion on yield optics (treated as opinion, not fact). Added **R-K** (yield-optics / momentum bias, P2): displayed yield is mark-to-market on unclaimed basket alpha, so validators chasing displayed yield are pulled toward price-pumping SNs over steady builders — a second selection axis distinct from R-J, and the harder one for us because its only "mitigation" (manufacture price action) violates the integrity discipline. Added **coordinated-trigger variant to R-C** (public weight cut after a rise signals stakers to claim → transparency doubles as cascade-coordination channel). Added **Q6** (validator yield surfaced as NAV vs realised — gates R-K severity). Reinforced accountability-via-yield skepticism via claim-timing noise. Fixed a duplicated R-C line carried from v0.2. Register 10 → **11 risks**; severities hold.
- **v0.3 (2026-06-17)** — Incorporated founder (Const) 8-point case + verified ecosystem evidence. Added **mandate note** to exec summary: assessment optimises SN21-only; Const optimises network-aggregate; aggregate gains are distributional, so a network-good change can be SN21-neutral/negative. Softened **R-E** (validator-curated baskets already exist off-protocol — Mentat, Crucible; on-chain transparency is *better* governance than opaque status quo; concentration danger persists). Refined **R-C** (steadier-than-retail base but staker-layer redemption trigger → lower base vol / fatter tail; added SN76 flash-event precedent). Promoted **R-J** theoretical→**evidence-backed** (Mentat risk ladder screens out thin/young subnets; SN76 ~97% slippage). Recalibrated **R-I** (high founder conviction raises ship-probability, offsets convergent opposition; "25 lines" contradicted by §7; plan for "when, modified"). Added **Q5** (does SN21 clear existing allocator liquidity screens). Register unchanged at 10 risks; severities held, evidence base strengthened.
- **v0.2 (2026-06-17)** — Incorporated independent validator-archetype critique. Added **R-J** (adverse selection toward liquid/incumbent subnets, P2) and validator-archetype lens to exec summary. Sharpened **R-C** (engineered yield-herding trigger; conservation invariant limits literal principal theft). Sharpened **R-E** (biased-archetype self-correction is incomplete for starvation). Reframed **R-H** from personal manager-risk → neutrality-removal / buy-flow-pool shrinkage. Recalibrated **R-I** (convergent unprompted opposition lowers clean-merge probability). Added **Q4** (root-stake stickiness) and **D3** (liquidity-bias screen). Register now 10 risks.
- **v0.1 (2026-06-17)** — Initial register (9 risks, 4 tiers) and Model A/B. Inputs illustrative pending D1. Three open questions (Q1–Q3) gating R-D severity, R-B severity, and R-C trigger sharpness.
