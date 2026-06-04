# Positions on V2 §7 Open Questions

**Author:** Engineering, for Khurram → Rob
**Date:** 2026-05-30
**Basis:** Code-grounded reading of the AdTAO/Hope repo. Every position cites the file + line where today's logic lives, so the proposal slots into real plumbing instead of inventing parallel systems.
**Reads against:** `~/Downloads/JAMES_WORKFLOW_REPLACEMENT_V2.md` §7.

Format per question: **the question** → **recommended position** → **why** → **what to confirm with Rob**.

---

## Q1 — Peer-cohort `segment_spec`: which dimensions are mandatory, what's the fallback ladder?

**Position:**

- **Always mandatory:** `vertical`. The only one auto-derived today and the most semantically discriminating. Never widen it; widening vertical breaks the meaning of the comparison.
- **Mandatory once Q2 resolves:** `market_type` (rural / suburban / urban).
- **Optional but auto-derived when possible:** `spend_tier`, `conversion_model`.
- **Fallback ladder when cohort lacks `SEGMENT_MIN_N=50`:**
  1. Widen `spend_tier` by one band (e.g. `$2–5k/mo` → `$1–10k/mo`).
  2. Widen `conversion_model` (e.g. `purchase-heavy` → `mixed`).
  3. Widen `market_type` by one notch only — rural ↔ suburban OR suburban ↔ urban — **never rural ↔ urban**.
  4. Drop `conversion_model` entirely, keep the rest.
  5. Degrade to vertical-only and flag the response with `cohort_confidence: low` + the exact widening chain applied.

**Why:** `app/services/mcp/primitives/benchmark.py:101-114` already declares 6 dimensions in `segment_spec` but only filters on `vertical` at line 207. `VALID_ANGLES` (lines 34-47) lists vertical, bid_strategy, budget_tier, campaign_type, geo, landing_page_quality — forward-compat-shaped but not enforced. So the schema slot exists; what's missing is the matcher and the fallback. `SEGMENT_MIN_N=50` (line 56) and `K_ANONYMITY_MIN=5` are already the floor; ladder respects both. Widening `spend_tier` first is safest because spend bands are continuous; widening `market_type` is structural (rural and urban are *not* on a continuum).

**Confirm with Rob:** is the rural ↔ urban hard-block right? Or do we allow it under explicit operator override with a `cohort_confidence: very_low` flag?

---

## Q2 — Market-type source: geo / population density / operator tag?

**Position:** **Derived from geo-targeting + population density, with operator override.**

- For each account, read the campaign-level geo targeting (`geo_target_constants` we already sync — `app/models/geo/`).
- Cross-reference each targeted geo against a population-density lookup. GeoNames is already in the stack (per CLAUDE.md tech-stack section).
- Compute a `market_density_score` per geo target, then roll up to a single per-account `market_type` using top-N targeted geos weighted by impression share (so a campaign blanketing 50 zip codes is dominated by where the impressions actually land).
- Persist on a new `account_classification` table (new schema — there's no existing rural/suburban/urban classification anywhere in the repo).
- **Operator override** field on the same row, takes precedence when set. Handles edge cases (a rural-coded service operating in the suburban fringe of a major city; a national brand serving both).

**Why:** The Explore audit confirms: no market-tier classification exists in the codebase today. Geo infrastructure is `geo_target_constants` only. GeoNames is already a dependency — no new external integration. Pure operator-tagging is brittle (operators forget to tag, new accounts arrive untagged). Pure geo-derivation is best-effort but transparent and recomputable. Hybrid handles both, and the override gives us a clean escape hatch for the inevitable edge cases.

**Confirm with Rob:** density thresholds (urban / suburban / rural cutoffs). My default: urban ≥ 3,000/km², suburban 500–3,000/km², rural < 500/km². These are standard US Census-ish bands — fine to override.

---

## Q3 — Goal schema: explicit columns or map from generic?

**Position:** **Additive migration — add explicit columns alongside the existing generic ones. No breaking change.**

Today, `AccountGoal` at `app/models/accounts/performance.py:31-32` has only:
- `metric_type` (String(50))
- `goal_value` (Float)

Add (nullable, defaults NULL):
- `objective_type` — enum: `TROAS`, `MAX_CONVERSIONS`, `MAX_PURCHASES_AT_TROAS`, `MAX_LEADS_AT_TCPA`, `BRAND_VISIBILITY`
- `target_roas` (Float)
- `target_cpa` (Float)
- `target_conversions_weekly` (Float)
- `goal_horizon_days` (Integer, default 28)

Keep `metric_type` + `goal_value` for backward compat — the decision engine reads explicit fields first, falls back to inferring from `metric_type` if explicit are NULL. Legacy goals continue working untouched.

**Why:** `AccountGoal` is consumed by DE prerequisites/scoring (per V2 §1). Dropping the generic fields breaks that consumption. Additive migration is the standard low-risk pattern — explicit fields land empty for legacy goals; decision engine and tier classifier read explicit if present. Honest goal-relative tiering ("+157% above this account's own target ROAS") is impossible without structured fields; this is the prerequisite for the killer tier-list claim in V2 §2.2.

**Confirm with Rob:** the enum values for `objective_type` — does the list match how he'd describe goals to customers? Are we missing one (e.g. `MAX_BUDGET_UTILISATION` for ramp-up accounts)?

---

## Q4 — Tier thresholds: peer-cohort auto-calibration, per-MSP config, or hybrid?

**Position:** **Hybrid — peer-cohort percentile defaults + per-MSP override.**

- **Default** boundaries derive from peer-cohort percentile thresholds:
  - `TOP` = top-decile in cohort
  - `HEALTHY` = top-quartile
  - `MARGINAL` = median ± 1 standard deviation
  - `LOW` = bottom-quartile
  - `CRITICAL` = bottom-decile
- **Per-MSP override** in a config object stored on the org/MSP record. Same shape as `benchmark.py:700-707`'s hardcoded `_confidence_tier()` (200→high / 50→medium / 5→low). Persist per-org instead of in code.

**Why:** Today's tier thresholds are hardcoded — `_confidence_tier()` at `benchmark.py:700-707` uses 200/50/5 across the board, with `K_ANONYMITY_MIN=5` and `SEGMENT_MIN_N=50` constants. No per-MSP config exists. Pure auto-calibration is honest but rigid; pure per-MSP config invites every MSP to inflate their numbers. Hybrid keeps integrity (default is the honest cohort percentile) and allows operator nuance (an enterprise MSP serving Fortune-500 wants different cutoffs than a freelancer serving SMBs).

**Confirm with Rob:** should the per-MSP override require approval from an AdTAO admin (anti-inflation guardrail), or be self-serve?

---

## Q5 — Significance cutoffs: global vs per-vertical minimum sample?

**Position:** **Per-archetype defaults already exist — keep them — and add an optional `vertical_overrides` dict for low-volume verticals.**

- Today: `SufficiencyThresholds` dataclass at `app/services/decision_engine/detection/data_sufficiency.py:49-65` has `min_clicks=100`, `min_conversions=20`, `min_impressions=1000` loaded per-archetype from `config.data_requirements`. The per-archetype convention already exists.
- Add: optional `vertical_overrides: dict[str, SufficiencyThresholds]` on each archetype config. Defaults to empty; vertical-specific entries take precedence when present.
- Use it for high-ticket / low-volume verticals: commercial roofing, legal, B2B SaaS enterprise, home services where weekly conv counts are routinely single-digit even on healthy accounts.

**Why:** Per-archetype convention is already built and consumed. We don't need to invent a new layer; we extend the existing layer. Global cutoffs are wrong for high-ticket verticals — a roofing-contractor account doing 4 conv/week is *healthy* but would never fire any archetype gated on `min_conversions=20`. Vertical override fixes this without touching the global defaults.

**Confirm with Rob:** which verticals warrant override on day 1? My starter list: commercial roofing, legal, dental implants, commercial HVAC, B2B SaaS-enterprise.

---

## Q6 — Exclusion governance: approval tier for parent-level exclusion cascades?

**Position:** **T3 (standard human approval, never auto) with dual confirmation + pre-execution dry-run preview.**

- Use the existing approval-tier enum at `app/services/decision_engine/auto_approval_evaluator.py:25,45` — `T1_AUTO / T2_SOFT / T3_STANDARD / T4_ESCALATED`.
- Parent-scale exclusion cascades touch N child accounts at once → by definition T3 (never T1/T2). Reserve T4 for actions that touch shared infra (account-wide pause, MCC settings).
- **Dual confirmation:** the operator approves the exclusion *and* separately confirms the affected-child-list after seeing the dry-run.
- **Pre-execution dry-run preview** showing `{child_account, placements_to_be_excluded, currently_active_match_count, currently_spending_micros_28d}` so the operator sees blast radius before approving.
- **Hard block** if any child is in a "frozen" state (recent incident, customer-paused, hand-off-in-progress) — block the cascade and require per-child decision instead.

**Why:** The auto-approval pipeline already gates on `blast_radius` (one of the 7 gates referenced in V2 §1's evidence chain). T3 is the right floor — not T4, because T4 escalates beyond the operator. Dual confirmation closes the "I clicked yes too fast" risk; the dry-run preview is the standard pattern for any destructive bulk operation. The frozen-state hard block handles the customer-comms risk where an exclusion landing during an active incident makes things worse.

**Confirm with Rob:** what counts as a "frozen" state? My default: any child account with an open T4 escalation, any account marked `customer_pause=true` in the last 7 days, any account in a `hand_off_pending` state.

---

## Q7 — Bittensor SN21: target date for ingest into recommendation envelope?

**Position:** **Do not commit a date. Commit on three preconditions before ingest into the primary envelope.**

- SN21 is "built, not integrated" today — `system_estimate` field at `app/api/bittensor/validator_api.py:190-192` is hardcoded `None`. First epoch was ~1 week ago. There is no calibration data yet.
- **Three preconditions before ingest:**
  1. Validator returns non-null `system_estimate` for **≥100 consecutive episodes** (proves the pipeline is stable).
  2. **Calibration sweep:** compare SN21 predictions against `decision_outcomes` ground truth across **≥30 days of executed decisions**. Require RMSE within a tightly-bounded band (suggest ≤25% on the primary metric, operator's call).
  3. **Adversarial review:** confirm miner consensus isn't gameable — stake diversity check, collusion detection, outlier-miner deweighting.
- **Until all three are green:** surface SN21 predictions only in a **separate "AdTAO Lab prediction" panel** with prominent *"experimental — not used for execution gating"* labelling. Never in the primary recommendation envelope. Never as a basis for an auto-approval tier change.

**Why:** Premature ingest is the single biggest reputation risk for the whole product. If our public claim is "provably better" and our predictions are visibly wrong in customer demos because we shipped before calibration, the wedge is dead. The conservative path costs us ~2-3 months of "we have it but it's gated"; the aggressive path costs us trust if it breaks in public. The risk/reward is wildly asymmetric; gate hard.

**Confirm with Rob:** RMSE band for precondition 2 — is 25% tight enough, or should we hold to 15% before primary-envelope ingest? Tighter is safer; longer to ship.

---

## Cross-cutting recommendation

Across all 7, the pattern is:

- **Use what's already there.** Every position above extends an existing schema/service rather than inventing a parallel one. `benchmark` already has the segment-spec shape; `AccountGoal` already exists; `SufficiencyThresholds` is already per-archetype; the approval-tier enum is already T1–T4; `system_estimate` field is already plumbed (just NULL).
- **Be honest about what's not wired.** Q4 and Q7 explicitly defer or gate to protect the "provably better" claim. Q3 keeps the generic fields alive even when we add explicit ones — no breaking changes ever.
- **Hybrid > pure-anything.** Q2, Q4, Q5 all land on operator-overridable defaults. Pure auto-derivation is brittle, pure operator config is gameable; the override-with-default pattern handles both edge cases and the day-1 zero-config user.

If Rob signs off on these, **Phase 0 in V2 §5 is unblocked** and we can scope the `benchmark` extension ticket immediately — it's the gating dependency on everything else.
