# SN21 · HOPE Emissions Dashboard

Bittensor Subnet 21 monitor with authenticated web dashboard. Tracks owner-key
emissions, the entitlement schedule, House-labeled validators/miners, holder
movements, and burn-aware weekly earnings.

## Stack

- **FastAPI** — dashboard + API
- **APScheduler** — daily UTC syncs (no separate cron service)
- **Render.com** — web service + 1 GB persistent disk for JSON stores
- **Chart.js** — browser-side charts
- **bittensor SDK** — metagraph reads
- **Taostats API** — wallet balance, transfers, metagraph, holders, prices
- **CoinGecko / Binance** — TAO/USD price fallbacks

## Tabs

| Tab | What it shows |
|-----|---------------|
| **Home** | Live metrics (owner pool 18%, our entitlement, alpha price, TAO price, wallet balance/USD) · **House Earnings · Current Mining Week** (miners net + gross, validators, owner key, burn pill) · 5-week stacked weekly chart · trend charts · active UID table |
| **Activity** | Subnet 24h pool volumes (buy/sell), holder count, burn rate, active validator/miner counts · 30-day trend charts |
| **Neurons** | All 256 SN21 UIDs split into validators / miners, with mining/validation window detection (Mon 12:00 ET → following Mon 12:00 ET), submitting-in-window flag, and **House toggle column** (☆/★) plus All/House/Other filter pills |
| **Validators** | On-chain weight-copy scan: burn-status banner, per-validator scoring breadth, vTrust, stake%, cosine-to-consensus, and copy verdict (copier vs independent, with source guess) · **Our validator wallet identification** (coldkey→stake breakdown for UID 64, cross-checked against on-chain `TotalHotkeyAlpha`) |
| **Movement** | Our owner-coldkey alpha balance over time · 24h holder movers (top inflows/outflows, NEW/EXITED/BOUGHT/SOLD), with House column and house/other split in the summary |

## House vs Other labels

Any wallet (coldkey or hotkey SS58) can be tagged **House** so dashboards can
split your operator's keys from third parties.

- A UID is House if either its **coldkey** OR its **hotkey** is in the label set.
- Labels live in `data/wallet_labels.json` and survive deploys.
- Env seed (`HOUSE_COLDKEYS`, `HOUSE_HOTKEYS`) populates the store on first
  boot; after that the dashboard UI is the source of truth.
- The SN21 owner hotkey (`is_owner_hotkey=true` on the metagraph) is
  auto-labeled as House on first sight.

Toggle inline on the **Neurons** tab via the ☆/★ button on each row, or via:

```bash
# CRUD (session-cookie auth required)
GET    /api/labels                  # list current labels
POST   /api/labels                  # { ss58, kind: "coldkey"|"hotkey", note? }
DELETE /api/labels/{ss58}           # remove
```

## Burn-aware weekly earnings

Aggregated to the SN21 mining/validation week (`Mon 12:00 ET → following Mon 12:00 ET`):

| Bucket | Burn behaviour |
|--------|----------------|
| House Miners — **net** | `daily_mining_alpha − daily_burned_alpha` summed across the week — true realised earnings |
| House Miners — gross | `daily_mining_alpha` summed — what would have been earned at 0 % burn |
| House Validators | `daily_validating_alpha` summed — **burn-immune** |
| Owner Key Emissions | `our_entitled_alpha` summed (the 18 % subnet cut × tier) — **burn-immune** |

Today the subnet runs at 100 % burn so the miner *net* card reads zero.
When the first non-100% epoch lands, the green burn pill flips on and the net
column starts moving — **no deploy needed**, the math just resolves.

```bash
GET  /api/house/weekly?weeks=4      # current week + N prior weeks (auth)
POST /api/house/snapshot            # take per-UID daily snapshot now (auth)
```

Set `BURN_FLIP_DATE=YYYY-MM-DD` in env to surface the expected first
non-100% epoch on the dashboard.

## Data files (on /data disk)

```
/data/
├── daily_log.json              — one entry per day: subnet snapshot + active UIDs
├── owner_ledger.json           — running entitlement accumulation
├── taostats_owner_transfers.json — owner-coldkey TAO transfers + balance + tao_price
├── subnet_daily.json           — daily pool/holders rows for Activity tab (365d)
├── holders_snapshots.json      — last 7 daily holder snapshots (~1968 rows each)
├── neurons_daily.json          — last 90 days of per-UID earnings rows
├── wallet_labels.json          — House vs Other label store
├── digest_state_<kind>.json    — per-digest idempotency state (last_sent_date, etc.)
├── digest_archive_<kind>.json  — per-digest memory (last 30 sent texts; LLM context)
├── subnet_scan.json            — latest Scout scan (ranked candidates)
├── subnet_scan_history.json    — daily Scout rows (90-day retention)
├── subnet_notes.json           — manual qualitative overrides per candidate netuid
├── weights_scan.json           — latest validator weight-copy / burn scan
├── weights_scan_history.json   — daily burn-fraction / copier-count rows (90d)
└── validator_names.json        — hotkey→operator-name cache (Taostats)
```

## Scout — candidate subnet scanner

Daily-scheduled scan of a curated shortlist of *other* subnets where we could
run our validator. Each subnet is scored on the economics of deploying our
SN21-alpha-denominated budget there.

Per subnet, the scanner computes:

- **Permit feasibility** — lowest active permit-holder's stake (the displacement
  target) vs the alpha we'd hold after converting the budget. `headroom_ratio` ≥
  1.5 → `permit_secured: true`.
- **Yield** — projected emission share at our stake, daily/annual TAO, annual
  ROI %.
- **Slippage** — proper x·y=k AMM math on three legs (SN21 sell → target buy →
  target sell). Reports per-leg slippage + round-trip cost in TAO and %.
- **Risk signals** — burn %, top-10 / top-64 stake concentration, unique
  coldkeys in top-64, 30d net-flow as % of mcap, active validator/miner counts.
- **Composite score** = annual ROI × (1 − round-trip cost) × manual multiplier.

Manual qualitative overrides (reputation, prior incidents, scoring-window
concerns) live in `data/subnet_notes.json` and are applied as a 0–1 multiplier
on the composite score. Seeded with `{"28": {"multiplier": 0.5}}` pending an
emission-farming post-mortem review.

Config:

```ini
SCAN_NETUIDS=2,8,13,28,43          # shortlist
SCAN_BUDGET_SN21_ALPHA=500000       # SN21 alpha sold to fund the entry
```

```bash
GET  /api/scan/candidates          # latest ranked scan
GET  /api/scan/history?days=30     # composite-score trend
POST /api/scan/run                 # manual scan (~30s)
GET  /api/scan/notes               # qualitative overrides
POST /api/scan/notes/{netuid}      # { multiplier?, note? }
```

A separate **weekly Scout digest** posts to its own Telegram channel
(`TELEGRAM_SCOUT_BOT_TOKEN` / `TELEGRAM_SCOUT_CHAT_ID`) on Monday 10:00 UTC,
narrating the ranking, week-over-week rank changes, and any flipped permit
feasibility.

## Daily digest

Pluggable digest pipeline under `digest/` — gather (source) → compose (LLM
or fallback) → send (channel). Two configs registered today: `sn21_daily`
posted to Telegram at 09:30 UTC after all syncs complete, and `scout_weekly`
posted to a separate Telegram channel on Mondays at 10:00 UTC.

```
digest/
├── core.py                     — DigestConfig, run_digest()
├── channels/telegram.py        — POST sendMessage
├── composers/llm.py            — Claude Haiku via Anthropic API
├── composers/fallback.py       — deterministic markdown if LLM unavailable
├── sources/sn21_daily.py       — reads JSON stores, returns structured inputs
└── prompts/sn21_daily.md       — system + user prompt template
```

Adding a new digest = drop a source module, add a prompt, append a
`DigestConfig` in `app.py`. See `.env.example` for required env vars
(Telegram bot + Anthropic key).

**Memory.** Each digest's last 30 sent texts persist in
`digest_archive_<kind>.json`. On every compose the prior days (excluding
today) are passed to the LLM as a `=== PRIOR DIGESTS ===` block so it
can spot continuity, repetition, and trend reversals — capped by
`DIGEST_LLM_MEMORY_CHARS` (default 10 000). The prompt instructs the
model to trust today's data over memory on any conflict.

**Trend windows.** The SN21 source exposes 7d and 30d deltas for every
metric (`trends`) and per-coldkey top-10 movers per window
(`movers_7d`, `movers_30d`). The 30-day per-coldkey window relies on
the holders-snapshot retention (now 31). Until that retention fills,
the window reports `actual_days < 30` honestly and falls back to the
oldest available snapshot.

## Scheduled jobs (UTC)

| Job | When | Source |
|-----|------|--------|
| Chain collect (metagraph + prices) | 08:00 | `collector.run_collection` |
| Taostats owner sync (transfers + balance + price) | 08:15 | `taostats_sync.sync_owner_transfers` |
| Subnet daily sync (Activity tab data) | 08:30 | `subnet_sync.sync_subnet_daily` |
| Holders snapshot (Movement tab data) | 08:45 | `holders_sync.sync_holders_snapshot` |
| Neurons per-UID daily snapshot (House weekly data) | 09:00 | `neurons_daily_sync.sync_neurons_daily` |
| Scout scan (candidate subnets) | 09:15 | `subnet_scan.run_scan` |
| Validator weight-copy / burn scan | 09:20 | `weights_scan.run_scan` |
| Daily SN21 digest (Telegram) | 09:30 (override via `DIGEST_TIME_UTC`) | `digest.run_digest("sn21_daily")` |
| **Scout weekly digest (Telegram)** | **Mon 10:00** | `digest.run_digest("scout_weekly")` |
| Tier-boundary log marker | one-off at each tier flip date | `app.log_tier_boundary` |

Holders sync now self-schedules **one retry 30 min later** if Taostats 429s
exhaust the page-level retry budget (8 attempts, 60s cap, page-aware pacing
from page 5 onwards).

## API surface

All endpoints below require dashboard-session auth except `/api/import-data`,
which takes the same secret in `X-SN21-Key` (or `Authorization: Bearer`).

### Read
- `GET /api/summary` — Home cards (latest snapshot + ledger totals + wallet)
- `GET /api/history?days=30` — time-series for Home charts
- `GET /api/uids` — active UIDs from latest snapshot
- `GET /api/taostats?transfers_limit=100` — Taostats sync result
- `GET /api/subnet-summary` — Activity tab cards
- `GET /api/subnet-history?days=30` — Activity tab charts
- `GET /api/holders/movement?limit=50` — Movement tab top movers
- `GET /api/holders/our` — Movement tab "Our Owner Pool" series
- `GET /api/neurons` — Neurons tab full payload (256 UIDs)
- `GET /api/labels` — current House label set
- `GET /api/house/weekly?weeks=4` — burn-aware weekly earnings rollup
- `GET /api/scan/candidates` — latest Scout scan (ranked candidate subnets)
- `GET /api/scan/history?days=30` — composite-score history per candidate
- `GET /api/scan/notes` — qualitative overrides ({ netuid: { multiplier, note } })
- `GET /api/weights/scan` — latest validator weight-copy / burn scan (Validators tab)
- `GET /api/weights/history?days=30` — daily burn-fraction / copier-count rows
- `GET /api/validator/wallets` — coldkey→stake breakdown for our validator (UID 64)

### Write / trigger (auth)
- `POST /api/collect` — manual chain collect
- `POST /api/taostats/sync` — manual Taostats sync
- `POST /api/subnet/sync` — manual subnet daily sync
- `POST /api/holders/sync` — manual holders snapshot (~12 s)
- `POST /api/house/snapshot` — manual per-UID daily snapshot
- `POST /api/labels` — add House label
- `DELETE /api/labels/{ss58}` — remove House label
- `POST /api/backfill` — long-running chain backfill (archive subtensor)
- `POST /api/import-data` — upload `daily_log.json` / `owner_ledger.json` (header-key auth)
- `POST /api/digest/preview?kind=sn21_daily` — compose digest, return text + inputs (no send)
- `POST /api/digest/send?kind=sn21_daily&force=1` — compose + send via Telegram now
- `POST /api/scan/run` — run Scout scan now (~30 s for the 5-netuid shortlist)
- `POST /api/scan/notes/{netuid}` — set qualitative override `{ multiplier?, note? }`
- `DELETE /api/scan/notes/{netuid}` — remove override
- `POST /api/weights/scan` — run on-chain validator weight scan now (~30 s)

The topbar **Refresh** button fans out collect → taostats → subnet → house-snapshot
sequentially with 300 ms gaps. Holders snapshot is intentionally excluded
(~12 s); use the per-tab **Sync now** buttons for that and the Activity sync.

## Environment variables

```ini
# Dashboard auth (required)
DASHBOARD_PASSWORD=…

# Data dir (Render disk; falls back to ./data locally)
SN21_DATA_DIR=/data

# Ownership tier schedule (start of month-1)
OWNERSHIP_START_DATE=2026-03-20

# Subtensor archive node for chain backfill
SUBTENSOR_ARCHIVE_NETWORK=archive

# Taostats — wallet, holders, transfers, metagraph, prices
TAOSTATS_API_KEY=
TAOSTATS_OWNER_ID=

# House labels (env seed; UI is source of truth after first boot)
HOUSE_COLDKEYS=…,…
HOUSE_HOTKEYS=…,…

# Burn flip — informational (dashboard surfaces until live burn drops below 100%)
BURN_FLIP_DATE=

# Daily digest (Telegram + Claude Haiku)
DIGEST_ENABLED=true
DIGEST_TIME_UTC=09:30
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
ANTHROPIC_API_KEY=

# Scout — candidate subnet scanner + weekly digest
SCAN_NETUIDS=2,8,13,28,43
SCAN_BUDGET_SN21_ALPHA=500000
TELEGRAM_SCOUT_BOT_TOKEN=
TELEGRAM_SCOUT_CHAT_ID=
```

## Local dev

```bash
mkdir -p data
pip install -r requirements.txt
DASHBOARD_PASSWORD=dev SN21_DATA_DIR=./data .venv/bin/uvicorn app:app --reload --port 8000
```

Set `secure=False` on the `set_cookie` call in `app.py` for HTTP localhost.

## Deploy to Render

Push to `main` — the service auto-deploys (`render.yaml` is the source of truth).
The 1 GB disk at `/data` keeps JSON stores alive across deploys. Set the env
vars above in the Render dashboard.
