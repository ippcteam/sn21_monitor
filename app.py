"""
SN21 Dashboard — FastAPI app
Serves the dashboard, handles auth, runs daily collection via APScheduler.
"""

import json
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, Request, Response, HTTPException, Depends
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
DASHBOARD_PASSWORD = os.environ.get("DASHBOARD_PASSWORD", "changeme")
COOKIE_NAME        = "sn21_session"
COOKIE_MAX_AGE     = 60 * 60 * 24 * 30  # 30 days
DATA_DIR           = Path(os.environ.get("SN21_DATA_DIR", "/data"))
DAILY_LOG          = DATA_DIR / "daily_log.json"
OWNER_LEDGER       = DATA_DIR / "owner_ledger.json"

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
    ledger = load_json(OWNER_LEDGER, {"total_accumulated_alpha": 0.0, "entries": []})

    latest = log[-1] if log else None
    prev   = log[-2] if len(log) >= 2 else None

    def pct_change(today, yesterday):
        if yesterday and yesterday != 0:
            return round((today - yesterday) / yesterday * 100, 2)
        return None

    if latest:
        s = latest["subnet"]
        prev_s = prev["subnet"] if prev else {}
        return {
            "date":                  latest["date"],
            "block":                 latest["block"],
            "active_uids":           len(latest["active_uids"]),
            "total_alpha_emission":  s["total_alpha_emission"],
            "owner_share_alpha":     s["owner_share_alpha"],
            "alpha_price_tao":       s.get("alpha_price_tao"),
            "alpha_price_usd":       s.get("alpha_price_usd"),
            "tao_price_usd":         s.get("tao_price_usd"),
            "running_total_alpha":   ledger["total_accumulated_alpha"],
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
                "date":    e["date"],
                "running": e["running_total_alpha"],
                "daily":   e["owner_share_alpha"],
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


@app.post("/api/collect")
async def manual_collect(_=Depends(require_auth)):
    """Manually trigger a collection (for testing or catch-up)."""
    try:
        from collector import run_collection
        result = run_collection()
        return {"status": "ok", "date": result["snapshot"]["date"]}
    except Exception as e:
        logger.error(f"Manual collection failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Scheduler ─────────────────────────────────────────────────────────────────

def scheduled_collection():
    try:
        from collector import run_collection
        run_collection()
    except Exception as e:
        logger.error(f"Scheduled collection failed: {e}")


scheduler = BackgroundScheduler(timezone="UTC")
scheduler.add_job(
    scheduled_collection,
    CronTrigger(hour=8, minute=0),
    id="daily_collection",
    replace_existing=True,
)


@app.on_event("startup")
async def startup():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    scheduler.start()
    logger.info("Scheduler started — daily collection at 08:00 UTC")


@app.on_event("shutdown")
async def shutdown():
    scheduler.shutdown()
