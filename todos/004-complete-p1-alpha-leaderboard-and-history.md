---
status: complete
priority: p1
issue_id: "004"
tags: [taostats, api, holders, stake]
dependencies: ["001"]
---

# Switch stake-balance reads to the alpha leaderboard and history

## Problem Statement

Holders, stake watch, the subnet holder count, and the weights-scan name lookup all call `/api/dtao/stake_balance/latest/v1`. Three of them send `order=balance_desc`, which `/v1/alpha/leaderboard` rejects. Stake-watch history becomes one end-of-day row.

## Findings

- Plan: `docs/plans/taostats-v1-cutover.md`, Batch 4.
- `order=balance_desc` is in `holders_sync._fetch_page`, `weights_scan._fetch_hotkey_name`, and `weights_scan.our_validator_wallets`.
- Allowed sorts are `global_rank` and `subnet_rank`. Rank 1 is the largest alpha balance, so `order_by=subnet_rank&order_dir=asc` matches the old descending balance order.
- `subnet_total_holders`, `balance`, `balance_as_tao`, `coldkey`, `hotkey`, and `hotkey_name` keep their names. Coldkey and hotkey are plain SS58 strings. Holders `_ss58` already accepts a string.
- Page size max is 200. Holders already uses 200.
- The leaderboard refreshes hourly. History (`/v1/alpha/history`) is one row per day at the last block. Stake watch already overlays the latest point on daily history.
- History requires `coldkey`, `hotkey`, and `netuid`. The `block_number` filter is gone.

## Proposed Solutions

### Option 1: Replace paths and build queries with `leaderboard_params`

**Approach:** Drop `order`. Keep paging and the stored holder fields.

**Pros:**
- Movement diffs stay keyed by hotkey and coldkey
- The 30-hour inflow check still has a latest point

**Cons:**
- A manual sync can be up to an hour behind the chain

**Effort:** 2 hours

**Risk:** Low

---

### Option 2: Keep requesting `order=balance_desc` until 9 November

**Approach:** Switch the path only.

**Pros:**
- Smaller diff today

**Cons:**
- The new API 400s immediately, so the overlap window cannot be used to test

**Effort:** 30 minutes

**Risk:** High

## Recommended Action

Follow Batch 4. Holders page size stays 200. History omits `order` and `block_number`.

## Technical Details

**Affected files:**
- `holders_sync.py`
- `stake_watch.py`
- `weights_scan.py`
- `subnet_sync.py` holder count is todo 003; this todo must not reintroduce `order` there

**Related components:**
- Movement tab and the digest's holder movers read `data/holders_snapshots.json`
- Stake-watch alert uses `data/stake_watch_history.json`

**Database changes (if any):**
- None

## Resources

- **Plan:** `docs/plans/taostats-v1-cutover.md`
- **OpenAPI:** `GET /v1/alpha/leaderboard`, `GET /v1/alpha/history`

## Acceptance Criteria

- [x] Latest stake reads use `/v1/alpha/leaderboard`
- [x] History reads use `/v1/alpha/history`
- [x] No stake query contains an `order` key
- [x] Leaderboard queries set `order_by=subnet_rank` and `order_dir=asc`
- [x] Holders `PAGE_SIZE` remains 200
- [x] `python -m pytest tests/test_taostats_v1.py tests/test_owner_share_lock.py -q` passes

## Work Log

### 2026-10-12 - Plan written

**By:** Cursor agent

**Actions:**
- Listed the three `order=balance_desc` call sites

**Learnings:**
- Sort order does not change holder deltas when every page is fetched. It still matters if a page fails partway, so the sort stays largest-first.

### 2026-10-12 - Leaderboard and history

**By:** Cursor agent

**Actions:**
- Holders, stake watch, and weights scan call `/v1/alpha/leaderboard` through `leaderboard_params` (`subnet_rank` asc, no `order`)
- Stake history calls `/v1/alpha/history` with coldkey, hotkey, and netuid only
- Holders page size stays 200

**Learnings:**
- Live leaderboard was about 33 minutes old (`age_seconds=1998`), which matches the hourly refresh

## Notes

- Blocked by 001
- Live holder count and history checks are todo 007
