---
status: complete
priority: p1
issue_id: "001"
tags: [taostats, api, adapters]
dependencies: []
---

# Add the Taostats `/v1` adapter module

## Problem Statement

Nine modules call the old Taostats `/api/` paths. The new API renames fields and splits two responses. If each caller maps those fields itself, scout and the daily subnet row will drift.

## Findings

- Plan: `docs/plans/taostats-v1-cutover.md`, Batch 1.
- Old paths switch off on 9 November 2026. Host, key, and `Authorization` header stay.
- `bot_watch.py` is already on `/v1/subnets/stake-events`.
- Stored JSON keys (`total_tao`, `fear_and_greed_index`, `max_neurons`, `is_immunity_period`) must stay. The dashboard and digest read those names.

## Proposed Solutions

### Option 1: One adapter module, callers keep their retry loops

**Approach:** `taostats_v1.py` holds paths and pure functions that return old-shaped dicts. No HTTP.

**Pros:**
- One mapping for subnet sync and scout
- Unit tests need no API key

**Cons:**
- A new module beside the existing per-file clients

**Effort:** 2-3 hours

**Risk:** Low

---

### Option 2: Map fields inside each caller

**Approach:** Update every `.get` at the call site.

**Pros:**
- No new file

**Cons:**
- Pool and subnet joins would be copied in `subnet_sync.py` and `subnet_scan.py`

**Effort:** 4-6 hours

**Risk:** Medium

## Recommended Action

Build Option 1 exactly as the adapter contract in `docs/plans/taostats-v1-cutover.md` Batch 1. Do not import the module from callers in this todo.

## Technical Details

**Affected files:**
- `taostats_v1.py` — new
- `tests/test_taostats_v1.py` — new

**Related components:**
- Consumed later by todos 002–006

**Database changes (if any):**
- None

## Resources

- **Plan:** `docs/plans/taostats-v1-cutover.md`
- **Migration guide:** https://taostats.io/blog/api-migration-guide
- **OpenAPI:** https://api.taostats.io/openapi.json

## Acceptance Criteria

- [x] `taostats_v1.py` exports the paths and functions listed in the plan
- [x] Transfer and leaderboard param builders emit no `order` key
- [x] `legacy_pool` maps `tao_in_pool` to `total_tao` and raises when `tao_in_pool` is missing
- [x] `legacy_subnet` maps `max_allowed_uids` and the 24h recycle field, sets three net-flow keys to `None`, and raises when `incentive_burn` is missing
- [x] `legacy_metagraph_row` maps `is_immune` and splits an `ip:port` axon
- [x] `python -m pytest tests/test_taostats_v1.py -q` passes
- [x] No production caller imports the module yet

## Work Log

### 2026-10-12 - Plan written

**By:** Cursor agent

**Actions:**
- Reviewed every `/api/` call site against the migration guide and OpenAPI
- Wrote the adapter contract into the cutover plan

**Learnings:**
- `subnet_rank` ascending is the old `balance_desc` order, because rank 1 is the largest alpha balance
- `net_flow_*` has no new endpoint

### 2026-10-12 - Adapter and tests

**By:** Cursor agent

**Actions:**
- Added `taostats_v1.py` with the path constants and legacy adapters. No HTTP.
- Added `tests/test_taostats_v1.py`
- Ran `.venv/bin/python -m pytest tests/test_taostats_v1.py -q` — 11 passed
- Confirmed no production module imports `taostats_v1`

**Learnings:**
- This repo's pytest run needs `python -m pytest` so the project root stays on `sys.path`

## Notes

- Batch 1 of `docs/plans/taostats-v1-cutover.md`
- Unblocks 002, 003, 004, 005, and 006
