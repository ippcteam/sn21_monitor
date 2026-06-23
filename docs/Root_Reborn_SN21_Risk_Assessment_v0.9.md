# Root Reborn — SN21 Risk Assessment

**Version:** v0.9
**Date:** 2026-06-23
**Status:** Living document — adversarial register + empirical test plan
**Owner:** Rob Warner · Publication accountability: Jayesh
**Lens:** SN21 only (not network aggregate)

---

## Changelog — v0.8 → v0.9

| Change | Detail |
|---|---|
| **New §1** | Formulas in plain English — no math background assumed |
| **New §2** | Operating-capital thesis — owner emission moves from *market-agnostic* to *market-contingent*, front-loaded to the early window. Answers "is owner emission close to worthless?" (no — conditional, and mostly self-throttled by the burn) |
| **New §4** | Empirical Test Lab — full spec for a separate repo (`sn21-emission-lab`) to pull real chain state and model old-vs-new, sweep the burn, project decay, and model extraction. Built so it can be *seen*, not trusted |
| **Updated §5** | Action steps re-anchored on building and running the lab before any irreversible decision |
| Carried | R-Q (top P1), R-M/N/O/P, retired R-D — full write-ups in v0.8 |

> Principle for this version: **reproduce reality before trusting any projection.** The lab's first job is to rebuild SN21's *current* emission from first principles and match it against taostats. Only a model that reproduces today earns the right to predict tomorrow.

---

## 1. Formulas in plain English

The whole mechanism is one line:

```
your slice of network emission  =  youth allowance  ×  market salary  ×  attendance gate
emission_share_i                =  root_prop_i      ×  price_i        ×  (1 − miner_burn_i)
```

Three dimmer switches, multiplied. If any one is near zero, the whole slice is near zero. Owner operating capital is **18% of this slice**.

### Switch 1 — Youth allowance (`root_prop`)
```
root_prop = R / (R + A)
R = a fixed network number (root TAO stake × tao_weight) — same for every subnet
A = your subnet's issued alpha — grows every tempo as you emit
```
- When `A` is tiny (young subnet, little alpha issued yet), `root_prop ≈ 1` — almost no penalty.
- As `A` grows over months/years, `root_prop` shrinks — your slice decays as you mature.
- **Plain:** a head-start for the young that fades as you grow. SN21 is two months old → this is near its peak **now** and tapers over roughly your exit window. This front-loads runway into the period you most need it. *(Risk R-M tracks the fade; §2 explains why the fade is acceptable for a startup.)*

### Switch 2 — Market salary (`price`)
```
price = the smoothed (EMA) market price of your alpha token, in TAO
```
- A smoothed average (EMA = exponential moving average) so a one-off spike or dip doesn't swing it.
- The chain pays you in proportion to what the market thinks your subnet is worth — more staking demand, deeper pool, higher price → bigger slice.
- **Plain:** your salary is now set by your own market's health. This is the genuinely new condition on your operating capital. *(Risk R-N tracks the two-way coupling.)*

### Switch 3 — Attendance gate (`1 − miner_burn`)
```
miner_burn (b) = the fraction of your miner pay routed to the owner/burn key instead of real miners
```
- Pay all miners → `b = 0` → gate = 1 → no penalty.
- Burn 75% (our current setting) → `b = 0.75` → gate = **0.25** → your **entire** slice (owner + validator + miner) is cut to a quarter.
- **Plain:** you collect pay in proportion to how much you actually pay miners. We have manually turned this switch down to 0.25. *(Risk R-Q — the top risk. We are doing this to ourselves.)*

### Putting it together
Two of our three switches are bright: **youth allowance** is near max (young), and the inputs to a healthy **market salary** are present (88 real scored miners, genuine product). The **attendance gate** is the one we've dimmed to 0.25. The single highest-leverage move we control is turning that gate back up.

---

## 2. Operating-capital thesis — is owner emission close to worthless?

**Short answer: over-dramatic on "close to worthless," correct that the *character* of the capital has changed.**

### What changed — capital became conditional, not worthless
Under the old mechanism, owner emission was effectively **market-agnostic**: you received it more or less regardless of your token's price. Under the new mechanism, `emission = root_prop × price × (1−b)`, so owner emission is **market-contingent** — paid in proportion to a market that values you. The "free capital regardless of market" era ends; the new deal is "capital as a function of a market that values what you built." For a subnet with no real demand that is a death sentence. For one pulling 88 scored miners and a genuine product, it is a workable — arguably aligned — deal.

### Why the doom you're feeling is mostly the burn, not the mechanism
The owner emission you're looking at has already been cut to a quarter by a switch **you set for the old rules** (the 75% burn). Strip that out — model owner emission at the burn rate the *new* mechanism rewards — and most of the "worthless" feeling disappears. Do not convict the mechanism for a self-inflicted, recoverable cut. **The mechanism at a sane burn rate is currently favourable to SN21.**

### Why the mechanism is favourable to *you specifically, right now*
`root_prop` is highest when alpha issuance is lowest — i.e. when a subnet is young. The author states the intent: *new entrants get an easier on-ramp; incumbents must keep earning their share on price.* For a startup using emission as runway this is the opposite of a disaster — it **front-loads operating capital into the early, most capital-constrained period** and tapers it over roughly the 30-month exit window. The chain is generous to the young and stingy to the old. You are the young.

### The extraction trap (the part not yet fully clocked)
Owner emission is paid in **alpha**, not cash. To turn it into operating capital you sell alpha into your own pool, which:
1. pushes your price **down** (AMM slippage), and
2. under price-coupling, **reduces your future emission**.

So extraction now carries a reflexive cost it didn't have before. What makes extraction viable is **pool depth** (the TAO reserve), and pool depth comes from TAO injection, which scales with `emission_share` — which the 75% burn is currently throttling by 75%. So the burn hurts a *third* way: it keeps the pool thin, making the emission you do get harder to convert to cash without cratering your own market. *(Modelled in §4, Scenario S4.)*

### The unlock — reducing the burn fixes everything at once
| Effect of cutting the burn | Mechanism |
|---|---|
| Bigger owner slice | `(1−b)` rises → emission_share rises linearly |
| Deeper pool, easier extraction | higher emission_share → more TAO injection → less slippage |
| Price support | higher emission_share → more staker yield → more buy-side demand |
| Stronger genuine-mining signal | paying miners more is exactly what the triumvirate's fake-mining detector wants to see (R-O) |
| No participation risk | 28→32→88 scored miners at 25% payout proves retention is not the binding constraint |

### Reason-one is strengthened, not threatened
SN21 was joined for (1) access to mining talent and (2) emission as early-stage operating capital. This mechanism **punishes owners who don't pay miners** — i.e. Bittensor is doing the *opposite* of dissuading mining. Reason one is reinforced. The same change that worried us on reason two strengthens reason one, and reducing the burn serves both simultaneously.

### Honest limits on this thesis
The **direction** is confident; the **magnitude** is empirical and currently unknown: how high `root_prop` actually is for SN21 today, how much we can extract before moving price, and the shape of the decay curve. Those are precisely what the test lab (§4) exists to measure. Until it runs, treat §2 as a calibrated hypothesis, not a settled conclusion.

---

## 3. Risk register snapshot (post-v0.8, carried)

| ID | Risk | Priority | Note |
|---|---|---|---|
| **R-Q** | 75% burn cuts total emission_share to 25% | **P1 top** | self-inflicted, recoverable |
| R-M | root_prop structural decay | P1 | reframed in §2 as acceptable front-loading |
| R-N | price ↔ emission coupling | P1 | the new market-contingency |
| R-C | redemption / AMM cascade | P1 | amplified by price term |
| R-O | discretionary boolean burn (validator/triumvirate) | P1 tail | burn reduction also removes the bad optic |
| R-K | validator-yield surfacing (Q6) | P2 | — |
| R-P | sparse-epoch burn-key leakage | P2 | partly moot at high deliberate b |
| R-H | neutrality removal | P2 | — |
| [MERGE] | Yuma consensus drag | P2 | — |
| R-D | Taoflow reflexivity | retired | premise obsolete |

Full write-ups: v0.7 (R-M/N/O/P), v0.8 (R-Q).

---

## 4. Empirical Test Lab — `sn21-emission-lab`

**Purpose:** a *separate* repo that pulls SN21's real chain state, implements the incumbent and new emission mechanisms from the actual subtensor source, and lets us see old-vs-new, the optimal burn, the decay curve, and extraction economics — as charts and tables, no math background required.

**Suggested repo:** `ippcteam/sn21-emission-lab` (separate from `SN21-adtao` and `sn21_monitor`).
**Stack:** Python · `bittensor` SDK + async subtensor RPC · taostats API (cross-check) · `pandas` · `matplotlib`/Chart.js · `pytest`. Optionally surface outputs into the existing `sn21_monitor` dashboard.
**Owners:** Khurram (architecture, data layer, tests) · Jayesh (mechanism models, scenarios, ML/data) · Rob (consumes outputs, decisions).

### 4.0 Ground truth — read the code, not the blog
The `const_reborn` post is the *conceptual* guide; it simplifies. The authoritative formula lives in the subtensor source at the `v3.4.6-421` release (the coinbase / emission pallet). **Task 0:** extract the exact `emission_share`, `root_prop`, EMA-price, and `miner_burn` computations from that source and implement *those*, using the post only to interpret intent. This directly addresses the opacity: the mechanics become code we own and can step through.

### 4.1 Data layer — `chain_pull.py` (and what each symbol really is)
Pull for netuid 21 (and, where noted, all netuids for normalization):

| Symbol / quantity | Plain name | Source | Notes |
|---|---|---|---|
| `A` (α_i) | your issued alpha | metagraph / `SubnetAlphaOut(21)` | grows each tempo |
| `R` (T_root · w) | network root weight | total root stake × `tao_weight` hyperparam | global; query both parts |
| `price_i` (EMA) | market salary | subtensor moving-price storage | the EMA, not spot |
| spot price | for slippage/extraction | pool reserves: `SubnetTAO(21)` / `SubnetAlphaIn(21)` | TAO_reserve / alpha_reserve |
| pool reserves | TAO & alpha depth | as above | extraction model input |
| `b` (miner_burn) | attendance gate input | metagraph incentive vector + owner/burn UID | ≈0.75 for us — confirm the UID |
| net flow (EMA) | incumbent-model input | taostats subnet flow / staking events | for reproducing today |
| all-subnet `price_j` | normalization Σ | iterate netuids | emission_share is *relative* |

**Emission_share is a share:** SN21's slice = SN21's score ÷ sum of all subnets' scores. The lab must pull (or reasonably approximate) every subnet's inputs, or it will model the numerator without the denominator.

### 4.2 Mechanism models — `mechanisms.py`
Implement, each as a pure function matching the source:
- `incumbent_emission_share(...)` — whatever is live today (confirm via Action 0; most likely Taoflow / net-flow, with the zero-floor for negative flow). Optionally also `legacy_price_share(...)` (pre-Taoflow pure price).
- `new_emission_share(root_prop, price, b)` — the product of the three switches.
- Both normalized across subnets to yield SN21's actual slice.

### 4.3 Validation milestone — reproduce today (the credibility anchor)
**Before any scenario runs:** feed real current inputs into `incumbent_emission_share` and check the output matches SN21's *actual* current emission as reported by taostats, within tolerance. 
- **Match** → the engine is trustworthy → proceed to scenarios. 
- **No match** → the model is wrong → fix it, do not act on projections. 
This is the test that lets a non-mathematician trust the rest: *the model can rebuild reality before it predicts.*

### 4.4 Scenarios — `scenarios.py`
Each scenario states the question, the output to read, and the decision it informs.

| ID | Question | Method | Output to read | Decision |
|---|---|---|---|---|
| **S1** | What changes for us at activation, all else equal? | Plug current real numbers into incumbent vs new; report SN21 slice + absolute owner emission under each | Two-bar comparison: owner emission old vs new | Size of the activation shock (at current b) |
| **S2** | What burn rate maximizes our operating capital? | Sweep `b` 0→0.75; compute owner emission, miner pay, TAO injection at each | Curve: owner emission vs `b` (expect it to *rise* as `b` falls) | **Target `b`** (D-Q) |
| **S3** | How fast does the youth allowance fade? | Project `A` (alpha issuance) forward from current rate; recompute `root_prop` and owner emission over 30 months | Decay line to 2028 | Runway profile; input to the financial model |
| **S4** | How much cash can we actually extract per week, and at what price cost? | Simulate selling weekly owner alpha into the pool (constant-product slippage); vary pool depth (which depends on `b`) | Realized TAO and price impact per extraction rate | **Sustainable weekly extraction** without cratering price |
| **S5** | Is reducing the burn safe given miner dumping? | Model miners receiving more alpha at lower `b`, selling some fraction; net price = added TAO injection − added sell pressure; sweep the "miner sell fraction" assumption | Sensitivity band: net price effect vs sell-fraction | **Safe step size** for burn reduction |

### 4.5 Reporting — `report.py` / notebook
- Charts: S1 old-vs-new bars; S2 burn-sweep curve; S3 decay line; S4 slippage curve; S5 sensitivity band.
- Auto-generated plain-language summary per scenario ("at b=0.45, owner emission is X× current, pool depth Y× current, safe given miner sell-fraction below Z%").
- Optional: pipe into `sn21_monitor` Chart.js for a live view.

### 4.6 Property tests — `tests/`
Encode the post's claimed properties and confirm our implementation honours them:
- **Symmetry:** a buy and an equal sell move the emission vector equal-and-opposite (V2 pools).
- **No memory:** `b` recovers full emission the next tempo after burning stops.
- **Linear burn:** `emission_share` scales linearly with `(1−b)`.
If our code reproduces these, it matches the chain's stated intent; if not, we've misread the source.

---

## 5. Action steps — re-anchored on the lab

| # | Action | Test / verification | Owner | When |
|---|---|---|---|---|
| 0 | Confirm `v3.4.6-421` live status + activation block; confirm which mechanism is currently live | release notes / chain query | Jayesh | Immediate |
| 1 | **Stand up `sn21-emission-lab`; extract exact formulas from subtensor source** (Task 0) | Code compiles; formulas traced to specific pallet functions | Khurram + Jayesh | Days 1–3 |
| 2 | **Pass the reproduction milestone (§4.3)** | Modelled current emission matches taostats within tolerance | Khurram + Jayesh | Day 4 — gates all decisions |
| 3 | Run S1 (old-vs-new) and S2 (burn sweep) | Owner-emission shock quantified; target `b` identified | Jayesh | Week 1 |
| 4 | Run S3 (decay), S4 (extraction), S5 (dump safety) | Runway curve; sustainable extraction; safe step size | Jayesh | Week 1–2 |
| 5 | **Re-run financial / vesting model** with lab outputs (R-Q + R-M + extraction) | Owner emission to 2028 under real `root_prop`, target `b`, extraction constraint | Rob + John Davy | Week 2 |
| 6 | **Controlled burn step-down** from lab's target `b` and S5 step size | 0.75 → first step, with abort thresholds on price/depth/retention | Rob + Tensora | After lab |
| 7 | Live `b`, `root_prop`, price-EMA monitors in `sn21_monitor` | Per-tempo metrics + alert if `b` drifts | Khurram | On activation |
| 8 | Triumvirate legibility dossier (R-O) | active miners, distribution spread, score variance, code liveness | Jayesh + Khurram | 2 weeks |
| 9 | Quantify Yuma consensus drag; own-validation robustness | vtrust / weight divergence vs third-party validators | Jayesh + Tensora | 2 weeks |

**Reading order for a non-mathematician:** S1 shows the shock → S2 shows the fix → S3 shows the runway shape → S4/S5 show how to extract and how fast to move. Never act on a scenario until Action 2 (reproduction) has passed.

**Channel discipline:** nothing about burn, price, or emission economics on any public channel. Miner payout changes → SN21 Discord with advance notice; changes apply from the start of the next epoch, never mid-epoch.

---

## 6. Open gaps & decisions

- **[GAP G-9.1]** Exact source-level formulas for `emission_share` / `root_prop` / EMA price / `b` in `v3.4.6-421` (Action 1). Until extracted, §1–2 are conceptually correct but numerically unconfirmed.
- **[GAP G-9.2]** Which mechanism is live today (incumbent for the reproduction test)? (Action 0)
- **[GAP G-9.3]** The current `root_prop` value for SN21 and its forward decay rate — unknown until S3 runs.
- **[D-Q]** Target burn rate and step-down schedule — set by S2 + S5, not by intuition.
- **[D-Q2]** Does the live financial model treat the burn as costless to emission_share, and does it assume flat (market-agnostic) emission? If yes on either, it overstates owner emission and must be rebuilt (Action 5).
- **[D-9.1]** Align Tensora + DSV: the prior 75% advice was correct for the old mechanism and is now inverted; agree the principle before changing payout.

---

*v0.9 — the mechanism is opaque only until it's code we own. Reproduce today, then model tomorrow, then act. Direction is clear; the lab supplies the numbers.*
