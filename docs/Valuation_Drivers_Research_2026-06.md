# SN21 Valuation Drivers — Research Record & Conclusions

**Author:** Engineering, for Rob
**Date:** 2026-06-30
**Mandate:** SN21 ranks **89/128 by alpha value**. Establish, with evidence, *what actually drives subnet valuations*, validate Rob's 11 hypotheses, and define demand-side levers to hit the milestones: **top-50 = 0.008 TAO, top-25 = 0.014, top-10 = 0.030** (all validated against live rank-prices).
**Data:** live finney chain (`all_subnets()`, `MinerBurned`, emission storage); taoflute Grafana→Postgres (`delegation_history`, `snapshot_history`, `materialized_overview_data`, `materialized_news`); multi-agent web research. Pulled 2026-06-29, block ~8,514,243.
**Reusable artifacts:** `flow_events.py`, `cross_section.py` (committed); decomposition/trajectory scripts; 6 memory records (`sn21-valuation-decomposition`, `sn21-flow-event-study`, `sn21-cross-section`, `sn21-qualitative-drivers`, plus corrections to `sn21-owner-share-stake-watch`).

---

## 1. Executive summary

**SN21's constraint is no longer "do the right activities" — it is "convert attention into staked, durable TAO."** Five independent analyses converge:

1. **Alpha value = demand ÷ float.** SN21 is a **high-float** subnet (90th percentile circulating alpha), not a low-demand one. It already holds *more pool-TAO than the subnets ranked just above it*; it prices lower purely because its demand is diluted across ~5× more float. Float is structural and rising ~4%/month, so **demand is the only lever**, and the milestone target *rises over time*.
2. **SN21 was effectively pre-operational until late May 2026** (dormant from registration ~Mar 2025; public launch + crowdfund late March 2026; 100% burn until mainnet activation late May). The long-run trajectory therefore measures a *dormant* subnet and is **not** a verdict on the operating one; the 5.37M float is largely an **inherited overhang** from that period, not active dilution. In the only meaningful window — **~6 weeks operational (mid-May→now)** — third-party flow shows a launch pop (+19.5 TAO) then **6 consecutive weeks of net selling** (~−8 TAO/wk, ≈−51 total); price −10.6%; float still +~1%/wk. The demand problem is real and operational — but the dataset is **6 weeks, not a year**.
3. **Demand follows tangible economic substance, not narrative.** Three separate analyses (flow event study → *yield*; cross-section → *owner commitment*; qualitative coding → *revenue*) all point the same way. Simplicity, crypto-adjacency, whitepapers, and product-model are **null** in the data.
4. **The market may be too young for fundamentals to dominate.** Only ~3/46 sampled subnets have verifiable revenue; the signal is real but modest and confounded — a *bet on where a maturing market is heading*, not a proven law today.
5. **SN21's recent +19% had no buyer behind it.** Third parties were net sellers (−18 TAO/14d); the owner side holds (verified, zero outflow); the rise was emission optics. X is working at the **top of the funnel** (attention, holders) and breaking at **conversion to staked TAO**.

**The single highest-leverage lever — and the only one that doesn't require owner treasury — is giving external holders a reason to stake and hold** (staking-gated product access / yield), turning the attention SN21 already wins into the sticky flow the rank responds to.

---

## 2. Method

Alpha price in dTAO is mechanically an AMM ratio, `tao_in / alpha_in`. We separated:
- **Proximate cause** (accounting): float vs demand, fully on-chain, confounder-free.
- **Distal causes** (Rob's 11 hypotheses): theories of *what generates net TAO inflow*.

Because n≈64 active subnets with ~20 candidate factors invites overfitting and confounding, we **triangulated three methods** that fail differently: cross-sectional correlation (breadth), event studies (causal-ish, within-subnet time series), and qualitative case coding (mechanism). A finding is trusted when methods agree. The dependent variable throughout is **net non-owner TAO inflow** — the binding lever — not the daily price pump.

---

## 3. Findings by analysis

### 3.1 Decomposition (proximate cause)
- SN21: rank 89/128, price 0.004345, 31st pctile. Pool `tao_in` 8,309 TAO, `alpha_in` 1.91M, circulating `alpha_out` 3.46M (**90th pctile float**).
- vs the top-25 *cohort median*, the gap is **78–91% demand-side** (real winners hold 30k–72k TAO). vs the *rank-20–30 boundary*, it flips to **141% float-side** — SN21 has **more** pool-TAO than the marginal subnets and is held below them only by ~5× larger float.
- **Longevity is a float liability, not an asset** (hypothesis #9 inverted): old subnet ⇒ large cumulative issuance ⇒ permanent price drag.
- **Demand-path cost** (constant-product, sticky net inflow): **+2,966 TAO** (top-50), **+6,606** (top-25), **+13,524** (top-10).

### 3.2 Trajectory (time-series decomposition) — SCOPED to operational history
**Critical scope:** SN21 was dormant/pre-operational until **late-May 2026 mainnet activation** (registered ~Mar 2025; public launch + crowdfund late March 2026; 100% burn until late May). The full-window numbers below describe a *dormant* subnet accruing emission with no product to absorb it — **do not read them as a verdict on the operating subnet**; they explain *why* the float overhang exists.
- Pre-operational/full window (context only): `tao_in` +196%, float +184%, price +47%; the rise was **protocol emission, not buying** (net user flow −151 TAO). This is expected for a dormant subnet.
- **Operational window (mid-May→now, ~6 weeks — the meaningful data):** price 0.00499 → 0.00446 (**−10.6%**, dip to 0.00353 on 6/05 then recovery); float 5.04M → 5.37M (**+~1%/week, still growing**); third-party flow = **+19.5 TAO launch week, then 6 straight weeks of net selling** (~−8 TAO/wk, ≈−51 total). The demand problem is **confirmed operational**, not a dormancy artifact — but it is only 6 weeks of data. Plausible mechanism: **crowdfund/launch participants distributing** after the activation pop.

### 3.3 Flow event study (`flow_events.py`)
DV = abnormal non-owner flow; built-in placebo calibrates the null (t≈0, validated).
- **`emissions_recovered`: t=+2.11 (7d), +2.64 (21d)** — the *only* event that draws durable outside inflow; it **builds over 3 weeks**. Flow chases **yield/survival**.
- **`miner_burn`: t=−3.18** — burn *spikes* precede outflow. But SN21's burn level (`MinerBurned` 0.772) is **53rd pctile — typical**, so burn-reduction is a *low-value* lever for SN21.
- **Owner-buyback → third-party flow: t=−0.19 (null).** Buybacks bring no follower impulse.
- Dev commits, registrations, name/twitter changes: null.

### 3.4 Cross-section (`cross_section.py`)
DV = net non-owner inflow, controlled for float + age, n=64.
- **`owner_deposits` is the only robust positive factor** (partial ρ +0.285 @90d, +0.515 @30d). Supports buyback-as-**posture** (correlate of commitment), *not* as a trigger — exactly Rob's framing. Correlational and confounded.
- **Null:** social cadence (X/discord/has-twitter), multi-subnet ownership, whale concentration, miner-burn level, dev activity, age. **Posting frequency does not separate demand.**

### 3.5 Qualitative coding (multi-agent, n=46 stratified sample)
Six web-verifying agents coded Rob's hypotheses #1–6; merged and correlated.
- **vs value *level* (log price): all six hypotheses NULL.** Positioning does not set value.
- **vs *demand*: only revenue (#4) significant** (partial ρ +0.263, z=2.1). Partnerships/product-model weak; simplicity/crypto-adjacency/whitepaper null.
- **Revenue=2 subnets all share third-party-VERIFIABLE proof:** Chutes (OpenRouter public leaderboard), lium (revenue > emissions), NATIX (Grab as named customer). Not self-reports.

**SN21 scorecard vs sample mean:** revenue **0** vs 0.41 (biggest gap, on the one demand driver); output-is-product **0** vs 1.52 (bottom — AdTAO consumes output internally, but weak driver); simplicity **3** vs 3.15 (**average — "too complex" worry unfounded**); crypto-adjacency **0** vs 0.59 (minority, null); whitepaper **1** vs 0.13 (rare — and **buys nothing**, null on both DVs).

---

## 4. Recent natural experiment + owner-flow correction

Rob stepped up X, announced 2 named customers, reports +8% holders; **price rose ~+19%** (6/08→6/29, peak +22.7%). On-chain reality:
- **Non-owner net flow −18.2 TAO** (third parties net *sellers*); sells > buys nearly every day. **No net buyer** — the rise was protocol emission against real selling.
- **Holder count up + net TAO down = broad but shallow:** small wallets in, larger holders out. X drives the **top of funnel**, not conversion to staked TAO.

**Correction (Rob caught a misclassification, twice):** the `Owner21` hotkey's daily ~1.6 TAO is **owner-key emission accruing**, then split 25%/25% to Rob (`5DkEA…`, the documented owner-share coldkey) and investor (`5Ft5Ji…`). The `is_transfer` leg is **distribution, not a sale**. Traced both destinations → **neither sells; both hold. Zero owner outflow.** The name-based "owner buying / owner propping" claims in earlier drafts were wrong and have been retracted; `flow_events.py` is annotated. The event-study and cross-section results use **non-owner** flow and are unaffected. Net: the owner side is a model holder; **the demand gap is entirely external.**

---

## 5. Verdict on Rob's 11 hypotheses

| # | Hypothesis | Verdict |
|---|---|---|
| 4 | Reported revenue | **Supported** — the one qualitative demand driver, *if third-party-verifiable*. SN21's is self-reported ⇒ codes ~0. |
| 11 | Alpha buyback | **Supported as posture**, not as a flow trigger. Owner can't fund material buys ⇒ not a primary lever. |
| 7 | Comms / X | **Untested→partly live.** Works for attention/holders; does **not** convert to staked TAO on its own. |
| 1 | Mining-output-is-product | Weak. SN21 is the extreme (internal consumption) but it's a minor driver. |
| 2 | Simplicity | **Null.** SN21 is average, not complex. |
| 3 | Crypto-adjacency | **Null** (mild headwind at most). |
| 5 | Partnerships | Weak; most subnets lack them too. |
| 6 | Whitepaper | **Null.** SN21 has the rare one; it buys nothing. |
| 8 | Institutional investment | Weak (whale concentration shows only at 30d). |
| 9 | Longevity | **Inverted — a float liability.** |
| 10 | Multiple subnets per owner | **Null.** |

**Stop investing in:** whitepaper polish, simplicity messaging, crypto-repositioning — unrewarded by the data.

---

## 6. Conclusions

1. SN21's price problem is **structural float + absent external demand**, masked by protocol emission. The owner side is behaving correctly (accrue and hold).
2. **No observable lever strongly manufactures demand.** The best-supported signals (revenue, yield, owner commitment) are correlational and point at *tangible substance over narrative* — and the dTAO market may be too immature to price fundamentals yet.
3. SN21 already wins **attention** (active X, amplification, named customers, holder growth). It does not yet win **staked, durable TAO**. The funnel breaks at **holder → staker**.
4. The owner **cannot be the demand** (treasury-constrained, and the math dwarfs any buyback). The owner's role is to **catalyze** external demand and **not dump** (already true).

---

## 7. Next steps

**P1 — Build the holder→staker conversion mechanism (the core lever).**
Give external alpha-holders a reason to stake and hold, not flip: staking-gated access to the AdTAO product (advertisers/agencies must hold alpha to use it), staker yield, or governance. This is the only lever that converts existing attention into sticky flow *without* owner treasury, and it echoes the one proven driver (yield).

**P2 — Make revenue third-party-verifiable.**
Move proof off self-published posts onto a scoreboard SN21 doesn't control: a **named advertiser/agency customer**, a **public realized-results dashboard**, on-chain settlement tied to real ad spend. Add an **accountant-signed report** specifically for the institutional/OTC diligence track (weaker for crypto stakers, strong for funds).

**P3 — Forward flow-capture harness.**
Extend `flow_events.py` to snapshot **net non-owner flow** at +1/+3/+7d around each future proof-point (customer announcement, staking-utility launch, campaign) vs baseline — turning each move into a measured test of "did this convert to sticky TAO," in real time rather than weeks later. (Now de-risked: we know non-owner flow is the clean signal.)

**P4 — Owner self-funding flywheel.**
Where capital exists, recycle a slice of the TAO emission cut / future revenue into **visible** buy-and-hold (TAO-denominated, no USD needed). Owner catalyzes; revenue funds.

**P5 (optional) — Peer case studies.**
Deep-dive mature, high-float subnets that climbed anyway (SN21's true comparison class) for the causal mechanism behind a flow turnaround.

---

## 8. Caveats

**Operational history is only ~6 weeks** (mainnet activation late-May 2026): SN21-specific trajectory/flow numbers spanning before that describe a *dormant* subnet and are scoped accordingly (§3.2). SN21's own −34 TAO/90d flow figure is partly pre-operational; the field/cross-section correlations (other subnets) and the current-snapshot decomposition are unaffected. Other caveats: observational data; correlational findings with reverse-causality and confounding risk (especially revenue ↔ general legitimacy); n=46–64 with modest effect sizes and multiple-comparison exposure; owner-detection by name is unreliable (corrected); X content quality and private/OTC capital are unobservable. The conclusions are directionally robust because methods triangulate, not because any single correlation is decisive.
