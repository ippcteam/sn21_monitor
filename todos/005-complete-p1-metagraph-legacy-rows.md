---
status: complete
priority: p1
issue_id: "005"
tags: [taostats, api, neurons]
dependencies: ["001"]
---

# Read the metagraph from `/v1/subnets/metagraph`

## Problem Statement

Neurons, the validator coldkey lookup, and scout stake ladders call `/api/metagraph/latest/v1`. The new route renames immunity, turns `axon` into an `ip:port` string, and removes `daily_reward`, `rank`, `trust`, and `stake`. The default page size is 50, which would drop most of SN21's 256 UIDs if a caller forgot `limit`.

## Findings

- Plan: `docs/plans/taostats-v1-cutover.md`, Batch 5.
- `neurons_sync.py` pages at 100 and follows `next_page`. `subnet_scan.py` does the same. `wallet_balances.lookup_validator_coldkey` uses `limit=5`.
- `neurons_sync._normalise_row` reads `is_immunity_period`. Missing becomes `False`, so every IMM badge would clear.
- Axon handling already ignores a non-dict, which would blank IP and port. `legacy_metagraph_row` should rebuild `{ip, port, block: None}` before that code runs.
- `trust` and `stake` were `"0"` on the old API. Losing them does not change stake math, which uses `total_alpha_stake`.
- `daily_reward` equalled `emission × 20` on the rows Taostats checked. That identity is not confirmed for SN21. Do not invent it here.
- Daily mining, burn, owner, and validating alpha fields keep their names and stay RAO strings.

## Proposed Solutions

### Option 1: Normalize each raw row with `legacy_metagraph_row`

**Approach:** Path swap plus the adapter. Leave `daily_reward` empty until todo 007 confirms the formula.

**Pros:**
- Immunity and axon survive
- No guessed reward column

**Cons:**
- The neurons reward cell is blank until the live check

**Effort:** 2 hours

**Risk:** Low

---

### Option 2: Set `daily_reward` to `emission * 20` now

**Approach:** Apply the migration guide's sample identity.

**Pros:**
- The reward column stays filled

**Cons:**
- Wrong if SN21 does not match the sample

**Effort:** 2 hours

**Risk:** Medium

## Recommended Action

Follow Batch 5. Option 1. Keep the existing limits and `next_page` loops.

## Technical Details

**Affected files:**
- `neurons_sync.py`
- `wallet_balances.py` — path only
- `subnet_scan.py` — path plus `legacy_metagraph_row` before `_parse_metagraph`

**Related components:**
- Neurons tab, house weekly, and miner payouts read the normalized neuron rows
- `tests/test_neurons_role.py` and `tests/test_neurons_burn.py` build rows themselves and do not call Taostats

**Database changes (if any):**
- None

## Resources

- **Plan:** `docs/plans/taostats-v1-cutover.md`
- **OpenAPI:** `GET /v1/subnets/metagraph`, schema `MetagraphResponse`

## Acceptance Criteria

- [x] All three metagraph paths are `/v1/subnets/metagraph`
- [x] Page limits stay 100, 100, and 5
- [x] `is_immune: true` becomes `is_immunity_period: true`
- [x] Axon `1.2.3.4:9000` becomes ip `1.2.3.4` and port `9000`
- [x] `daily_reward` is not synthesized in this todo
- [x] `python -m pytest tests/test_taostats_v1.py tests/test_neurons_role.py tests/test_neurons_burn.py tests/test_wallet_balances.py -q` passes

## Work Log

### 2026-10-12 - Plan written

**By:** Cursor agent

**Actions:**
- Compared `MetagraphResponse` properties to `_normalise_row`

**Learnings:**
- Wallet coldkey lookup only needs string hotkey and coldkey, which `_ss58` already handles

### 2026-10-12 - Metagraph rows

**By:** Cursor agent

**Actions:**
- Neurons, scout, and wallet lookup read `/v1/subnets/metagraph`
- Page sizes stay 100, 100, and 5
- `legacy_metagraph_row` restores `is_immunity_period` and splits `axon`
- `daily_reward` was left empty in this batch. Todo 007 filled it after the live check

**Learnings:**
- New axon values are `ip:port` strings. A missing axon stays absent

## Notes

- Blocked by 001
- Todo 007 filled `daily_reward` from `emission * 20` after the live identity held
