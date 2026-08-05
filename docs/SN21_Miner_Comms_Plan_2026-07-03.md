# SN21 — Miner Communications Plan for the Burn Reduction & August 3 Mechanism Relaunch

**Date:** 3 July 2026 (rev. 1, same day: incorporates the 3 August incentive-mechanism restructure) · **Companion to:** SN21_Miner_Burn_Recommendation_2026-07-02.md · **Status:** Pre-execution — comms must land before the week-1 cut

**Hard deadline created by our own policy:** the operating agreement promises ~4 weeks' notice for any scoring-policy change. The mechanism restructure lands 3 August; counting back, disclosure must happen in the week-1 briefings (~6 July). The restructure is therefore not optional content for those briefings — it is contractually forced by the commitment that makes the rest of this plan credible.

---

## 0. The problem this plan solves

We are about to (a) triple miners' gross rewards, and (b) attach a retention condition to the new portion. To a skeptical miner, (b) pattern-matches to every exit-scam in crypto: *"the owner wants me to hold his token while he benefits from the price."* If we message this wrong, we get the worst of both worlds — miners dump defensively before the policy starts, and the story "SN21 is squeezing miners" spreads. If we message it right, we get a curated set of professional operators who see this as the best-paying, most transparent deal on Bittensor.

**Governing principle: skeptics don't believe words, they believe incentives and arithmetic.** Every claim we make must be (1) verifiable on-chain by the miner themselves, (2) framed as our incentive being the *same token* as theirs, and (3) small enough to be checked within a week. We never ask for trust twice: each weekly step creates a checkable prediction, and each fulfilled prediction buys the next step.

---

## 1. Audience and starting position

- **Curated set (vetted operators + our house miners).** Professional, numerate, will re-derive our math. Have seen subnets rug miners via weight changes. Default assumption: *the owner is optimizing for the owner.*
- **Incumbent miners not yet in the curated set.** Risk group: abrupt exclusion = alpha dumping + public drama. Need an invitation path, not a cliff.
- **The wider Bittensor public / OTF.** Not a direct audience, but everything we publish will be read through the "is this a Ponzi mechanic?" lens (§7.1 of the recommendation). Nothing we say to miners can contain buy-in, entry-stake, or lock language.

Assume every private document leaks. Write everything as if Const will read it.

---

## 2. The core narrative (the honest story, one paragraph)

This is **one relaunch, told once** — new economics *and* a new contest, presented as a single package miners can evaluate whole. Skeptics tolerate one big package; they read serial surprises as salami-slicing. Announcing the burn cut in July and then "one more thing" in August would burn the trust the first announcement bought.

> SN21 is relaunching, in two connected moves. **First, the economics.** The network changed its rules on 24 June: under the new emission mechanism, the 74% of miner rewards SN21 burns is **pure waste** — the protocol destroys it (nobody receives it, including us) *and* punishes the subnet's emission share by the same proportion. So we're stopping: over the next ~4 weeks we're cutting the burn from 74% to 20%, and to 0% at the relaunch. That roughly **triples what miners earn**. **Second, the work.** On 3 August the incentive-mechanism contest is restructured — a new, published mechanism defining what SN21 miners compete on and how they're scored, with the full spec in your briefing pack today so you have a month to build for it. Because we want the tripling to make SN21 miners wealthy rather than just funding a weekly dump, the *new* portion of rewards comes with one condition: keep at least 85% of it staked while you mine here. Your existing income is untouched, your stake stays liquid (no lock, no unbonding), and you can exit entirely whenever you want. We benefit the exact same way you do — through the token we're both paid in — and every claim in this paragraph is checkable on-chain.

Everything else in the comms is elaboration, proof, or objection-handling for this paragraph.

The bundling also fixes a soft spot in the original plan: "curated set + our house miners" under owner-set scoring can read as an insiders' club. "Curated set competing under a new published mechanism" reads as professionalization — the vetting selects who may enter the contest; the mechanism decides who wins it.

---

## 3. The WIIFM arithmetic (lead with this — it survives any bullshit test)

Per 100 α of miner emission, per week, illustrative at the 20% burn target:

| | Today (74% burn) | Under the policy (20% burn) |
|---|---|---|
| You receive | 26 α | 80 α |
| Destroyed by protocol | 74 α | 20 α |
| Freely sellable, no conditions | 26 α (your existing flow — **unchanged**) | 26 α + 15% of the freed 54 α ≈ **34 α** |
| Retained as your staked alpha | 0 | ≈ 46 α/week, compounding |

Three sentences of framing that must accompany the table:

1. **Nothing is taken away; everything is added.** The retention rule applies only to the *newly freed* rewards. Your current sellable income does not shrink by one alpha — it grows ~30%.
2. **The retained alpha is yours, liquid, in your coldkey.** Plain stake — no lock, no unbonding period, no smart-contract custody. The only thing at stake is future scoring: sell more than 15% of the freed rewards in a week and your weight goes to zero. Exit is always allowed; exit-and-keep-mining is the only thing that isn't.
3. **Worst modeled case, you're still far ahead.** Even in our stress scenario (mass exit at day 90, price −11% vs holding), a miner under this policy holds ~3× the value of a miner under today's burn. The downside of the deal is "you got a big raise and the token dipped." The downside of today is "74% of your work is incinerated."

Do **not** lead with price projections. Publish the mechanism (emission share is proportional to 1 − burn; excess inflow becomes protocol buys of alpha), state that our internal simulations are positive across scenarios, and offer the mechanics for them to verify. Specific numbers like "+65%" in public read as pumping, create liability when markets do market things, and hand OTF a "price-promising subnet" narrative. The tripling of *rewards* is a protocol fact; the price path is a model.

---

## 4. Objection map — the seven questions and the honest answers

Every briefing and FAQ must handle these head-on, in the miner's voice. Evasion on any one of them poisons the rest.

**Q1. "Why should I believe the burned alpha helps nobody? Surely you were keeping it."**
A: It's verifiable from the deployed subtensor source and on-chain flows: burned miner emission is destroyed by the protocol; the owner allocation is a separate, protocol-fixed 1,296 α/day that does not change with the burn. We were not receiving your burned rewards, and cutting the burn pays us zero additional tokens. Give the exact storage keys / extrinsics so a technical miner can check in an afternoon. **This is the single highest-leverage proof in the whole plan** — it converts "the owner is taking from miners" into "the owner was wasting and has stopped."

**Q2. "So what do *you* get out of this?" (never dodge this one)**
A: Full candor: the cut raises SN21's emission share ~3.8×, TAO flows into our pool instead of competitors', and if the mechanics work, the alpha price rises — which benefits us through the same token you're paid in. We are not neutral; we are *aligned*. The one thing we don't get is any of your rewards. An owner who benefits only via the token price is an owner with a permanent incentive not to wreck the token.

**Q3. "The retention rule is you locking up my money to pump your bag."**
A: Three honest parts. (1) Yes, retention exists so the raise lifts the token instead of dumping it — and *you* are the largest beneficiary of that, because you're now the token's largest recipient. (2) It is not a lock: the alpha sits as plain stake in your coldkey, withdrawable in one transaction. The cost of selling is losing your slot, not losing your money. (3) We hold ourselves to a stricter standard: owner alpha is locked on-chain — verifiably harder to sell than yours. (State this plainly; do not explain the conviction-defense rationale — see redlines.)

**Q4. "You'll change the rules once I've accumulated."**
A: The policy is published with a numeric schedule (burn steps, retention threshold, measurement window) before the first cut. Every element lands on-chain weekly where it can be checked: the burn in our published weights, retention compliance from coldkey flows. Two standing commitments, in writing in the operating agreement: **retention will never be tightened retroactively or during a drawdown**, and any policy change gets 4 weeks' notice. And we can point to the notice policy already operating: the biggest rule change on the calendar — the 3 August mechanism restructure — is in your briefing pack today, exactly the 4 weeks ahead the agreement promises. That is not a coincidence; it's the policy working on its first test.

**Q5. "Is this the 'stake-to-mine' Ponzi pattern OTF kills subnets for?"**
A: No, and the difference is precise: you buy nothing, deposit nothing, and lock nothing to mine here. There is no entry stake and no requirement to ever purchase alpha. The only condition is on *how fast you sell rewards you were given* — the same shape as equity vesting at every serious company, not pay-to-play. (Having this distinction crisp in writing also protects *us* if the question is raised publicly.)

**Q6. "Why now? What's the catch / what do you know that I don't?"**
A: The network changed (Root Reborn, live 24 June) and a merged follow-up (PR #2800) makes burn the *only* lever any subnet controls — 81 subnets face the same incentive to cut, and the payoff goes to whoever moves first with a miner base that doesn't dump. We're moving now to be first, and we need committed operators to make it stick. This is the true answer, it's flattering to them (we need you), and it creates useful urgency without hype.

**Q7. "What if I don't make it under the new mechanism? I'll have a month of retained alpha and then you zero me."**
A: This is the sharpest rational fear in the whole package, and the answer must be in the operating agreement, not just spoken. Three parts. (1) **You'll know before you commit:** the full mechanism spec is in the briefing pack, a month before it goes live — you can assess your own competitiveness before you accumulate anything under the retention rule. (2) **Displacement is not a rug:** a miner who becomes uncompetitive under the new mechanism and exits keeps everything — the retained alpha is theirs, plain stake, one transaction to withdraw. The retention rule stops paying *and* selling *and* mining; it never confiscates. (3) **The exit ramp is structured, not a cliff:** a miner scoring below viability after 3 August gets a wind-down window (recommend 2 weeks of tapered weight) rather than same-epoch zeroing, so departures are staggered and orderly — which also protects the miners who stay (see §6a).

---

## 5. Redlines — what we do NOT communicate (and why)

1. **The conviction-takeover mechanism and our lock defense (§7.3).** Publishing it advertises the attack and the threshold. If asked why owner alpha is locked: "long-term commitment, verifiable on-chain" — true and sufficient.
2. **No "stake-to-mine," entry-stake, buy-in, or lock language anywhere**, including private drafts. The public entry gate is withdrawn; nothing may resurrect its vocabulary.
3. **No public price targets or projection tables.** Mechanism yes, simulations-are-positive yes, "+27%/+65%" no. (In 1:1 conversations with vetted operators under the agreement, sharing scenario ranges *with the ceteris-paribus caveat* is acceptable — they'll model it themselves anyway.)
4. **No "we control 100% of the weights" framing.** Factual but reads as "we can rug you." Say: "our validator sets scoring policy, and every step of it is published and on-chain."
5. **Never frame retention as float-reduction or price-support.** Frame it as what it also truly is: making the raise durable for the people receiving it. Same fact, miner-centered telling.
6. **The investor recommendation doc does not circulate.** This comms plan and the miner-facing materials are written to survive a leak; that doc was not.
7. **The mechanism spec is public; the burn schedule is not.** These travel on different calendars deliberately (see §6a). The 3 August date and the full mechanism spec are announced openly — miners need lead time to build, and an open spec is our best professionalization signal. The burn steps continue to be reported only *after* each lands. Never publish a combined roadmap that pins burn levels to calendar dates.

---

## 6. Anti-dump design in the communications themselves

The user constraint: no unnecessary alpha selling. Comms choices that protect it:

- **Invitation before exclusion.** Incumbent miners outside the curated set get a private invitation to sign the operating agreement *before* any weight consequences. An abruptly zeroed miner is a guaranteed seller and a loud one. Sequence: invite → 2-week window → only then re-weight. Exits we do force should land in different weeks, not as one event.
- **Retention is the norm from message one.** The very first framing a miner sees of the freed rewards is "your growing staked position," never "your new payout." Money mentally filed as *position* doesn't get sold on day one; money filed as *income* does.
- **No cliff dates in public.** The public sees each burn step *after* it lands ("burn is now X, as scheduled"), not a countdown. Private schedule for signed miners only. Countdowns invite pre-positioning and coordinated sell-the-news.
- **Never tighten during a drawdown — say it out loud.** Codifying §4's caveat into the public policy removes the "they'll trap us when it drops" fear that itself causes pre-emptive selling.
- **Weekly proof beats launch hype.** One low-key factual update per week (burn level, emission share, compliance rate) builds the "these people do exactly what they say" reputation that makes miners comfortable *holding*. A single big splashy announcement does the opposite: attracts tourists, sets expectations, invites dumps on any wobble.

### 6a. The August 3 transition — the concentrated dump risk and its management

A mechanism restructure redistributes scores: some miners will lose under the new contest. A miner zeroed on 3 August holds ~4 weeks of accumulated retained alpha and zero reason to keep it — left unmanaged, that sell pressure clusters on one *public* date, at the most price-sensitive point of the execution. Four provisions, all of which must be in the operating agreement and the week-1 briefing:

1. **Vet for the new mechanism, not the old one.** Curated-set admission criteria are written against competitiveness under the 3 August mechanism. Do not invite anyone in July who will be displaced in August — invite-then-zero in 3 weeks is worse than never inviting, and it manufactures exactly the seller we're trying not to create.
2. **Structured exit ramp instead of a cliff.** Miners scoring below viability after 3 August get a ~2-week tapered wind-down, not same-epoch zeroing. Departures land staggered across weeks, never as one event. During the taper the retention rule no longer binds them (they're exiting — pretending otherwise just delays the same sale), but the taper spreads it.
3. **Retention-measurement continuity across the switch.** The 15%/week allowance and the trailing-week window carry over the mechanism change unbroken — a miner's compliance history and accumulated position are unaffected by the restructure. State this explicitly; silence here reads as a reset trap.
4. **Baseline reset, published in advance.** "Freed rewards" is defined relative to the pre-cut burn; after 3 August, per-miner reward flows change shape under the new mechanism. Publish before launch exactly how the freed-reward baseline is computed post-restructure, so no miner can be surprised by a compliance calculation they couldn't reproduce themselves.

**Calendar decoupling (restates redline 7):** the mechanism launch is necessarily public and dated; the burn steps stay post-hoc. The public story on 3 August is "new contest, zero burn" — a result, not a countdown. Expect the open mechanism spec to draw new-miner attention from mid-July; the application funnel must exist by then (moved up from week 5 — see §7).

---

## 7. Execution: comms steps mapped to the burn schedule and the 3 August launch

**Sequencing decision (recommended):** complete the cut to ≤20% *before* 3 August, and reserve the final step to 0% as the launch-day signal. Rationale: the weekly-proof cadence stays intact (each burn step's emission-share effect is attributed cleanly, unpolluted by the mechanism change), the new contest launches into an already-improved economy, and "zero burn" becomes the mechanism launch's headline — one strong signal on the one unavoidably public date, earned by three prior weeks of miner compliance. The alternative (landing ≤20% *on* launch day) moves two variables at once, makes week-1 compliance under the new mechanism noisy, and wastes the 0% step's signaling value.

| Week (dates) | Burn / mechanism action | Comms action |
|---|---|---|
| **0 (now, 3–5 Jul)** | Owner alpha lock | **Prepare, privately:** (a) miner one-pager: core relaunch narrative + WIIFM table + FAQ (the §4 objection map, verbatim Q&A form); (b) operating agreement with the standing commitments (no retroactive tightening, 4-week change notice) **plus the §6a transition provisions** (exit ramp, measurement continuity, baseline definition); (c) the **full 3 August mechanism spec**, finalized enough to brief — if the spec isn't ready to hand to miners by ~6 July, the launch date or the notice commitment must move, and that is a decision to make now, not in week 3; (d) "verify it yourself" appendix — storage keys, extrinsics, and a script/dashboard link so every claim is checkable; (e) internal Q&A red-team: have someone play the angriest miner *and* the miner who expects to lose under the new mechanism, revise until nothing lands. |
| **1 (6–12 Jul)** | Brief curated set; cut 74%→~64% | **1:1 briefings, not a broadcast — the whole package at once:** burn schedule, retention policy, and the 3 August mechanism spec together (this satisfies the 4-week notice; disclosure after this week breaks it). House miners first — signed before external conversations, making "operators are joining" true from day one. Each operator gets the one-pager + agreement + a live conversation where Q1–Q7 are raised *by us* before they ask. Invitations to incumbent miners open the same week, vetted against the *new* mechanism (§6a.1). First cut lands → same-day note to signed miners: "burn is 64%, emission share moved as predicted — here's the chain data." **First checkable promise kept.** |
| **2–4 (13 Jul–2 Aug)** | Staged cuts to ≤20% by ~27 Jul; retention scoring live from week 2 | Weekly factual update to the miner set: burn level, emission share vs prediction, TAO inflow, aggregate compliance (never name-and-shame; a private warning precedes any zeroing). First retention week done → highlight aggregate retained position growing: "the set now holds X α." **Mid-July:** mechanism spec + application funnel go public (§6a) — recruiting-oriented, mechanism-honest, zero price talk, no burn-schedule dates. Signed miners build and test against the new mechanism; run at least one scoring dry-run before launch so 3 August is a switch, not a surprise. |
| **5 (3 Aug)** | **Mechanism launch + final step to 0%** | The one public, dated event — and it announces *results*: "SN21 relaunches today: new contest live (spec published since mid-July), miner burn now **zero**." Frame the 0% step as earned by the miner set: "compliance held ≥85% for three straight weeks, so we're going all the way." Same-day note to miners confirms measurement continuity (§6a.3–4): same retention window, same allowance, published baseline. |
| **6–7 (Aug)** | Post-launch transition | Exit ramp in effect for miners below viability (§6a.2) — tapered, staggered, no single-epoch zeroings. Weekly updates now also report contest health (participation, score distribution) alongside burn/compliance. Watch for the displaced-miner dump signature in per-coldkey flows; if departures cluster, slow the taper — never accelerate it. |
| **Ongoing** | — | Weekly cadence continues. Public posture stays minimal and factual: results, not plans — "burn is zero, take-home is up ~4×, here's the mechanism and how to apply." |

---

## 8. What "success" looks like (check weekly)

- ≥85% retention compliance without any zeroing needed after week 3.
- No incumbent-exclusion drama: every departing miner exited via the invitation window or the §6a exit ramp, not a surprise zeroing.
- Zero public "SN21 pay-to-play / Ponzi" chatter (monitor via existing X-listen + Discord pipelines).
- Miner applications *inbound* by the mid-July spec publication — the deal marketing itself is the sign the WIIFM message landed.
- No detectable pre-announcement selling by briefed parties (per-coldkey flow monitoring already covers this).
- **No dump signature on 3 August:** no cluster of retained-alpha sales in the launch week attributable to displaced miners — the direct test of whether §6a worked.
- **Launch continuity:** ≥80% of the week-4 curated set still scoring two weeks after the mechanism switch. Below that, the vetting criteria (§6a.1) were wrong, and the lesson feeds the next admission round.

The single metric that summarizes the whole plan: **by the 3 August relaunch, the miners are the ones telling the story** — "best-paying subnet on Bittensor, owner does exactly what he says" — because every week we made a small on-chain-checkable prediction and it came true.
