---
status: complete
priority: p1
issue_id: "003"
tags: [taostats, api, subnet, scout]
dependencies: ["001"]
---

# Join the split pool and subnet responses

## Problem Statement

Activity, the daily digest, scout scores, and the lab miner-burn all read one old subnet payload and one old pool payload. `/v1/` splits each of those into two routes and drops net flow. A path-only change returns 200, and subnet daily would save null volume and a zero scout reserve.

## Findings

- Plan: `docs/plans/taostats-v1-cutover.md`, Batch 3.
- `subnet_sync.py` writes `data/subnet_daily.json`. It keeps the previous row only when a sub-fetch raises.
- `subnet_scan.py` scores AMM slippage from `pool["total_tao"]`. The new name is `tao_in_pool` on `/v1/subnets/pools`. Volumes and sentiment are on `/v1/subnets/pools/aggregate`.
- `incentive_burn` stays on `/v1/subnets/metrics`. `max_neurons` is `max_allowed_uids` on `/v1/subnets/hyperparameters`. `registration_allowed`, `tempo`, and burn bounds are on hyperparameters.
- `recycled_24_hours` is `tao_from_neuron_registration_24_hours` on metrics.
- `net_flow_1_day`, `net_flow_7_days`, and `net_flow_30_days` have no replacement.
- `lab/chain_pull.py` only needs `incentive_burn` from `data[0]`.

## Proposed Solutions

### Option 1: Join in the fetchers via `legacy_pool` and `legacy_subnet`

**Approach:** Two HTTP calls, one old-shaped dict, existing `_rao_to_tao` mapping unchanged. Raise `ValueError` when `tao_in_pool` or `incentive_burn` is missing so the current fallback keeps yesterday's row.

**Pros:**
- Digest and Activity keep their keys
- A partial new payload cannot wipe the daily file

**Cons:**
- Two extra HTTP calls per subnet in the scout loop

**Effort:** 3-4 hours

**Risk:** Medium

---

### Option 2: Store the new field names

**Approach:** Change `subnet_daily.json`, the digest, and the Activity template together.

**Pros:**
- Stored data matches the new API

**Cons:**
- Breaks every reader of historical rows that use the old keys

**Effort:** 6-8 hours

**Risk:** High

## Recommended Action

Follow Batch 3. Save net-flow keys as JSON `null`. Point the lab burn fetch at `/v1/subnets/metrics` only.

## Technical Details

**Affected files:**
- `subnet_sync.py`
- `subnet_scan.py`
- `lab/chain_pull.py`

**Related components:**
- `digest/sources/sn21_daily.py` reads `fear_and_greed_*` and burn fields from the daily file
- `templates/dashboard.html` reads `max_neurons`, `tempo`, `net_flow_*`, `recycled_24h_tao`

**Database changes (if any):**
- None. New daily rows keep the old keys. Net flow becomes null from the cutover day forward.

## Resources

- **Plan:** `docs/plans/taostats-v1-cutover.md`
- **OpenAPI:** `PoolResponse`, `AggregateResponse`, `SubnetMetricsResponse`, `HyperparametersResponse`

## Acceptance Criteria

- [x] Pool fetch reads `/v1/subnets/pools` and `/v1/subnets/pools/aggregate`
- [x] Subnet fetch reads `/v1/subnets/metrics` and `/v1/subnets/hyperparameters`
- [x] Stored pool still has `total_tao`, volume fields, and `fear_and_greed_index`
- [x] Stored subnet still has `incentive_burn`, `max_neurons`, `tempo`, and `recycled_24h_tao`
- [x] Stored subnet has `net_flow_1d_tao`, `net_flow_7d_tao`, and `net_flow_30d_tao` set to null
- [x] Missing `tao_in_pool` or `incentive_burn` raises, so the daily sync keeps the prior row
- [x] Lab burn reads `/v1/subnets/metrics`
- [x] Holder count reads `subnet_total_holders` from the leaderboard
- [x] `python -m pytest tests/test_taostats_v1.py tests/test_digest_sn21_daily.py tests/test_lab_amm.py -q` passes

## Work Log

### 2026-10-12 - Plan written

**By:** Cursor agent

**Actions:**
- Confirmed which scout and digest fields sit on which new schema

**Learnings:**
- A 200 from the unjoined route is more dangerous than a 400, because subnet daily treats only exceptions as failure

### 2026-10-12 - Pool and subnet joins

**By:** Cursor agent

**Actions:**
- `subnet_sync` and `subnet_scan` join pools with aggregate, and metrics with hyperparameters, then map through `legacy_pool` and `legacy_subnet`
- Holder count reads `/v1/alpha/leaderboard` with `subnet_rank` ascending
- Lab burn reads `/v1/subnets/metrics` only
- Offline suite: `.venv/bin/python -m pytest -q -m "not live"` — 171 passed

**Learnings:**
- Stored `net_flow_1d_tao`, `net_flow_7d_tao`, and `net_flow_30d_tao` are null because those fields have no `/v1` source

## Notes

- Blocked by 001
- Can run in parallel with 002, 004, 005, and 006 after 001
- Live equality of `tao_in_pool` and old `total_tao` is todo 007
