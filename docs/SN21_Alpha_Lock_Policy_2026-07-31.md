# SN21 — Miner Alpha Lock Policy (the holding bar)

**Date:** 2026-07-31  **Owner:** Rob Warner
**Status:** Proposed — supersedes the single-step floor in `SN21_Daily_Stream_Design_v0.5.md` §8 / [D9]
**Chain basis:** finney spec 440 (live), collateral runtime 437 live. Live state block ~8,715,990.
**Readers:** Khurram, Jayesh, Tensora, John Davy

---

## 1. What this is

Miners must hold alpha to score in SN21. The bar starts small and rises weekly for four weeks to a
target, so nobody is ever forced to buy alpha on-market and nobody can farm the subnet with a
zero-skin position.

The bar is **enforced by our validator scoring**, not by the chain. That distinction is load-bearing
and is stated plainly in §6.

---

## 2. The bar

**Schedule A is the live schedule.** Burn is held at b = 0.451 (decision 2026-07-31, §7) — miners
share ~1,621 α/day.

| When | Floor | ≈TAO @ 0.003229 | ≈USD @ TAO $192 | Weekly step |
|---|---|---|---|---|
| IM launch | 300 α | 0.97 | $186 | — |
| +1 week | 475 α | 1.53 | $294 | +175 |
| +2 weeks | 650 α | 2.10 | $403 | +175 |
| +3 weeks | 825 α | 2.66 | $511 | +175 |
| +4 weeks | **1,000 α** | 3.23 | $620 | +175 |

**Schedule B — dormant.** Retained only in case the burn decision is ever reopened. If burn were cut
to 0 (miners sharing ~2,952 α/day), every step scales by 1.82×: 300 → 625 → 950 → 1,275 → **1,600 α**.
Do not run this schedule without re-reading §7.

**The α denomination has already proved itself:** alpha fell 18% in the four days between drafting
and confirmation (0.003922 → 0.003229 TAO). The TAO column moved; the bar did not need re-cutting.

Denominated in **α, not TAO** — the bar auto-scales in fiat/TAO terms if price recovers, and a flat α
number is restated at each four-weekly review.

---

## 3. Why these numbers

**The invariant is the step, not the target.** Each weekly increment must be fillable inside its own
week by the *weakest miner we want to keep*, out of that miner's own earnings. That is what makes
the bar a retention tool rather than an entry gate.

Emission arithmetic (live state, `scratch_live_state.json`):

- SN21 mints 1.0 α/block = **7,200 α/day**, gate-independent ([F3](SN21_Emission_Gate_Findings_and_Actions_2026-07-27.md)).
- Owner cut 18% → 1,296 α/day. Remainder 5,904 splits 50/50 validators/miners → **2,952 α/day** to the miner side.
- At b = 0.451, miners actually receive 2,952 × 0.549 = **1,621 α/day**. At b = 0, **2,952 α/day** ([F6](SN21_Emission_Gate_Findings_and_Actions_2026-07-27.md): the freed 1,331 α/day).

Fill test, using the §7 weight curve's marginal scoring slot at 2% weight:

| | 2%-slot income | Weekly step | Headroom |
|---|---|---|---|
| Schedule A | 32 α/day = 227 α/week | 175 α | +30% |
| Schedule B | 59 α/day = 413 α/week | 325 α | +27% |

The champion (~55% weight: 892 α/day at b=0.451, 1,624 α/day at b=0) clears any single step in under
a day, and the whole target in ~1–2 days.

**Why not higher.** Past ~1,000 α (A) / ~1,600 α (B), a 2% slot can no longer keep pace and would
take home nothing for over a month. That thins the earning set — the opposite of what a daily
champion contest needs. A materially higher bar would have to be tiered by weight, which contradicts
the flat-α decision in [D9].

**Why not lower.** Below this the lock stops being a deterrent: the forfeit has to be worth more than
a week of dumping, and a sub-500 α floor is under two days of champion income.

**Slots below 2% weight are exempt** until they cross it. They cannot fill a step in a week, and
zero-weighting them for that would turn retention into a cull.

---

## 4. What the ramp actually withholds

The ramp is the sink; the floor itself is a one-time stock.

| | Schedule A | Schedule B |
|---|---|---|
| New lock per slot over 4 weeks | 700 α | 1,300 α |
| × ~10 earning slots (§7 expects 5–15) | 7,000 α | 13,000 α |
| Miner emission over the same 28 days | 45,388 α | 82,656 α |
| **Share of miner emission withheld** | **15.4%** | **15.7%** |
| Locked stock at target vs 3.55M α issued | 0.28% | 0.45% |

Both schedules land on the same ~15% withholding — that is the design anchor, and it is deliberately
the same number as the ≤15%/week sell cap in the operating agreement, so the two rules say one thing.

**After week 4 the ongoing suppression is zero.** A static floor stops absorbing flow the moment it
is filled. Sustained restraint comes from the sell cap plus forfeit risk, and from stepping the floor
again at each four-weekly review (suggest +10–15%) if we want the sink to persist.

---

## 5. How the bar fills

- **No upfront buy-in, no entry gate.** For miners who opt into the chain rail, incentive is escrowed
  into `min_locked` until the floor is met, then normal payouts resume. A model that never earns
  never owes anything.
- **Miners who prefer immediate take-home may front the collateral voluntarily** (`add_collateral`)
  or simply hold the equivalent stake on the coldkey — their choice.
- **Existing scoring miners are grandfathered onto the fill path.** No cash call on people already
  working for us.
- Because the §7 curve pays challengers partial weight on the way up, every model approaching
  championship contention has already served its escrow. The fill phase is a probation period that
  triggers itself, at exactly the moment a new big earner would otherwise be an unvetted dump risk.

---

## 6. Enforcement — what is real and what is not

**The chain will not force a miner to hold** ([F7](SN21_Emission_Gate_Findings_and_Actions_2026-07-27.md)).
The reward-capturing `min_locked` floor in the collateral runtime is **miner opt-in**
(`coldkey_owns_hotkey`); the owner knob `CollateralLockShare` only locks part of the ~0.1 TAO
registration deposit. SN21 today runs p = 0 (off), k = 1.0.

So the bar works like this:

1. **Compulsion is ours:** our validator's weight scoring. Below the current step → weight goes to
   zero. This is curated-set curation under a private operating agreement, not a published
   pay-to-play rule.
2. **Verification is the chain's:** we read the miner's opt-in `min_locked` floor as the tamper-proof
   hold signal, and fall back to coldkey stake/float monitoring for miners who have not opted in.
3. **Teeth:** a zero-weighted miner stops earning; with no earnings there is no drain, so an opted-in
   miner's collateral freezes permanently. Forfeiting the floor *plus* losing a paying slot is the
   penalty — deterrence comes from that ratio, not from the floor's size.
4. **Stated plainly to miners:** a dethroned champion's floor stays locked until they earn again.
   Locked capital is an incentive to keep competing rather than rage-quit; we say so out loud rather
   than let someone discover it.
5. **Honest limit:** this is a deterrent, not a physical lock. No unbonding period, no clawback. A
   miner who decides the dump is worth more than the slot can still dump.

**Safety note (verified from source):** miner collateral is a separate mechanism from conviction
locks. Miners locking alpha as collateral build **zero** conviction toward subnet ownership — the
takeover vector ([F8](SN21_Emission_Gate_Findings_and_Actions_2026-07-27.md)) does not apply here.

---

## 7. The burn decision — cancelled, not staged (2026-07-31)

**Burn is held at 0.451.** The staged cut in the emission-gate plan (P2) is withdrawn, not deferred.

The reasoning, now that the treasury option is off the table (no capital for the ~3,200 TAO / ~$614k
required to reach the gate bar):

- Burn→0 was never an injection lever. At b = 0 SN21's TAO emission reaches ~3.2 TAO/day against a
  ~4.2 TAO/day injection cap — channel still shut ([F5](SN21_Emission_Gate_Findings_and_Actions_2026-07-27.md)).
  And injection at the current price is arithmetically price-neutral: the pool takes TAO and alpha in
  exactly the ratio `tao_in/alpha_in`, so the ratio does not move. Only the excess above the cap
  becomes a chain buy, and we never reach it.
- Its only real value was as a **discount on a price push**: it multiplies `s = price × (1−burn)` by
  1.82×, and since the gate is a Hill function with h ≈ 2.9 (share scales as ~`s^3.9` below the bar),
  it roughly halves the price move needed to clear the bar — 3.57× down to 1.96×. With no capital to
  spend, that discount has no redemption date.
- **It is also badly mispriced against our own take.** Burn→0 redirects 1,331 α/day (~4.3 TAO/day,
  ~$301k/yr) to miners. Our entitlement is 25% of the owner cut — 324 α/day, ~$73k/yr — rising to
  50% mid-September 2026 and 75% from March 2027 (972 α/day, ~$220k/yr). Even at the full 75% we
  would be handing miners more than we receive.

**If it is ever reopened:** ramp first or simultaneously, never burn-first-alone, and switch to
Schedule B from day one — cutting burn mid-ramp doubles every miner's fill rate and the remaining
steps stop binding.

---

## 8. Price expectation — state it before we act

The lock does not rescue the price and is not sold internally as if it does.

With burn held (§7), the ramp is the only thing moving, so the sign is now **mildly positive**:
7,000 α withheld over four weeks (~0.34% of the AMM alpha side, `alpha_in` 2.04M) against nothing
added. In cash terms that is ~23 TAO — trivial. **The ramp is worth doing for retention and
enforceability, not for price.**

The rejected alternative for the record: burn→0 would have added 1,331 α/day = 37,268 α of new
sellable supply over the same four weeks, ~5.3× what the ramp withholds, with no offsetting chain
buy. That pair was supply-positive and mildly price-negative.

**Our price exposure roughly triples by March 2027** as the entitlement steps 25% → 50% → 75%. Float
discipline gets *more* important over that window, not less — which is the second reason burn stays
where it is.

---

## 9. Open items

| ID | Item | Owner | Blocking? |
|---|---|---|---|
| L1 | ~~Confirm burn-UID 135 is a null sink~~ — moot while burn is held at 0.451 (§7) | Rob | Closed |
| L2 | Weight-zeroing path in the live validator scoring code, reading `min_locked` + coldkey float | Khurram | Yes — the bar is unenforceable without it |
| L3 | Operating-agreement wording for the bar and the ≤15%/week sell cap | Rob | Before launch announcement |
| L4 | Confirm the §7 curve's 2% threshold; the fill test in §3 is anchored on it | Khurram | Before the first review |
| L5 | Decide whether the floor keeps stepping at each four-weekly review (§4) or goes static | Rob | First review |

---

## Changelog

| Version | Date | Changes |
|---|---|---|
| v0.2 | 2026-07-31 | **Confirmed.** Burn held at 0.451 — the staged cut is cancelled, not deferred (§7 rewritten), so Schedule A is live and Schedule B goes dormant. Owner entitlement schedule recorded: 25% now → 50% mid-Sept 2026 → 75% March 2027. TAO/USD columns re-struck at 0.003229 / $192 after an 18% four-day price fall; α figures unchanged, which is the denomination working as designed. §8 sign flips to mildly positive |
| v0.1 | 2026-07-31 | First issue. Replaces the 300 α → 600 α single step with a four-week weekly ramp; adds the burn-linked Schedule B; re-bases enforcement on validator scoring after [F7] (chain floor is miner opt-in, not owner-imposable) |
