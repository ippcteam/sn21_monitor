# SN21 lab assessment — subtensor PR burst, 2026-07-28/29

Run: block **8,727,588** (2026-07-29 12:17 UTC), finney, 128 subnets / 71 emitting.
SN21 live burn **b = 0.4508** (down from 0.602 — the cut has happened).
Gate anchored on the calibrated live hyperparams **q = 0.77, h = 2.9**.

Reproduction gate: model **0.003986%** vs chain **0.003894%**, rel.err **0.024** — PASS.
SN21 today earns **0.1402 TAO/day** (tao_in 0.00001947 TAO/blk, chain buy **zero**).

Corroboration: core dev `mcjkula` stated on PR #3013 that the live quantile is
**0.75**. Our independent fit to SN21's on-chain share gave 0.77. The gate
calibration is anchored correctly.

---

## Live vs proposal — the headline

**All five PRs are OPEN. None is merged. None is on finney. Nothing here is live.**

The only thing live is what was already live: the **v440 q-mass Hill gate**
(PR #2990, spec 440). Two of the five are not even review-ready.

| PR | Title | State | Author | Lane |
|----|-------|-------|--------|------|
| #3007 | recycleAlpha in StakingV2 EVM precompile | OPEN, no reviews | LandynDev | Consider |
| #3010 | Allocate TAO emissions across top 64 subnets | **OPEN DRAFT**, no reviews | gzaentz | Consider |
| #3011 | Conviction-adjusted emission gate (lambda) | OPEN, no reviews | Kaizen0304 | Consider |
| #3012 | Cap chain buys at unburned miner emissions | **OPEN DRAFT**, no reviews | gzaentz | Consider |
| #3013 | Raise emission bar quantile 0.61 → 0.8073 | OPEN, no reviews | ap-choji | Consider |

Registered in the lab as `ranked_tiers_3010`, `conviction_boost_3011`,
`chain_buy_cap_3012`, `q_raise_3013` — all `stage="proposed"`.

---

## SN21 impact, ranked by what actually moves us

| Mechanism | SN21 share | vs live | TAO/day |
|-----------|-----------|---------|---------|
| v440 gate (LIVE) | 0.0040% | ×1.00 | 0.140 |
| #3010 ranked tiers | **0.0450%** | **×11.29** | **1.620** |
| #3013 q → 0.8073 | 0.0049% | ×1.22 | 0.144 |
| #3011 conviction (as shipped, λ=0) | 0.0040% | ×1.00 | 0.140 |
| #3012 chain-buy cap | 0.0040% | ×1.00 | 0.140 |

---

## #3010 — ranked tiers. The one that matters.

Applied **after** the v440 gate, to the already-normalised share map:
ranks 1–32 share 75%, ranks 33–64 share 25%, **ranks 65+ get exactly zero**.
A hard cliff where v440 gave a soft one.

**SN21 post-gate rank = 58 of 71 → tier 2.** Tier 2's 25% is spread over 32
subnets instead of our current sliver of a 71-way split, so we gain **×11.3**.
The top of the book pays for it — Chutes, lium.io, Minos, Affine, Targon each
lose ×0.77. Seven subnets are zeroed outright: sn89, sn71, sn127, sn2, sn93,
sn75, sn103.

**But we are 6 ranks from zero, and the cliff is real:**

| Stress | Rank | Tier | #3010 share |
|--------|------|------|-------------|
| burn b = 0.00 | 47 | T2 | 0.4323% (15.6 TAO/day) |
| burn b = 0.20 | 54 | T2 | 0.1891% |
| **burn b = 0.4508 (today)** | **58** | **T2** | **0.0450%** |
| burn b = 0.60 | 63 | T2 | 0.0132% |
| burn b = 0.80 | 68 | **ZERO** | 0 |
| price ×0.60 | 64 | T2 | 0.0062% |
| **price ×0.50** | 66 | **ZERO** | 0 |

A halving of our EMA price, or pushing burn back to 0.8, drops us off the
cliff to zero TAO emission. Headroom in gated weight to the rank-64 line is
only ×3.84.

At b = 0 under #3010 we would earn **15.6 TAO/day vs 0.14 today** — ×111. The
burn lever and the tier lever multiply.

## #3013 — near-inert diff, live-fire policy

The diff only edits `DefaultEmissionBarQuantile` in lib.rs. That default is read
only when the storage item was never written. `mcjkula` said so on the thread:

> "the current quantile is 0.75 ... you are changing the default value here
> (which won't do much). ... the Triumvirate just needs to change it with the
> `sudo_set_emission_bar_quantile` call. So no PR/code change needed."

**The real finding is not the PR. It is that our single largest emission
parameter is one sudo extrinsic, with no runtime upgrade, no release, no
warning.** q sweep against live state:

| q | theta | SN21 share | vs live |
|---|-------|-----------|---------|
| 0.61 (code default) | 2.5133% | 0.0004% | ×0.11 |
| 0.75 (core dev: live) | 1.2375% | 0.0026% | ×0.64 |
| 0.77 (our fit) | 1.0422% | 0.0040% | ×1.00 |
| 0.8073 (#3013) | 0.9638% | 0.0049% | ×1.22 |
| 0.90 | 0.6389% | 0.0141% | ×3.54 |

Raising q loosens the gate and helps us; it costs us nothing and we cannot
cause it. Lowering q to the 0.61 code default would cut us ×0.11 overnight.

## #3011 — conviction boost. A no-op that arms a lever.

Gate is evaluated at `s × (1 + λ·C)` where `C = conviction / alpha_out` capped
at 1. Base weight and the bar keep using raw `s`. **λ defaults to 0, range
[0,8], sudo-settable** — so even if merged and deployed it changes nothing
until the Triumvirate turns it on.

SN21 holds **zero locks**, so C = 0 and we gain nothing at any λ.

- **If λ is turned on and we stay unlocked**: others lock, we lose ground.
  Everyone at C=0.5, us at 0 → ×0.91 at λ=1, ×0.79 at λ=8.
- **If we lock first**: C=1 gives ×6.9 at λ=1, ×18.6 at λ=2, ×44.7 at λ=4.

This is the first proposal in the v425→v440 train handing a below-bar subnet a
lever that is **not price**. It also changes the economics of the conviction
work already on file: the lock we have been treating as a pure defensive cost
against takeover would acquire a yield.

## #3012 — chain-buy cap. Not our problem today; helps us second-order.

Caps the chain buyback at
`alpha_emission × (1−owner_cut) × 0.5 × (1−MinerBurned) × price`, reservoiring
the remainder instead of swapping it.

`camfairchild` (core dev) challenged it directly — *"Is this not doubling the
miner burn penalty?"* — and the author conceded the point and defended it as
intentional, naming a burn-independent variant as a near-equivalent alternative.
So the double-penalty is acknowledged, and the design is not settled.

**SN21's chain buy is currently zero** — our injection is nowhere near the
root-proportion cap — so the double-penalty does not touch us at any b. Our
notional cap would be 0.00075 TAO/blk, well above our zero.

Where it bites is the mature top of the book. Network-wide it removes
**~643 TAO/day of buy pressure**, concentrated exactly on the subnets whose
prices dominate the gate distribution:

| Subnet | buy pressure removed |
|--------|---------------------|
| sn64 Chutes | 151 TAO/day |
| sn51 lium.io | 110 TAO/day |
| sn4 Targon | 101 TAO/day |
| sn120 Affine | 77 TAO/day |
| sn8 Vanta | 46 TAO/day |
| sn53 engy | 43 TAO/day |

Note these are almost all **burn = 0** subnets: the binding constraint is
maturity, not burn. Since the gate scores us on relative price and theta is a
property of the whole distribution, removing price support from the head should
compress the distribution and loosen the bar for everyone below it. Directionally
positive for SN21 — but that is a second-order effect the current model does not
close the loop on (it would need a price-response model, which is S6 territory).

## #3007 — EVM precompile. Zero emission impact, one non-obvious link.

Exposes the existing `recycle_alpha` extrinsic to EVM contracts. Recycled alpha
reduces `SubnetAlphaOut` (unlike `burnAlpha`). No emission-formula change at all.

The one thing worth noting: **`SubnetAlphaOut` is the denominator of #3011's
conviction ratio** `C = conviction / alpha_out`. If both land, recycling alpha
raises C without adding a single locked token — and #3007 makes that
programmable from a contract. Speculative, both PRs are unmerged, but it is the
kind of interaction worth watching if #3011 gains traction.

---

---

## Follow-up: is the burn recommendation b = 0? (and a correction)

Direction: **yes** — b = 0 dominates at every model tested, and S6 says realized
miner dump never overturns it (b=0 still beats hold at 50% dump). But the burn
case does **not** depend on #3010, and one standing conclusion is now wrong.

**The burn multiplier is the same under both mechanisms.** TAO/day at fixed price:

| b | ungated v432 | **v440 gate (LIVE)** | #3010 |
|---|-----|------|-------|
| 0.7685 | 3.56 | 0.005 | 0.000 |
| 0.6000 | 6.15 | 0.042 | 0.475 |
| **0.4508 (today)** | 8.44 | **0.143** | 1.620 |
| 0.2000 | 12.29 | 0.606 | 6.809 |
| 0.0000 | 15.34 | **1.399** | 15.560 |

b=0 is ×9.8 under the live gate and ×9.6 under #3010 — the tier gain (×11) and
the burn gain (×9.7) are independent and multiplicative. #3010 amplifies the
burn case; it does not create it. Act on the live gate, not on a draft PR.

**CORRECTION — the chain-buy price channel is CLOSED, not open.** The standing
note that the price channel opens below b ≈ 0.79 was computed on the **un-gated
v432 share**, which puts SN21 at 8.44 TAO/day at today's burn. We actually
receive **0.14 TAO/day** — 59× overstated. Through the live gate:

- SN21 at **b = 0** earns **1.40 TAO/day**
- injection cap = **3.56 TAO/day** (root_prop 0.1488 × alpha_emission × spot)
- 1.40 < 3.56 → **excess TAO is zero at every burn level; the channel never opens**

The chain confirms it: SN21's live `excess_tao_emission` is exactly **0**.

So under the live gate, cutting burn buys **emission volume and pool depth — not
price**. `lab/scenarios.py` S6 still runs on `root_reborn_v425_2800` (un-gated),
so its price table (+40% at 180d, b=0) is not credible under the gate and should
not be quoted until S6 is re-anchored on the gate.

**Under #3010 the channel would open at b ≤ 0.326** — 15.56 TAO/day at b=0 vs the
3.56 cap. That is the qualitative difference the tiers make: deep burn cuts start
reaching price instead of only depth.

**And #3010 makes high burn fatal rather than merely expensive.** At b ≥ 0.8 we
fall to rank 68 → **zero emission**. Under the live gate the same burn just
crushes us to 0.0001%. The binding constraints on going to b=0 remain miner
quality control and dump absorption, not emission math.

---

## Second follow-up: does RAISING burn defend the price? (it does — reversal)

Prompted by a miner (TECH_DEV): *"Alpha price is very low, and subnet emission
also 0.00%. How about increase burn rate? I have this subnet alpha, I don't want
to decrease price."*

Both observations are factually correct: our share is 0.0039% (rounds to 0.00%)
and spot is 0.003326. And **the proposed fix works** — S6 redone through the live
gate (theta = 1.0422%, q = 0.77, h = 2.9) says so. SN21 spot at 180 days vs
holding b = 0.4508:

| b | 15% dump | 50% dump | 100% dump | TAO/day |
|---|---|---|---|---|
| 1.00 | **+3.99%** | **+13.59%** | +28.05% | 0.000 |
| 0.80 | +2.50% | +8.33% | +16.59% | 0.003 |
| 0.60 | +1.06% | +3.43% | +6.61% | 0.042 |
| **0.4508** | — | — | — | 0.143 |
| 0.20 | −1.72% | −5.33% | −9.72% | 0.604 |
| 0.00 | −3.01% | −9.19% | −16.35% | 1.389 |

**This reverses the b = 0 recommendation on the price dimension.** The reason is
the closed price channel established above: the TAO that cutting burn wins is
*pure balanced injection* — it deepens the pool without moving price — while the
miner alpha it releases *is* sold. Emission up, price down.

Three qualifications that matter more than the direction:

1. **The entire effect is the miner-dump channel.** At dump = 0 every burn level
   is bit-identical. Burn does nothing except reduce what miners can sell.
2. **Burn cannot raise the price — only slow the decline.** Searched the whole
   b × dump grid: the best achievable 180-day spot is **exactly today's**
   (0.003326, at b = 0.90 / dump = 0). There is **no** (b, dump) combination
   where price rises. Under the v440 gate SN21 has no price-*raising* mechanism
   at any burn level.
3. **The price it buys is expensive.** At a realistic 15% dump, going b = 0.45 →
   1.0 is worth +4.0% over 180 days and costs 100% of our emission (0.143
   TAO/day), starves all 125 scored miners (1,621 α/day today), and under #3010
   at b ≥ 0.8 drops us to rank 68 — zero emission.

So this is a genuine trade, not a dominant lever in either direction. Burn is
bleed-control. The price problem is a demand problem.

## What to do

1. **Nothing is live — do not act on any of it.** The only live change remains
   the v440 gate, and our response to that is unchanged.
2. **Watch #3010 hardest.** It is a draft, but it is worth ×11 to us and it
   would zero seven subnets. If it moves toward merge, our rank-58 position and
   the ×3.84 headroom to the rank-64 cliff become the operating metric.
3. **The burn cut already made is the right call and should go further.** Under
   both the live gate and #3010, b is the lever we control: b=0 is ×9.8 under
   v440 today and ×111 under #3010.
4. **Add a q tripwire.** q is a sudo dial, not a PR. A move from 0.77 to the
   0.61 code default is ×0.11 on our emission with no warning and no upgrade.
   We currently have no monitor on `EmissionBarQuantile`.
5. **#3011 changes the conviction calculus if λ is ever set.** Not yet, and not
   by default. Revisit if it merges.
