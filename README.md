# SN21 · HOPE Emissions Dashboard

Bittensor Subnet 21 daily emissions monitor with authenticated web dashboard.

## Stack

- **FastAPI** — serves dashboard + API
- **APScheduler** — daily 08:00 UTC collection (no separate cron service needed)
- **Render.com** — web service + 1GB persistent disk for JSON logs
- **Chart.js** — browser-side charts (no extra backend)
- **bittensor SDK** — metagraph data
- **CoinGecko** — TAO/USD price (free, no API key)

## Dashboard Shows

| Card | Data |
|------|------|
| Owner Share Today | Daily 18% alpha cut |
| Running Accumulation | Total owner alpha earned since day 1 |
| Alpha Price | τ per ξ (with USD estimate) |
| TAO Price | USD from CoinGecko |

Charts: owner accumulation over time, alpha price history, TAO price history, daily emission (total vs owner).

## Deploy to Render

### 1. Push to GitHub

```bash
git init
git add .
git commit -m "init sn21 dashboard"
git remote add origin https://github.com/YOUR_USERNAME/sn21-dashboard.git
git push -u origin main
```

### 2. Create Render Web Service

1. Go to https://render.com → **New → Web Service**
2. Connect your GitHub repo
3. Render will auto-detect `render.yaml`

Or set manually:
- **Runtime**: Python 3
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `uvicorn app:app --host 0.0.0.0 --port $PORT`

### 3. Set Environment Variable

In Render dashboard → **Environment**:

```
DASHBOARD_PASSWORD = your-secret-password-here
```

Never commit this. The `render.yaml` marks it `sync: false` so Render won't auto-populate it.

### 4. Attach Persistent Disk

Render dashboard → your service → **Disks** → Add:
- **Name**: sn21-data
- **Mount Path**: /data
- **Size**: 1 GB

This keeps your JSON logs alive across deploys.

### 5. Deploy

Render will build and deploy. Your dashboard will be live at:
```
https://sn21-dashboard.onrender.com
```

(Or your custom domain if configured.)

## File Structure

```
sn21-dashboard/
├── app.py            — FastAPI app, auth, scheduler, API routes
├── collector.py      — Metagraph + price fetching, log writing
├── requirements.txt
├── render.yaml       — Render deployment config
└── templates/
    ├── login.html    — Auth page
    └── dashboard.html — Main dashboard
```

## Data Files (on /data disk)

```
/data/
├── daily_log.json     — One entry per day, full snapshot
└── owner_ledger.json  — Running accumulation tracker
```

## Manual Collection

Hit **Collect Now** in the dashboard to trigger an immediate collection outside the daily schedule.

Or via API (authenticated):
```bash
curl -X POST https://your-app.onrender.com/api/collect \
  -H "Cookie: sn21_session=YOUR_SESSION_TOKEN"
```

## Local Dev

```bash
# Use a local /data path for dev
mkdir -p /data
pip install -r requirements.txt
DASHBOARD_PASSWORD=dev uvicorn app:app --reload --port 8000
```

Note: for local dev, change `secure=True` to `secure=False` in the `set_cookie` call in `app.py`.
