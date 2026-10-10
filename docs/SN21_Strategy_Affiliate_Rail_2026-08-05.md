# SN21 Strategy — Affiliate Rail (USD referrers → $ or α premium)

**Date:** 2026-08-05  
**Status:** Draft for decision  
**Owner:** Rob Warner  
**Rail:** Growth / distribution  
**Companion specs:** [On-chain performance reporting](SN21_Strategy_OnChain_Performance_Reporting_2026-08-05.md) · [USD delivery bond](SN21_Strategy_USD_Delivery_Bond_2026-08-05.md) · [α payment rail](SN21_Strategy_Alpha_Payment_Rail_2026-08-05.md) · [Combined settlement mechanics](SN21_Stripe_Alpha_Settlement_Spec_2026-08-05.md)

---

## 1. One-liner

**When a referred buyer pays in USD, the referrer chooses 10% cash or a 15% α premium (90-day plain-stake vest) — so distribution can pull either operating partners or α-aligned promoters, without customers holding tokens.**

---

## 2. Marketing thesis

### Problem
AdTAO’s best early distribution is **people inside Bittensor and adjacent crypto** (funds, subnet operators, agencies serving crypto brands). Cash-only affiliate programmes attract Web2 media brokers; they do not deepen α alignment. α-only programmes exclude useful non-crypto referrers.

### Thesis
Let the referrer reveal their type by **election**:

1. **USD election (10%)** — for agencies and operators who want cash. Normal growth spend.  
2. **α premium election (15%)** — higher bounty **because** it creates extra AMM bid and a vested holder. The premium *is* the incentive to take α.  
3. **Same proof calendar** — affiliates are armed with comparative stats → on-chain accuracy → autonomous results as the sales kit; payouts claw back if the underlying invoice refunds.  
4. **No customer wallet requirement** — affiliate α is AdTAO-bought and vested to the referrer; the advertiser still pays Stripe.

### Why α premium > USD rate
| | USD 10% | α premium 15% |
|---|---|---|
| Referrer get | Cash | More notional, in α |
| AdTAO get | Distribution | Distribution **+** incremental α buy  
| Hold | None | 90d plain vest (anti-farm) |
| Story | “Partner programme” | “Promote AdTAO, earn vested α tied to real invoices” |

### Who this converts
| Audience | Election we expect | Message |
|---|---|---|
| BT-native KOLs / holders | α premium | Earn vested α when your referrals pay — proof links on every deal. |
| Crypto-facing agencies | Mixed | Cash or α; use our on-chain scoreboard in pitches. |
| Web2 media partners | USD | Standard rev-share; ignore α. |
| Subnet / ecosystem intros | α premium | Align with SN21 float, not just a finder’s fee. |

### What we do **not** claim
- Open Sybil-friendly “anyone with a link.” v1 is **KYC’d / known partners**.  
- HotkeyLock “conviction” affiliate locks — vest is **plain stake policy**.  
- α-rail (pay-in) affiliate in v1 — defer to v2.

---

## 3. Technical approach

### 3.1 Actors
| Actor | Role |
|---|---|
| Referrer | KYC’d partner; `referrer_id` + coldkey for α election. |
| Buyer | Pays Stripe with `ref=` / metadata `referrer_id`. |
| Settlement Engine | Attributes invoice; creates `AffiliatePayout`. |
| Buy Executor | For α election: AMM buy → Affiliate Vault / referrer stake. |
| Affiliate Vault | Stages α premiums during vest (or stake direct to referrer with registry vest flag). |
| Public Registry | Affiliate hash ↔ bond ↔ extrinsics. |

### 3.2 Parameters (v1)
| Param | Value |
|---|---|
| `affiliate_usd_bps` | **1000 (10%)** of `usd_net` |
| `affiliate_alpha_premium_bps` | **1500 (15%)** of `usd_net` → α at fill |
| Vest (α election) | **90 days** plain stake |
| Clawback window | **60 days** on refund/chargeback |
| Stacking | Affiliate from **ops share**; then **15% delivery bond** still runs on full `usd_net` |
| Eligibility | Allowlisted `referrer_id` only |
| α-rail invoices | No affiliate in v1 |

### 3.3 Waterfall example ($1,000 net, α-electing referrer)
1. Affiliate α premium notional $150 → AMM buy → 90d vest.  
2. Delivery bond $150 → Vault (USD rail).  
3. Ops cash $700 (before Stripe fees / tax).

USD election: $100 cash + $150 bond + $750 ops.

### 3.4 Payout object
```text
AffiliatePayout {
  payout_id, bond_id, referrer_id
  election              // "usd" | "alpha"
  basis_usd_net
  usd_paid_cents? | alpha_filled?
  vest_days             // 90 if alpha
  extrinsics[]
  status                // pending | vested | released | clawback
}
```

### 3.5 Remarks & hashes
```text
affiliate_hash = sha256("adtao-v1|aff|" + payout_id + "|" + referrer_id)
Remark: ADTAO|AFF|v1|<affiliate_hash>|<payout_id>
```

**Lock type:** 90d **plain-stake vest** tracked in registry — **not** HotkeyLock.

### 3.6 Build order
1. Referrer allowlist + election on partner portal.  
2. Stripe metadata `referrer_id` on Checkout / PaymentIntent.  
3. Payout engine (Connect or monthly USD batch; α buy + vest).  
4. Registry “Affiliates” tab.  
5. Clawback hooks on Stripe refunds.

---

## 4. Link to proof publication strategy

Affiliates need **sharable proof artifacts** more than they need higher bps. Each proof drop is a partner enablement release.

| When | Proof published | How affiliates use it |
|---|---|---|
| **This month** | Comparative stats | Launch partner programme + one-pager. Give allowlisted referrers a link pack: stats URL, registry URL, sample Stripe `ref=` codes. First payouts can be small pilots. |
| **→ September** | Prediction + automate-toward-goal sellable | Partner push on **subscription** SKUs (higher LTV); payouts still attributed per Stripe invoice with parent `subscription_id` visible on registry. |
| **Week 2–3** | Prediction accuracy on-chain | Update battlecard: “Outcomes verified on-chain.” Affiliates cite `window_id`s in outbound. Optional: bonus badge on registry for referrals whose bonds close on-chain (comms only, not extra bps in v1). |
| **Week ~10** | Autonomous performance on-chain | Push “autonomous PPC” SKU through partners. α-electing affiliates get the trophy narrative: their vested α sits beside burned delivery bonds from deals they sourced. |

### Publication surface
- Partner portal mirrors Performance + Settlement tabs.  
- Each `AffiliatePayout` row links to parent `bond_id` and, when available, `outcome_refs` / `window_id`.  
- Public scoreboard: affiliate α vested YTD (aggregate; optional named partners if they opt in).

### Instrumentation
- Mix shift: % electing α vs USD after each proof drop.  
- Refund/clawback rate by referrer.  
- Whether α-electing referrers correlate with higher quality (lower refund, longer retainers).

---

## 5. Comms hooks (ready copy)

> Refer a customer who pays in dollars. Take 10% in cash — or take 15% as AdTAO alpha with a 90-day vest. Alpha payouts are bought on-market and recorded on our public registry next to the delivery bond for that invoice. Your best sales asset is our performance scoreboard: comparative stats now, on-chain accuracy next, autonomous results after that.

Launch affiliates **with** comparative stats so partners are not selling on narrative alone.

---

## 6. Decision checklist

- [ ] Approve 10% USD / 15% α premium / 90d vest / 60d clawback  
- [ ] Allowlist v1 partners + coldkeys  
- [ ] Stripe `referrer_id` metadata live  
- [ ] Registry Affiliates tab + partner one-pager with stats links  
- [ ] Legal: affiliate T&Cs (election, vest, clawback)  

---

## 7. v2 (explicitly out of scope now)

- Affiliate on **α payment rail** (e.g. +5% of `alpha_paid` vested).  
- Open self-serve referral links.  
- Extra bps for bonds closed on-chain (proof bonus).  
