# SN21 — Emission Gate (v440): Findings & Recommended Actions

**Date:** 2026-07-27  **Chain:** finney, **live spec_version 440 (confirmed on-chain)**
**Modelled at block ~8,715,829.** Companion detail: `SN21_Emission_Gate_Risk_v440_2026-07-27.md`.

---

## 1. What happened

A runtime change — **RaoFoundation/subtensor PR #2990, "release-v440: emission gate"** — merged and is **executing on finney now**. It adds a **q-mass Hill gate** on top of the emission-share formula:

    e_i = gate(s_i)·s_i / Σ gate(s_j)·s_j ,   gate(s) = 1 / (1 + (θ/s)^h)

where `s_i` is the old `price·(1−burn)` demand share and `θ` is a "bar" set so the top subnets carry a quantile `q` of all demand. Above the bar → passes; below → crushed toward zero. Deployed params ≈ **q 0.77, h 2.9**.

**Proof it's live:** the lab reproduces the whole 62-subnet distribution to **2.9% median error only with the gate applied** (158% without it).

---

## 2. Key findings (verified)

| # | Finding | Evidence |
|---|---|---|
| F1 | **Gate is live and concentrates emission.** ~24 subnets clear the bar (gate≥½), ~44 retain meaningful pass; 51 of ~69 subnets lose >50% share. Winners: SN64 Chutes, SN51, SN4, SN120, SN107 (~+50%). | Live-state model + on-chain reproduction |
| F2 | **SN21 is gutted.** Rank 57/128, deep below the bar. Emission share **0.30% (un-gated) → 0.0094% actual on-chain, a ~97% cut.** | Live chain state |
| F3 | **The gate hits TAO price-support, not alpha emission.** SN21 still mints a full 1.0 α/block. | 57 gated subnets still emit 1.0 α/block |
| **F4** | **Owner-key income is LEVEL — and always has been.** ~1,296–1,300 α/day (the 18% cut), **independent of burn rate and of the gate.** The gate changed the *value* (TAO/USD via price), not the *quantity*. | `owner_ledger.json`: `owner_share_alpha` = 1299.6 flat since Feb across all burn/price regimes |
| F5 | **Burn is no longer a price lever.** Under the gate the chain-buy channel stays **shut even at burn=0** (SN21 emission 3.2 < injection cap 4.2 TAO/day). Cutting burn gives 9× of a near-zero number — no pump. | Gated injection-cap test on live state |
| F6 | **Cutting burn to 0 costs no owner income.** It redirects the burned miner-incentive (~1,331 α/day) from destroyed/recycled to real miners; the cost is lost deflation + miner sell-supply, **not** the owner cut. | Corrects an earlier error; grounded in F4 |
| F7 | **A chain-forced "require miner hold" does not exist.** The collateral runtime (437) is live, but the reward-capturing `min_locked` floor is **miner-opt-in** (`coldkey_owns_hotkey`); the owner knob (`CollateralLockShare`) only locks part of the tiny registration deposit. SN21 today: p=0 (off), k=1.0. | subtensor `collateral.rs` source + live query |
| F8 | **Conviction takeover is a live, standing risk.** SN21 armed, threshold ~357k α (~1,700 TAO); we hold zero defensive locks and **locking is off the table** (owner holdings small, backers constrained). | Source (PR #2800) + memory + user constraint |

---

## 3. Strategic read

The gate **severed the mechanical levers** (burn→emission→price) at SN21's rank and forces the subnet onto an **organic-demand standard**. Consequences:

- **Real demand is now the *only* value engine.** Only demand that lifts SN21's EMA price toward the bar restores emission and the chain-buy channel. Everything else is in service of that.
- **Owner cash-flow (in α) is intact and burn/gate-independent** — the downside is *price*, not accrual.
- **The burn cut is a supply-side *investment*, not a win in itself** — its only payoff is whatever demand the freed miner rewards buy. It should be sized and timed against demand, and staged.
- **Anti-dump enforcement is ours to build** — the chain won't force miners to hold; our validator weight-scoring (curated set) is the only compulsion, and it's a deterrent, not a physical lock (no unbonding, no clawback).

---

## 4. Recommended actions (prioritised)

**P0 — Resolve the one open question (blocks the burn decision)**
- [ ] **Confirm whether burn-UID 135 is a wallet we control.** If yes, burn→0 forgoes a *separate* owner-controlled stream (net it in). If it's a burn/null sink, burn→0 truly costs the owner nothing. Everything in §4/P2 assumes this is answered.

**P1 — Build the wallet holding gate (prerequisite for any burn cut)**
- [ ] Coldkey dump/float monitor → weight-zeroing in the live validator scoring path, wrapped as **curated-set curation under a private operating agreement** (keep it curation, not a published pay-to-play rule — the OTF landmine).
- [ ] Read cooperating miners' `min_locked` floor (live rail) as the verifiable hold signal to score against.
- [ ] Bank the caveat: deterrent, not a lock.

**P2 — ~~Cut burn — staged~~ — CANCELLED 2026-07-31. Burn held at 0.451.**
- Superseded by `SN21_Alpha_Lock_Policy_2026-07-31.md` §7. Cancelled, not deferred.
- **Why:** burn→0 is not an injection lever (F5) — its only value was as a ~2× discount on the price
  move needed to clear the bar (3.57× → 1.96× on `s`, via the h≈2.9 Hill curve). With no capital for
  the ~3,200 TAO / ~$614k treasury push, that discount has no redemption date.
- **And it is mispriced against our take:** burn→0 hands miners 1,331 α/day (~$301k/yr) while our
  entitlement is 25% of the owner cut — 324 α/day, ~$73k/yr, rising to 50% mid-Sept 2026 and 75%
  from March 2027 (972 α/day, ~$220k/yr). Even at 75% we would give miners more than we receive.
- **P0 (burn-UID 135) closes with it** — moot while burn is held.
- Reopen only alongside a funded, catalyst-backed price push, and only with P1 armed.

**P3 — Generate alpha demand (the engine)**
- [ ] The real re-rating path: demand → price → SN21 climbs toward the bar → emission + chain-buy channel switch back on (reflexive).
- [ ] Below the bar there is no mechanical help — treat demand as the primary workstream, everything else as enablement.

**P4 — Conviction defense without locking**
- [ ] Since locking is out, the `conviction_watch.py` tripwire is the whole defense — **give it a rehearsed response playbook** (who acts, what levers, at ~50% of threshold). Detection without a rehearsed response is just advance notice of a loss.

**P5 — Lab hygiene**
- [ ] Re-anchor `LIVE_VERSION` to `hill_gate_v440_2990` and rebuild S6/S7 around the gated channel, so the dashboard stops showing the phantom pre-gate "cut burn → pump."
- [ ] New reviewed mechanism `lab/mechanisms/hill_gate_v440_2990.py` already registered (stage=mainnet, calibrated to live).

---

## 5. One-line bottom line

**The gate cut our emission ~97% and killed the burn→price lever, but not our owner α accrual (that's flat and burn/gate-independent — only its price fell). We can't force miners to hold, so we build that ourselves; then a staged burn cut funds real miners at ~no owner cost. Demand is the only thing that restores value — everything else just clears the runway.**
