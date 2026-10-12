# Taostats `/v1` cutover

Project: `taostats-v1-cutover`
Branch: `chore/taostats-v1-cutover`
Status: ready to execute
Deadline: old `/api/` routes switch off on 9 November 2026. Both APIs answer until then.
Sources: [launch note](https://taostats.io/blog/taostats-new-api-launch), [migration guide](https://taostats.io/blog/api-migration-guide), `https://api.taostats.io/openapi.json` checked 12 October 2026.

Execute with the plan-batch workflow. One batch at a time. Stop after each batch for review. Do not start the next batch in the same turn.

## Goal

Every scheduled and on-demand Taostats read keeps working after `/api/` is gone. Stored JSON keeps the keys the dashboard, digest, and scout already read. A successful HTTP 200 with renamed fields must not overwrite a good daily row with nulls.

## Unchanged

- Host `https://api.taostats.io` (`TAOSTATS_API_BASE`)
- `TAOSTATS_API_KEY` in `Authorization`, raw key, no `Bearer` prefix
- `requests` (the blocked User-Agent applies to Python `urllib` only)
- List envelope `{data, pagination}` and `next_page`
- RAO amounts as decimal strings. Existing `int()` / `float()` parsers accept them
- `bot_watch.py` already calls `/v1/subnets/stake-events` with `order_by` and `order_dir`

## Out of scope

- Finding a replacement for `net_flow_1_day`, `net_flow_7_days`, `net_flow_30_days`. Those fields stay on our rows as JSON `null`.
- Rewriting historical changelog entries, docs, or the miner-payout seed that mention old paths.
- Merging each file's 429 retry loop into one client.
- Renaming keys inside `subnet_daily.json`, `neurons` payloads, or `taostats_owner_transfers.json`.
- Editing `bot_watch.py`.

## Approach

Add `taostats_v1.py` as the only place that knows new paths and old field names. Callers keep their retry loops and their stored-key normalizers. The adapter returns a dict shaped like the old response row.

Rejected: change every `.get("total_tao")` and dashboard key to the new names. That touches the digest, scout, and Activity tab for no gain.

Rejected: a generated OpenAPI client. Nine call sites do not need one.

## Adapter contract

`taostats_v1.py` exports the following. Unit tests import these directly.

```text
PATH_TRANSFERS = "/v1/transfers"
PATH_PRICE = "/v1/price"
PATH_ALPHA_LEADERBOARD = "/v1/alpha/leaderboard"
PATH_ALPHA_HISTORY = "/v1/alpha/history"
PATH_METAGRAPH = "/v1/subnets/metagraph"
PATH_POOLS = "/v1/subnets/pools"
PATH_POOLS_AGGREGATE = "/v1/subnets/pools/aggregate"
PATH_SUBNET_METRICS = "/v1/subnets/metrics"
PATH_SUBNET_HYPERPARAMETERS = "/v1/subnets/hyperparameters"
PATH_VALIDATORS_ACTIVE = "/v1/validators/active"

account_path(address) -> "/v1/accounts/{address}"
ss58(value) -> str | None          # dict.ss58 or a stripped string
transfer_params(address, network="finney", limit=200) -> dict
    # keys: network, address, limit, order_by=timestamp, order_dir=desc
    # no key named "order"
leaderboard_params(**filters) -> dict
    # copies filters, sets order_by=subnet_rank, order_dir=asc
    # drops any incoming "order"
    # subnet_rank 1 is the largest alpha balance, so asc matches old balance_desc
legacy_pool(pool_row, aggregate_row) -> dict
    # raises ValueError if tao_in_pool is missing
    # total_tao <- tao_in_pool
    # price, liquidity, market_cap, total_alpha, block_number, timestamp from the pool row
    # 24h volume, buy/sell counts, price_change_* from the aggregate row, same names
    # fear_and_greed_index <- sentiment_index
    # fear_and_greed_sentiment <- sentiment
    # rank is None
legacy_subnet(metrics_row, hyper_row) -> dict
    # raises ValueError if incentive_burn is missing
    # copies metrics fields that kept their names (validators, active_*, active_keys,
    #   neuron_registration_cost, neuron_registrations_this_interval, registration_allowed
    #   is NOT on metrics — it is on hyperparameters)
    # recycled_24_hours <- tao_from_neuron_registration_24_hours
    # recycled_lifetime stays
    # max_neurons <- hyperparameters.max_allowed_uids
    # tempo, min_burn, max_burn, burn_half_life, burn_increase_mult, registration_allowed
    #   from hyperparameters
    # net_flow_1_day, net_flow_7_days, net_flow_30_days are None
legacy_metagraph_row(row) -> dict
    # shallow copy
    # is_immunity_period <- is_immune when the old key is absent
    # axon "ip:port" becomes {"ip", "port", "block": None}; split on the last colon
    # a missing axon stays absent
    # daily_reward <- emission * 20 when the key is absent (live identity held on 2026-10-12)
legacy_account_ss58(row, fallback) -> str
    # string address, or address.ss58, else fallback
```

`registration_allowed` lives on hyperparameters, not metrics. `incentive_burn` lives on metrics.

## Persistence rule

`subnet_sync.sync_subnet_daily` already keeps the previous row when a sub-fetch raises. `legacy_pool` and `legacy_subnet` raise `ValueError` on the two fields we cannot lose (`tao_in_pool`, `incentive_burn`), so that existing fallback runs. A joined row that merely lacks net flow is valid and is saved with those keys set to `null`.

Holders, basket, and weights already skip the write when the HTTP call raises. Keep that.

## Batches

### Batch 1 — Adapter module

Todo: `todos/001-ready-p1-taostats-v1-adapters.md`

1. Add `taostats_v1.py` with the contract above. No HTTP.
2. Add `tests/test_taostats_v1.py` covering:
   - transfer params contain `order_by` / `order_dir` and contain no `order`
   - leaderboard params force `subnet_rank` + `asc` and drop an incoming `order`
   - `account_path` percent-encodes nothing unexpected for a plain SS58 (SS58 alphabet is URL-safe; still use the address as a single path segment)
   - `ss58` reads a dict and a string
   - `legacy_pool` maps `tao_in_pool` and aggregate volumes, and raises when `tao_in_pool` is absent
   - `legacy_subnet` maps `max_allowed_uids` and `tao_from_neuron_registration_24_hours`, sets the three net-flow keys to `None`, and raises when `incentive_burn` is absent
   - `legacy_metagraph_row` maps `is_immune` and splits `axon`
   - `legacy_account_ss58` reads a string
3. Run `python -m pytest tests/test_taostats_v1.py -q`

Done when those tests pass and no caller imports the module yet.

### Batch 2 — Owner transfers, balance, price

Todo: `todos/002-ready-p1-owner-transfers-balance-price.md`

Files: `taostats_sync.py`

1. Point `TRANSFER_PATH` and `PRICE_LATEST_PATH` at the new constants.
2. `fetch_all_transfers` uses `transfer_params`. The optional `from` / `to` merge keeps those keys and also uses `order_by` / `order_dir`.
3. `fetch_owner_balance` GETs `account_path(address)` with no query parameters. Omit `address` and `network` from the query string. Still read `body["data"][0]`. Set `address` via `legacy_account_ss58`.
4. `fetch_tao_usd` stays `{"asset": "tao"}` against `/v1/price`. `float()` of a decimal string already works.
5. Extend `tests/test_taostats_v1.py` (or a sibling) with a mocked `requests.Session` if the functions can be called without the network. If mocking the session is awkward, test the params helpers only and assert the path constants in `taostats_sync` equal the adapter constants.
6. Run `python -m pytest tests/test_taostats_v1.py tests/test_wallet_balances.py -q`

Done when a balance fetch cannot send `network` or `order`, and wallet-balance unit tests still pass.

### Batch 3 — Pool and subnet joins

Todo: `todos/003-ready-p1-pool-and-subnet-join.md`

Files: `subnet_sync.py`, `subnet_scan.py`, `lab/chain_pull.py`

1. `subnet_sync.fetch_pool_latest` calls pools and pools/aggregate for `netuid=21`, passes both rows through `legacy_pool`, then keeps the existing `_rao_to_tao` / `_to_float` mapping.
2. `subnet_sync.fetch_subnet_latest` calls metrics and hyperparameters, passes both through `legacy_subnet`, then keeps the existing mapping. `max_neurons`, `tempo`, and `recycled_24h_tao` therefore stay populated. Net-flow fields save as `null`.
3. `fetch_total_holders` calls the leaderboard with `leaderboard_params(netuid=21, limit=1)` and still reads `subnet_total_holders`.
4. `subnet_scan` uses the same two joins before `_score_subnet` and `_risk_signals`. `_score_subnet` keeps reading `total_tao`, `price`, and `alpha_volume_24_hr` off the legacy dict. `_risk_signals` keeps reading `incentive_burn`, `net_flow_30_days`, `active_validators`, `active_miners`, `neuron_registration_cost`, `registration_allowed`.
5. `lab/chain_pull.py` reads `incentive_burn` from `/v1/subnets/metrics` only. The body is still `data[0]`. Do not join hyperparameters there.
6. Add adapter-level tests if batch 1 missed a field this batch reads. Add one test that a missing `tao_in_pool` raises, so `sync_subnet_daily`'s existing exception path keeps the prior row. Do not need a full sync integration test if that path is unchanged and the raise is tested.
7. Run `python -m pytest tests/test_taostats_v1.py tests/test_digest_sn21_daily.py tests/test_lab_amm.py -q`

Done when scout still sees a TAO reserve under the key `total_tao`, and net flow is explicitly null rather than a dropped key.

### Batch 4 — Alpha leaderboard and history

Todo: `todos/004-ready-p1-alpha-leaderboard-and-history.md`

Files: `holders_sync.py`, `stake_watch.py`, `weights_scan.py`

1. Replace stake-balance latest paths with `PATH_ALPHA_LEADERBOARD`.
2. Every latest call uses `leaderboard_params`. The three current `order=balance_desc` sites are `holders_sync._fetch_page`, `weights_scan._fetch_hotkey_name`, and `weights_scan.our_validator_wallets`.
3. Keep `PAGE_SIZE = 200` in holders. A limit above 200 is a 400.
4. `stake_watch` history path becomes `PATH_ALPHA_HISTORY`. Keep sending `coldkey`, `hotkey`, `netuid`, and `limit`. Omit `order` and `block_number`. Latest uses `leaderboard_params` with those three filters.
5. `_ss58` in holders already accepts a string. Leave it.
6. Add a unit test that each built query dict has no `order` key.
7. Run `python -m pytest tests/test_taostats_v1.py tests/test_owner_share_lock.py -q`

Done when a holder page and a weights-scan page cannot send `order`.

### Batch 5 — Metagraph

Todo: `todos/005-ready-p1-metagraph-legacy-rows.md`

Files: `neurons_sync.py`, `wallet_balances.py`, `subnet_scan.py`

1. Point all three `METAGRAPH` paths at `PATH_METAGRAPH`.
2. Run each raw row through `legacy_metagraph_row` before `neurons_sync._normalise_row` and `subnet_scan._parse_metagraph`.
3. Leave `daily_reward` unset when the new row lacks it. The neurons table cell may be blank until batch 7 records whether old `daily_reward` equals `emission * 20` on SN21. Do not guess that formula in this batch.
4. Keep existing page sizes (`100` in neurons and scout, `5` on the wallet hotkey lookup). Keep `next_page` loops.
5. `wallet_balances.lookup_validator_coldkey` only needs string hotkey and coldkey. `_ss58` there already accepts a string. Path change is enough.
6. Run `python -m pytest tests/test_taostats_v1.py tests/test_neurons_role.py tests/test_neurons_burn.py tests/test_wallet_balances.py -q`

Done when an `is_immune: true` fixture becomes `is_immunity_period: true`, and an axon string `1.2.3.4:9000` becomes ip `1.2.3.4` and port `9000`.

### Batch 6 — Active validators

Todo: `todos/006-ready-p1-validators-active.md`

Files: `validator_basket_sync.py`

1. Point `AVAILABLE_PATH` at `PATH_VALIDATORS_ACTIVE`.
2. `_fetch_available` sends `{"netuid": NETUID}` once. Omit `page` and `limit`. Read `data` as the full list. Delete the page loop.
3. `parse_available_row` already accepts a string `address` and a string `hotkey_alpha`. Add a unit test with a string address next to the existing object-address test in `tests/test_validator_basket.py`.
4. Run `python -m pytest tests/test_validator_basket.py tests/test_taostats_v1.py -q`

Done when the basket fetch has a single request shape and both address shapes parse.

### Batch 7 — Live comparison and full regression

Todo: `todos/007-ready-p1-live-comparison.md`

This batch is the gate. It needs `TAOSTATS_API_KEY` in the environment. Skip the live file when the key is absent. Never print the key. Never commit `.env`.

1. Add `tests/test_taostats_v1_live.py`, marked so a normal `pytest` run skips it without a key (`pytest.importorskip` is the wrong tool; use `pytest.mark.skipif`).
2. Register the marker in `pytest.ini` or `conftest.py` if pytest warns about an unknown marker.
3. Live contract checks, all against `/v1/`, netuid 21. Hard failures:
   - `/v1/price?asset=tao` returns a parseable `data[0].price`
   - `/v1/accounts/{TAOSTATS_OWNER_ID}` returns `data[0].balance_total` and the address string equals the owner id. Skip this one check when `TAOSTATS_OWNER_ID` is unset.
   - pools `tao_in_pool` and `price` present; aggregate `tao_volume_24_hr` present
   - metrics `incentive_burn` present; hyperparameters `max_allowed_uids` and `tempo` present
   - metagraph pagination with `limit=200` returns at least 200 rows and the uid set size is 256
   - leaderboard `limit=1` returns integer `subnet_total_holders`
   - `/v1/validators/active?netuid=21` returns 200 and a non-empty `data` list
   - the same validators URL with `limit=1` returns 400 (locks the "omit limit" rule)
   - alpha history for the stake-watch coldkey, hotkey, and netuid returns 200 with `balance` and `timestamp` when those env values are set; skip when they are not
   - `bot_watch.STAKE_EVENTS_PATH` is still `/v1/subnets/stake-events`
4. Side-by-side checks while `/api/` still answers. If an old path returns 404, skip the pair and keep the `/v1/` contract checks. Hard failures when both answer:
   - `tao_in_pool` equals old `total_tao` as integers
   - `max_allowed_uids` equals old `max_neurons`
   - `incentive_burn` floats differ by less than `1e-6`
   - metagraph uid sets are equal
   - for five shared uids, when `block_number` matches, `daily_mining_alpha` strings are equal
   - record, and do not fail, the old `daily_reward` versus `emission * 20`. Write the result into the test output and into this plan's work note in todo 007. Fill `daily_reward` in `legacy_metagraph_row` only if they match on all five uids.
5. Soft report only (print, do not fail): sentiment index delta, market-cap delta, holder-count delta, validator hotkey symmetric difference, age of the leaderboard timestamp, old net-flow values that we now store as null.
6. Run offline regression:

```bash
python -m pytest -q -m "not live"
python -m pytest -q tests/test_taostats_v1_live.py
```

7. Update module docstrings that still say the old paths: `taostats_sync.py`, `subnet_sync.py`, `subnet_scan.py`, `holders_sync.py`, `stake_watch.py`, `neurons_sync.py`, `validator_basket_sync.py`, `weights_scan.py`, `lab/chain_pull.py`. Leave historical `CHANGELOG.md` sections as they are. Add one new changelog entry for the cutover. Update the Taostats comment in `.env.example` only if it still points at a dead docs URL. Keys stay on the header described there.
8. Do not run the dashboard sync buttons against production data as part of this batch. The live pytest file is the check.

Done when offline pytest passes, live pytest passes with a key, and the daily_reward decision is recorded.

## Testing matrix

| Behavior | Where it is proved |
| --- | --- |
| No `order` query key | `tests/test_taostats_v1.py` |
| No `page` or `limit` on validators | basket unit test of the params, plus live 400 when `limit=1` is sent on purpose |
| `tao_in_pool` becomes stored `total_tao` | adapter unit test, live integer equality |
| Missing `tao_in_pool` or `incentive_burn` raises | adapter unit test, so subnet daily keeps the prior row |
| Net flow stored as null | adapter unit test |
| Immunity and axon | adapter unit test |
| String SS58 address | adapter unit test and `tests/test_validator_basket.py` |
| Existing basket, wallet, neuron, digest, bot tests | batch pytest commands |
| Bot watch path untouched | live file asserts the constant |
| 256 SN21 uids | live metagraph pagination |
| Price, burn, pool reserve, holder count | live, with the tolerances above |

## Stop conditions

Stop and ask when:

- A `/v1/` call we believe is valid returns 400. Paste the error `message` (it names the bad parameter). Do not guess a new parameter name.
- Live `tao_in_pool` does not equal old `total_tao`.
- Live metagraph uid count is not 256.
- `incentive_burn` is missing on `/v1/subnets/metrics`.
- The live file would need to print the API key or write a store under `data/`.
