# SN21 Strategy — USD Delivery Bond (Stripe → α)

**Date:** 2026-08-05 (rev — billing mode; Sep revenue; variable emission burn)  
**Status:** Draft for decision  
**Owner:** Rob Warner  
**Rail:** Web2 / Stripe  
**Companion specs:** [On-chain performance reporting](SN21_Strategy_OnChain_Performance_Reporting_2026-08-05.md) · [α payment rail](SN21_Strategy_Alpha_Payment_Rail_2026-08-05.md) · [Affiliates](SN21_Strategy_Affiliate_Rail_2026-08-05.md) · [Combined settlement mechanics](SN21_Stripe_Alpha_Settlement_Spec_2026-08-05.md)

---

## 1. One-liner

**Advertisers pay USD in Stripe (subscription or one-time). AdTAO settles 15% of each net payment as an on-chain α delivery bond, remarked to the Stripe payment id — so revenue → α demand is publicly auditable without customers holding α, and capital can see recurring vs one-off.**

---

## 2. Marketing thesis

### Problem
dTAO markets do not capitalise Web2 SaaS revenue unless that revenue is **wired into α**. Category peers (Bitcast) price higher when brand spend settles in α; AdTAO’s buyers are media operators who will never hold tokens. Self-reported revenue and X posts create attention; they do not create pool demand.

### Thesis
Make AdTAO the ops desk that converts **outcome spend → α scarcity**:

1. **Customer stays in USD** — no wallet friction, no OTF “stake-to-mine” optics aimed at advertisers.
2. **Every invoice leaves an on-chain scar** — Stripe receipt ↔ extrinsic hash ↔ bond ↔ burn on success.
3. **Recurring is labelled** — Stripe tells us subscription vs one-time; the registry does too. Diligence can separate ARR-like cash from pilots.
4. **Success is the settlement-burn trigger** — comparative stats, then on-chain prediction accuracy, then autonomous performance are not “content”; they are the **oracle that closes bonds**.
5. **Narrative that survives diligence** — “We don’t ask advertisers to buy α. We settle a published share of their fees into α bonds and burn on verified outcomes.”

### Revenue timeline
Significant Stripe volume is expected from **September 2026**, when **prediction** products and **automate-toward-goal** become launchable SKUs. Ship the USD rail and registry on earlier pilots so September revenue hits a live capture path on day one — not a retroactive promise.

### Who this converts
| Audience | Message |
|---|---|
| BT capital / α holders | Revenue is no longer off-protocol — watch the scoreboard (USD settled → α bought → α burned), split by subscription vs one-time. |
| Advertisers / agencies | Unchanged product pitch: pay USD for PPC outcomes. Settlement is AdTAO’s problem. |
| Affiliates / ecosystem | USD rail is the volume base their commissions attach to. |
| Sceptics | Verify any receipt against the registry; underfunded bonds are labelled, never faked. |

### What we do **not** claim
- That 15% settle alone lifts SN21 to top-quartile price (float is still structural).
- That advertisers become token holders.
- That emission / miner burn is fixed by this rail — that lever stays **variable** with tokenomics, chain changes, and miner-pool dynamics. Capture (`settle_bps`) is the durable published commitment; emission burn is managed separately.

---

## 3. Technical approach

### 3.1 Actors
| Actor | Role |
|---|---|
| Advertiser | Pays Stripe PaymentIntent / Invoice in USD. |
| Settlement Engine | Webhook consumer; creates Bond; enforces bps/floors/waterfall. |
| Buy Executor | AMM/OTC acquires α (or bridges owner-cut α). |
| Settlement Vault | Public coldkey; plain-stakes bonds; never HotkeyLock. |
| Public Registry | `stripe_hash` ↔ extrinsics ↔ bond status. |
| Outcome closer | Attestation (v1) → on-chain windows (v2/v3). |

### 3.2 Parameters (v1)
| Param | Value |
|---|---|
| `settle_bps` | **1500 (15%)** of **net** fee |
| Monthly USD cap | **None** |
| Per-invoice floor | **$25** settle budget |
| Economic ceil | **None** (slice large AMM fills for slippage) |
| Funding waterfall | (1) USD → AMM/OTC · (2) owner-cut α at MTM · (3) public `underfunded` |
| Success close | **50% burn** / **50% Proof Reserve** (90d plain stake) — **v1 default**, adjustable by published policy |
| Fail close | **100%** return to treasury |
| Refund buffer | Hold **10%** of settle budget in USD **14d** before buy |
| `billing_mode` | `subscription` \| `one_time` \| `unknown` from Stripe |
| Lock type | **Plain stake + settlement burn only** — no HotkeyLock / conviction |

### 3.3 Bond object (summary)
```text
Bond {
  bond_id, rail: "usd"
  stripe_payment_id   // private
  stripe_hash         // sha256("adtao-v1|" + stripe_payment_id)  // public
  billing_mode        // subscription | one_time | unknown
  stripe_subscription_id?, stripe_invoice_id?, stripe_price_id?
  usd_net, settle_bps, usd_to_alpha
  alpha_filled, fill_extrinsics[]
  funding             // "amm_buy" | "owner_alpha" | "mixed"
  status              // pending_fill | active | success_closed | fail_closed | refunded
  outcome_refs[]      // campaign id → later window_ids
}
```

### 3.3.1 Stripe billing mode
Resolve on webhook (`invoice.paid`, `payment_intent.succeeded`, subscription objects). Same 15% settle for both modes; scoreboard splits recurring vs one-time so capital does not mistake setup spikes for subscription run-rate. Full rules: [settlement spec §4.1.1](SN21_Stripe_Alpha_Settlement_Spec_2026-08-05.md).

### 3.4 On-chain remark
```text
ADTAO|BOND|v1|<stripe_hash>|<bond_id>
```
Batched via `utility.batch_all(system.remark, transfer/stake)`.

### 3.5 Verification (anyone)
1. Stripe receipt → PaymentIntent / Invoice id.  
2. `stripe_hash = sha256("adtao-v1|" + id)`.  
3. Registry row + explorer extrinsic; remark matches; α within ±2% slippage.

### 3.6 Build order
1. Vault coldkey + publish address.  
2. Stripe webhooks (`payment_intent.succeeded`, `charge.refunded`, `invoice.paid`, subscription lifecycle) + `billing_mode` resolver.  
3. Settlement Engine + Buy Executor + remark batcher.  
4. Public registry + scoreboard (subscription vs one-time totals).  
5. Outcome closer (attest → windows).  
6. Flow harness: +1/+3/+7d non-owner TAO around fills.  
7. Ready before **September** prediction / automate-toward-goal SKU launch.

---

## 4. Link to proof publication strategy

The proof calendar is the **bond oracle**, not a separate marketing track.

| When | Proof published | How USD bonds use it |
|---|---|---|
| **This month** | Comparative stats (public scoreboard) | Announce USD rail + registry the same day. Bonds tag `campaign_id` + `billing_mode`. Success = pre-agreed KPI attested by ops + customer ack; PDF/hash on registry. Comparative stats page links “active bonds / α burned YTD.” |
| **→ September** | Prediction live as product + automate-toward-goal path | **Revenue inflection:** billable prediction / goal-automation SKUs (prefer subscriptions). Rails already classifying and settling those invoices. |
| **Week 2–3** | Prediction accuracy **on-chain** | Prefer close condition: bond `outcome_refs` include `window_id`s; success = published score ≥ baseline. Marketing line: “Stripe payment X closed against on-chain window Y.” |
| **Week ~10** | Autonomous PPC performance **on-chain** | Same machinery; success = autonomous window beats baseline (CPA/ROAS/waste). Full story: fee → bond → autonomous proof → burn. |

### Publication surface (single scoreboard)
- **Performance tab:** comparative / prediction / autonomous metrics (the product proof).  
- **Settlement tab:** USD settled → α filled → α burned (the α proof), with **subscription vs one-time** breakdown.  
- Cross-links: each closed bond cites the proof artifact that authorised the burn.

### Instrumentation
Around each proof drop **and** each cluster of bond fills, log net non-owner TAO flow at +1/+3/+7d. Proof without flow = attention only; fills without proof = unearned sink — we want both.

---

## 5. Comms hooks (ready copy)

> AdTAO customers pay in dollars — subscriptions and one-time invoices alike. We settle 15% of every net fee into an on-chain alpha delivery bond, linked to the Stripe payment, and we publish whether that cash was recurring or one-off. When outcomes clear our published bar — soon on-chain — a published share of that alpha is burned. Advertisers never touch a wallet. Anyone with a receipt can audit the chain.

Announce **with** comparative stats, not after. Do **not** pitch a fixed emission-burn rate as part of this story.

---

## 6. Decision checklist

- [ ] Approve uncapped 15% settle; 50/50 success burn/reserve as **v1 default**  
- [ ] Approve Stripe `billing_mode` on every USD bond  
- [ ] Provision Vault; publish address  
- [ ] T&Cs: fees may be α-settled by AdTAO (no customer custody)  
- [ ] Scoreboard live before September prediction / automate SKU launch  
- [ ] Joint launch: comparative stats + USD rail  
- [ ] Keep emission / miner burn as separate variable policy (not a settle covenant)  
