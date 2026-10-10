# SN21 Strategy — On-Chain Performance Reporting (Proof Oracle)

**Date:** 2026-08-05 (rev — Sep product/revenue inflection)  
**Status:** Draft for decision  
**Owner:** Rob Warner  
**Role:** Product proof + settlement oracle  
**Companion specs:**  
[USD Delivery Bond](SN21_Strategy_USD_Delivery_Bond_2026-08-05.md) ·  
[α Payment Rail](SN21_Strategy_Alpha_Payment_Rail_2026-08-05.md) ·  
[Affiliate Rail](SN21_Strategy_Affiliate_Rail_2026-08-05.md) ·  
[Combined settlement mechanics](SN21_Stripe_Alpha_Settlement_Spec_2026-08-05.md) ·  
[Daily Stream Design v0.5](SN21_Daily_Stream_Design_v0.5.md) §13 (transparency feeds D11/D12)

---

## 1. One-liner

**Publish AdTAO performance in three escalating stages — comparative stats now, prediction accuracy on-chain in ~2–3 weeks, autonomous PPC performance on-chain in ~10 weeks — so BT capital, rails, and affiliates all share one verifiable oracle instead of blog claims.**

---

## 2. Marketing thesis

### Problem
SN21’s demand gap is not “no product story.” It is **unverifiable substance**. Valuation research already showed: self-reported revenue and X posts move attention; they do not reliably move staked TAO. Marketing peers with clearer on-chain commodities (Bitcast) or louder enterprise logos still force the question: *what exactly cleared, against what baseline, and can I check without trusting the owner?*

AdTAO’s product path (forecast → act → correct) is stronger than a pure narrative subnet **only if** that loop is published where the network can audit it.

### Thesis
Treat performance reporting as **infrastructure**, not content:

1. **One scoreboard, two tabs** — Performance (did the product work?) and Settlement (did fees become α?). Cross-linked, never separate blogs.  
2. **Escalate trust, don’t wait for perfect** — comparative stats unlock the rails this month; on-chain windows replace attestation as soon as they exist.  
3. **Proof is the bond oracle** — USD bonds, α pay-ins, and affiliate narratives all close against the same `window_id` / KPI artifacts.  
4. **Audience split is intentional** — advertisers care about CPA/ROAS in plain language; BT capital cares that the same numbers are hashed on-chain. One dataset, two framings.

### Who this converts
| Audience | What they need from the scoreboard |
|---|---|
| BT capital / α holders | Third-party-checkable windows; burn linkage; no “trust us” PDF as the final word |
| Advertisers / agencies | Clear before/after and goal metrics; privacy-safe aggregates |
| Miners | Cohort accuracy feed proves scoring is real (Daily Stream D11) |
| Affiliates | Sharable artifacts for outbound (“window W beat baseline”) |
| Sceptics | Hash → file → metric reproducibility |

### What we do **not** claim
- That publishing alone re-rates α (rails still wire demand).  
- That every advertiser account is doxxed on-chain (privacy: aggregates + consented case studies).  
- That v1 attestation equals v2 on-chain finality — we label the trust level on every row.

---

## 3. Three-stage roadmap

| Stage | When | Trust level | What is published | Closes bonds? |
|---|---|---|---|---|
| **A — Comparative stats** | **This month** | Public web + file hash (optional anchor) | AdTAO vs baseline / peers on agreed KPI set | Yes — via ops + customer attestation referencing `campaign_id` + report hash |
| **B — Prediction accuracy on-chain** | **~2–3 weeks** | Metrics file + **on-chain commitment** | Daily/rolling miner + portfolio prediction quality vs settled outcomes | Yes — prefer `window_id` + score ≥ baseline |
| **Commercial inflection** | **September 2026** | Product + Stripe | **Prediction** and **automate-toward-goal** sellable (prefer subscriptions); settlement rails already live so revenue is classified recurring vs one-time from day one | Bonds on those invoices use A now, B/C as available |
| **C — Autonomous performance on-chain** | **~10 weeks** | Same rail as B | Autonomous control-loop results (act → outcome) vs published baseline | Yes — autonomous `window_id` ≥ baseline |

Stages **stack**; they do not replace each other. Stage A remains the human-readable front door. B and C become the settlement-grade backend. September is the **revenue** gate (billable prediction + goal automation), not a reason to delay rails or Stage A.

---

## 4. Technical approach

### 4.1 Generic publication rail (from Daily Stream §13)

Reuse / extend the IM transparency rail rather than inventing a second stack:

```text
metrics_file (JSON/Parquet, public URL)
    → sha256(file)
    → on-chain commitment extrinsic (remark or dedicated commitment)
    → signed archive (same attestation regime as outcome feed)
```

Spec the rail **generic** (any metrics bundle), so comparative, prediction, and autonomous feeds are three *payloads* on one path.

### 4.2 Stage A — Comparative stats (this month)

**Purpose:** Ship something sharable immediately; launch settlement rails beside it.

| Element | Spec |
|---|---|
| Surface | Public scoreboard URL (Performance tab) |
| Contents | Portfolio-level (and consented account-level) comparisons: AdTAO-influenced periods vs holdout/baseline; waste, CPA/ROAS, or account goal metric |
| Method note | Seasonality / account-mix caveats published beside charts (align with D12 spirit: anonymised aggregates, before/after) |
| Artifact | `comparative_report_id` + `report_hash = sha256(file)` |
| Optional | Anchor `report_hash` on-chain even in Stage A (cheap credibility) |
| Bond link | `Bond.outcome_refs = [campaign_id, comparative_report_id]` · success = KPI met + customer ack |

**Privacy:** default anonymised; named case studies only with written consent.

### 4.3 Stage B — Prediction accuracy on-chain (~2–3 weeks)

**Purpose:** Make “SN21 does real forecasting work” network-verifiable; give bonds a trustless close condition.

| Element | Spec |
|---|---|
| Payload | Aggregation over Daily Stream scored episodes (D11): full-cohort accuracy + champion/portfolio summary |
| Cadence | Daily (or next-day) from stream maturity; partial numbers acceptable early |
| Identity | `window_id` (date or episode-basket id) + `metrics_hash` + commitment extrinsic |
| Metrics (illustrative) | Quantile accuracy, calibration, direction, goal metric — same weights as IM (50/20/15/15) unless republished |
| Baseline | Pre-declared: e.g. champion vs naive / vs prior champion / vs published floor |
| Bond link | Success if linked `window_id` meets baseline; registry stores extrinsic |

**Audience note:** Miners use this to verify scoring; holders use it to verify substance; advertisers see a simplified “forecast quality” tile fed from the same file.

### 4.4 Stage C — Autonomous performance on-chain (~10 weeks)

**Purpose:** Prove the control loop (prediction → action → correction), not only forecast skill.

| Element | Spec |
|---|---|
| Payload | Autonomous intervention windows: actions taken, counterfactual/baseline, realized outcome at horizon |
| Identity | `auto_window_id` + metrics file + on-chain commitment |
| Metrics | Goal metric lift vs baseline (account-native); guardrails (spend caps, brand-safety flags) |
| Bond link | Prefer autonomous windows for managed/autonomous SKU bonds; prediction windows remain valid for forecast-only SKUs |

### 4.5 Scoreboard information architecture

```text
adtao.io/scoreboard (or stats subdomain)
├── Performance
│   ├── Comparative (Stage A)
│   ├── Prediction accuracy (Stage B)
│   └── Autonomous (Stage C)
├── Settlement
│   ├── USD bonds (subscription | one_time)
│   ├── α pays
│   ├── Affiliates
│   └── Burns / Proof Reserve   // settlement burns; emission burn is separate policy
└── Verify
    └── paste Stripe id / extrinsic / window_id → resolve links
```

Every **success_closed** bond cites at least one Performance artifact. Every major Performance publish cites Settlement totals (α burned since last report).

### 4.6 `window_id` / artifact schema (minimum)

```text
PerformanceArtifact {
  stage              // "comparative" | "prediction" | "autonomous"
  artifact_id        // window_id or report_id
  period_start / period_end
  metrics_url
  metrics_hash
  commitment_extrinsic?   // required for stages B/C; optional for A
  baseline_ref
  result             // "pass" | "fail" | "n/a"
  summary_human      // one paragraph for affiliates / X
}
```

### 4.7 Build order
1. **Week 0:** Scoreboard shell + Stage A comparative publish + hash (anchor if ready).  
2. **With rails launch:** Settlement tab + Verify; bonds reference `campaign_id` / report hash / `billing_mode`.  
3. **~2–3 weeks:** Stage B daily accuracy feed on commitment rail (IM D11 path). Bond closer prefers `window_id`.  
4. **By September 2026:** Prediction + automate-toward-goal commercial SKUs live; subscription Stripe prices wired so settlement sees recurring cash.  
5. **~10 weeks:** Stage C autonomous payload on same rail. Autonomous SKU bonds prefer `auto_window_id`.  
6. Ongoing: flow harness on proof drops (+1/+3/+7d non-owner TAO).

---

## 5. How the three commercial rails consume this oracle

| Rail | Stage A | Stage B | Stage C |
|---|---|---|---|
| **USD delivery bond** | Launch + attest close | Close on prediction `window_id` | Close autonomous SKUs on `auto_window_id` |
| **α payment rail** | Launch −30% list beside stats | Holder CTA: “burn against window W” | α retainers for autonomous seats |
| **Affiliates** | Partner one-pager + stats links | Battlecard: on-chain verified | Push autonomous SKU; trophy case with burns |

**Rule:** do not launch a new proof stage without updating all three rail landing pages and the registry close rules the same day.

---

## 6. Trust labels (mandatory UX)

Every Performance tile and bond close reason shows one of:

| Label | Meaning |
|---|---|
| `attested` | Ops + customer ack / internal methodology (Stage A default) |
| `anchored` | File hash committed on-chain; file public |
| `on_chain_window` | Stage B/C window with commitment + reproducible metrics file |

Never imply `on_chain_window` for Stage A rows.

---

## 7. Comms hooks (ready copy)

**Stage A**
> We’re publishing comparative performance for AdTAO-managed outcomes — baselines, lifts, and methods — on a public scoreboard. Same day, Stripe fees begin settling into on-chain alpha bonds you can audit from a payment receipt.

**Stage B**
> Prediction accuracy is now committed on-chain. Each window has a metrics file, a hash, and an extrinsic. Delivery bonds can close against those windows. Check the scoreboard; don’t trust a screenshot.

**Stage C**
> Autonomous PPC performance is on the same rail: actions, baselines, realized outcomes. Fee → bond → autonomous window → burn is one linked path.

---

## 8. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Over-claiming “on-chain” too early | Hard trust labels; Stage A says comparative/attested |
| Privacy leak of advertiser data | Aggregates default; consent for named cases; no raw account dumps |
| Orphan proof (published but unused by rails) | Same-day rail + registry updates required |
| Orphan rails (bonds with soft attestation forever) | Migration deadline: new bonds after Stage B GA prefer window close |
| Metric games | Pre-declare baselines; version methodology in the file header |
| IM delay slips Stage B | Keep Stage A + attested closes; do not slip rail launch |

---

## 9. Decision checklist

- [ ] Approve three-stage calendar and trust labels  
- [ ] Scoreboard IA (Performance + Settlement + Verify)  
- [ ] Stage A comparative methodology + first publish date  
- [ ] Confirm Stage B uses Daily Stream D11 commitment rail  
- [ ] Define Stage C autonomous metric set + baseline rule  
- [ ] Bond closer migration: attested → `window_id` preference after B GA  
- [ ] Joint launch plan: Stage A + USD/α/affiliate rails  
- [ ] September commercial plan: prediction + automate-toward-goal SKUs on Stripe subscriptions where possible  

---

## 10. Success criteria (90 days)

1. Stage A live with ≥1 public comparative report and stable URL.  
2. Stage B live with daily (or next-day) committed accuracy windows.  
3. ≥1 delivery bond `success_closed` against an on-chain `window_id`.  
4. Settlement tab shows cumulative burns citing Performance artifacts; USD settled split subscription vs one-time.  
5. Affiliates shipping links to scoreboard (not PDFs) in outbound.  
6. Stage C design frozen by week 6; first autonomous window committed by ~week 10.  
7. September: prediction / automate-toward-goal invoices flowing through live settle rails.

---

## 11. Document set (keep together)

| Doc | Role |
|---|---|
| **This file** | Proof oracle — what we publish and when |
| [USD Delivery Bond](SN21_Strategy_USD_Delivery_Bond_2026-08-05.md) | Web2 fee → α bond |
| [α Payment Rail](SN21_Strategy_Alpha_Payment_Rail_2026-08-05.md) | BT-native pay-in |
| [Affiliate Rail](SN21_Strategy_Affiliate_Rail_2026-08-05.md) | Referrer $ or α premium |
| [Settlement mechanics](SN21_Stripe_Alpha_Settlement_Spec_2026-08-05.md) | Engineer reference for all rails |
