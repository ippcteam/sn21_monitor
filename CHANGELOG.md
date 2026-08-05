# Changelog

All notable changes to the SN21 Monitor. Newest first.

## 2026-07-29 — Emission gate: read q/h/θ instead of fitting them

### Fixed
- **The gate hyperparams were fitted when they can simply be read.** `q`, `h` and
  `θ` are plain storage items (`EmissionBarQuantile`, `EmissionGateExponent`,
  `EmissionGateBar`). The lab carried `LIVE_Q = 0.77 / LIVE_H = 2.9`, fitted to
  SN21's observed share; **the chain runs q = 0.75, h = 3.0 exactly**. `chain_pull`
  now reads all three into ChainState (`gate_q`/`gate_h`/`gate_theta`) and
  `hill_gate_v440_2990` consumes them, preferring the chain's own last-computed θ
  over reconstructing the bar. `_gate_q`/`_gate_h` still override, for sweeps.
- **`LIVE_VERSION` flipped to `hill_gate_v440_2990`.** The un-gated v432 formula
  had been failing its own reproduction gate since the gate activated at block
  ~8,715,000 — every run printed "REGRESSION DETECTOR". Measured on live state at
  block ~8,728,000 with the chain-read hyperparams:

  | mechanism | network median rel.err | within tol | SN21 |
  |---|---|---|---|
  | `root_reborn_v425_2800` (was live) | 1.783 | 6/62 | off by 64.0× |
  | `hill_gate_v440_2990` (now live) | 0.207 | 27/62 | off by 0.33× |

  **The gate still does not clear the 0.15 tolerance** — magnitudes remain
  directional, with residual model error to chase (emit-enabled set, MinerBurned
  basis, excess-TAO leg). The earlier "rel.err 0.024 PASS" came from fitting
  (q,h) to SN21's own share, which is circular and hid this gap.

### Added
- **Gate-parameter tripwire in `dereg_watch.py`** — q/h/θ are recorded every run
  and **any change to q or h alerts**, because nothing else catches them: they
  move by a single `ensure_root` call (`sudo_set_emission_bar_quantile`), with no
  PR, no runtime upgrade, no release note, effective the next block. Dropping q to
  the 0.61 code default was measured at ~×0.11 on SN21's emission. θ is recorded
  but only reported on a ≥25% move, since the chain recomputes it every 360 blocks
  off the live distribution and it drifts continuously.

## 2026-07-29 — Dereg is a rank, not a floor: live prune-queue tripwire

### Fixed
- **The dereg floor was never a chain constant.** `DEREG_FLOOR_TAO = 0.0035`
  (lab/scenarios.py, root_reborn_model.py) was an admitted assumption, and by
  today SN21's own EMA (0.00338) had fallen *below* it — the lab was scoring
  "high" dereg risk against a number the chain never reads. Source-read of
  subtensor `main` and verified live @ block 8,727,955: `do_register_network`
  dissolves one subnet on every registration once the network is full (128/128
  live today), and `get_network_to_prune` (coinbase/root.rs:299) picks the
  **lowest `SubnetMovingPrice` among non-immune subnets** (immunity 864,000
  blocks = 120 d), ties to the earliest registration. So the guardrail is a RANK
  buffer, not a price level.

### Added
- **`dereg_watch.py`** — live prune-queue position. Reads every subnet's EMA +
  registration block, counts how many non-immune subnets sit below SN21 (the
  buffer), and derives the **live floor** (the current prune target's EMA) and a
  **guard price** (the EMA that still leaves 10 subnets below us — what
  extraction binds against). Cross-checked against the node's own
  `subnetInfo_getSubnetToPrune`, and the defence table is priced with
  `swap_simSwapTaoForAlpha` rather than inferred from reserve ratios.
  - **Kill rate** — registrations per 30/90/180 d (one prune each while full):
    ~7.5 d/prune today → `runway_days` at the current rank.
  - **Tier ladder 0-5** on the buffer (5 = we are the prune target), plus an
    **erosion tripwire**: ≥8 places lost in ≤14 d alerts even when the tier is
    unchanged — the level-only model would have stayed silent through the
    36 → 24 slide of the last 8 days.
- **Endpoints** — `GET /api/dereg/watch`, `GET /api/dereg/watch/history`,
  `POST /api/dereg/watch`.
- **Scheduler** — `dereg_watch_2d` every 2 days at **07:50 UTC**
  (`CronTrigger(day="*/2")`, calendar-anchored so Render redeploys can't drift it).
- **Tests** — `tests/test_dereg_watch.py`: immunity excluded from the buffer,
  floor = cheapest *non-immune*, guard preserves the configured buffer, runway =
  buffer × cadence, tier ladder, erosion window.

### Changed
- **S4 extraction** binds on the live `dereg_guard_tao()` instead of the fixed
  floor; `binding_constraint` says so, and states plainly when no live data
  exists rather than substituting a number.
- **Recommendations** — dereg risk is tiered off the live buffer (with an
  erosion bump), the "Dereg guard" action now says to stake TAO into the pool
  (the EMA follows spot within ~1 day: ~8-hour half-life), and the verdict
  reports buffer + runway instead of "headroom %".
- **`root_reborn_model.py`** — `resolve_dereg_floor()` reads the live floor and
  prints its provenance, so a stale fallback can never read as a live number.

## 2026-06-08 — Market context: SN21 alpha move vs the whole field

### Added
- **`market_sync.py`** — daily all-subnets alpha-price scan. One finney chain
  call (`subtensor.all_subnets()`) pulls every subnet's AMM reserves; computes
  each subnet's alpha price in **TAO** (`tao_in / alpha_in`, the same ratio the
  collector uses for SN21) and in USD. Measuring in TAO strips out TAO's own
  market move, isolating *subnet-relative* performance — so a TAO-wide selloff
  is no longer mistaken for an SN21 problem.
  - **Breadth + cohorts** — % of subnets up/down, median 24h move, best/worst
    performer, price deciles (top 10% … bottom 10%).
  - **SN21 standing** — price percentile/decile, daily-move percentile, move vs
    field median, and a `verdict`: `market_wide` (moved with the field),
    `sn21_specific` (lagged while the market held), `outperforming`, or `inline`.
- **`data/subnets_market.json`** (latest full snapshot) +
  **`data/subnets_market_history.json`** (one compact row/day, 365d — drives the
  SN21 rank-over-time chart) + **`data/subnets_price_ledger.json`**
  (`{date:{netuid:price}}`, 14d window, for robust 24h/7d deltas).
- **Endpoints** — `GET /api/market/summary`, `GET /api/market/history?days=N`,
  `POST /api/market/sync` (manual run).
- **Scheduler** — `daily_market_scan` at **08:05 UTC** (after the 08:00 chain
  collect, before the 08:15 Taostats sync).
- **Digest** — `sn21_daily` now carries a `market` block; the composer leads the
  PRICE discussion with the market verdict (e.g. "−6% in USD, but ~80% is TAO
  market-wide; in TAO terms SN21 sits at the 54th percentile — in line with
  peers") and RISKS surfaces `sn21_specific` weakness or reassures on
  `market_wide` moves.
- **Dashboard** — new **Market** tab: verdict banner, SN21-vs-field cards,
  percentile-rank-over-time chart, and best/worst-performer tables.

## 2026-06-04 — Validator weight-copy scan + wallet identification

### Added
- **`weights_scan.py`** — direct finney chain read of every validator's
  published weight vector (`subtensor.weights(netuid=21)`), joined to the
  metagraph (stake, vTrust, last weight-set age, hot/coldkeys) and enriched
  with operator names (Taostats `hotkey_name`, cached in
  `data/validator_names.json`). Computes per-validator scoring breadth
  (#miners scored), top-target share, stake-weighted **cosine-to-consensus**,
  and a pairwise cosine-similarity matrix across weight-setters.
  - **Burn-mode detection** — flags validators assigning ≥98% to the
    subnet-owner UID; reports the burning fraction and, when ≥80% of setters
    burn, marks the whole subnet in burn-mode. Copy verdicts are labelled
    `burn` (no signal) in that state so identical one-hot vectors aren't
    misread as copying.
  - **Copy detection** — once vectors differentiate, each setter gets a
    nearest-neighbour verdict (`identical→copy` / `near-copy` / `similar` /
    `independent`) plus a highest-stake source guess within its similarity
    cluster.
  - **`our_validator_wallets()`** — full coldkey→stake breakdown behind our
    validator hotkey (UID 64), cross-checked against on-chain
    `TotalHotkeyAlpha` so the wallet list is provably complete.
  - Recognises the owner UID (135) and UID 64 as ours by matching
    `SubnetOwner(21)` / the on-chain coldkey, even when keys aren't
    House-labelled.
- **`data/weights_scan.json`** (latest) + **`data/weights_scan_history.json`**
  (daily burn-fraction / copier-count rows, 90-day retention).
- **API**: `GET/POST /api/weights/scan`, `GET /api/weights/history`,
  `GET /api/validator/wallets`.
- **Scheduler** — daily on-chain weights scan at 09:20 UTC.
- **Dashboard** — new **Validators** tab: burn-status banner, summary cards
  (setters / burning / our vTrust / our miners scored / owner-UID incentive),
  a validator table (name · House/ours/owner tags · stake% · vTrust · scored ·
  top-target · cos-to-consensus · copy verdict · weight-set age), and an
  "Our validator · wallet identification" table with the chain cross-check
  tick.

### Notes
- Uses only `math` (no new dependency); reuses `collector._configure_chain_ssl`
  for WebSocket verification on Render.
- As of launch the subnet is in **full burn-to-owner mode** — all 11
  weight-setting validators (UID 64 included) assign 100% to owner UID 135, so
  no copy signal exists yet. The scan is built to surface copiers the moment
  validators flip to differentiated scoring.

## 2026-05-17 — Scout: candidate-subnet scanner + weekly digest

### Added
- **`subnet_scan.py`** — daily-scheduled scanner (09:15 UTC) for a curated
  shortlist of candidate netuids (default SN2/8/13/28/43). Per subnet
  computes: permit feasibility against the lowest active permit-holder,
  projected emission share and annual ROI on the configured budget, proper
  constant-product AMM slippage on the three-leg trade (SN21 sell → target
  buy → target sell), and risk signals (burn %, top-10/64 concentration,
  net flow vs mcap, miner/validator counts). Composite score =
  `annual_roi × (1 − round_trip_cost) × manual_multiplier`.
- **`data/subnet_scan.json`** + **`data/subnet_scan_history.json`** (90-day
  retention) + **`data/subnet_notes.json`** (qualitative overrides, seeded
  with SN28 multiplier 0.5 pending emission-farming post-mortem review).
- **API**: `GET /api/scan/candidates`, `GET /api/scan/history`,
  `POST /api/scan/run`, `GET /api/scan/notes`,
  `POST/DELETE /api/scan/notes/{netuid}`.
- **`digest/sources/scout_weekly.py`** — reads the latest scan + 7d history,
  emits per-subnet rank changes, score deltas, permit-flip flags.
- **`digest/channels/telegram_scout.py`** — separate Telegram channel using
  `TELEGRAM_SCOUT_BOT_TOKEN` / `TELEGRAM_SCOUT_CHAT_ID`.
- **`digest/prompts/scout_weekly.md`** — narrative format for the Scout
  weekly digest (ranking, permit feasibility, yield projections, risk
  signals, week-over-week diffs).
- **Weekly digest schedule** — Mondays 10:00 UTC. Enabled by extending
  `DigestConfig` with an optional `cron_kwargs` field for non-daily
  triggers; existing `sn21_daily` config unchanged.

### New env vars
- `SCAN_NETUIDS=2,8,13,28,43` — candidate shortlist
- `SCAN_BUDGET_SN21_ALPHA=500000` — SN21 alpha to convert into target alpha
- `TELEGRAM_SCOUT_BOT_TOKEN` — Scout-channel bot
- `TELEGRAM_SCOUT_CHAT_ID` — Scout-channel chat id

## 2026-05-10 — Digest memory + 7d/30d trend windows

### Added
- **Multi-window trends in `digest/sources/sn21_daily.py`**. Each metric
  (alpha price, TAO USD, holder count, liquidity, burn rate, our
  entitled α, daily volumes) now reports `today / -7d / -30d / 7d_pct
  / 30d_pct`, plus the actual look-back distance so the LLM can caveat
  short windows honestly.
- **Per-coldkey top-10 movers for 7d and 30d windows** (`movers_7d`,
  `movers_30d`). Aggregates across each coldkey's hotkey positions; tags
  house, NEW, EXITED, and known validator brand. Falls back to the
  oldest available snapshot until the new 31-day retention has filled.
- **Digest archive (memory)**. After every successful send, the
  rendered text is appended to `digest_archive_<kind>.json` (max
  `archive_retention_days`, default 30). On the next compose, the last
  N entries (excluding today, capped to ~10 KB by
  `DIGEST_LLM_MEMORY_CHARS`) are passed to the composer as a `=== PRIOR
  DIGESTS ===` block so the LLM can spot continuity, repetition, and
  trend reversals across days.
- **Composer signature change**: both `digest/composers/llm.py` and
  `digest/composers/fallback.py` now accept `prior_digests` (optional).
  Fallback surfaces a `MEMORY: N digests on file` pointer; LLM weaves
  cross-day context per the updated prompt.
- **Prompt revision** (`digest/prompts/sn21_daily.md`). New PATTERNS
  section (only emitted when memory + a real pattern exist), TRENDS
  section, MOVERS · 7D and MOVERS · 30D sections, and explicit memory
  rules ("trust today's data on conflicts").

### Changed
- **`holders_sync.py` retention 7 → 31**. Roughly +4.5 MB on the
  persistent disk; required for 30-day per-coldkey movers. New entries
  start accumulating immediately; the 30d window honestly reports
  `actual_days < 30` until it fills.

### New env var
- `DIGEST_LLM_MEMORY_CHARS` (default `10000`) — caps the prior-digests
  block size so the user-message token count stays bounded.

### Fixed
- **`neurons_daily.json` shape mismatch.** The store is
  `{"rows": [...]}` (per-UID-per-day), not a flat list — the new
  `_trend_row` helper tried `rows[-1]` on the dict and raised
  `KeyError: -1`, taking `gather()` down on Render. Added
  `_neurons_daily_series` to aggregate per-UID rows into one
  per-date record (sums mining / burned / validating / owner alpha,
  carries the subnet-level `burn_rate_pct`). `_trend_row` now guards
  against non-list inputs so any future store-shape regression
  degrades gracefully instead of blowing up the whole digest. Same
  shape assumption was latent in the original `_burn_section` —
  silently falling through to `subnet_daily.incentive_burn × 100`;
  both paths now agree.

## 2026-05-10 — Daily digest (Telegram, LLM-narrated)

### Added
- **`digest/` package** — pluggable daily digest pipeline. One
  `DigestConfig` per registered digest; the orchestrator (`run_digest`)
  runs `gather → compose → send` with per-digest idempotency state on
  disk (`digest_state_<kind>.json`) and a `force` bypass for manual
  re-runs.
- **`digest/sources/sn21_daily.py`** — pure-read source. Pulls from
  `subnet_daily.json`, `holders_snapshots.json`,
  `taostats_owner_transfers.json`, `daily_log.json`, `neurons_daily.json`
  and produces a structured inputs dict (price, pool, movers, owner
  pool, burn, emissions, tier, anomaly flags). Tags validator-brand
  exits (Taostats / tao.bot / 1T1B / Datura / OTF / Polychain / Crucible / Yuma).
- **`digest/composers/llm.py`** — Claude Haiku 4.5 via the Anthropic
  Python SDK. System + user prompt split on `---` in the markdown
  template (`digest/prompts/sn21_daily.md`).
- **`digest/composers/fallback.py`** — deterministic markdown output
  used if the LLM key is missing or the call errors. Tagged `[fallback]`
  in the message so the operator knows which path produced it.
- **`digest/channels/telegram.py`** — Bot API `sendMessage`. Plain text,
  no parse_mode escaping, web-page-preview disabled.
- **`POST /api/digest/preview?kind=sn21_daily`** — composes and returns
  the message + structured inputs without sending.
- **`POST /api/digest/send?kind=sn21_daily&force=1`** — composes and
  sends now. `force=1` bypasses the same-day idempotency guard.
- **Scheduled job 09:30 UTC** (override via `DIGEST_TIME_UTC=HH:MM`) —
  fires after all syncs complete.

### New env vars
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` — Telegram bot channel.
- `ANTHROPIC_API_KEY` — LLM composer; missing key → fallback path.
- `DIGEST_ENABLED` (default `true`) — kill switch.
- `DIGEST_TIME_UTC` (default `09:30`) — schedule override.
- `DIGEST_LLM_MODEL` (default Haiku 4.5), `DIGEST_LLM_MAX_TOKENS` (default 1024).

### Dependencies
- `anthropic>=0.40.0` added to `requirements.txt`.

## 2026-05-08 — House labels + burn-aware weekly earnings + holders sync hardening

### Added
- **Wallet labels (`labels.py`).** Tag any SS58 (coldkey or hotkey) as
  House. Storage: `data/wallet_labels.json`. Env seed via
  `HOUSE_COLDKEYS` / `HOUSE_HOTKEYS`; dashboard UI is the source of
  truth after first boot. Auto-tags the SN21 owner hotkey on first sight.
  CRUD: `GET/POST /api/labels`, `DELETE /api/labels/{ss58}`.
- **Per-UID daily earnings snapshot (`neurons_daily_sync.py`).** New
  scheduled job at 09:00 UTC writes one row per SN21 UID with
  `daily_mining_alpha`, `daily_burned_alpha`, `daily_validating_alpha`,
  `daily_owner_alpha` plus prices. Idempotent per date, 90-day
  retention. Foundation for weekly rollups.
- **Burn-aware weekly earnings (`house_weekly.py`).** Sums the per-UID
  rows over the SN21 mining/validation week (Mon 12:00 ET → Mon 12:00
  ET). Miners report gross / burned / net; validators and owner-key
  18 % are burn-immune and reported as-is. WoW deltas + coverage
  fraction. Endpoint: `GET /api/house/weekly?weeks=N`.
- **Weekly window helpers (`windows.py`).** `weekly_window`,
  `previous_weekly_window`, `date_in_weekly_window`.
- **Home tab "House Earnings · Current Mining Week" cards.** Three
  cards (House Miners net + gross strikethrough · House Validators ·
  Owner Key Emissions) with WoW deltas, USD conversions, and a live
  burn-rate pill that flips green the moment burn drops below 100 %.
- **5-week stacked weekly chart** on Home with translucent burned-α
  overlay so the visual shrinks the moment the burn flip lands.
- **Neurons tab House column.** ☆/★ toggle button per row plus
  All / House only / Other only filter pills. Header cards show House
  counts and live subnet burn rate.
- **Movement tab House split.** House column on movers table; summary
  row shows `House +X / -Y · Other +X / -Y` alongside totals.
- `BURN_FLIP_DATE` env — surfaces the expected first non-100 % epoch
  date on the dashboard until the live burn rate drops.

### Changed
- **`neurons_sync.py`** — every UID now carries `is_house` and
  `daily_mining_alpha_net`. Payload gains a top-level `burn` block
  (rate, gross, burned, net) and `house_*` counts in `totals` /
  `submitting_in_window`.
- **`holders_sync.py`** — movers tagged `is_house`. Movement summary
  adds `house_inflows_alpha` / `house_outflows_alpha` and
  corresponding `other_*` fields.
- **Refresh button** now also takes a daily House snapshot in the
  fan-out sequence.

### Fixed (data integrity)
- **Holders sync 429 handling.** Cause: every 08:45 UTC daily run
  since May 5 hit Taostats 429 on page 6 of
  `/api/dtao/stake_balance/latest/v1` and exhausted the old 5-retry
  budget, freezing `holders_snapshots.json` at the May 4 manual run.
  With only one snapshot, `get_movement` fell into the `prior=None`
  branch and reported every position as NEW with `alpha_prev = 0`.
  Fix:
  - `Retry-After` header honoured when Taostats sends one.
  - Retries bumped 5 → 8; cap raised 30 s → 60 s; worst-case backoff
    ~4 min, well within the daily window.
  - Page-aware pacing: pages > 4 sleep 2.0 s instead of 0.6 s, since
    Taostats reliably throttles around page 6.
  - Failed scheduled run now self-schedules **one retry 30 min later**
    via `DateTrigger`, up to two retries (3 attempts per day).

## 2026-05-04 — Subnet sync hardening

- Bumped `MAX_429_RETRIES` to 7 on `subnet_sync._get`; sub-fetches now
  separated by 700 ms to avoid bursting Taostats.
- Each sub-fetch wrapped in try/except — partial failures preserve
  prior data and stamp `stale_fields` rather than 500-ing the row.

## 2026-05-04 — 429-proof every Taostats path

- Exponential-backoff retry (1/2/4/8/16 s) added to `subnet_sync._get`,
  `neurons_sync._fetch_page`, and confirmed on `taostats_sync._get_json`
  and `holders_sync._fetch_page` (later strengthened above).
- `taostats_sync.sync_owner_transfers` reads existing store before
  writing and preserves prior `balance`, `transfers`, and
  `tao_price_usd` when sub-fetches fail.
- Refresh button sequences syncs serially with 300 ms gaps instead of
  firing parallel.

## 2026-05-04 — UX polish

- USD wallet value promoted to its own Home card.
- `Collect Now` renamed to `Refresh`; fans out to all syncs.
- Activity tab gets its own `Sync now` button.

## 2026-05-04 — Movement tab (Feature 3)

- New `holders_sync.py`: paginates `/api/dtao/stake_balance/latest/v1`
  (~1,968 holders, 10 pages, ~3 s with rate-friendly delays). Stores
  up to 7 daily snapshots. Diffs by `(hotkey, coldkey)` pair to yield
  top movers and per-holder deltas.
- New endpoints: `/api/holders/movement`, `/api/holders/our`,
  `POST /api/holders/sync`. New scheduler job at 08:45 UTC.
- Movement tab UI: three "Our Owner Pool" cards (alpha balance, 24h
  change, snapshots stored) + top movers table with NEW / EXITED /
  BOUGHT / SOLD badges and inflow/outflow totals.

## 2026-05-04 — Neurons tab (Features 4 + 5)

- New `windows.py`: ET-aware mining/validation week schedule.
  Validation = Sun 00:00 → Mon 12:00 ET. Mining = Mon 12:00 → Sun 00:00 ET.
- New `neurons_sync.py`: pulls all 256 SN21 UIDs from Taostats
  metagraph, classifies validator vs miner, marks each row
  `submitting_in_window` via block→UTC estimation. 60 s cache.
- Neurons tab UI: subnet header (window status, validator/miner
  counts, burn note), validators table, miners table with gross /
  burned / net alpha. Owner hotkey and immunity period flagged.

## 2026-05-04 — Activity tab (Feature 2)

- New `subnet_sync.py`: pulls 24h pool volumes, subnet hyperparams,
  and total holder count daily. 365-day retention.
- New endpoints: `/api/subnet-summary`, `/api/subnet-history`,
  `POST /api/subnet/sync`.
- Activity tab UI: six cards (holders, alpha bought/sold, net flow,
  active val/min, burn rate) and three 30-day charts.

## 2026-05-04 — Tab navigation + USD card

- Foundation commit for v2: horizontal tab nav (Home/Activity/Neurons/
  Movement) with vanilla-JS hash routing and lazy data loading per tab.
- Wallet card now shows USD equivalent and 24h-ago USD line.

## 2026-05-04 — Live wallet balance + Taostats price source

- New "Wallet balance (on-chain)" card — pulls
  `/api/account/latest/v1` from Taostats and renders 24h delta.
- TAO/USD source switched to Taostats first (datacenter-friendly,
  authenticated), then CoinGecko, then Binance fallback. Resolves the
  CoinGecko/Binance gaps from Render egress.

## 2026-05-04 — Daily emission math fix

- `metagraph.emission` returns the per-tempo UID slice (the 82 %
  miner+validator share), **not** gross daily emission. Old code
  treated it as gross — undercounted by ~24.4× (=20 tempos/day / 0.82).
- Fix: scale up using `hparams.tempo` and `tempos_per_day`. Idempotent
  in-place migration on legacy rows gated by `subnet.emission_scale_v == 2`.

## Earlier — initial build

- Daily collector via APScheduler at 08:00 UTC.
- Owner-pool 18 % share + entitlement schedule (25 / 50 / 75 / 90 %).
- Persistent ledger of accumulated owner alpha.
- FastAPI dashboard with cookie-session auth, login page, Chart.js
  trend charts.
- Render web service + 1 GB disk at `/data`.
- `POST /api/import-data` for bulk uploads with `X-SN21-Key` header auth.
