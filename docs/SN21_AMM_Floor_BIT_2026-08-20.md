# SN21 lab assessment — BIT AMM Pool adjustment (d2tao / locked-TAO floor)

**Date:** 2026-08-20
**Status:** Proposal only. No public subtensor PR found as of this date.
**Stance:** Consider this — model it, do not act on a migration bid.
**Source:** SN29 / Coldint, *BIT — AMM Pool adjustment v0.1* (February 2026),
[https://coldint.io/d2tao.pdf](https://coldint.io/d2tao.pdf)
**Chat trigger:** 2026-08-20 — claim that Const will “fix liquidity pools”;
safety net gone; “token can go zero”; framed as bullish for small caps.
The PDF is what was offered when someone asked for the PR.
**Lab code:** `lab/amm.py` (`amm_floor_from_row`, CPMM floor + BIT price factor).
**Companions:** `dereg_watch.py` (the *other* floor — EMA rank),
`lab/scenarios.py` (S4/S5 still assume constant-product),
[Disposition 2026-07-31](SN21_Disposition_2026-07-31.md),
[Root Reborn risk](Root_Reborn_SN21_Risk_Assessment.md).

---

## TL;DR

This is **not** “remove the dereg floor.” Bittensor already has no fixed
deregistration price. The BIT removes the **AMM residual-TAO price floor**
(`plowest`) that stops alpha from going to zero when everyone unstakes.

**SN21 is not sitting on that safety net.** On the July-31 snapshot, `plowest`
is ~0.00045–0.00055 TAO/α — about 14% of then-spot, well below the prune band.
What keeps the slot is the **rank buffer** in `dereg_watch`, not locked TAO.

**If it ships as written:** slightly positive for an operating SN21 (zombies
can finally die; burn/settlement become cleaner; a slow locked-TAO release
into holders). Worse left tail if demand stays soft (no residual bid; holders
unstake *before* prune instead of waiting for liquidation).

Do **not** bank the paper’s instant ~2× reprice. Migration is designed to be
slow, and people will sell into it. Live pools may already be PalSwap /
balancer-weighted; the PDF is written against Uniswap-v2 `x·y=k`.

---

## 1. Two floors — do not mix them

| | Dereg *selection* | AMM *price* floor (`plowest`) |
|---|---|---|
| What it is | Lowest `SubnetMovingPrice` among non-immune subnets when a new registration hits a full 128 | Residual TAO still in the LP after all α is sold |
| Chain constant? | **No.** Rank, not a TAO/α number. The old lab `DEREG_FLOOR_TAO = 0.0035` was an assumption and was already wrong by 2026-07-29. | Not a named hyperparam. It is implied by `k` and total α. |
| Who reads it | `get_network_to_prune()` | Anyone selling into the pool (and dereg-arb traders) |
| SN21 guardrail today | `dereg_watch` buffer (tier 0 ≈ 20 names below on 2026-07-31) | Distant. ~0.0005 TAO/α on the July snapshot. |
| This BIT | Unchanged | **Removes it.** Price and pool TAO can both go to 0. |

Chat shorthand (“remove dereg floor”) is the AMM column. Keep using
`dereg_watch` for survival.

---

## 2. What the current pool does (the problem the BIT names)

Constant-product: `τ_in · α_in = k`, spot `p = τ_in / α_in`.

Let `α0 = α_in + α_held` (pool α + outstanding α; in our pulls,
`α_held ≈ alpha_issued`).

If every holder sells:

```
τ_locked = τ_in · α_in / α0          # TAO that cannot be extracted by trading
plowest  = τ_locked / α0             # = τ_in · α_in / α0²
p_liq    = τ_in / α_held             # dereg liquidation vs remaining holders
```

Undesirable properties the BIT calls out:

1. **Safety net.** Max relative drop is `1 − plowest/p`. You can size a
   stake with a known floor.
2. **Dereg-safe subnets.** If `plowest` sits above the typical prune band,
   the name cannot be sold onto the dereg list no matter how abandoned it is.
3. **Dereg arb.** Liquidation can pay *above* spot (`p_liq` vs `p`), so
   holding into prune beats unstaking.
4. **Permanently locked TAO.** Roughly half of emitted TAO stays in LPs.
   Participants cannot extract the full emission.
5. **Last-α jackpot.** One remaining α earns all staking rewards against a
   non-zero floor.

Kakashi’s “only pre-dTAO cabal could farm this at launch” is about (2): you
needed a huge TAO bag at dTAO genesis to seed a high `k` and become undead.

---

## 3. What the BIT proposes

New goals: full unstake → `p = 0` and `τ_in = 0`; curve still monotone;
ops stay closed-form.

Claimed new spot (their eq. 11), *at the current reserves*:

```
p_new = τ_in / α_in  +  2 · τ_in / α_held
      = p_old · (1 + 2 · α_in / α_held)
```

That instant factor is **not** a promise of a 2× candle. They specify a
multi-day / week / month ease-in: each block the price is nudged toward the
target while `α0` and `f` are updated so the live point stays on the curve.
While the quoted price rises, `plowest` falls. They expect buy-the-high-`f`
and sell-the-lost-floor flows to damp each other.

Other claimed effects after migration:

- Locked TAO is handed to holders (via the price path), not left in the LP.
- Burning α raises price *directly* (via `α_held` in eq. 11). Today a burn
  mostly traps more TAO in the pool.
- Dereg arb dies: `p_liq ≤ p` always, so you unstake *before* prune.
- Abandoned names can actually go to zero and get pruned. Complements Taoflow.

**Implementation caveat (2026-08-20).** The PDF (Feb 2026) assumes Uniswap-v2
constant product. Finney has already moved toward PalSwap / balancer weights
(Spec 420 family). If Const ships a “pool fix,” the *intent* (no residual
floor) may land under different algebra. Re-read the PR. Do not treat these
equations as live until `lab/amm.py` is rewritten from source.

---

## 4. SN21 snapshot math (refreshable — do not treat as live)

July 2026 docs do not share one consistent `(τ_in, α_in, α_held)` triple.
Use the identities, then re-run `amm_floor_from_row` on a live `chain_pull`.

**Disposition 2026-07-31 table** (price 0.00333, float 3,568,900, pool 7,369 TAO;
`α_in` derived as `τ_in / p`):

| | Value |
|---|---|
| `τ_in` | 7,369 TAO |
| `α_in` (derived) | ~2.21M |
| `α_held` (float) | 3.57M |
| `α0` | ~5.78M |
| `τ_locked` | ~2.82k TAO |
| `plowest` | **~0.00049 TAO/α** (~15% of then-spot) |
| Instant BIT factor `1 + 2 α_in/α_held` | ~2.24× (do not bank) |

**Valuation 2026-06-29** (internally consistent: `8309 / 1.91M = 0.00435`):
`τ_locked` ~3.0k, `plowest` ~0.00055, factor ~2.10×.

**Alpha-lock 2026-07-31** quotes `α_in` 2.04M at the same date as Disposition’s
7,369 / 0.00333 — those three cannot all be true at once. Direction is stable
across the mess: **floor ≈ 0.00045–0.00055, locked TAO ≈ 2.5–3.0k, SN21 is
not dereg-safe.**

Root Reborn’s 0.0035 “floor” was the *assumed prune band*, not `plowest`.
SN21 was ~15% above that band in June and had already printed an EMA
*below* 0.0035 by 2026-07-29. Different object.

---

## 5. SN21 impact register

Filtered only for this slot. “Bullish for small caps” is a market-structure
claim, not an SN21 guarantee.

| ID | Effect | Sign | Why it matters here |
|---|---|---|---|
| A1 | Zombie / high-floor names become prunable | **+** if we stay a going concern | SN21 is an operator with product + rails, not a pre-dTAO floor aristocrat. Dead names releasing TAO / slots is the steelman of the chat. |
| A2 | Slow locked-TAO release into holders | **+ tactical** | ~2.5–3k TAO is real, but ease-in + sell-into-rise will eat most of the paper 2×. |
| A3 | Burn / settlement burns move price more directly | **+** | Delivery-bond and vault burns ([settlement spec](SN21_Stripe_Alpha_Settlement_Spec_2026-08-05.md)) get cleaner mechanical payoff. Miner-burn policy stays a separate lever. |
| A4 | More of emission is extractable | **+ / mixed** | Fits “harvest the owner cut” more than “climb the gate.” |
| A5 | No residual bid; dump can go to literal zero | **− tail** | High float + documented net selling. Root Reborn redemption (R-C) and miner unlocks lose the ~0.0005 backstop. |
| A6 | Near-prune spiral is faster | **− tail** | Holders unstake before dereg instead of waiting for `p_liq`. `dereg_watch` buffer still governs survival; the path to the bottom gets more violent. |
| A7 | More names can fall into the prune band | **mixed** | Zombies dropping *below* us widen the buffer; us being more dumpable narrows it. Net sign is “are we the zombie?” |
| A8 | Lab S4/S5 / Root Reborn impact math go stale | **ops** | Those use `p1/p0 = (1/(1+x))²`. Wrong the day a new curve is live. |

**Net:** slightly positive for an operating SN21, clearly negative for a
neglected SN21. Not a free small-cap pump.

---

## 6. What we do if a PR appears

1. **Confirm it is this BIT** (or PalSwap-equivalent with the same intent).
   Chat + a February PDF is not a deploy.
2. **Read the source**, not the blog. If the algebra differs, rewrite
   `lab/amm.py` from the PR and add a mechanism note — this is *not* an
   `emission_share` scorer, so it does not belong in `lab/mechanisms/`
   unless they also change the emission formula.
3. **Bitsec / accounting review** before treating migration as a treasury
   event. John’s instinct in the thread is correct: a curve that can hit
   zero will have dissolve / injection / reservoir edge cases.
4. **Refresh the snapshot** from live `chain_pull` (`alpha_in`, `tao_in`,
   `alpha_issued`) via `amm_floor_from_row`. Throw away §4 numbers.
5. **Stop citing a price floor in cascade models.** Survival = rank buffer
   only. Widen S5 dump-safety to “can print zero.”
6. **Do not pre-buy the migration factor.** If we are still a going
   concern, the durable work is the same as July: visible bid, reporting,
   settlement burns. The BIT makes those levers sharper; it does not
   replace them.

---

## 7. Refresh recipe

```python
from lab.amm import amm_floor_from_row
# row = the SN21 dict from lab.chain_pull (alpha_in, tao_in, alpha_issued)
print(amm_floor_from_row(row))
```

Expected keys: `locked_tao`, `plowest`, `p_liq`, `spot`, `floor_over_spot`,
`instant_bit_factor`, `dereg_safe_hint` (true only if `plowest` is in the
same order as spot — SN21 should stay false).

When the BIT (or a successor) is *live*, add a failing reproduction note
here and switch S4/S5 off CPMM.

---

## 8. Version

| | |
|---|---|
| v0.1 | 2026-08-20 — first pass from the SN29 PDF + 2026-08-20 chat. No PR. SN21 numbers from July docs, labeled inconsistent, formulas in `lab/amm.py`. |
