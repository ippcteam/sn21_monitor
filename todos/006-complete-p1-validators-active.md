---
status: complete
priority: p1
issue_id: "006"
tags: [taostats, api, validators]
dependencies: ["001"]
---

# Load SN21 validators from `/v1/validators/active`

## Problem Statement

The 08:50 UTC basket sync pages `/api/dtao/validator/available/v1` with `limit` and `page`. `/v1/validators/active` returns the whole list in one body and answers 400 if either parameter is sent.

## Findings

- Plan: `docs/plans/taostats-v1-cutover.md`, Batch 6.
- `validator_basket_sync._fetch_available` loops on `page` with `PAGE_SIZE = 200`.
- The new query accepts only `netuid`.
- Response fields stay `address`, `name`, `hotkey_alpha`, `netuid`. `address` is a plain SS58 string. `parse_available_row` and `_ss58` already accept a string. Existing tests still pass an `{ss58, hex}` object.
- `hotkey_alpha` can lag by up to a day, so entered and exited names can be a day late. That is expected. Do not try to correct it.

## Proposed Solutions

### Option 1: One request, `netuid` only

**Approach:** Delete the page loop. Keep `parse_available_row`.

**Pros:**
- Matches the new contract
- Parser tests stay valid

**Cons:**
- Basket membership can lag a day

**Effort:** 1 hour

**Risk:** Low

---

### Option 2: Keep paging and catch the 400

**Approach:** Try with `page`, then retry without it.

**Pros:**
- Works during the overlap if the old route is still selected by mistake

**Cons:**
- Hides a bad request behind a retry

**Effort:** 1 hour

**Risk:** Medium

## Recommended Action

Follow Batch 6. Option 1. Add a string-address case beside the existing object-address test.

## Technical Details

**Affected files:**
- `validator_basket_sync.py`
- `tests/test_validator_basket.py`

**Related components:**
- Basket snapshot joins the holders index from todo 004's data file. This todo does not change that join.

**Database changes (if any):**
- None

## Resources

- **Plan:** `docs/plans/taostats-v1-cutover.md`
- **OpenAPI:** `GET /v1/validators/active`

## Acceptance Criteria

- [x] The fetch URL is `/v1/validators/active`
- [x] The only query parameter is `netuid`
- [x] The page loop is gone
- [x] `tests/test_validator_basket.py` covers a string `address` and the existing object `address`
- [x] `python -m pytest tests/test_validator_basket.py tests/test_taostats_v1.py -q` passes

## Work Log

### 2026-10-12 - Plan written

**By:** Cursor agent

**Actions:**
- Read `_fetch_available` and `parse_available_row`

**Learnings:**
- The parser already accepts both address shapes. The break is the query, not the row.

### 2026-10-12 - Active validators

**By:** Cursor agent

**Actions:**
- Basket sync requests `/v1/validators/active` once with `netuid` only
- Unit test covers a string address beside the existing object address
- Live check: the same URL with `limit=1` returns 400

**Learnings:**
- One old validator address was absent from the new list on 2026-10-12. Membership can lag up to a day, so that delta is recorded and not a failure

## Notes

- Blocked by 001
- Live 400-on-`limit` check is todo 007
