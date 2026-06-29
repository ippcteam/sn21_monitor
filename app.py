"""
SN21 Dashboard — FastAPI app
Serves the dashboard, handles auth, runs daily collection via APScheduler.
"""

import json
import logging
import os
import secrets
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from fastapi import Body, FastAPI, Request, Response, HTTPException, Depends, File, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

from collector import migrate_and_rebuild_from_logs, save_json
from config import DATA_DIR, DAILY_LOG, OWNER_LEDGER
from digest.core import DigestConfig, run_digest
from digest.channels import telegram as telegram_channel
from digest.channels import telegram_scout as telegram_scout_channel
from digest.sources import scout_weekly as scout_weekly_source
from digest.sources import sn21_daily as sn21_daily_source
from ownership import OWNERSHIP_START, next_tier_info, scheduled_tier_events
from subnet_scan import (
    delete_note as scan_delete_note,
    latest_scan as scan_latest,
    load_notes as scan_load_notes,
    run_scan as scan_run,
    scan_history,
    set_note as scan_set_note,
)
from market_sync import (
    history as market_history,
    latest as market_latest,
    run_sync as market_run,
)
from movers_attribution import (
    backtest_latest as movers_backtest_latest,
    capture_daily as movers_capture,
    latest as movers_latest,
    run_backtest as movers_run_backtest,
)
from social_posts import own_posts as social_own_posts
from subnet_sync import SUBNET_DAILY_STORE, sync_subnet_daily
from taostats_sync import TAOSTATS_STORE, sync_owner_transfers
from weights_scan import (
    latest_scan as weights_latest,
    our_validator_wallets,
    run_scan as weights_run,
    scan_history as weights_history,
)
from stake_watch import (
    STAKE_WATCH_HISTORY,
    STAKE_WATCH_STORE,
    run_stake_watch,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_backfill_lock = threading.Lock()
_backfill_running = False
_lab_lock = threading.Lock()
_lab_running = False

# ── Config ────────────────────────────────────────────────────────────────────
DASHBOARD_PASSWORD = os.environ.get("DASHBOARD_PASSWORD", "changeme")
COOKIE_NAME        = "sn21_session"
COOKIE_MAX_AGE     = 60 * 60 * 24 * 30  # 30 days

# Active sessions (in-memory — reset on restart, which is fine)
active_sessions: set[str] = set()

app = FastAPI(title="SN21 Dashboard", docs_url=None, redoc_url=None)
templates = Jinja2Templates(directory="templates")


# ── Auth ──────────────────────────────────────────────────────────────────────

def get_session(request: Request) -> str | None:
    return request.cookies.get(COOKIE_NAME)


def require_auth(request: Request):
    token = get_session(request)
    if not token or token not in active_sessions:
        raise HTTPException(status_code=302, headers={"Location": "/login"})
    return token


def require_import_key(request: Request) -> None:
    """Same secret as dashboard login; use header so curl works without cookies."""
    key = (request.headers.get("X-SN21-Key") or "").strip()
    auth = request.headers.get("Authorization") or ""
    if auth.startswith("Bearer "):
        key = auth[7:].strip()
    if not key:
        raise HTTPException(status_code=401, detail="Missing X-SN21-Key or Authorization: Bearer")
    if len(key) != len(DASHBOARD_PASSWORD) or not secrets.compare_digest(key, DASHBOARD_PASSWORD):
        raise HTTPException(status_code=401, detail="Unauthorized")


# ── Data helpers ──────────────────────────────────────────────────────────────

def load_json(path: Path, default):
    try:
        if path.exists():
            with open(path) as f:
                return json.load(f)
    except Exception:
        pass
    return default


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = ""):
    return templates.TemplateResponse("login.html", {"request": request, "error": error})


@app.post("/login")
async def login(request: Request):
    form = await request.form()
    password = form.get("password", "")

    if not secrets.compare_digest(password, DASHBOARD_PASSWORD):
        return RedirectResponse("/login?error=1", status_code=303)

    token = secrets.token_hex(32)
    active_sessions.add(token)

    response = RedirectResponse("/", status_code=303)
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=True,  # set False only for local dev
    )
    return response


@app.get("/logout")
async def logout(request: Request):
    token = get_session(request)
    if token:
        active_sessions.discard(token)
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(COOKIE_NAME)
    return response


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, _=Depends(require_auth)):
    return templates.TemplateResponse("dashboard.html", {"request": request})


# ── API ───────────────────────────────────────────────────────────────────────

@app.get("/api/summary")
async def api_summary(_=Depends(require_auth)):
    """Latest snapshot + ledger totals for dashboard cards."""
    log    = load_json(DAILY_LOG, [])
    ledger = load_json(
        OWNER_LEDGER,
        {"total_accumulated_alpha": 0.0, "total_accumulated_our_alpha": 0.0, "entries": []},
    )

    latest = log[-1] if log else None
    prev   = log[-2] if len(log) >= 2 else None

    def pct_change(today, yesterday):
        if yesterday and yesterday != 0:
            return round((today - yesterday) / yesterday * 100, 2)
        return None

    if latest:
        s = latest["subnet"]
        prev_s = prev["subnet"] if prev else {}
        our_today = s.get("our_entitled_alpha")
        our_prev = prev_s.get("our_entitled_alpha") if prev_s else None

        taostats = load_json(TAOSTATS_STORE, {})
        wallet = taostats.get("balance") or {}
        live_tao_usd = taostats.get("tao_price_usd")
        balance_total_tao = wallet.get("balance_total_tao")
        balance_24h_tao = wallet.get("balance_total_24hr_ago_tao")
        wallet_pct = (
            round((balance_total_tao - balance_24h_tao) / balance_24h_tao * 100, 2)
            if (balance_total_tao is not None and balance_24h_tao)
            else None
        )
        tao_usd_for_summary = s.get("tao_price_usd") or live_tao_usd
        balance_total_usd = (
            round(balance_total_tao * tao_usd_for_summary, 2)
            if (balance_total_tao is not None and tao_usd_for_summary)
            else None
        )
        balance_24h_usd = (
            round(balance_24h_tao * tao_usd_for_summary, 2)
            if (balance_24h_tao is not None and tao_usd_for_summary)
            else None
        )

        return {
            "date":                  latest["date"],
            "block":                 latest["block"],
            "active_uids":           len(latest["active_uids"]),
            "total_alpha_emission":  s["total_alpha_emission"],
            "owner_share_alpha":     s["owner_share_alpha"],
            "our_entitled_alpha":    our_today,
            "entitlement_rate":      s.get("entitlement_rate"),
            "alpha_price_tao":       s.get("alpha_price_tao"),
            "alpha_price_usd":       s.get("alpha_price_usd"),
            "tao_price_usd":         s.get("tao_price_usd") or live_tao_usd,
            "running_total_alpha":   ledger.get("total_accumulated_alpha", 0.0),
            "running_total_our_alpha": ledger.get("total_accumulated_our_alpha", 0.0),
            "our_entitled_usd_est":  s.get("our_entitled_usd_est"),
            "owner_pool_usd_est":    s.get("owner_pool_usd_est"),
            "running_total_our_usd": ledger.get("total_accumulated_our_usd"),
            "tier":                  next_tier_info(),
            "ownership_start_date":  OWNERSHIP_START.isoformat(),
            "emission_change_pct":   pct_change(
                s["total_alpha_emission"],
                prev_s.get("total_alpha_emission")
            ),
            "alpha_price_change_pct": pct_change(
                s.get("alpha_price_tao") or 0,
                prev_s.get("alpha_price_tao") or 0
            ),
            "tao_price_change_pct":  pct_change(
                s.get("tao_price_usd") or 0,
                prev_s.get("tao_price_usd") or 0
            ),
            "our_entitled_change_pct": pct_change(
                our_today or 0,
                our_prev,
            ),
            "wallet": {
                "address":           wallet.get("address"),
                "balance_total_tao": balance_total_tao,
                "balance_total_usd": balance_total_usd,
                "balance_24h_ago_tao": balance_24h_tao,
                "balance_24h_ago_usd": balance_24h_usd,
                "balance_change_24h_pct": wallet_pct,
                "block_number":      wallet.get("block_number"),
                "timestamp":         wallet.get("timestamp"),
                "alpha_balances":    wallet.get("alpha_balances") or [],
                "fetched_at_utc":    taostats.get("fetched_at_utc"),
            },
        }
    return {"error": "No data yet"}


@app.get("/api/history")
async def api_history(_=Depends(require_auth), days: int = 30):
    """Time-series data for charts."""
    log    = load_json(DAILY_LOG, [])
    ledger = load_json(OWNER_LEDGER, {"entries": []})

    recent_log    = log[-days:]    if log    else []
    recent_ledger = ledger["entries"][-days:] if ledger.get("entries") else []

    return {
        "emission_series": [
            {
                "date":       e["date"],
                "total":      e["subnet"]["total_alpha_emission"],
                "owner":      e["subnet"]["owner_share_alpha"],
                "our":        e["subnet"].get("our_entitled_alpha"),
            }
            for e in recent_log
        ],
        "price_series": [
            {
                "date":            e["date"],
                "alpha_price_tao": e["subnet"].get("alpha_price_tao"),
                "tao_price_usd":   e["subnet"].get("tao_price_usd"),
            }
            for e in recent_log
        ],
        "accumulation_series": [
            {
                "date":              e["date"],
                "running":           e.get("running_total_our_alpha"),
                "running_owner":     e.get("running_total_alpha"),
                "daily":             e.get("our_entitled_alpha"),
                "daily_owner":       e.get("owner_share_alpha"),
            }
            for e in recent_ledger
        ],
    }


@app.get("/api/uids")
async def api_uids(_=Depends(require_auth)):
    """Latest active UID breakdown."""
    log = load_json(DAILY_LOG, [])
    if not log:
        return []
    return log[-1].get("active_uids", [])


@app.get("/api/taostats")
async def api_taostats(_=Depends(require_auth), transfers_limit: int = 100):
    """
    Last Taostats sync snapshot (TAO transfers for owner SS58). Full list on disk;
    response truncates `transfers` for browser use — see `transfer_count`.
    """
    raw = load_json(TAOSTATS_STORE, {})
    transfers = raw.get("transfers") or []
    out = {k: v for k, v in raw.items() if k != "transfers"}
    out["transfers"] = transfers[: max(0, min(transfers_limit, 500))]
    out["transfers_returned"] = len(out["transfers"])
    out["transfers_truncated"] = len(transfers) > len(out["transfers"])
    return out


@app.post("/api/taostats/sync")
async def api_taostats_sync(_=Depends(require_auth)):
    """Run Taostats fetch immediately (same job as daily schedule)."""
    try:
        return sync_owner_transfers()
    except Exception as e:
        logger.exception("Taostats sync failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/stake/watch")
async def api_stake_watch(_=Depends(require_auth)):
    """Last owner-share stake-watch snapshot (are the daily emission shares landing?)."""
    return load_json(STAKE_WATCH_STORE, {})


@app.post("/api/stake/watch")
async def api_stake_watch_run(_=Depends(require_auth), notify: bool = False):
    """Run the stake watch now. notify=1 also fires the Telegram alert on a stall."""
    try:
        return run_stake_watch(notify=notify)
    except Exception as e:
        logger.exception("Stake watch failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/stake/history")
async def api_stake_history(_=Depends(require_auth)):
    """Stake-watch check history (status + staked-α over time)."""
    return load_json(STAKE_WATCH_HISTORY, [])


@app.get("/api/subnet-summary")
async def api_subnet_summary(_=Depends(require_auth)):
    """Latest subnet daily row + 24h-ago row for delta calc (Activity tab)."""
    log = load_json(SUBNET_DAILY_STORE, [])
    if not log:
        return {"error": "No data yet — run /api/subnet/sync"}
    latest = log[-1]
    prev = log[-2] if len(log) >= 2 else None

    def delta_pct(today, yesterday):
        if today is None or not yesterday:
            return None
        try:
            return round((today - yesterday) / yesterday * 100, 2)
        except Exception:
            return None

    holders_delta = None
    if prev and latest.get("subnet_total_holders") is not None and prev.get("subnet_total_holders"):
        holders_delta = latest["subnet_total_holders"] - prev["subnet_total_holders"]

    return {
        "date": latest["date"],
        "fetched_at_utc": latest.get("fetched_at_utc"),
        "block": latest.get("block"),
        "subnet_total_holders": latest.get("subnet_total_holders"),
        "holders_change_24h": holders_delta,
        "pool": latest.get("pool") or {},
        "subnet": latest.get("subnet") or {},
        "deltas_24h_pct": {
            "alpha_buy_volume": delta_pct(
                (latest.get("pool") or {}).get("alpha_buy_volume_24h"),
                (prev or {}).get("pool", {}).get("alpha_buy_volume_24h"),
            ),
            "alpha_sell_volume": delta_pct(
                (latest.get("pool") or {}).get("alpha_sell_volume_24h"),
                (prev or {}).get("pool", {}).get("alpha_sell_volume_24h"),
            ),
            "buyers": delta_pct(
                (latest.get("pool") or {}).get("buyers_24h"),
                (prev or {}).get("pool", {}).get("buyers_24h"),
            ),
            "sellers": delta_pct(
                (latest.get("pool") or {}).get("sellers_24h"),
                (prev or {}).get("pool", {}).get("sellers_24h"),
            ),
        },
    }


@app.get("/api/subnet-history")
async def api_subnet_history(_=Depends(require_auth), days: int = 30):
    """Last N daily rows for Activity tab charts."""
    log = load_json(SUBNET_DAILY_STORE, [])
    if not isinstance(log, list):
        return []
    return log[-max(1, min(days, 365)):]


@app.post("/api/subnet/sync")
async def api_subnet_sync_now(_=Depends(require_auth)):
    """Run the subnet daily sync immediately."""
    try:
        return sync_subnet_daily()
    except Exception as e:
        logger.exception("Subnet sync failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/holders/movement")
async def api_holders_movement(_=Depends(require_auth), limit: int = 50):
    """Top movers in/out of SN21 in the last 24h (Movement tab)."""
    try:
        from holders_sync import get_movement
        return get_movement(limit=limit)
    except Exception as e:
        logger.exception("Holders movement failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/holders/our")
async def api_holders_our(_=Depends(require_auth)):
    """Our owner-coldkey alpha balance across stored snapshots."""
    try:
        from holders_sync import get_our_movement
        return get_our_movement()
    except Exception as e:
        logger.exception("Holders our-movement failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/holders/sync")
async def api_holders_sync_now(_=Depends(require_auth)):
    """Run the full SN21 holder snapshot now (~10 paged calls; takes a few seconds)."""
    try:
        from holders_sync import sync_holders_snapshot
        return sync_holders_snapshot()
    except Exception as e:
        logger.exception("Holders sync failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/neurons")
async def api_neurons(_=Depends(require_auth)):
    """All 256 SN21 UIDs split into validators / miners with window-aware submitting flag."""
    try:
        from neurons_sync import fetch_neurons
        return fetch_neurons()
    except Exception as e:
        logger.exception("Neurons fetch failed")
        raise HTTPException(status_code=500, detail=str(e))


# ── Wallet labels (House vs Other) ────────────────────────────────────────────

@app.get("/api/labels")
async def api_labels_list(_=Depends(require_auth)):
    """Current wallet label set (House)."""
    from labels import list_labels
    return {"labels": list_labels()}


@app.post("/api/labels")
async def api_labels_set(payload: dict = Body(...), _=Depends(require_auth)):
    """Add or update a House label.

    Body: { ss58: str, kind: "coldkey"|"hotkey", note?: str }
    """
    from labels import set_label
    ss58 = (payload.get("ss58") or "").strip()
    kind = (payload.get("kind") or "").strip()
    note = payload.get("note")
    if not ss58:
        raise HTTPException(status_code=400, detail="ss58 is required")
    if kind not in {"coldkey", "hotkey"}:
        raise HTTPException(status_code=400, detail="kind must be 'coldkey' or 'hotkey'")
    try:
        return {"label": set_label(ss58, kind, note)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/api/labels/{ss58}")
async def api_labels_delete(ss58: str, _=Depends(require_auth)):
    """Remove a House label."""
    from labels import remove_label
    return {"removed": remove_label(ss58), "ss58": ss58}


# ── House weekly earnings ─────────────────────────────────────────────────────

@app.get("/api/house/weekly")
async def api_house_weekly(_=Depends(require_auth), weeks: int = 4):
    """Weekly House earnings (current + N prior weeks). Burn-aware: miner
    rollups expose gross / burned / net; validators and owner key are burn-
    immune and reported as-is."""
    try:
        from house_weekly import get_weekly
        return get_weekly(weeks=weeks)
    except Exception as e:
        logger.exception("House weekly rollup failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/house/snapshot")
async def api_house_snapshot_now(_=Depends(require_auth)):
    """Run a per-UID daily earnings snapshot now (idempotent for today's date)."""
    try:
        from neurons_daily_sync import sync_neurons_daily
        return sync_neurons_daily()
    except Exception as e:
        logger.exception("Neurons daily snapshot failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/house/miners")
async def api_house_miners(_=Depends(require_auth)):
    """In-house miners: alpha holding ('my money') + rolling 4-week earnings & trend."""
    from house_miners import get_house_miners
    return get_house_miners()


@app.post("/api/house/miners/sync")
async def api_house_miners_sync(_=Depends(require_auth)):
    """Rebuild the in-house miners holdings + earnings snapshot now."""
    try:
        from house_miners import build_house_miners
        return build_house_miners()
    except Exception as e:
        logger.exception("House miners sync failed")
        raise HTTPException(status_code=500, detail=str(e))


# ── Scout (candidate subnet scanner) ──────────────────────────────────────────


@app.get("/api/scan/candidates")
async def api_scan_candidates(_=Depends(require_auth)):
    """Latest Scout scan: ranked subnets with feasibility / yield / slippage / risk."""
    payload = scan_latest()
    if not payload:
        return {"error": "No scan yet — POST /api/scan/run"}
    return payload


@app.get("/api/scan/history")
async def api_scan_history(_=Depends(require_auth), days: int = 30):
    """Composite-score history per subnet (last N days)."""
    return scan_history(days=days)


@app.post("/api/scan/run")
async def api_scan_run(_=Depends(require_auth)):
    """Run the Scout scan immediately (~30s for the 5-netuid shortlist)."""
    try:
        return scan_run()
    except Exception as e:
        logger.exception("Scout scan failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/scan/notes")
async def api_scan_notes(_=Depends(require_auth)):
    """Qualitative overrides: { netuid: { multiplier, note } }."""
    return scan_load_notes()


@app.post("/api/scan/notes/{netuid}")
async def api_scan_notes_set(
    netuid: int, payload: dict = Body(default={}), _=Depends(require_auth)
):
    """Set qualitative override for one netuid. Body: { multiplier?, note? }."""
    multiplier = payload.get("multiplier")
    note = payload.get("note")
    if multiplier is not None:
        try:
            multiplier = float(multiplier)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="multiplier must be numeric")
    return {"netuid": netuid, "override": scan_set_note(netuid, multiplier=multiplier, note=note)}


@app.delete("/api/scan/notes/{netuid}")
async def api_scan_notes_delete(netuid: int, _=Depends(require_auth)):
    """Drop a qualitative override (revert to multiplier=1.0)."""
    return {"netuid": netuid, "removed": scan_delete_note(netuid)}


# ── Validator weights (copy / burn scan + wallet identification) ──────────────


@app.get("/api/weights/scan")
async def api_weights_scan(_=Depends(require_auth)):
    """Latest validator weight-copy / burn-status scan (cached 60s on disk)."""
    payload = weights_latest()
    if not payload:
        return {"error": "No scan yet — POST /api/weights/scan"}
    return payload


@app.post("/api/weights/scan")
async def api_weights_scan_run(_=Depends(require_auth)):
    """Run the on-chain weight scan now (~30s; reads every validator's vector)."""
    try:
        return weights_run()
    except Exception as e:
        logger.exception("Weights scan failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/weights/history")
async def api_weights_history(_=Depends(require_auth), days: int = 30):
    """Daily burn-fraction / copier-count history (last N days)."""
    return weights_history(days=days)


@app.get("/api/validator/wallets")
async def api_validator_wallets(_=Depends(require_auth), hotkey: str | None = None):
    """Full coldkey→stake breakdown behind our validator hotkey (UID 64 by default)."""
    try:
        return our_validator_wallets(hotkey=hotkey)
    except Exception as e:
        logger.exception("Validator wallets lookup failed")
        raise HTTPException(status_code=500, detail=str(e))


# ── Market context (all-subnets alpha-price peer comparison) ──────────────────


@app.get("/api/market/summary")
async def api_market_summary(_=Depends(require_auth)):
    """Latest all-subnets scan: SN21 standing, breadth, cohorts, per-subnet prices."""
    payload = market_latest()
    if not payload:
        return {"error": "No market scan yet — POST /api/market/sync"}
    return payload


@app.get("/api/market/history")
async def api_market_history(_=Depends(require_auth), days: int = 30):
    """SN21 percentile-rank / market-breadth history (last N days)."""
    return market_history(days=days)


@app.post("/api/market/sync")
async def api_market_sync(_=Depends(require_auth)):
    """Run the all-subnets alpha-price scan now (one chain call; ~10s)."""
    try:
        return market_run()
    except Exception as e:
        logger.exception("Market scan failed")
        raise HTTPException(status_code=500, detail=str(e))


# ── Movers Attribution (what drives 20%+ pumps: media vs mechanics vs dark) ────

@app.get("/api/movers/summary")
async def api_movers_summary(_=Depends(require_auth)):
    """Latest forward-capture: today's classified movers + rolling lead-lag cohort table."""
    payload = movers_latest()
    if not payload:
        return {"error": "No movers capture yet — POST /api/movers/capture"}
    return payload


@app.get("/api/movers/backtest")
async def api_movers_backtest(_=Depends(require_auth)):
    """Historical baseline study (winners/losers/control lead-lag from taoflute history)."""
    payload = movers_backtest_latest()
    if not payload:
        return {"error": "No backtest yet — POST /api/movers/backtest"}
    return payload


@app.post("/api/movers/capture")
async def api_movers_capture(_=Depends(require_auth)):
    """Snapshot all subnets' media/mechanics recency, tag movers, refresh rolling table."""
    try:
        return movers_capture()
    except Exception as e:
        logger.exception("Movers capture failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/movers/backtest")
async def api_movers_run_backtest(_=Depends(require_auth)):
    """Recompute the historical baseline from taoflute history (a few read-only queries)."""
    try:
        return movers_run_backtest()
    except Exception as e:
        logger.exception("Movers backtest failed")
        raise HTTPException(status_code=500, detail=str(e))


# ── Social · our own X posts (reuses the X Listen service) ────────────────────

@app.get("/api/social/posts")
async def api_social_posts(_=Depends(require_auth)):
    """Our managed X accounts' posts + latest metrics, proxied from the X Listen service."""
    try:
        return social_own_posts()
    except Exception as e:
        logger.exception("Social posts fetch failed")
        raise HTTPException(status_code=500, detail=str(e))


def _backfill_thread_worker(start_iso: str, end_iso: str) -> None:
    global _backfill_running
    try:
        from backfill_chain import run_chain_backfill

        run_chain_backfill(date.fromisoformat(start_iso), date.fromisoformat(end_iso))
    except Exception:
        logger.exception("Chain backfill failed")
    finally:
        with _backfill_lock:
            _backfill_running = False


# ── Emission Lab (model proposed mechanisms vs live SN21 state) ───────────────


def _lab_run_worker(version: str) -> None:
    global _lab_running
    try:
        from lab.runner import run_lab

        run_lab(version=version, live=True, persist=True)
    except Exception:
        logger.exception("Lab run failed")
    finally:
        with _lab_lock:
            _lab_running = False


@app.get("/api/lab/mechanisms")
async def api_lab_mechanisms(_=Depends(require_auth)):
    """Registered emission mechanisms (with deploy stage + stance) plus the
    proposed-PR watchlist — i.e. the full Consider→Plan→Go change pipeline."""
    from lab import store as lab_store
    from lab.watcher import proposed_changes
    return {
        "mechanisms": lab_store.registry_meta(),
        "proposed": proposed_changes(),
    }


@app.get("/api/lab/runs")
async def api_lab_runs(_=Depends(require_auth), limit: int = 50):
    """Historical lab-run log (most recent first) — the decision record."""
    from lab import store as lab_store
    return {"runs": lab_store.list_runs(limit=limit), "running": _lab_running}


@app.get("/api/lab/latest")
async def api_lab_latest(_=Depends(require_auth)):
    """Latest full lab run (reproduction gate + all scenarios)."""
    from lab import store as lab_store
    run = lab_store.latest_run()
    if not run:
        return {"error": "No lab run yet — POST /api/lab/run"}
    return run


@app.get("/api/lab/run/{run_id}")
async def api_lab_run_detail(run_id: str, _=Depends(require_auth)):
    """Full detail of one historical lab run."""
    from lab import store as lab_store
    run = lab_store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"No lab run {run_id}")
    return run


@app.post("/api/lab/watch")
async def api_lab_watch(notify: bool = False, _=Depends(require_auth)):
    """Check subtensor GitHub for a new release now; draft a stub on a new tag.
    notify=1 also sends the Telegram notice."""
    from lab.watcher import check_for_updates
    try:
        return check_for_updates(notify=notify)
    except Exception as e:
        logger.exception("Lab watch failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/lab/run")
async def api_lab_run(version: str = "root_reborn_v346_421", _=Depends(require_auth)):
    """Run the lab now in the background (~30-60s: chain pull + reproduction + scenarios)."""
    from lab.mechanisms import REGISTRY
    if version not in REGISTRY:
        raise HTTPException(status_code=400, detail=f"Unknown mechanism: {version}")
    global _lab_running
    with _lab_lock:
        if _lab_running:
            raise HTTPException(status_code=409, detail="Lab run already in progress")
        _lab_running = True
    threading.Thread(
        target=_lab_run_worker, args=(version,), daemon=True, name="sn21-lab-run",
    ).start()
    return {"queued": True, "version": version}


@app.post("/api/backfill")
async def api_backfill(
    start: str | None = None,
    end: str | None = None,
    _=Depends(require_auth),
):
    """
    One-time / occasional chain backfill (archive subtensor + CoinGecko TAO history).
    Set SUBTENSOR_ARCHIVE_NETWORK=archive when your default node cannot serve old blocks.
    """
    global _backfill_running
    with _backfill_lock:
        if _backfill_running:
            raise HTTPException(status_code=409, detail="Backfill already running")
        _backfill_running = True
    s = start or OWNERSHIP_START.isoformat()
    e = end or date.today().isoformat()
    threading.Thread(
        target=_backfill_thread_worker,
        args=(s, e),
        daemon=True,
        name="sn21-backfill",
    ).start()
    return {"queued": True, "start": s, "end": e}


@app.post("/api/collect")
async def manual_collect(_=Depends(require_auth)):
    """Manually trigger a collection (for testing or catch-up)."""
    try:
        from collector import run_collection
        result = run_collection()
        return {"status": "ok", "date": result["snapshot"]["date"]}
    except Exception as e:
        logger.exception("Manual collection failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/import-data")
async def api_import_data(
    request: Request,
    daily_log: UploadFile | None = File(None),
    owner_ledger: UploadFile | None = File(None),
):
    """
    Push JSON snapshots onto the server data disk (e.g. after local backfill).
    Auth: header X-SN21-Key: <DASHBOARD_PASSWORD> or Authorization: Bearer <password>

    curl example:
      curl -X POST "https://YOUR_APP.onrender.com/api/import-data" \\
        -H "X-SN21-Key: $DASHBOARD_PASSWORD" \\
        -F "daily_log=@data/daily_log.json" \\
        -F "owner_ledger=@data/owner_ledger.json"
    """
    require_import_key(request)
    if daily_log is None and owner_ledger is None:
        raise HTTPException(status_code=400, detail="Provide daily_log and/or owner_ledger file fields")

    if daily_log is not None:
        raw = await daily_log.read()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="daily_log is not valid JSON")
        if not isinstance(data, list):
            raise HTTPException(status_code=400, detail="daily_log must be a JSON array")
        save_json(DAILY_LOG, data)
        migrate_and_rebuild_from_logs()

    if owner_ledger is not None:
        raw = await owner_ledger.read()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="owner_ledger is not valid JSON")
        if not isinstance(data, dict):
            raise HTTPException(status_code=400, detail="owner_ledger must be a JSON object")
        save_json(OWNER_LEDGER, data)

    return {
        "status": "ok",
        "wrote": {
            "daily_log": daily_log is not None,
            "owner_ledger": owner_ledger is not None,
        },
        "data_dir": str(DATA_DIR),
    }


# ── Scheduler ─────────────────────────────────────────────────────────────────

def scheduled_collection():
    try:
        from collector import run_collection
        run_collection()
    except Exception as e:
        logger.error(f"Scheduled collection failed: {e}")


def scheduled_taostats_sync():
    try:
        sync_owner_transfers()
    except Exception:
        logger.exception("Scheduled Taostats sync failed")


def scheduled_subnet_sync():
    try:
        sync_subnet_daily()
    except Exception:
        logger.exception("Scheduled subnet daily sync failed")


def _holders_sync_with_retry(attempt: int = 1) -> None:
    """Run the holders snapshot. On failure, schedule one retry 30 min later."""
    try:
        from holders_sync import sync_holders_snapshot
        sync_holders_snapshot()
        if attempt > 1:
            logger.info("Holders snapshot retry #%s succeeded", attempt)
    except Exception:
        logger.exception("Holders snapshot attempt %s failed", attempt)
        if attempt < 3:
            run_at = datetime.now(timezone.utc) + timedelta(minutes=30)
            scheduler.add_job(
                _holders_sync_with_retry,
                DateTrigger(run_date=run_at),
                args=[attempt + 1],
                id=f"holders_retry_{run_at.strftime('%Y%m%dT%H%M')}",
                replace_existing=True,
                misfire_grace_time=3600,
            )
            logger.warning(
                "Scheduled holders snapshot retry #%s at %s UTC",
                attempt + 1, run_at.isoformat(),
            )


def scheduled_holders_sync():
    _holders_sync_with_retry(attempt=1)


def scheduled_neurons_daily():
    try:
        from neurons_daily_sync import sync_neurons_daily
        sync_neurons_daily()
    except Exception:
        logger.exception("Scheduled neurons daily snapshot failed")


def scheduled_market_sync():
    try:
        market_run()
    except Exception:
        logger.exception("Scheduled market scan failed")


def scheduled_scout_scan():
    try:
        scan_run()
    except Exception:
        logger.exception("Scheduled Scout scan failed")


def scheduled_weights_scan():
    try:
        weights_run()
    except Exception:
        logger.exception("Scheduled weights scan failed")


def scheduled_house_miners():
    try:
        from house_miners import build_house_miners
        build_house_miners()
    except Exception:
        logger.exception("Scheduled house-miners snapshot failed")


def scheduled_lab_run():
    try:
        from lab.runner import run_lab
        run_lab(version="root_reborn_v346_421", live=True, persist=True)
    except Exception:
        logger.exception("Scheduled lab run failed")


def scheduled_lab_watch():
    try:
        from lab.watcher import check_for_updates
        check_for_updates()
    except Exception:
        logger.exception("Scheduled lab watch failed")


def scheduled_stake_watch():
    try:
        run_stake_watch(notify=True)
    except Exception:
        logger.exception("Scheduled stake watch failed")


def scheduled_movers_capture():
    try:
        movers_capture()
    except Exception:
        logger.exception("Scheduled movers capture failed")


def log_tier_boundary(message: str) -> None:
    logger.info("SN21 entitlement tier boundary — %s", message)


# ── Digest configs ────────────────────────────────────────────────────────────

def _digest_time_utc() -> tuple[int, int]:
    """Override default 09:30 UTC via DIGEST_TIME_UTC=HH:MM."""
    raw = (os.environ.get("DIGEST_TIME_UTC") or "").strip()
    if not raw:
        return (9, 30)
    try:
        hh, mm = raw.split(":", 1)
        return (max(0, min(23, int(hh))), max(0, min(59, int(mm))))
    except (ValueError, AttributeError):
        logger.warning("Bad DIGEST_TIME_UTC=%r — using 09:30", raw)
        return (9, 30)


_PROMPTS_DIR = Path(__file__).resolve().parent / "digest" / "prompts"

DIGESTS: dict[str, DigestConfig] = {
    "sn21_daily": DigestConfig(
        kind="sn21_daily",
        gather=sn21_daily_source.gather,
        prompt_path=_PROMPTS_DIR / "sn21_daily.md",
        channel_send=telegram_channel.send,
        schedule_cron=_digest_time_utc(),
        state_filename="digest_state_sn21.json",
        archive_filename="digest_archive_sn21.json",
        archive_retention_days=30,
        title="SN21 Daily",
    ),
    "scout_weekly": DigestConfig(
        kind="scout_weekly",
        gather=scout_weekly_source.gather,
        prompt_path=_PROMPTS_DIR / "scout_weekly.md",
        channel_send=telegram_scout_channel.send,
        schedule_cron=(10, 0),  # informational; real schedule via cron_kwargs below
        state_filename="digest_state_scout.json",
        archive_filename="digest_archive_scout.json",
        archive_retention_days=12,  # 12 weekly digests of memory
        title="Scout Weekly",
        cron_kwargs={"day_of_week": "mon", "hour": 10, "minute": 0},
    ),
}


def scheduled_digest(kind: str) -> None:
    cfg = DIGESTS.get(kind)
    if cfg is None:
        logger.warning("Scheduled digest %s: no config registered", kind)
        return
    try:
        run_digest(cfg, force=False, dry_run=False)
    except Exception:
        logger.exception("Scheduled digest %s failed", kind)


@app.post("/api/digest/preview")
async def api_digest_preview(kind: str = "sn21_daily", _=Depends(require_auth)):
    """Compose the digest but DO NOT send. Returns markdown + structured inputs."""
    cfg = DIGESTS.get(kind)
    if cfg is None:
        raise HTTPException(status_code=404, detail=f"Unknown digest kind: {kind}")
    return run_digest(cfg, force=True, dry_run=True)


@app.post("/api/digest/send")
async def api_digest_send(
    kind: str = "sn21_daily",
    force: bool = False,
    _=Depends(require_auth),
):
    """Compose and send now. ?force=1 bypasses the same-day idempotency guard."""
    cfg = DIGESTS.get(kind)
    if cfg is None:
        raise HTTPException(status_code=404, detail=f"Unknown digest kind: {kind}")
    return run_digest(cfg, force=force, dry_run=False)


scheduler = BackgroundScheduler(timezone="UTC")
scheduler.add_job(
    scheduled_collection,
    CronTrigger(hour=8, minute=0),
    id="daily_collection",
    replace_existing=True,
)
scheduler.add_job(
    scheduled_market_sync,
    CronTrigger(hour=8, minute=5),
    id="daily_market_scan",
    replace_existing=True,
)
scheduler.add_job(
    scheduled_taostats_sync,
    CronTrigger(hour=8, minute=15),
    id="daily_taostats",
    replace_existing=True,
)
scheduler.add_job(
    scheduled_subnet_sync,
    CronTrigger(hour=8, minute=30),
    id="daily_subnet",
    replace_existing=True,
)
scheduler.add_job(
    scheduled_holders_sync,
    CronTrigger(hour=8, minute=45),
    id="daily_holders",
    replace_existing=True,
)
scheduler.add_job(
    scheduled_neurons_daily,
    CronTrigger(hour=9, minute=0),
    id="daily_neurons_snapshot",
    replace_existing=True,
)
scheduler.add_job(
    scheduled_scout_scan,
    CronTrigger(hour=9, minute=15),
    id="daily_scout_scan",
    replace_existing=True,
)
scheduler.add_job(
    scheduled_weights_scan,
    CronTrigger(hour=9, minute=20),
    id="daily_weights_scan",
    replace_existing=True,
)
scheduler.add_job(
    scheduled_house_miners,
    CronTrigger(hour=9, minute=10),
    id="daily_house_miners",
    replace_existing=True,
)
scheduler.add_job(
    scheduled_lab_run,
    CronTrigger(hour=9, minute=25),
    id="daily_lab_run",
    replace_existing=True,
)
scheduler.add_job(
    scheduled_lab_watch,
    CronTrigger(hour="*/6", minute=10),
    id="lab_watch",
    replace_existing=True,
)
scheduler.add_job(
    scheduled_stake_watch,
    CronTrigger(hour=7, minute=30),
    id="daily_stake_watch",
    replace_existing=True,
)
scheduler.add_job(
    scheduled_movers_capture,
    CronTrigger(hour=9, minute=35),  # after market_sync (08:05) has written today's price ledger
    id="daily_movers_capture",
    replace_existing=True,
)
for _kind, _cfg in DIGESTS.items():
    if _cfg.cron_kwargs:
        _trigger = CronTrigger(**_cfg.cron_kwargs)
    else:
        _h, _m = _cfg.schedule_cron
        _trigger = CronTrigger(hour=_h, minute=_m)
    scheduler.add_job(
        scheduled_digest,
        _trigger,
        args=[_kind],
        id=f"daily_digest_{_kind}",
        replace_existing=True,
    )


@app.on_event("startup")
async def startup():
    try:
        migrate_and_rebuild_from_logs()
    except Exception:
        logger.exception("migrate_and_rebuild_from_logs on startup")

    now = datetime.now(timezone.utc)
    for run_at, msg in scheduled_tier_events():
        if run_at > now:
            scheduler.add_job(
                log_tier_boundary,
                DateTrigger(run_date=run_at),
                args=[msg],
                id=f"tier_boundary_{run_at.date().isoformat()}",
                replace_existing=True,
            )

    scheduler.start()
    digest_lines = [
        f"{k} {cfg.schedule_cron[0]:02d}:{cfg.schedule_cron[1]:02d}"
        for k, cfg in DIGESTS.items()
    ]
    logger.info(
        "Data dir: %s — schedulers on (stake-watch 07:30; collect 08:00; market 08:05; Taostats 08:15; subnet 08:30; holders 08:45; neurons-daily 09:00; scout 09:15; weights 09:20 UTC; digests: %s; tier boundaries)",
        DATA_DIR, ", ".join(digest_lines) or "none",
    )


@app.on_event("shutdown")
async def shutdown():
    scheduler.shutdown()
