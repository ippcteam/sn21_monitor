# Changelog

All notable changes to the SN21 Monitor. Newest first.

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
