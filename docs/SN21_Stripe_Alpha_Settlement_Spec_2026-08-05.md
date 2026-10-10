# SN21 — Stripe → α Settlement Contracts (Delivery Bond)

**Date:** 2026-08-05 (rev 3 — billing mode; Sep revenue; variable burn)  
**Status:** Draft for decision  
**Owner:** Rob Warner  
**Depends on:** [Valuation_Drivers_Research_2026-06.md](Valuation_Drivers_Research_2026-06.md), [SN21_Disposition_2026-07-31.md](SN21_Disposition_2026-07-31.md), [SN21_Miner_Burn_Recommendation_2026-07-02.md](SN21_Miner_Burn_Recommendation_2026-07-02.md) §7.3 (conviction), [SN21_Alpha_Lock_Policy_2026-07-31.md](SN21_Alpha_Lock_Policy_2026-07-31.md)

**Strategy docs (thesis + proof linkage — start here):**

1. [On-Chain Performance Reporting](SN21_Strategy_OnChain_Performance_Reporting_2026-08-05.md) — proof oracle  
2. [USD Delivery Bond](SN21_Strategy_USD_Delivery_Bond_2026-08-05.md)  
3. [α Payment Rail](SN21_Strategy_Alpha_Payment_Rail_2026-08-05.md)  
4. [Affiliate Rail](SN21_Strategy_Affiliate_Rail_2026-08-05.md)

This file is the **combined mechanics** reference for engineers.

---

## 1. Doctrine

**Three rails, one registry:**

1. **USD rail (Web2):** Advertiser pays Stripe. AdTAO settles a published fraction of each net payment as an on-chain α delivery bond. Remark hashes to the Stripe payment id.
2. **α rail (BT-native):** Buyer pays in α at a **published commercial discount** to the USD list. Payment α goes to Vault (burn + bond) — native demand, no Stripe.
3. **Affiliate rail:** On USD purchases, referrer elects **USD cash** or an **α premium** (plain-staked vest). Same registry attributes the payout.

Web2 customers never need a wallet. BT natives are rewarded for paying in α. Every economic event is auditable.

**Revenue timing (commercial):** Significant external revenue is expected from **September 2026**, when prediction products and automate-toward-goal can launch as sellable SKUs. Until then, rails + registry still run on whatever Stripe volume exists (pilots, setup, early retainers) so the capture mechanism is live before the inflection — not invented after.

**Burn rate (tokenomics):** Miner-emission burn and related subnet tokenomic levers stay **variable policy**. They are driven by Bittensor formula changes, competitive emission dynamics, and miner-pool behaviour ([Miner Burn Recommendation](SN21_Miner_Burn_Recommendation_2026-07-02.md)). This settlement stack does **not** hard-pin emission burn. What stays durable and published here is **commercial capture** (`settle_bps`, registry, outcome close). Settlement success-burn / α-rail burn splits below are **v1 operating defaults** — adjustable by published policy update, not frozen tokenomics.

---

## 2. What this is / is not

| Is | Is not |
|---|---|
| Dual list price: USD and discounted α | Token-gating the Ads UI for CMOs |
| Ops settlement + optional native α checkout | Discretionary FOMO buybacks |
| Verifiable Stripe / extrinsic / α-pay links | Forcing advertisers to hold α |
| Stripe **subscription vs one-time** on every USD bond | Treating all Stripe cash as equivalent ARR |
| Plain stake + settlement burns (conviction-safe) | HotkeyLock / conviction locks for settlement or affiliates |
| Affiliate choice: USD or α premium | Paying affiliates in HotkeyLock “conviction” |
| Living emission-burn policy (separate lever) | A hard emission-burn covenant inside this settlement contract |

**Hard constraint:** no `HotkeyLock` / conviction locks on Vault, payment, or affiliate legs. “Locked” in this doc means **plain stake with a published vest schedule** (policy + registry), not chain conviction locks. Owner defense locks stay separate.

---

## 3. Actors & keys

| Actor | Role |
|---|---|
| **Advertiser (USD)** | Pays Stripe. Never sees α. |
| **BT-native buyer** | Pays invoice in α to Pay-in address / Vault at α list price. |
| **Affiliate / referrer** | Brings buyer; elects USD or α premium on attributed USD sales. |
| **AdTAO Co. (ops desk)** | Runs Settlement Engine; AMM buyer on USD rail. |
| **Settlement Vault** | Public coldkey. Holds plain-staked bonds + Proof Reserve. |
| **Affiliate Vault** | Public coldkey (or sub-account). Stages α premiums before vest release. |
| **Buy Executor** | AMM/OTC acquire α; remark batcher. |
| **Public Registry** | Stripe hash / α-pay hash / affiliate id ↔ extrinsics ↔ bond state. |
| **Miners** | Unchanged; retention = plain stake per lock policy. |

---

## 4. Contract objects

### 4.1 Delivery Bond (unchanged core)

```text
Bond {
  bond_id, rail             // "usd" | "alpha"
  stripe_payment_id?        // usd rail only (private)
  stripe_hash?              // sha256("adtao-v1|" + stripe_payment_id)
  billing_mode              // "subscription" | "one_time" | "unknown"
  stripe_invoice_id?        // when payment is invoice-backed
  stripe_subscription_id?   // set when billing_mode = subscription
  stripe_price_id?          // Price / Product linkage for SKU analytics
  alpha_pay_extrinsic?      // alpha rail payment extrinsic
  alpha_pay_hash?           // sha256("adtao-v1|alpha|" + extrinsic)
  referrer_id?              // affiliate code if any
  usd_gross?, usd_net?      // usd rail
  alpha_paid?               // alpha rail: α received from buyer
  settle_bps
  usd_to_alpha?             // usd rail settle budget
  alpha_target, alpha_filled
  fill_extrinsics[]
  vault_coldkey
  status                    // pending_fill | active | success_closed | fail_closed | refunded
  outcome_refs[]
  opened_at / closed_at
}
```

### 4.1.1 Billing mode (Stripe → bond)

USD-rail bonds must classify revenue quality for capital diligence (recurring vs one-off). Derive at webhook time; never invent ARR from unclassified cash.

| Signal | `billing_mode` | Notes |
|---|---|---|
| PaymentIntent / Charge linked to an Invoice with `subscription` set, or `invoice.paid` for a subscription invoice | `subscription` | Store `stripe_subscription_id`, `stripe_invoice_id`, `stripe_price_id` |
| Checkout / PaymentIntent with `mode=payment`, or invoice with no subscription | `one_time` | Setup fees, one-shot campaigns, non-recurring invoices |
| Ambiguous / missing linkage after retries | `unknown` | Settle still runs; scoreboard excludes `unknown` from “recurring” totals until resolved |

**Same settle math for both modes in v1** (`settle_bps` uncapped). Classification is for registry, scoreboard, and reverse-valuation — not a different capture rate.

**α rail:** set `billing_mode` from the commercial SKU (retainer → `subscription`, pilot/setup → `one_time`) even though there is no Stripe object.

### 4.2 Affiliate Payout

```text
AffiliatePayout {
  payout_id, bond_id, referrer_id
  election              // "usd" | "alpha"
  basis_usd_net         // attributed invoice net
  usd_bps               // if usd election
  alpha_premium_bps     // if alpha election (on basis, converted at fill)
  usd_paid_cents?
  alpha_filled?
  vest_days             // plain-stake hold before releasable (alpha election)
  extrinsics[]
  status                // pending | vested | released | clawback
}
```

---

## 5. Economics

### 5.1 Delivery bond (USD rail) — **no monthly cap**

| Param | v1 value | Rationale |
|---|---|---|
| `settle_bps` | **1500 (15%)** of **net** fee | Visible; 85% remains for ops + affiliates |
| `monthly_usd_cap` | **None** | Removed — settle scales with revenue |
| `per_invoice_floor_usd` | **$25** | Tiny invoices still create a bond |
| `per_invoice_ceil_usd` | **None** as economic cap | Ops may **slice** large fills across multiple AMM txs for slippage; not a budget ceiling |
| Funding waterfall | (1) USD → AMM/OTC buy · (2) owner-cut α at MTM if cash timing gap · (3) public `underfunded` if both short | Never silent fail |
| Success burn / retain | **50% / 50%** Proof Reserve (90d) | **v1 default** — settlement burn split is adjustable policy (publish before change); not emission burn |
| Fail close | **100%** return to treasury | |
| Refund reserve | Hold **10%** of settle budget in USD **14d** before buy | Chargeback buffer |
| Billing mode | From Stripe (§4.1.1) | Scoreboard splits subscription vs one-time settled USD |

**Example:** $1,000 net → $150 α budget → buy/stake to Vault with `stripe_hash` remark.

**Cash reality:** uncapped settle means ops must treat 15% as true COGS. If a month is cash-tight, waterfall (2) keeps the Stripe↔α link alive using owner-cut α — the registry shows `funding: owner_alpha` vs `funding: amm_buy` so we never fake market demand.

### 5.2 α payment rail (BT-native) — commercial advantage

**Dual list price** (publish both):

| | USD list | α list |
|---|---|---|
| Definition | Stripe price `P_usd` | Pay-in α amount `P_alpha` |
| Formula | — | `P_alpha = (P_usd × (1 − alpha_discount)) / spot_alpha_usd` |
| v1 `alpha_discount` | — | **30%** off USD list (significant, not suicidal) |
| Quote life | — | Spot TWAP **30 min**; quote valid **15 min** |
| Min ticket | — | ≥ **$50** USD-equivalent at quote |

**Where the α goes on pay-in:**

| Slice | % of α received | Destination |
|---|---|---|
| Instant burn | **40%** | **v1 default** — adjustable; permanent sink while in force |
| Delivery bond | **60%** | Vault plain stake; same success burn/reserve policy as USD rail |

No second 15% “settle” on top — the buyer already paid in α; splitting burn/bond *is* the settlement.

**Why this is useful:**

- Real α bid from people who already hold it (the missing Web2 proxy).
- 30% discount is the commercial reason to choose the rail.
- Instant 40% burn makes wash-trading expensive (pay α → get service worth 70¢ on the dollar → 40% gone immediately).
- Same public registry / outcome machinery as USD bonds.

**Anti-abuse:**

- One coldkey cannot circle-wash: burn is immediate; service credit is non-transferable; no α refund on cancel (USD credit only at ops discretion).
- α rail disabled for invoices already tagged to a USD affiliate election in the same period (pick one rail).

### 5.3 Affiliate scheme (USD purchases)

Attributed when checkout carries `ref=` / Stripe metadata `referrer_id`.

| Param | v1 | Notes |
|---|---|---|
| `affiliate_usd_bps` | **1000 (10%)** of **usd_net** | Paid in USD (Stripe Connect or monthly wire) |
| `affiliate_alpha_premium_bps` | **1500 (15%)** of **usd_net** | Higher than USD option — the α premium *is* the incentive to take α |
| Vest (α election) | **90 days** plain-staked on Affiliate Vault / referrer coldkey | Policy vest; **not** HotkeyLock |
| Clawback | Full if chargeback/refund in 60d | |
| Stacking with settle | Affiliate taken from **ops share** (the 85%), **then** 15% settle applies to net **after** affiliate USD accrual | α premium: convert bps → USD notional → buy/transfer α (extra AMM bid) |
| Cap per referrer | None in v1 | Monitor concentration; add later if gamed |
| Who can affiliate | KYC’d partners / known coldkeys | No anonymous Sybil farm |

**Waterfall on a $1,000 net USD invoice with α-electing referrer:**

1. Affiliate α premium notional = 15% × $1,000 = $150 → AMM buy α → stage on Affiliate Vault with 90d vest remark.  
2. Delivery settle = 15% × $1,000 = $150 → AMM buy α → Vault bond (same as today).  
3. Ops retains $700 cash (before Stripe fees / tax).  

**If referrer elects USD:** $100 cash affiliate; $150 α bond; ops $750.

**α-rail purchases:** no USD affiliate cash (no Stripe). Optional v2: α-rail affiliate = extra **5%** of `alpha_paid` vested to referrer from ops treasury α — defer until USD rail is live.

---

## 6. Lifecycles

### 6.1 USD rail (+ optional affiliate)

```text
Stripe succeeded (+ referrer_id?)
  → Bond(pending_fill) + optional AffiliatePayout(pending)
  → [affiliate α premium buy if elected]
  → [15% settle AMM/owner-α buy → Vault + remark(stripe_hash)]
  → Bond(active)
  → outcome → success: burn 50% / reserve 50%
            → fail: return bond α to treasury
  → affiliate: release after vest or clawback
```

### 6.2 α rail

```text
Buyer accepts quote → transfers P_alpha to Pay-in
  → remark(ADTAO|ALPHAPAY|v1|<hash>|<invoice_id>)
  → 40% burn + 60% Vault bond
  → Bond(active, rail=alpha)
  → same outcome close as USD rail
```

### Outcome calendar

| Phase | Success definition |
|---|---|
| Now | Attested KPI + customer ack (PDF hash) |
| Week 2–3 | On-chain prediction `window_id` ≥ baseline |
| Week ~10 | Autonomous window ≥ baseline |

---

## 7. Verification

### 7.1 Hashes

```text
stripe_hash    = sha256("adtao-v1|" + stripe_payment_id)
alpha_pay_hash = sha256("adtao-v1|alpha|" + payment_extrinsic_hash)
affiliate_hash = sha256("adtao-v1|aff|" + payout_id + "|" + referrer_id)
```

### 7.2 Remarks

```text
ADTAO|BOND|v1|<stripe_hash>|<bond_id>
ADTAO|ALPHAPAY|v1|<alpha_pay_hash>|<invoice_id>
ADTAO|AFF|v1|<affiliate_hash>|<payout_id>
```

### 7.3 Public registry

Scoreboard tabs: **USD bonds · α pays · Affiliates · Burns**.  
USD bonds (and totals) split **subscription / one-time / unknown**.  
Anyone with a Stripe receipt or explorer extrinsic can verify.

---

## 8. Components to build

| # | Component | Notes |
|---|---|---|
| 1 | Stripe webhooks | `payment_intent.succeeded`, `invoice.paid`, `customer.subscription.*`, refund, Connect payout — resolve billing_mode |
| 2 | Settlement Engine | settle_bps, floors, waterfall, affiliate election, billing_mode |
| 3 | α quote + Pay-in watcher | TWAP, 15m quotes, pay-in coldkey monitor |
| 4 | Buy Executor + remark batcher | USD settle + affiliate α premium |
| 5 | Vault / Affiliate Vault | plain stake only |
| 6 | Registry + scoreboard | three rails; subscription vs one-time totals |
| 7 | Outcome closer | attest → windows |
| 8 | Monitor hooks | fills, settlement burns, α-rail volume, affiliate mix, underfunded, recurring share of settled USD |

---

## 9. Policy interactions

| Policy | Interaction |
|---|---|
| Miner retention | Orthogonal; plain stake |
| Conviction defense | No HotkeyLock on Vault / affiliate / pay-in legs |
| **Emission / miner burn** | **Separate living lever** — may move with chain formula, competition, miner pool. Not a settle covenant. Do not market a fixed emission-burn rate as part of this rail. |
| Settlement burn splits | v1 defaults (50/50 success; α-rail 40/60); change via published policy + scoreboard note |
| Owner-cut | Timing bridge for USD settle only; labelled in registry |

---

## 10. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Uncapped 15% stresses cash | Owner-α bridge + public funding label; ops forecasting on pipeline |
| α-rail wash trade | 40% instant burn; non-transferable credits; quote TWAP |
| Affiliate spam / Sybil | KYC partners; clawback; watch α-election farm patterns |
| “Locked” confused with conviction | Copy: **vested plain stake**; never HotkeyLock |
| Discount too deep | Start 30%; review quarterly vs gross margin |
| Double dip (α pay + USD affiliate) | Single rail per invoice |
| Capital confuses emission burn with settle burn | Comms + scoreboard: capture % durable; emission burn labelled “policy / variable” |
| One-time spikes misread as ARR | billing_mode required; recurring totals exclude `one_time` and `unknown` |

---

## 11. Decision checklist

- [ ] Approve uncapped `settle_bps = 1500`; success burn 50/50 as **v1 default** (adjustable)  
- [ ] Approve α rail: **30%** discount, **40%** instant burn / **60%** bond as **v1 default**  
- [ ] Approve affiliate: **10% USD** or **15% α premium** with **90d** plain vest  
- [ ] Approve Stripe `billing_mode` on every USD bond (subscription / one_time / unknown)  
- [ ] Confirm emission / miner burn stays **out of** this covenant (variable policy elsewhere)  
- [ ] Provision Settlement Vault + Affiliate Vault + Pay-in addresses; publish  
- [ ] T&Cs: USD settle, α pay-in, affiliate elections; burn-split change notice  
- [ ] Ship registry before prediction / automate SKUs drive September revenue  
- [ ] Announce with comparative stats  

---

## 12. Success criteria (90 days)

1. ≥95% of eligible Stripe nets have linked bonds with `billing_mode` resolved (≠ `unknown`) for ≥90% of USD settled.  
2. Scoreboard shows **subscription vs one-time** settled USD and α filled.  
3. α rail live with ≥1 real BT-native paying customer.  
4. Affiliate registry live; ≥1 USD and ≥1 α-premium payout path exercised.  
5. Zero HotkeyLock on settlement/affiliate keys.  
6. Scoreboard totals: USD settled → α bought · α paid · α burned · affiliate α vested.  
7. By **September 2026** launch window: prediction + automate-toward-goal SKUs billable; rails already settling those invoices.

---

## 13. Open points

1. AMM vs OTC for large uncapped fills (slice policy).  
2. α-rail affiliate (v2).  
3. Whether α list discount varies by SKU (setup vs managed retainers).  
4. Stripe Connect vs monthly affiliate USD batch.  
5. Proof Reserve segregation from owner defense keys.  
6. Whether subscription renewals share a parent `stripe_subscription_id` rollup on the scoreboard (recommended: yes).  
7. Notice period / changelog format when settlement burn splits change.
