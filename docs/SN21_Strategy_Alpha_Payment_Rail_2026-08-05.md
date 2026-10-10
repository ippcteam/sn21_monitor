# SN21 Strategy — α Payment Rail (BT-native checkout)

**Date:** 2026-08-05  
**Status:** Draft for decision  
**Owner:** Rob Warner  
**Rail:** Bittensor-native / pay-in α  
**Companion specs:** [On-chain performance reporting](SN21_Strategy_OnChain_Performance_Reporting_2026-08-05.md) · [USD delivery bond](SN21_Strategy_USD_Delivery_Bond_2026-08-05.md) · [Affiliates](SN21_Strategy_Affiliate_Rail_2026-08-05.md) · [Combined settlement mechanics](SN21_Stripe_Alpha_Settlement_Spec_2026-08-05.md)

---

## 1. One-liner

**Bittensor natives buy AdTAO services in α at a published 30% discount to the USD list; 40% of pay-in α burns immediately and 60% becomes a delivery bond — native demand without asking Web2 advertisers to hold tokens.**

---

## 2. Marketing thesis

### Problem
The binding α-demand gap is **persona mismatch**: advertisers will not hold α, while BT capital already does but has no product reason to spend it on AdTAO. USD settlement creates ops-driven demand; it does not give holders a **commercial advantage** for using α.

### Thesis
Open a second checkout rail aimed at people who already live in the ecosystem:

1. **Significant discount (30%)** — the only honest reason a rational holder pays in α instead of USD.  
2. **Instant burn (40%)** — proves the rail is not a wash machine; paid α cannot fully round-trip.  
3. **Same outcome oracle as USD bonds** — α payment is not a separate “crypto product”; it buys the same delivery, closed by the same proof publications.  
4. **Proxy buyer, solved** — Web2 stays on Stripe; BT-native rail is who parks α against AdTAO success.

### Positioning vs USD rail
| | USD rail | α rail |
|---|---|---|
| Buyer | Media buyer / agency | Subnet holder, fund, BT operator |
| Friction | None (Stripe) | Wallet + quote |
| Advantage | Familiarity | **30% off list** |
| α effect | Ops buys α with fee share | Buyer **supplies** α (burn + bond) |
| Message | “Revenue wired to α” | “Holders get the best price” |

### Who this converts
| Audience | Message |
|---|---|
| α holders / funds | Pay in α, save 30%, watch burn+bond on the registry. |
| Ecosystem partners | Prefer α invoices for retainers/pilots inside BT. |
| BT-native agencies | Resell AdTAO to crypto brands; settle your seat in α. |
| Web2 advertisers | Ignore this rail — Stripe is for you. |

### What we do **not** claim
- That CMOs will switch to α checkout.  
- That 30% discount is forever (review vs margin quarterly).  
- That α rail replaces USD volume — it is the **high-signal** rail, not the volume rail.  
- That emission / miner burn is fixed by this rail — emission burn stays a **variable** tokenomic lever; α-rail burn splits are v1 operating defaults only.

---

## 3. Technical approach

### 3.1 Actors
| Actor | Role |
|---|---|
| BT-native buyer | Accepts α quote; transfers α to Pay-in. |
| Quote service | 30m TWAP of α/USD; 15m quote TTL. |
| Pay-in watcher | Detects transfer + remark; splits burn/bond. |
| Settlement Vault | Receives 60% bond leg (plain stake). |
| Public Registry | `alpha_pay_hash` ↔ extrinsics ↔ bond. |
| Outcome closer | Shared with USD rail. |

### 3.2 Pricing
```text
P_alpha = (P_usd × (1 − alpha_discount)) / spot_alpha_usd
```

| Param | v1 |
|---|---|
| `alpha_discount` | **30%** |
| Spot | **30-minute TWAP** (α/TAO × TAO/USD or direct) |
| Quote life | **15 minutes** |
| Min ticket | ≥ **$50** USD-equivalent at quote |

### 3.3 Pay-in split
| Slice | % of α received | Destination |
|---|---|---|
| Instant burn | **40%** | **v1 default** (adjustable policy) — permanent sink while in force |
| Delivery bond | **60%** | Vault plain stake; same success burn/reserve policy as USD rail |

No additional 15% “settle” on top — pay-in α *is* the settlement.

### 3.4 Anti-abuse
- Service credits non-transferable.  
- No α refund on cancel (ops may issue USD credit only).  
- Immediate burn makes wash trades loss-making.  
- Single rail per invoice (no α pay + USD affiliate double path on same invoice in v1).

### 3.5 Remarks & hashes
```text
alpha_pay_hash = sha256("adtao-v1|alpha|" + payment_extrinsic_hash)
Remark: ADTAO|ALPHAPAY|v1|<alpha_pay_hash>|<invoice_id>
Bond remark (60% leg): ADTAO|BOND|v1|<alpha_pay_hash>|<bond_id>   // rail=alpha
```

**Lock type:** plain stake + burn only — **no HotkeyLock**.

### 3.6 Build order
1. Publish α price list beside USD SKUs.  
2. Pay-in coldkey + quote API.  
3. Watcher: confirm amount ≥ quote, split 40/60, burn + Vault stake.  
4. Registry “α pays” tab.  
5. Shared outcome closer with USD bonds.

---

## 4. Link to proof publication strategy

α-rail buyers are the audience most likely to **read** on-chain proof. Use proof drops as α-rail acquisition moments.

| When | Proof published | How α rail uses it |
|---|---|---|
| **This month** | Comparative stats | Launch α list + Pay-in. Landing: “BT-native price = 30% under USD. Burns and bonds visible next to performance stats.” Seed 1–2 friendly α invoices (pilot partners). Tag SKU as subscription vs one-time on the bond. |
| **→ September** | Prediction + automate-toward-goal products | Prefer α retainers for BT-native seats on those SKUs; volume still expected mostly on USD subscriptions. |
| **Week 2–3** | Prediction accuracy on-chain | Close α bonds against `window_id`s. Comms: “This α payment burned against on-chain window W.” Target funds/holders who discount narrative without chain proof. |
| **Week ~10** | Autonomous performance on-chain | Push retainer SKUs on α rail (“autonomous seat, paid in α”). Success burns become the holder-facing trophy case. |

### Publication surface
- Performance tab shows the same metrics for USD- and α-funded delivery.  
- Settlement tab splits **α paid in** vs **α bought from USD settle** — both feed burns.  
- Proof posts always include a secondary CTA: *“Holders: pay this invoice in α at −30%.”*

### Instrumentation
Track separately: α-rail volume, burn from pay-in, bond fills, and whether proof weeks lift α-rail conversion (quote accepts / paid invoices).

---

## 5. Comms hooks (ready copy)

> If you already hold AdTAO alpha, you shouldn’t pay full dollar price. Pay invoices in alpha at 30% off the USD list. Forty percent burns on arrival; the rest bonds to delivery and burns again when our published performance bar clears — including on-chain accuracy windows as they go live.

Pair every major proof post with an α-rail CTA; do not bury it in docs only.

---

## 6. Decision checklist

- [ ] Approve 30% discount, 40/60 burn/bond split as **v1 defaults**  
- [ ] Provision Pay-in + Vault; publish addresses  
- [ ] Quote TWAP source documented  
- [ ] Scoreboard “α pays” tab with comparative stats launch  
- [ ] At least one pilot α invoice before week 2–3  
- [ ] September: α list prices for prediction / automate retainer SKUs  

