# SN21 Daily Stream — Design in Plain English

**Status:** Proposed — under developer evaluation. Supersedes v0.2 (2026-07-20) and the cadence sections of the Forward-Prediction Plan (2026-06-12). Incorporates the Const call design (2026-07-07), the developer study (2026-07-18), the v435 collateral integration (2026-07-22), the transparency feeds (2026-07-22), and the thin-day weighting + eligibility taxonomy (2026-07-23).
**Version:** v0.6
**Owner:** Rob Warner
**Readers:** Khurram, Jayesh, Tensora, John Davy

---

## 1. The design in one paragraph

Every day, the changes made across our connected accounts go out to miners as one mixed basket. Miners' models predict the outcome of each change the same day, before any outcome exists. Predictions are locked on the day they are made. Outcomes are measured at 7, 14, and 28 days — plus a 7-day settling window so late-arriving conversions can land before we score. Because a different day's basket matures every day, fresh scores arrive every day. Weights update daily from a moving average through a published weight curve — steep, but with no winner-take-all cliff — and emissions follow the weights on Bittensor's own continuous clock. The model that actually runs live across the portfolio (the champion) changes only under a deliberate promotion rule, never on a single day's result. Every earning miner backs their slot with a holding bar that rises weekly over the first four weeks, escrowed on the chain's own collateral rail and enforced by our validator's scoring. New models are admitted the moment they pass the backtest gate. The weekly epoch is retired; the only fixed rhythm left is a four-weekly parameter review.

---

## 2. The daily clock

| Day | What happens |
|---|---|
| Day 0 | Changes happen on live accounts |
| Day 1 | Basket assembled and revealed to miners; predictions made and locked |
| Day 14 | 7-day outcome measured (7 days + 7-day settle) — final |
| Day 21 | 14-day outcome measured — final |
| Day 35 | 28-day outcome measured — final |
| Every day | Score the baskets maturing today; fold into each miner's moving average; update weights through the weight curve (§7); check the champion-promotion rule (§7) |
| Continuously | Emissions flow per Bittensor tempo (~every 72 minutes) from current weights — no payout events to schedule. Collateral floors fill and drain automatically inside the same flow (§8) |
| Any day | New models admitted the moment they pass the backtest gate |
| Every 4 weeks | Parameter review. The only fixed calendar rhythm. Floor amounts and curve/promotion numbers are restated here |

Cold start: the pipeline takes 35 days to fill completely. First 7-day scores arrive on day 15; the stream runs at full depth from day 36. This wait is paid once. During cold start no model can be promoted champion (the promotion rule's 14-scored-days minimum covers this by construction — §7).

---

## 3. Why the outcomes wait an extra week

Google conversions trail clicks — sometimes by days. If we measure a "28-day outcome" on day 28, conversions that report late change the number *after* we scored miners against it. That breaks "scored against reality."

The fix: every horizon gets a 7-day settling window before measurement. The number we score against never moves afterwards. Cost: all scores land a week later than they otherwise would. Cheap price for outcomes that are final.

**[D1] Settling window = 7 days.** Jayesh to confirm from conversion-lag data that 7 days catches the bulk of late conversions; adjust if the data says otherwise.

---

## 4. Why daily scoring works (the "matures once" objection)

The developer study (§3) objected: an episode's outcome matures once, so you cannot score it daily.

Correct — and the design never does. We never rescore the same change. Each day, a *different* day's basket finishes maturing at each horizon: today we score the basket from 14 days ago at its 7-day horizon, 21 days ago at 14 days, and 35 days ago at 28 days. Fresh scores every day, each from a batch scored exactly once.

The objection is fatal to daily scoring of weekly *cohorts*. It does not apply to a rolling stream. There are no cohorts.

---

## 5. What this replaces, and by what right

The weekly epoch — "fixed weekly epochs, non-negotiable" — is a rule we wrote and published. It is not a chain constraint; Bittensor pays emissions continuously from current weights, roughly every 72 minutes. We may change our own rule, but only in the open:

- The weekly epoch is **fully retired**, not hollowed out. There is no scoring epoch, no payday, no admission window. Reveal, scoring, weights, and emissions all run continuously; models are admitted on backtest pass.
- What miners keep in its place: a **four-weekly parameter review** on a published calendar, with all rule changes announced in advance and no changes between reviews. This carries forward the real protection the epoch gave them — predictable rules — without the fake rhythm.
- Published as a governance amendment with notice, effective from a stated date. Never a quiet edit. Retiring a commitment we called non-negotiable is a bigger amendment than bending it — and the more honest one. The miner-facing case: you asked for faster feedback; a vestigial epoch would only delay your admission and mislabel your payouts.
- The retrodictive public release retires with it. Daily forward baskets draw from the public training pool, which re-scopes the 90-day public-release floor. **[D2]** This is a deliberate change to a committed constant and is stated as such in the amendment.
- Epoch-anchored bookkeeping (cancel-epoch accounting, "no mid-epoch parameter change") re-anchors to the review calendar. **[GAP-2, Khurram]** covers the re-denomination.

The miner-facing case (full text in the companion announcement): daily reveal means daily feedback instead of a weekly wait, a tighter improvement loop, and a network whose best model is live across the whole portfolio at all times.

---

## 6. Scoring, in brief

Unchanged from the current v2 formula: 50% quantile accuracy, 20% calibration, 15% direction, 15% goal metric. Every prediction is judged against *that account's own goal* — which is why lead-gen and ecommerce accounts can share one basket (see §10).

**What enters the basket is governed by a published eligibility taxonomy [D14].** The existing qualifying filters (minimum spend, minimum history, change size) gain a change-type dimension: **defensive-hygiene changes are excluded** — changes whose intended effect is protection, not performance. The canonical case: click-fraud tools mutating IP blocklists many times a day. These are worse than noise: predicting a single IP block is trivially "no measurable change," so a basket full of them lets every model farm easy calibration points, compressing the score differences the champion race depends on. The line is drawn by **intended effect, not by automation** — automated bid/budget rules are real decisions with real outcomes and stay in; automated spam-defense mutations are out. Adoption events stay eligible: "account enabled click-fraud prevention" is one genuinely predictable episode even though the thousand daily mutations it generates are not. The taxonomy is published from day one and maintained at the four-weekly reviews as new tool patterns emerge.

Horizons blend at 7/14/28 days. Scores fold into a per-miner moving average that is **episode-weighted, not day-weighted [D13]**: each prediction contributes equally, and a "day" has no weight of its own. A 40-episode Saturday automatically counts 40/250ths of a typical Tuesday — thin days discount themselves in exact proportion to how thin they are, with no volume threshold, no calendar rule, and nothing to game at a boundary. This also covers holidays, outages, and the cold-start ramp for free, and no minimum-day floor is needed. (Weekend baskets are also *different* — automation-heavy — not just smaller. That is fine for fairness: every model scores on the same basket, so ranking stays apples-to-apples within any day, and episode weighting caps how much a small odd day can move anyone's average.) Weights follow the average, so one lucky or unlucky day moves little. The moving-average time constants are re-stated in days, not epochs, since the epoch is no longer the scoring unit. **[GAP-2, Khurram]** — proposed: a 10–14-day half-life on the weight-driving average (at ~250 episodes/day this is long enough that no single day matters and short enough that a genuinely better model surfaces in about two weeks, matching the 7-day promotion hold in §7).

Rewards follow the weight curve in §7 — steep, but never 100/0. A new model earns as its scores accumulate; the champion holds the top slot until beaten *under the promotion rule*, not on a raw crossover.

---

## 7. Weights, and who goes live — two different things

v0.2 said "winners-take-all, softened by the moving average." The softening was doing two jobs at once, and one of them badly. The moving average stops a single lucky day from mattering — but strict winners-take-all still flips 100% of the weight the instant a challenger's average crosses the champion's *by any amount*. The instability isn't noisy scores; it's the cliff at the crossover. And the champion is not just a payout slot — it is the model driving real accounts. We will not swap the production model on a statistical tie.

So the design separates them:

**Emission weights — steep but continuous [D7].** Weight follows the moving-average score through a published curve: the top model takes roughly 50–60%, second place ~20%, a decaying tail after that, and zero below a published score threshold. A crossover shifts weight gradually as the gap widens; there is nothing discontinuous to flip. Challengers earning on the way up is not a bug: it funds their collateral floors (§8) so that any model approaching contention is already bonded, and it keeps the contest worth entering. The trade-off, stated plainly to miners: the champion earns ~55%, not 100%. That is the price of a system safe enough to run daily — and it makes the top slot *more* reachable, not less rewarding.

**Champion promotion — deliberate, with hysteresis [D8].** The live model switches only when a challenger meets ALL of:
1. leads the moving average by at least a published margin (initial proposal: 5%),
2. has held that lead for 7 consecutive days,
3. has at least 14 scored days of history.

Miss any condition and the incumbent stays. Close races leave the incumbent in place — an incumbent that is merely tied is the safer production choice. Condition 3 also closes the cold-start window: no model can be promoted on thin early averages.

The earning set this produces is naturally small: one champion, a handful of live challengers above the threshold — in practice we expect **5–15 earning models**, with a hard ceiling of 20 as a safety valve. When the basket splits (§10), each basket gets its own curve and champion, so the ceiling is per-basket. Exact curve shape, threshold, and margin are set at the first four-weekly review and published from day one, like the D4 trigger.

**At cutover, the legacy tail goes to zero [D10].** Today's weight vector pays dust to ~165 UIDs, mostly squatters. From IM launch, weight flows only through the curve above. 150+ UIDs lose their trickle overnight; this is announced plainly, in advance, as part of the amendment — it is the anti-dilution move that makes the earning slots worth defending.

---

## 8. Skin in the game — collateral floors (v435) [D9]

Bittensor's collateral runtime (shipped in 437, live on finney under spec 440) adds miner registration collateral at the protocol level: locked alpha on the miner's own key, released only through earned incentive, surviving deregistration, blocking hotkey rotation, with a self-maintaining floor (`min_locked`). We use it natively as the *verification rail* rather than hand-rolling balance checks — but the compulsion is ours, not the chain's (see enforcement below).

**Full policy, numbers, and derivation: `SN21_Alpha_Lock_Policy_2026-07-31.md`.** Summary:

**The policy:**
- Every earning model backs its slot with a collateral floor that **rises weekly for four weeks** from **300 α at IM launch** to a target, restated as a flat α amount at each four-weekly review. (Flat α, not "weeks of rewards": under the §7 curve, per-miner earnings vary too much for a per-miner denomination.) Two schedules, chosen by the burn setting in force at launch:

  | When | Schedule A — **LIVE** (b = 0.451) | Schedule B — dormant (burn→0) |
  |---|---|---|
  | IM launch | 300 α | 300 α |
  | +1 week | 475 α | 625 α |
  | +2 weeks | 650 α | 950 α |
  | +3 weeks | 825 α | 1,275 α |
  | +4 weeks | **1,000 α** | 1,600 α |

  **Burn is held at 0.451 (2026-07-31) — the staged cut is cancelled, not deferred.** Schedule A is the one we run; B exists only if that decision is ever reopened.

- **The weekly step, not the target, is the designed quantity.** Each increment must be fillable inside its own week out of the marginal 2%-weight slot's own earnings (227 α/week at b=0.451, 413 α/week at b=0) — so the bar never forces an on-market buy. The champion clears any step in under a day. **Slots below 2% weight are exempt** until they cross it.
- **Sized against emission, not intuition:** each schedule withholds ~15% of miner emission over the four weeks — deliberately the same number as the ≤15%/week sell cap, so the two rules say one thing. After week 4 a static floor absorbs nothing further; sustained restraint comes from the cap and forfeit risk.
- **Burn coupling:** if the decision is ever reopened, set burn first and run Schedule B from day one. Cutting burn mid-ramp doubles every miner's fill rate and the remaining steps stop binding.
- **No upfront buy-in, no entry gate.** The floor fills by *capture*: when a model starts earning, its incentive is escrowed into the lock until the floor is met, then normal payouts resume. A model that never earns never owes anything. A miner who prefers to start taking home rewards immediately may front the collateral voluntarily (`add_collateral`) — their choice.
- **Existing scoring miners are grandfathered onto the capture path** — no cash call on people already working for us.
- Because the §7 curve pays challengers partial weight on the way up, every model approaching championship contention has already served its escrow. The capture phase is a probation period that triggers itself, at exactly the moment a new big earner would otherwise be an unvetted dump risk.
- **Enforcement is ours, verification is the chain's [F7].** The chain will *not* force a miner to hold: the reward-capturing `min_locked` floor is **miner opt-in** (`coldkey_owns_hotkey`), and the owner knob `CollateralLockShare` only locks part of the ~0.1 TAO registration deposit (SN21 today: p=0, k=1.0). Compulsion therefore comes from our validator's weight scoring — below the current step, weight goes to zero — while the chain supplies the tamper-proof hold signal we read, with coldkey stake/float monitoring as the fallback for miners who have not opted in.
- **Enforcement teeth:** a miner zero-weighted for breaking the operating agreement (e.g. the ≤15%/week sell cap) stops earning — and with no earnings there is no drain, so their collateral freezes permanently. Forfeiting the floor plus losing a slot that pays real money is the penalty; deterrence comes from that ratio, not from the floor's size.
- **Stated plainly to miners:** a dethroned champion's floor also stays locked until they earn again. Locked capital is an incentive to keep competing rather than rage-quit; we say this out loud rather than let someone discover it.
- **Honest limit:** this is a deterrent, not a physical lock — no unbonding, no clawback. A miner who decides the dump is worth more than the slot can still dump.
- **Safety note (verified from source):** miner collateral is a separate mechanism from conviction locks. Miners locking our alpha as collateral build zero conviction toward subnet ownership — the takeover vector does not apply.

Owner-set chain parameters: `CollateralLockShare` p ≈ 0.75–0.9 — miner-friendly, since for a scored miner the locked share of the ~0.1 TAO registration cost pays back through work in days, while squatters' share freezes forever; `CollateralDrainRatio` k ≈ 0.5. These deter squatting and identity rotation; they do **not** implement the holding bar. Modeled in the emission lab (S8).

**Price expectation, stated before we act:** the ramp locks ~13,000 α (Schedule B, ~10 slots) ≈ 0.6% of the AMM alpha side, while burn→0 releases 1,331 α/day = ~37,000 α of new sellable supply over the same four weeks — roughly 2.9× what the ramp withholds — with no offsetting chain-buy, since the v440 gate keeps that channel shut even at burn=0 [F5]. The pair is supply-positive and therefore mildly price-negative. It is justified as funding real miners and buying enforceable retention, not as a price move.

---

## 9. The one blocking fact: volume

The whole design assumes enough qualifying changes per day to make daily scores meaningful.

- Rob's current expectation (2026-07-22): **~250 qualifying changes per day and growing**, lighter at weekends. At 250/day, a daily score averages ~250 predictions — a stable estimate, not a coin flip — and comfortably supports the §7 curve and the 10–14-day averages.
- The developer study's verified numbers: 4,312 registered accounts; ~65 qualifying episodes in week 22; 208 outcomes in the whole corpus.

These cannot both describe the same system. The likely gap is the pipeline: raw changes are plentiful, but registration coverage and the qualifying filters (minimum spend, minimum history, change size) admit a trickle. Nobody has measured the true number.

**[GAP-1, Jayesh — BLOCKING]** One ClickHouse query: the daily count of qualifying changes across all connected accounts, by day of week, under the published filters — **reported both raw and post-taxonomy [D14], with excluded change types broken out** (if the ~250/day expectation includes blocklist churn, effective qualifying volume may be materially lower, and the volume gate, earning-set size, and episode-weighted averages all key off the filtered number). Also state how many of the ~12,000 live accounts are actually registered in the pipeline, and what closing that gap yields.

**Decision rule, agreed in advance:**
- Several hundred per day (the expectation) → build the daily design as written.
- A few dozen per day → daily reveal still ships (it costs nothing), but weight updates stay weekly until volume clears a published threshold, **and the earning set shrinks to what the signal can rank** (5–8 models; you can only reliably distinguish as many models as the volume supports). **[D3]** — threshold set from GAP-1's answer and published to miners.

No other question blocks the design. This one does.

---

## 10. One contest or two? (lead-gen vs ecommerce)

Lead-gen and ecommerce accounts chase different goals. Per-episode scoring already absorbs this — each prediction is scored against its own account's goal — so they share one basket today without breaking the maths.

The risk: the §7 curve crowns one champion. With a lead-gen-heavy corpus, the champion will be a lead-gen model, and it will also be the model predicting on ecommerce accounts, where it may be mediocre.

The fix costs nothing now: the basket is the seam. Day one, one basket. Later, two baskets, two champions — same subnet, same rules, no migration. Each basket carries its own weight curve, promotion rule, and earning ceiling (§7).

**[D4] Published split trigger:** the basket splits when ecommerce reaches a stated share of daily episodes, **or** when the champion's error on ecommerce episodes runs materially worse than on lead-gen for a stated number of consecutive weeks. Jayesh already has the scoring data to track the second condition. Exact numbers set at first review; the trigger itself is published from day one, so specialists can build ahead of it.

---

## 11. How the developer study's questions are settled

| Study item | Answer |
|---|---|
| Q1 — daily release or daily scoring? | Both, as a rolling stream. His A/B fork existed because the Const design was never written down; this document is that design. |
| Q2 — cadence only, or full forward-prediction switch? | Full switch. Daily release of matured episodes hands out the answer key; the two cannot be separated. All Forward-Prediction Plan machinery (eligible_at at classification, signed hash-chained outcome feed, censoring, HOPE-managed exclusion, cutoff audit) carries forward unchanged. |
| Q3 — is the 2026-06-12 plan current? | No. This document supersedes its cadence sections. Everything not amended here stands. |
| Q4 — Tensora | Their scope grows: per-batch commit-reveal deadlines, daily feed archival and hash verification, escrow, attestation, **and the generic metrics-publication rail (§13, D11)**. Scope and timeline to be agreed before build. **[GAP-3, Rob]** |
| Q5 — dependency order | Payload v2 cutover (per-episode on-chain submission) is on the critical path and lands first, with coordinated miner notice. Per-cell consensus is an independent track. |
| Q6 — 90-day release floor | Confirmed re-scoped; see §5, [D2]. |
| §3.3 — "matures once" | Answered; see §4. |
| §3.4 — EMA constants are epoch-relative | Agreed; re-denominated in days. [GAP-2]. |
| Appendix B.4–B.6 — thin corpus | Agreed this is the real constraint; handled by the volume gate. [GAP-1], [D3]. |

**Out of scope for this document:** the Docker-runtime paradigm (miners submit containers, subnet executes them, backtest gate, uptime guarantee). It is the destination architecture from the Const call but a separate, larger build. **[D5]** — decide launch scope vs next phase before anyone sizes it. Nothing in this design blocks it; the daily stream is its substrate either way.

---

## 12. What gets built (pointer, not a plan)

The developer study §4 already lists the concrete work for the daily-release layer, and Forward-Prediction Plan §15 specifies it. Additions from this document: the 7-day settling window on all horizons, the 28-day horizon itself (currently not computed), daily scoring runs against maturing baskets, day-denominated moving averages, daily weight updates behind the [D3] volume gate, the [D4] split-trigger instrumentation, the [D7] weight curve and [D8] promotion-rule instrumentation (margin/hold tracking, promotion log), the [D9] collateral integration (floor state read from chain once v435 activates; soft scoring before), and the [D11] publication rail + daily accuracy aggregation (§13). Khurram turns this into the implementation plan once GAP-1 lands.

---

## 13. Published proof — the transparency feeds [D11, D12]

The subnet's credibility strategy is that claims are checkable, not spoken. Two feeds make that permanent, on two different clocks, sharing one rail.

**The rail (built with the IM — part of Tensora's scope).** A generic, attested metrics-publication path: a public metrics file, its hash anchored on-chain (commitment extrinsic), signed and archived under the same attestation regime as the outcome feed. Specced generic — any metrics file, not just accuracy — so later feeds land on it without rework.

**Feed 1 — live prediction accuracy, full cohort [D11]. In the IM build.** The daily stream already computes locked predictions against final (settled) outcomes; this feed is an aggregation over that same pipeline, published daily from stream maturity (first partial numbers ~day 15, full depth from day 36 — the stream's own clock, no extra scheduling). Audience: miners verifying the scoring is real; the network verifying SN21 does real work. Together with the legacy-tail zeroing [D10], launch says one thing twice: the fake stopped earning and the real became measurable.

**Feed 2 — account performance under AdTAO delivery [D12]. Separate track, methodology first.** For the subset of accounts where we are responsible for delivering results: published performance change, **anonymised aggregates only — never individual client data** — as before/after comparisons, **seasonally adjusted**, above a published minimum-aggregation floor (no bucket small enough to identify a client). Requires client consent handling and legal review; the attribution methodology (baseline, counterfactual, measurement windows, survivorship handling) is red-teamed and **published at a four-weekly review before any numbers appear**. Cadence ~monthly on the D11 rail. This track has its own owner and its own calendar: nothing about it gates the IM launch, and nothing about its client-side dependencies may slip the IM.

Why the split: feed 1 is a near-free by-product of the IM pipeline and strengthens the launch; feed 2 is a permanent, verifiable public claim about client outcomes — an asset if the methodology is defensible, a liability if it is sloppy. The rail is shared; the clocks are not.

---

## Decision register

| ID | Decision | Status |
|---|---|---|
| D1 | 7-day settling window on all horizons; 28d matures day 35 | Proposed — confirm against conversion-lag data |
| D2 | Retire retrodictive public release; re-scope 90-day floor; publish as governance amendment | Proposed |
| D3 | Daily weight updates gated on a published minimum daily episode volume; earning-set size scales with volume | Proposed — threshold from GAP-1 |
| D4 | One basket now; published lead-gen/ecommerce split trigger | Proposed — numbers at first review |
| D5 | Docker-runtime paradigm: launch scope or next phase | Open |
| D6 | Weekly epoch fully retired: continuous emissions, admission on backtest pass, four-weekly review calendar replaces it | Proposed |
| D7 | Weight curve replaces winner-take-all: top model ~50–60%, ~20% second, decaying tail, zero below published threshold; expected earning set 5–15, hard ceiling 20 per basket | Proposed — curve numbers at first review |
| D8 | Champion promotion is separate from weights: ≥5% moving-average lead, held 7 consecutive days, ≥14 scored days; incumbent stays otherwise | Proposed — margin confirmed at first review |
| D9 | Collateral floors via native capture: **four weekly steps 300 → 475 → 650 → 825 → 1,000 α** (Schedule A; burn held at 0.451 per 2026-07-31 — Schedule B dormant), flat α restated at reviews; step sized so the marginal 2%-weight slot fills it from own earnings inside the week; <2% weight exempt; ~15% of miner emission withheld over the ramp; no upfront gate; existing scorers grandfathered; **enforcement is our validator weight-scoring, chain `min_locked` is the verification rail only [F7]**; burn cut sequenced first or simultaneously, never after; owner params p≈0.75–0.9, k≈0.5. Full derivation: `SN21_Alpha_Lock_Policy_2026-07-31.md` | Proposed — supersedes the v0.3 single-step floor |
| D10 | Legacy weight tail zeroed at IM cutover (~165 dust UIDs → 0); announced in advance in the amendment | Proposed |
| D11 | Public prediction-accuracy feed (full cohort): daily aggregation over the stream's scored outcomes, metrics file public, hash anchored on-chain; rail specced generic; ships with the IM, publishing from stream maturity | Proposed |
| D12 | Account-performance publication (AdTAO-delivered accounts): separate track, methodology-first; anonymised aggregates only — never individual client data; before/after, seasonally adjusted, published aggregation floor; consent + legal review; methodology published at a review before any numbers; ~monthly on the D11 rail | Proposed |
| D13 | Moving average is episode-weighted, not day-weighted: thin days self-discount proportionally; no volume threshold, no calendar rule, no minimum-day floor | Proposed |
| D14 | Published change-type eligibility taxonomy: defensive-hygiene changes excluded (IP blocklist add/remove named); line drawn by intended effect, not automation; adoption events stay eligible; maintained at four-weekly reviews | Proposed |

## Gap register

| ID | Owner | Item | Blocking? |
|---|---|---|---|
| GAP-1 | Jayesh | True daily qualifying-change volume + registration coverage of the ~12K live accounts (Rob expects ~250/day; verify) | **Yes** |
| GAP-2 | Khurram | Day-denominated moving-average and tier constants (proposed: 10–14-day half-life on the weight-driving average) | No |
| GAP-3 | Rob | Tensora scope and timeline agreement (now includes the D11 publication rail) | Before build |
| GAP-4 | Rob | D12 owner, client-consent path, and legal review for the account-performance methodology | Before D12 numbers publish (does NOT gate the IM) |
| GAP-5 | Khurram | Weight-zeroing path in the live validator scoring code, reading `min_locked` + coldkey float — the holding bar is unenforceable without it [D9] | **Yes** — gates the ramp and the burn cut |

## Changelog

| Version | Date | Changes |
|---|---|---|
| v0.1 | 2026-07-20 | First draft, from the Const call (07-07), the developer study (07-18), and Rob's settling-window and basket-split decisions (07-20) |
| v0.2 | 2026-07-20 | Weekly epoch fully retired [D6] after Rob's challenge: continuous emissions per Bittensor tempo, admission on backtest pass, four-weekly review calendar as the only fixed rhythm |
| v0.3 | 2026-07-22 | Winner-take-all cliff removed: published weight curve [D7] + deliberate champion-promotion rule with hysteresis [D8], after Rob's single-day-winner challenge. v435 collateral floors integrated natively [D9]: capture-path escrow, no entry gate, existing scorers grandfathered, timetable-honest signaling. Legacy weight tail zeroed at cutover [D10]. Volume expectation updated to ~250/day (GAP-1 still to verify). GAP-2 constants proposed (10–14-day half-life) |
| v0.4 | 2026-07-22 | Transparency feeds added (§13): daily full-cohort accuracy feed on an on-chain-anchored rail, in the IM build [D11]; account-performance publication as a separate methodology-first track — anonymised aggregates only, before/after, seasonally adjusted [D12]. Tensora scope (Q4/GAP-3) extended with the rail; GAP-4 added for D12 consent/legal |
| v0.6 | 2026-07-31 | §8 rewritten [D9]: single 300→600 α step replaced by a four-week weekly ramp with burn-linked Schedule A/B targets (1,000 / 1,600 α), step-fillability as the sizing invariant, 2%-weight exemption, and ~15%-of-emission withholding matched to the sell cap. Enforcement re-based on validator weight-scoring after [F7] — the chain `min_locked` floor is miner opt-in, not owner-imposable, so the "chain enforcement on v435 activation" timetable language is retired (collateral runtime is already live under spec 440). Price expectation stated explicitly: the burn→0 + lock pair is supply-positive. Standalone: `SN21_Alpha_Lock_Policy_2026-07-31.md` |
| v0.5 | 2026-07-23 | Thin-day handling: moving average made episode-weighted [D13] — Rob's 50%-of-average deweighting instinct implemented as a continuous rule with no cliff, after the weekend-volume question. Change-type eligibility taxonomy [D14]: defensive hygiene (IP blocklist churn) excluded as free-points noise that compresses model discrimination; adoption events retained. GAP-1 restated to report raw vs post-taxonomy volume |

In AdTAO, we TRUST.
