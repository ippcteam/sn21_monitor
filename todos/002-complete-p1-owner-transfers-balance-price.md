---
status: complete
priority: p1
issue_id: "002"
tags: [taostats, api, wallet]
dependencies: ["001"]
---

# Switch owner transfers, balance, and TAO price to `/v1`

## Problem Statement

The 08:15 UTC Taostats job feeds the home wallet, the 24-hour balance delta, and the TAO/USD price. After 9 November the three old paths 404. Before that, `order=timestamp_desc` and a `network` query on the account route are 400s on `/v1/`.

## Findings

- Plan: `docs/plans/taostats-v1-cutover.md`, Batch 2.
- `taostats_sync.py` calls `/api/transfer/v1`, `/api/account/latest/v1`, and `/api/price/latest/v1`.
- `fetch_owner_balance` does `(row.get("address") or {}).get("ss58")`. On `/v1/` `address` is a string, so that line raises and the function returns `None`. The sync then keeps the previous balance forever.
- `/v1/accounts/{address}` takes the address in the path and no query parameters. The body is still a one-element `data` list.
- `/v1/price` is still a one-row `data` list. `price` is a decimal string. `float()` already accepts it.
- `wallet_balances.py` calls `fetch_owner_balance`. Its own unit tests mock that function.

## Proposed Solutions

### Option 1: Swap paths and params in `taostats_sync.py`

**Approach:** Use the Batch 1 helpers. Leave wallet summary math alone.

**Pros:**
- Home cards and `tests/test_wallet_balances.py` keep their stored shape

**Cons:**
- None material

**Effort:** 1-2 hours

**Risk:** Low

---

### Option 2: Parse the new account object in `wallet_balances.py` as well

**Approach:** Teach both modules the new address shape.

**Pros:**
- None over Option 1

**Cons:**
- Two parsers for one response

**Effort:** 2 hours

**Risk:** Low

## Recommended Action

Follow Batch 2 in `docs/plans/taostats-v1-cutover.md`. GET the account URL with an empty query. Build transfer queries from `transfer_params`, including the optional `from` / `to` merge.

## Technical Details

**Affected files:**
- `taostats_sync.py` — three paths and the account address parse
- `tests/test_taostats_v1.py` — path constants and param assertions

**Related components:**
- `wallet_balances.py` consumes `fetch_owner_balance`
- `collector.py` falls back to CoinGecko and Binance when `fetch_tao_usd` returns `None`

**Database changes (if any):**
- None. `data/taostats_owner_transfers.json` keeps its keys.

## Resources

- **Plan:** `docs/plans/taostats-v1-cutover.md`
- **OpenAPI:** `GET /v1/transfers`, `GET /v1/accounts/{address}`, `GET /v1/price`

## Acceptance Criteria

- [x] Transfer queries use `order_by=timestamp` and `order_dir=desc` and contain no `order`
- [x] Account GET uses `/v1/accounts/{address}` and sends no `network` or `address` query parameter
- [x] A string `address` is stored on the balance dict
- [x] Price path is `/v1/price` with `asset=tao`
- [x] `python -m pytest tests/test_taostats_v1.py tests/test_wallet_balances.py -q` passes

## Work Log

### 2026-10-12 - Plan written

**By:** Cursor agent

**Actions:**
- Traced `fetch_owner_balance` into the home summary and wallet snapshot

**Learnings:**
- A thrown address parse is swallowed and looks like a preserved prior balance

### 2026-10-12 - Paths and request tests

**By:** Cursor agent

**Actions:**
- Pointed `TRANSFER_PATH` and `PRICE_LATEST_PATH` at the `/v1` constants
- `fetch_all_transfers` now uses `transfer_params`, including the optional `from` / `to` merge
- `fetch_owner_balance` GETs `/v1/accounts/{address}` with an empty query and reads a string address
- Added mocked session tests in `tests/test_taostats_v1.py`
- `.venv/bin/python -m pytest tests/test_taostats_v1.py tests/test_wallet_balances.py -q` — 22 passed

**Learnings:**
- `network` stays on the stored balance snapshot and is no longer a query parameter

## Notes

- Blocked by 001
- Live proof is todo 007
