# SN21 Miner Comms — Daily Stream Relaunch Announcement (DRAFT)

**Date:** 22 July 2026 · **Status:** DRAFT — for internal red-team (per Comms Plan §7 week-0 step e) before any miner sees it
**Companion to:** SN21_Miner_Comms_Plan_2026-07-03.md (the governing plan) and SN21_Daily_Stream_Design_v0.3.md (the mechanism spec)
**Contains:** §A internal deltas vs the July-3 plan · §B the miner-facing announcement · §C FAQ additions (extends the plan's §4 objection map)

---

## §A. Internal — what changed since the July-3 plan (read before circulating)

1. **The launch date must move or the notice promise breaks.** The plan's own commitment: 4 weeks' notice for any scoring-policy change. The Daily Stream design materially changes the contest (daily cadence, weight curve, promotion rule, collateral floors) versus whatever was briefed in early July — the clock restarts for the changed elements. If this announcement lands the week of 22 July, the earliest honest launch is **~Wednesday 20 August**. Rob's "3 weeks" instinct needs either a moved date or an explicit signed waiver from every briefed miner. **Do not fudge this — Q4 of the objection map ("you'll change the rules") is answered entirely by our notice discipline, and this is its second test.**
2. **Redline 2 ("no lock language anywhere") is consciously amended.** The network's v435 upgrade makes *registration collateral* and *min_locked floors* protocol vocabulary, shipped by the core team. We use the protocol's own words — "registration collateral," "collateral floor," "the v435 upgrade" — and never our old banned words ("entry stake," "buy-in," "stake-to-mine"). The distinction that keeps Q5 (Ponzi pattern) answered: **miners never purchase anything to mine here; the floor fills from earnings escrow, not from a deposit.**
3. **Redline 3 (no price talk) unchanged and re-affirmed.** Nothing below contains a price number. Keep it that way through every edit.
4. **The burn schedule stays post-hoc** (redline 7). The announcement references the burn cuts as *landed results* only. Note for ops: the 0.45 step has NOT yet landed on chain as of 22 July — nothing below may claim it until it prints.
5. **The legacy-tail zeroing (D10) is the §6a displacement problem at 10× scale.** ~165 UIDs currently receive dust; at cutover they receive nothing. The invitation-before-exclusion sequence (plan §6) applies: this announcement is also the invitation, and the wind-down taper applies to any *scoring* miner displaced by the new contest — but dust UIDs that never scored get no taper (they were never in the contest; their trickle was an artifact of the old vector). State it plainly, once.
6. **Conviction defense stays out** (redline 1). The §B safety note about collateral-vs-ownership is phrased miner-benefit-only.

---

## §B. The announcement (miner-facing, verbatim draft)

### SN21 is moving to a daily contest. Here is the whole deal, in one place.

You asked for faster feedback. The weekly epoch was our rule, not the chain's — so we're retiring it. From **[LAUNCH DATE]**, SN21 runs as a daily stream: a fresh basket of real account changes every day, predictions locked the same day, outcomes measured at 7, 14, and 28 days against numbers that never move after we score them. A different day's basket matures every day, so scores — and your weights — update every day. Emissions already flow continuously (~every 72 minutes); now your scoring keeps pace with them.

This announcement is the complete package: the contest, who earns what, the collateral policy, and the schedule. The full mechanism spec is attached. Nothing else is coming later — and per our standing commitment, nothing here changes without four weeks' notice, and never retroactively.

### The contest

- **Daily baskets, same-day locked predictions.** Scoring formula unchanged from v2: 50% quantile accuracy, 20% calibration, 15% direction, 15% goal metric — every prediction judged against that account's own goal.
- **Admission is continuous.** Pass the published backtest gate, you're in — no admission windows, no waiting for an epoch that no longer exists.
- **Weights follow a published curve, not winner-take-all.** Your moving-average score sets your weight: the top model earns roughly 50–60% of miner emissions, second place ~20%, then a decaying tail, zero below a published threshold. We removed the winner-take-all cliff deliberately: it made the top slot flip on statistical ties, and it paid challengers nothing on the way up. Under the curve, a rising model earns while it climbs. In practice we expect **5–15 models earning at any time** (hard ceiling 20).
- **The champion — the model that actually runs live across the portfolio — changes by a deliberate rule, not a lucky day.** A challenger takes the top slot only after leading the moving average by a published margin for 7 consecutive days, with at least 14 scored days of history. Close races leave the incumbent in place. You will never lose the championship — or win it — on one day's noise.
- **One basket today; a published split trigger for lead-gen vs ecommerce specialists.** The trigger conditions are public from day one, so specialists can build ahead of it.
- **The only calendar rhythm left: a four-weekly parameter review**, on a published schedule, where any rule numbers are restated in advance. No changes between reviews.

### Who earns, and what stops

Today's weight vector pays a dust trickle to ~165 UIDs — most of which have never submitted a scoring prediction. **At launch, that ends.** Weight flows only through the curve above: real models, really scoring. If you hold a UID that earns dust today and you want to actually compete, the backtest gate is open now and admission is continuous — this announcement is your invitation. Scoring miners displaced by the new contest get a tapered wind-down, never a same-day zeroing; dust UIDs that never scored simply stop receiving an artifact of the old weight vector.

### Collateral: skin in the game, built into the chain — not a deposit

Bittensor's **v435 upgrade** (merged by the core team, deployment on the network's timetable, not ours) adds *miner registration collateral* at the protocol level: alpha locked on your own key, released back to you through earned incentive, surviving deregistration, with a floor that maintains itself. We will use it natively:

- **Every earning model backs its slot with a collateral floor: 300 α at launch, 600 α four weeks later**, restated as a flat number at each four-weekly review.
- **You buy nothing and deposit nothing.** The floor fills by escrow: when your model starts earning, your incentive fills the floor first, then flows to you normally. A model that never earns owes nothing. If you'd rather skip the escrow phase and start taking rewards home immediately, you may front the collateral voluntarily — your choice, never a requirement.
- **Current scoring miners are grandfathered onto the escrow path.** No cash call on anyone already working here.
- **The collateral is yours.** It drains back to you as withdrawable stake as you earn. Two things we say out loud so nobody discovers them later: a miner removed for breaking the operating agreement stops earning, and under the protocol's rules collateral without earnings stays locked — that is the penalty for breaking the agreement, and it is severe on purpose. And a dethroned champion's floor stays locked until they earn again — the network's way of rewarding staying in the contest over rage-quitting.
- **This is not stake-to-mine.** There is no purchase, no entry payment, no requirement to ever buy alpha. The floor is your own earnings, briefly escrowed, fully recoverable through the same work that filled it. It is the protocol's mechanism, shipped by the network's core team, and we are using it as designed.
- The policy is live from launch day; on-chain enforcement activates automatically whenever the network deploys v435. We signal now so nothing about it is a surprise.

### The retention rule (unchanged)

The 85% retention policy on freed rewards carries over the mechanism change unbroken — same allowance, same trailing-week window, and your compliance history and accumulated position transfer as-is. The standing commitments also carry over: retention is never tightened retroactively, never tightened during a drawdown, and every policy change gets four weeks' notice.

### What's in it for you (the arithmetic, all checkable)

The burn cuts you've watched land on-chain continue on the published policy: each step raises the miner pool for everyone still in it, and the legacy-tail zeroing concentrates that pool on models that actually score. A top-curve model under this design earns a multiple of today's flat-vector trickle — you can compute your own case from the curve numbers and the current pool in the spec, and verify every input on-chain. We don't publish price projections; we publish mechanisms and let you run them.

### The schedule

| When | What |
|---|---|
| Today | Full spec + operating-agreement addendum in your hands; backtest gate open; 1:1 briefings on request |
| [LAUNCH − 2 weeks] | Scoring dry-run against the live pipeline — launch is a switch, not a surprise |
| **[LAUNCH DATE]** | Daily stream live; weight curve live; legacy tail zeroed; collateral policy in force (escrow path) |
| [LAUNCH + 4 weeks] | Floor rises 300 → 600 α; first four-weekly parameter review (curve numbers, promotion margin, floor restated) |
| Every 4 weeks | Parameter review, published in advance |

Everything above is either on-chain now or lands on-chain where you can check it. Ask us the hard questions before launch — briefings are open.

*— SN21 / AdTAO*

---

## §C. FAQ additions (extend the plan's §4 objection map; same rules — miner's voice, honest answers)

**Q8. "Winner-take-all paid the best model 100%. You just cut the champion's pay to ~55% — that's a nerf."**
A: Under winner-take-all the champion held 100% until the day a rival crossed them by 0.1% — then held 0%. Expected earnings across a reign were high-variance and cliff-shaped, and challengers earned nothing while proving themselves, which starved the pipeline that keeps a contest alive. Under the curve the champion earns ~55% *durably*, protected by the promotion rule from losing the slot on noise, and every serious challenger funds their own run. Also arithmetic: ~55% of a pool concentrated on ≤20 models is far more than 100%-minus-cliff-risk of a pool sprayed across 165 UIDs.

**Q9. "The collateral floor is a lock. You said there'd be no locks."**
A: We said — and it remains true — that you will never be required to buy or deposit anything to mine here. What changed is the network itself: v435 ships registration collateral as a protocol feature, and the floor fills from your own earnings escrow, not your pocket. Your sellable income under the retention rule is untouched by it. The honest description: your first ~[300] α of earnings vest through work instead of arriving instantly — the same shape as every serious company's vesting, run by the chain, not by us.

**Q10. "If I'm dethroned or zeroed, my collateral is stuck. That's confiscation."**
A: It is never confiscated and never ours — it sits on your key, and the protocol releases it through earned incentive, which any return to scoring resumes. What we will not do is pretend the freeze isn't a real cost: it is the deterrent, and we chose it because the alternative (a fee) actually takes your money. Exit with your earned stake, keep your compliance history, and your collateral credit even survives deregistration under v435 — re-register later and it counts toward your requirement.

**Q11. "Why did my UID's emissions stop at launch? I did nothing wrong."**
A: If your UID was earning without scoring, it was collecting an artifact of the old flat weight vector — dust paid to 165 UIDs, most of which never submitted a prediction. The new design pays models that compete. The backtest gate is open, admission is continuous, and the earning curve means a competent new model earns from its first qualifying days. We announced this change [N] weeks in advance precisely so nobody finds out by watching their emissions stop.

**Q12. "Daily scoring means daily rule-fiddling."**
A: The opposite — daily *scoring*, four-weekly *rules*. Between reviews nothing changes: not the curve, not the margin, not the floors, not the retention numbers. The review calendar is published, changes are announced at least four weeks out, and the one time we retired a rule we'd called non-negotiable (the weekly epoch), we did it as a signed governance amendment with notice — which is exactly what this announcement is.

---

*Red-team checklist before circulation (plan §7 wk-0e): angriest-miner pass · displaced-miner pass · leak-test (assume Const reads it) · verify every on-chain claim against current chain state (burn level references especially — 0.45 not yet landed) · confirm launch date honors the 4-week notice or waivers are signed.*
