# SN21 Validator — `validator_trust` Collapse: Findings & Restoration Checklist

**Status:** OPEN — validator (UID 111) earning **zero** since 25 May 2026
**Prepared:** 2026-05-29 · **Updated:** 2026-05-29 with confirmed production-log evidence (§5.1)
**Audience:** Validator operator / developer (whoever runs `hope-validator` + heartbeat)
**Goal:** Restore `validator_trust` on UID 111 and resume validator dividend earnings on the ~494k α staked there.

> **🔑 Confirmed root cause (from production logs, §5.1):** The wallet/hotkey config is **correct**. The Monday scoring run is **aborting before it commits weights** with `weights_commit_failed: no scoreable miners; skipping weights commit` (9.C.3 never written). With no weights ever committed for the validator hotkey, the heartbeat has nothing to re-assert, so the chain's activity floor keeps `validator_trust` at 0. **The fix is to make the scoring run produce scoreable miners and actually commit weights** — not a wallet/stake/delegation change.

---

## 0. TL;DR

- Our validator is **UID 111**, hotkey `5GuiHB…ibJEz`. It holds **493,706 α** (15.6% of all validator stake on SN21) but is earning **0** because its on-chain **`validator_trust = 0`**.
- **`validator_trust` is NOT a function of stake.** It is produced by *this validator publishing consensus-aligned weights on schedule*. Proof: another validator (UID 3) earns with just 5,234 α at vtrust 1.0, while UID 111 (494k α) and UID 59 (607k α) earn nothing at vtrust 0.
- **Root cause:** the 20–21 May owner/validator key split moved the validator role to a **new hotkey that had no prior committed weights**. The chain's **16.7h activity floor** (`activity_cutoff = 5,000 blocks`) then dropped its weights out of consensus → vtrust collapsed on **Thu 21 May**. The heartbeat could not save it (`skipped_no_prior_weights`), and the **Mon 25 May scoring run did not successfully commit weights** for the new hotkey, so vtrust has stayed at 0.
- **The fix:** a **successful** `hope-validator` scoring run on UID 111's hotkey (score → commit → reveal) **plus** a working heartbeat re-asserting those weights every ~5h. Running the validator on Monday is the correct fix **only if the run completes end-to-end and the heartbeat then sustains it** — neither was true last week. This document lists the exact checks to guarantee it this time.
- **Prize:** at 494k α with vtrust restored to ~1.0, UID 111 should earn on the order of **~500 α/day** in validator dividends (extrapolated from working validators), versus 0 today.

---

## 1. Corrected ownership & key map

The keys were initially mislabeled. This is the verified, on-chain-correct mapping (per Taostats metagraph + operator confirmation):

| Role | SS58 | On-chain location | Notes |
|------|------|------|-------|
| **Operator/investor coldkey** | `5HjCYVfrWSkzTfJM5rkWBW3qTTJqXEFUzZrKty5hodpgfjyW` | coldkey of UID 111 & 135 | Controlled by the operators (Jack/Mark/Siam). The Taostats account Jack shared. |
| **Validator hotkey** | `5GuiHBTfciFauoF1XuyvVuWYrQaS7LExrbsqV5EmDU2ibJEz` | **UID 111** | **The validator. This is the key that must regain vtrust.** `is_child_key = true`. |
| **Subnet-owner hotkey** | `5EqAzby1upPkqpba5qrbDLZtFLmaTUe2PRbzih62voorQVHp` | **UID 135** | `is_owner_hotkey = true`. Earns the 18% owner emission (~1,296 α/day). Burn-immune, stake-independent. |
| **Our owner-share coldkey** | `5DkEA99gAAF2Ge6X3h76x98LbYtqT7gJ6h9VaApfMkKJCPJM` | **NOT a neuron** | Downstream recipient of our agreed share of owner emissions. Not registered on the metagraph. |
| Prior owner hotkey (historic) | `5HiWPApiuXz9DDnkyFu4M2tWs2ar6LTKt54Bo18EL6pgZsdn` | — | Auto-labelled owner hotkey on 8 May; superseded. |

**Earnings flow:**
```
18% subnet-owner emission ──► 5EqAzby1 (UID 135, operator coldkey 5HjCYVfr)   [owner earnings — WORKING]
                                  └─ our share transferred out ──► 5DkEA99 (our coldkey)   [what we see]

validator dividends ──► 5GuiHB (UID 111, operator coldkey 5HjCYVfr)           [validator earnings — BROKEN since 25 May]
```

---

## 2. Current state (live metagraph, block 8,292,268 — 2026-05-29 20:14 UTC)

| UID | Hotkey | Role | alpha_stake | root (as α) | **total stake α** | vtrust | dividends | val α/day |
|----:|--------|------|----:|----:|----:|----:|----:|----:|
| **111** | `5GuiHB…` | validator | 426,349.41 | 67,356.38 | **493,705.79** | **0.00** | **0** | **0** |
| 135 | `5EqAzby1…` | owner | 64.996 | 0 | 64.996 | 0.00 | 0 | 0 (earns 1,296 owner α/day instead) |

- UID 111 = **15.6%** of all validator stake on SN21 (3rd-largest), earning nothing.
- Stake is still **growing** (~55k α added 28 May) — the capital is committed; only the vtrust is missing.

---

## 3. Evidence

### 3.1 vtrust timeline — UID 111 / `5GuiHB` (source: Taostats metagraph history, netuid 21)

| Date | day | validator_trust | dividends | validating α/day | owner α/day | total stake α |
|------|-----|----:|----:|----:|----:|----:|
| 2026-05-19 | Tue | **1.00** | 0.0061 | 10.79 | 1296 | 35,436 |
| 2026-05-20 | Wed | **1.00** | 0.0879 | **251.14** | 1296 | 437,132 |
| 2026-05-21 | Thu | **0.00** ⬅ collapse | 0.0452 | 129.23 | **0** ⬅ owner role left | 436,572 |
| 2026-05-22 | Fri | 0.00 | 0.0055 | 15.65 | 0 | 436,977 |
| 2026-05-23 | Sat | 0.00 | 0.0006 | 1.79 | 0 | 437,338 |
| 2026-05-24 | Sun | 0.00 | 0.0000 | 0.09 | 0 | 437,565 |
| 2026-05-25 | Mon | 0.00 | 0 | **0.00** ⬅ Mon scoring run did NOT restore | 0 | 437,901 |
| 2026-05-26 → 29 | — | 0.00 | 0 | 0.00 | 0 | 438k → **493,706** |

Two events land on the **same day (21 May)**: `owner_alpha` drops to 0 (owner role moved off this key) **and** `validator_trust` collapses to 0. This is the key split.

### 3.2 vtrust is independent of stake (live, all 12 validators)

| UID | stake α | vtrust | val α/day |
|----:|----:|----:|----:|
| 182 | 1,271,355 | 1.00 | 1,328 |
| 65 | 331,051 | 1.00 | 266 |
| **3** | **5,234** | **1.00** | **5.7** |
| 59 | 606,570 | **0.00** | **0** |
| **111** | **493,706** | **0.00** | **0** |
| 135 | 65 | 0.00 | 0 |

UID 3 earns on 5,234 α; UID 111 earns nothing on 493,706 α. **Adding/delegating more stake to 111 multiplies its earnings by zero until vtrust is fixed.** 8 of 12 validators have vtrust 1.0; the broken ones (59, 111, 135) are not publishing consensus weights.

---

## 4. How SN21 validation actually works (from `ippcteam/SN21-adtao`)

SN21 is a **weekly commit-reveal** subnet. Two independent processes keep a validator earning:

### 4.1 Weekly scoring run — `hope-validator`
- **Window:** mining open Mon 17:00 UTC → next Mon 05:00 UTC; scoring open Mon 05:00–17:00 UTC. Reference timer fires **Mon 12:00 UTC** (mid-window). *(Our Render cron currently fires Mon 06:00 UTC — see §7 note.)*
- Reads each miner's on-chain commits, fetches prediction ciphertext from **archive tiers**, runs scoreability + scoring, computes **tiered weights with 95% burn**, and publishes via `set_weights` (commit-reveal: commit, then reveal ~360 blocks ≈ 72 min later).
- Emits the Layer 9.C.1/9.C.2/9.C.3/9.C.6 audit commitments.
- **Idempotent:** bails if `validator_already_scored_epoch` is true for this (validator, epoch).

### 4.2 Activity-floor heartbeat — `sn21-validator-heartbeat`
From `hope/validator/heartbeat.py` (verbatim):
> The chain's per-subnet `activity_cutoff` (**5,000 blocks ≈ 16.7h** on mainnet) forces validators to publish `set_weights` regularly or **their weights drop out of the consensus computation**. SN21's authoritative scoring runs only once per week — fine for producing meaningful weights, way too infrequent for the chain's activity floor.

- Runs every ~4h. Sets **no new weights** — it **re-asserts the last committed weights** (read from `SubtensorModule.Weights[netuid][uid]`) to stay above the activity floor. Self-throttles to ≤ once per 1,500 blocks (~5h).
- **Critical edge case:** if the validator has **never committed weights** (empty `Weights[netuid][uid]`), it exits `skipped_no_prior_weights` and does nothing.

**Both are required.** Scoring creates real weights weekly; the heartbeat keeps them in consensus between Mondays. If either is broken for the validator hotkey, vtrust decays to 0 within ~17h.

---

## 5. Root cause (confirmed)

1. **20–21 May:** operator split the combined owner+validator key. Validator role → **new hotkey `5GuiHB` (UID 111)**.
2. The new hotkey had **no prior committed weights of its own**. The heartbeat therefore could not re-assert anything (`skipped_no_prior_weights`).
3. With no weight updates for one `activity_cutoff` window (~16.7h), UID 111's weights **dropped out of consensus → `validator_trust` → 0 on Thu 21 May.** Residual dividends decayed over 21–24 May, hitting exactly 0 by 25 May.
4. The **Mon 25 May scoring run did not successfully commit weights** for `5GuiHB` (vtrust stayed 0). Likely causes, in order of probability:
   - Scoring env/wallet still pointed at the **old hotkey**, not `5GuiHB`.
   - **Release discovery / archive fetch failed** → "no scoreable miners" → weights commit skipped.
   - `already_scored` guard bailed on a stale/partial commit.
   - Scoring produced **no qualifying miners** → all-burn `{0: 1.0}` commit, which does not align with the consensus miner distribution.

**Net:** the validator is alive and even shows recent `LastUpdate`, but it is not landing consensus-aligned weights, so it scores vtrust 0 and earns 0.

---

## 5.1 Confirmed from production logs (Render, HOPE Platform)

Pulled the actual cron logs. These **confirm** the diagnosis and narrow the fix.

### Monday 25 May scoring run — `sn21-validator-scoring` (`crn-d827jc77f7vs73dsinpg`)

Run started 06:00 UTC. Verbatim key lines:

```
Using explicit RELEASE_KEY=WR-2026-W21-PUB-E1 (manual override)
Deploying wallet sn21-mainnet / validator
validator 5GuiHBTfci... has 0 revealed commitments (need 2 for audit); continuing with empty pre/post blobs (first-scoring path).
[RPC-DIAG] initial read: url=wss://entrypoint-finney.opentensor.ai:443 block=8259214 visible=28/256
... (many) archive fetch tier=2 ok=True match=True status=200 ...
On-chain epoch outcome:
  ok: False
  aborted_reason: weights_commit_failed: no scoreable miners; skipping weights commit
  9.C.1 block: 8259219
  9.C.3 block: None
==> Cron job run finished successfully
```

What this proves:

1. **✅ Wallet/hotkey config is correct.** `wallet=sn21-mainnet / validator` resolved to `5GuiHBTfci…` (UID 111). This is **not** a wrong-hotkey problem — C1 is already satisfied.
2. **✅ Archive tiers are reachable.** Dozens of `archive fetch tier=2 ok=True match=True status=200`. C4 is already satisfied.
3. **❌ The run aborted with `no scoreable miners` and never committed weights.** `9.C.1` (pre-scoring state) was committed at block 8259219, but **`9.C.3` (the weights commit) is `None`** → **no `set_weights` ever happened** → vtrust stays 0. This is the single point of failure.
4. **⚠️ `RELEASE_KEY` was hard-pinned** to `WR-2026-W21-PUB-E1` via env (`manual override`), bypassing the auto-discovery in `run.sh`. If that release does not correspond to the epoch/week actually being scored, **every miner's submission fails the scoreability match → "no scoreable miners."** This is the #1 suspect for the abort.
5. **⚠️ Degraded metagraph read:** `visible=28/256` — only 28 of 256 UIDs were visible on the initial RPC read. A partial view can also wipe out the scoreable set. Secondary suspect (RPC endpoint quality / timing).
6. **⚠️ The cron exited "successfully" (exit 0) despite `ok: False`.** Render shows the run green, which is **why this went unnoticed for a week.** The wrapper does not propagate the scoring abort as a non-zero exit. (Monitoring blind spot — see §9.)

### Heartbeat — `sn21-validator-heartbeat` (`crn-d85m288js32c73ains8g`)

Firing every 4h on 29 May (00:00 / 04:00 / 08:00 / 12:00 / 16:00 / 20:00 UTC), each "finished successfully":

```
Running heartbeat: network=finney netuid=21 wallet=sn21-mainnet hotkey=validator
2026-05-29 00:01:22 INFO Enabling default logging (Warning level)
==> Cron job run finished successfully
```

What this shows:

7. **✅ Heartbeat is alive and correctly targeted** (same `sn21-mainnet / validator` hotkey, netuid 21, ~4h cadence). C8 satisfied.
8. **⚠️ But it can't help yet.** Because 25 May never committed weights (point 3), there is nothing in `Weights[21][111]` to re-assert → the heartbeat exits `skipped_no_prior_weights` (a no-op). It will only start holding vtrust **after** a scoring run successfully commits weights.
9. **⚠️ Heartbeat logs at WARNING level**, so the actual `action=…` line (`submitted` / `skipped_no_prior_weights` / `failed`) is suppressed — you can't currently see what it decided. Raise log level to surface it (see §6.3 / §9).

### Bottom line from logs

The chain of failure is now fully established and **narrower than feared**:

```
RELEASE_KEY pinned to (likely wrong) WR-2026-W21-PUB-E1  ──┐
partial metagraph read (visible=28/256)                   ──┤──► "no scoreable miners"
                                                            │
   ──► weights commit skipped (9.C.3 = None) ──► no weights on-chain for UID 111
        ──► heartbeat has nothing to re-assert (skipped_no_prior_weights)
             ──► activity floor (16.7h) drops UID 111 from consensus ──► validator_trust = 0 ──► earnings = 0
```

The fix is **not** wallet, stake, or delegation. It is: **get the scoring run to produce scoreable miners and commit weights (9.C.3 ≠ None).** Everything downstream (heartbeat hold, vtrust recovery, earnings) then follows automatically.

---

## 6. Required checks — pre-Monday (developer action list)

Run/verify each. **Every box must be ✅ before Monday's scoring window (Mon 05:00 UTC).**

Items already **confirmed from the 25–29 May logs (§5.1)** are marked `[x] CONFIRMED`. The open work is concentrated in **§6.0 — the primary blocker.**

### 6.0 PRIMARY BLOCKER — make scoring produce scoreable miners and commit weights ⭐
*This is the one thing that was actually broken. If only this section is fixed, vtrust recovers.*

- [ ] **P1 — Stop hard-pinning `RELEASE_KEY`; let `run.sh` auto-discover the latest release** (or pin it to the **correct** release for the epoch being scored). The 25 May run used `RELEASE_KEY=WR-2026-W21-PUB-E1 (manual override)`. Confirm the release key matches the epoch whose miner submissions you are scoring — a mismatched/stale release makes **every** miner unscoreable.
  ```bash
  # What auto-discovery WOULD pick (compare against any pinned value):
  curl -fsS -H "X-API-Key: $HOPE_API_KEY" "$HOPE_API_URL/internal/bittensor/v1/releases" \
    | jq -r '.releases | sort_by(.created_at) | reverse | .[0].release_key'
  ```
- [ ] **P2 — Confirm miners actually submitted for this epoch and the scoreability gate passes for >0 of them.** Archive fetches returned `ok=True match=True` on 25 May yet the result was still "no scoreable miners" — so the exclusion is at the **scoreability/release-match** step, not archive reachability. Run a scoring dry-run/diagnostic (see `scripts/diag/`, `scripts/verify_epoch.py`) and confirm the scoreable count is non-zero before Monday.
- [ ] **P3 — Fix the degraded metagraph read.** The 25 May run logged `visible=28/256` on the initial RPC read. Use a reliable finney endpoint (or add ret/retry until `visible` ≈ 256) so the full miner set is available to score.
- [ ] **P4 — Verify a successful run writes `9.C.3` (weights commit ≠ None).** This is the pass/fail signal. On 25 May `9.C.3 block: None`. A good run must show a real block number for 9.C.3 and `ok: True`.
- [ ] **P5 — If a stale `9.C.1`/already-scored guard blocks the recovery run**, re-run with `SN21_IGNORE_ALREADY_SCORED=1` (env) / `--ignore-already-scored` for the recovery only. (25 May took the first-scoring path with "0 revealed commitments," so this may not be needed — but have it ready.)

### 6.1 Identity & registration
- [x] **C1 — Wallet points at the validator hotkey. CONFIRMED** (25 May log: `wallet=sn21-mainnet / validator` → `validator 5GuiHBTfci…` = UID 111). No action needed.
- [ ] **C2 — Hotkey is registered with a validator permit on netuid 21.** (Live metagraph shows permit=True; re-confirm at run time.)
  ```bash
  btcli subnet metagraph --netuid 21 --subtensor.network finney | grep -i 111
  # Expect: UID 111, VALIDATOR_PERMIT = True, ACTIVE = True
  ```

### 6.2 Scoring run dependencies (`deploy/validator_scoring/run.sh`)
- [ ] **C3 — `HOPE_API_KEY` + `HOPE_API_URL` valid; release discovery returns a release** (folds into P1).
- [x] **C4 — Archive tiers reachable. CONFIRMED** (25 May log: many `archive fetch tier=2 ok=True match=True status=200`). No action needed.
- [ ] **C5 — `ED25519_KEY_FILE` present and readable** (used for inner_sig on the 9.C commits; 9.C.1 committed OK on 25 May, so this is likely fine — re-confirm).
- [ ] **C6 — `BT_NETWORK=finney`, `NETUID=21`.** (Confirmed in logs; keep.)
- [x] **C7 — `hope-validator` CLI present. CONFIRMED** (the scoring code ran and produced a structured epoch outcome).

### 6.3 Heartbeat (the part that *holds* vtrust all week)
- [x] **C8 — `sn21-validator-heartbeat` cron running on the correct hotkey, ~4h cadence. CONFIRMED** (29 May logs).
- [ ] **C9 — Understand the "no prior weights" trap:** the heartbeat is currently a no-op (`skipped_no_prior_weights`) **because no weights were ever committed.** Once P1–P4 land a weights commit, the heartbeat will begin re-asserting (flips to `submitted` / `skipped_recent_activity`).
- [ ] **C9b — Raise heartbeat log verbosity to INFO** so the `action=…` line is visible (currently logs at WARNING; you cannot see whether it submitted or skipped). Needed to satisfy V4.

### 6.4 Diagnose last week's failure
- [x] **C10 — DONE (§5.1).** Confirmed reason: `weights_commit_failed: no scoreable miners; skipping weights commit` (9.C.3 = None). Wallet, archives, and heartbeat were all fine; the scoreable-miner set was empty.
- [ ] **C11 — Fix the silent-success monitoring gap.** The cron exited 0 despite `ok: False`. Make the wrapper propagate a non-zero exit on `ok: False` (and/or alert on `9.C.3 == None`) so a future failed run is not shown green. (See §9.)

---

## 7. Monday run — expectations & sequencing

1. The scoring run commits weights during the **Mon 05:00–17:00 UTC** window, then reveals ~360 blocks (~72 min) later.
2. **vtrust does not jump instantly.** After the reveal, the chain needs a consensus cycle for vtrust to climb. Expect recovery toward ~1.0 over the **following ~1–2 days**, mirroring the 19–20 May ramp.
3. From that point the **heartbeat must re-assert** the committed weights every ~5h to hold vtrust above the 16.7h activity floor for the rest of the week.

> **⚠️ Schedule note:** the Render cron `sn21-validator-scoring` is set to `0 6 * * 1` (**Mon 06:00 UTC**). The scoring window opens 05:00 UTC, so 06:00 is valid but early; the repo's reference timer recommends **Mon 12:00 UTC** (mid-window, safely after the 05:00 miner deadline). Confirm the release for the just-closed epoch is published before the run fires, or move the cron to ~12:00 UTC.

---

## 8. Verification — how to confirm success (post-run, with certainty)

Run these in order after Monday's scoring run. **All must pass** to declare "we are OK going forward."

- [ ] **V1 — Weights committed on-chain for UID 111.**
  ```bash
  btcli wallet overview --wallet.name <WALLET_NAME> --subtensor.network finney
  # or inspect SubtensorModule.Weights[21][111] — must be NON-EMPTY and span multiple miner UIDs (not just {0:1.0})
  ```
- [ ] **V2 — Scoring logs show a clean commit** (no `aborted_reason`; 9.C.1/9.C.3/9.C.2 committed; `set_weights` success).
- [ ] **V3 — `LastUpdate` for UID 111 is recent and keeps refreshing** (heartbeat working): gap to current block stays **< 5,000 blocks** at all times.
  ```bash
  # Re-check every few hours; the gap must never approach 5,000 blocks.
  btcli subnet metagraph --netuid 21 --subtensor.network finney | grep -i 111
  ```
- [ ] **V4 — Heartbeat logs show `submitted` or `skipped_recent_activity`** (NOT `skipped_no_prior_weights`, NOT `failed`).
- [ ] **V5 — `validator_trust` is rising** over the 24–48h after reveal (Taostats history below). Target: trending to ~1.0.
- [ ] **V6 — `dividends` > 0 and `daily_validating_alpha` > 0** for UID 111 — earnings have resumed.

### Quick chain-verifiable vtrust/earnings check (Taostats)
```bash
# Daily vtrust / dividends / validating-alpha history for the validator hotkey:
curl -s -H "Authorization: $TAOSTATS_API_KEY" -H "Accept: application/json" \
  "https://api.taostats.io/api/metagraph/history/v1?netuid=21&uid=111&limit=30&order=block_number_desc" \
  | jq -r '.data[] | "\(.timestamp[0:10])  vtrust=\(.validator_trust)  div=\(.dividends)  val_alpha=\(.daily_validating_alpha)"'
```
Or use the dashboard **Neurons** tab (`https://sn21-monitor.onrender.com`) and watch UID 111's vtrust/earnings; the burn-aware **House weekly** rollup (`GET /api/house/weekly`) will show the `house_validators` bucket move off zero once it earns.

---

## 9. Ongoing monitoring (so this never silently recurs)

- **🔴 Fix the silent-success gap first (root of why this ran for a week unnoticed).** The 25 May scoring cron exited **0** despite `ok: False` / `9.C.3 = None`, so Render showed it green. Make `scoring_trigger.sh` exit non-zero on `ok: False`, and/or add an explicit alert when **`9.C.3 block == None`** after a scoring run.
- **Weekly:** confirm the Monday scoring run committed weights — `ok: True` **and** `9.C.3 block` is a real number (not `None`), weights non-empty and not all-burn.
- **Daily:** UID 111 `validator_trust ≥ 0.9` and `daily_validating_alpha > 0`. Any drop to 0 = investigate immediately (you have ~16.7h before consensus drop becomes total).
- **Heartbeat health:** raise its log level to INFO and alert if any firing returns `failed` or `skipped_no_prior_weights`, or if `current_block − LastUpdate` for UID 111 exceeds ~3,000 blocks.
- **Watch the metagraph-read health:** alert if the scoring run's `[RPC-DIAG] … visible=N/256` shows `N` well below 256 (25 May saw `28/256`).
- **Suggested alert:** add UID 111 vtrust + LastUpdate-gap to the existing daily Telegram digest so a regression is visible next morning.

---

## 10. Answers to the specific questions raised

- **"Will most validators delegating to 111 fix vtrust?"** — **No.** vtrust is independent of incoming stake (see §3.2). Delegation only scales earnings *after* vtrust > 0.
- **"Where is the stake — 111 or 135?"** — **111** (493,706 α). 135 has 65 α.
- **"Is 135 the operator's owner key?"** — **Yes** — `5EqAzby1` (UID 135) is the on-chain subnet-owner hotkey on the operator coldkey `5HjCYVfr`. Our `5DkEA99` is a downstream share recipient, not a neuron.
- **"Will running the validator Monday at UID 111 fix it?"** — **Yes, conditionally:** only if the scoring run completes a successful score→commit→reveal for `5GuiHB` **and** the heartbeat then re-asserts those weights. Last week neither held. §6–§8 are the checks that make it certain this week.

---

## Appendix A — Identifiers

| Item | Value |
|------|-------|
| Subnet | netuid **21** (finney) |
| Validator UID / hotkey | **111** / `5GuiHBTfciFauoF1XuyvVuWYrQaS7LExrbsqV5EmDU2ibJEz` |
| Owner UID / hotkey | **135** / `5EqAzby1upPkqpba5qrbDLZtFLmaTUe2PRbzih62voorQVHp` |
| Operator coldkey | `5HjCYVfrWSkzTfJM5rkWBW3qTTJqXEFUzZrKty5hodpgfjyW` |
| Our owner-share coldkey | `5DkEA99gAAF2Ge6X3h76x98LbYtqT7gJ6h9VaApfMkKJCPJM` |
| Validator code | `github.com/ippcteam/SN21-adtao` |
| Deploy repo | `github.com/ippcteam/adtao-deploy` |
| `activity_cutoff` | 5,000 blocks ≈ 16.7h |
| Heartbeat throttle | 1,500 blocks ≈ 5h |

## Appendix B — Render services (workspace: HOPE Platform `tea-d08vdr2dbo4c73ec018g`)

| Service | ID | Schedule / type | Role |
|---------|----|----|------|
| sn21-validator-scoring | `crn-d827jc77f7vs73dsinpg` | cron `0 6 * * 1` | Weekly weight-setting (`hope-validator`) |
| sn21-validator-heartbeat | `crn-d85m288js32c73ains8g` | cron `0 */4 * * *` | Re-assert weights (activity floor) |
| sn21-archive | `srv-d7ubsg1kh4rs738m7kh0` | web + 1GB disk | Archive tier (prediction ciphertext) |
| sn21_monitor (dashboard) | `srv-d7cb31nlk1mc7394ccig` | web + 1GB disk | Monitoring (`sn21-monitor.onrender.com`) |

## Appendix C — Key WeightSetter behaviours to be aware of (`hope/validator/weight_setter.py`)
- Default **burn = 95%** (weight to UID 0).
- All miner scores zero ⇒ returns `{0: 1.0}` (full burn).
- Tiered allocator with no qualifying miners ⇒ `{0: 1.0}` (full burn).
- A pure all-burn weight vector sets *a* weight (helps the activity floor) but may **not** align with the consensus miner distribution — aim for runs that produce real, non-empty miner weights.
