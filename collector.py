"""
SN21 Data Collector
Pulls Bittensor metagraph data + TAO/Alpha prices and writes to disk.
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import requests

from config import DAILY_LOG, OWNER_LEDGER
from ownership import entitlement_rate_for_snapshot_date

logger = logging.getLogger(__name__)

NETUID          = 21
NETWORK         = "finney"
OWNER_SHARE_PCT = 0.18
DROP_THRESHOLD  = 0.10  # 10% drop triggers alert flag


def _configure_chain_ssl() -> None:
    """Point SSL at certifi so WebSocket chain connections verify on minimal images (e.g. Render)."""
    try:
        import certifi

        os.environ.setdefault("SSL_CERT_FILE", certifi.where())
        os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())
    except ImportError:
        pass


# ── Persistence ──────────────────────────────────────────────────────────────

def load_json(path: Path, default):
    try:
        if path.exists():
            with open(path) as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load {path}: {e}")
    return default


def save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    tmp.replace(path)


# ── External Prices ──────────────────────────────────────────────────────────

_HTTP_HEADERS = {
    "User-Agent": "SN21-Monitor/1.0 (+https://github.com/ippcteam/sn21_monitor)",
    "Accept": "application/json",
}


def get_tao_price_usd() -> float | None:
    """
    TAO/USD — CoinGecko often fails from datacenters without a real User-Agent;
    Binance TAO/USDT is used as fallback (≈ USD).
    """
    for cid in ("bittensor", "tensor"):
        try:
            r = requests.get(
                "https://api.coingecko.com/api/v3/simple/price",
                params={"ids": cid, "vs_currencies": "usd"},
                headers=_HTTP_HEADERS,
                timeout=15,
            )
            r.raise_for_status()
            v = r.json().get(cid, {}).get("usd")
            if v is not None:
                return float(v)
        except Exception as e:
            logger.warning("CoinGecko TAO id=%s: %s", cid, e)

    try:
        r = requests.get(
            "https://api.binance.com/api/v3/ticker/price",
            params={"symbol": "TAOUSDT"},
            headers=_HTTP_HEADERS,
            timeout=10,
        )
        r.raise_for_status()
        return float(r.json()["price"])
    except Exception as e:
        logger.warning("Binance TAO/USDT fallback failed: %s", e)
        return None


# ── Metagraph Snapshot ────────────────────────────────────────────────────────

def get_snapshot() -> dict:
    """Pull live SN21 metagraph data and return structured snapshot."""
    _configure_chain_ssl()
    import bittensor as bt

    logger.info("Syncing SN21 metagraph...")
    mg = bt.Metagraph(netuid=NETUID, network=NETWORK, sync=True)

    uids       = mg.uids.tolist()
    emissions  = mg.emission.tolist()
    dividends  = mg.dividends.tolist()
    incentives = mg.incentive.tolist()
    stakes     = mg.stake.tolist()
    hotkeys    = mg.hotkeys
    hparams    = mg.hparams
    pool       = mg.pool

    total_emission = sum(emissions)
    owner_share    = round(total_emission * OWNER_SHARE_PCT, 8)

    try:
        tao_in    = float(pool.tao_in)
        alpha_in  = float(pool.alpha_in)
        alpha_price_tao = tao_in / alpha_in if alpha_in > 0 else None
    except Exception:
        tao_in = alpha_in = alpha_price_tao = None

    tao_usd = get_tao_price_usd()

    alpha_price_usd = (
        round(alpha_price_tao * tao_usd, 6)
        if alpha_price_tao and tao_usd else None
    )

    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    ent_rate = entitlement_rate_for_snapshot_date(date_str)
    subnet = {
        "total_alpha_emission":  round(total_emission, 8),
        "owner_share_alpha":     owner_share,
        "miner_validator_alpha": round(total_emission * 0.82, 8),
        "alpha_price_tao":       round(alpha_price_tao, 8) if alpha_price_tao else None,
        "alpha_price_usd":       alpha_price_usd,
        "tao_price_usd":         tao_usd,
        "tao_in_pool":           round(tao_in, 4) if tao_in else None,
        "alpha_in_pool":         round(alpha_in, 4) if alpha_in else None,
        "tempo":                 int(hparams.tempo) if hasattr(hparams, "tempo") else None,
        "entitlement_rate":      ent_rate,
        "our_entitled_alpha":    round(owner_share * ent_rate, 8),
    }

    return {
        "date":      date_str,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "block":     int(mg.block),
        "subnet":    subnet,
        "active_uids": [
            {
                "uid":       uid,
                "hotkey":    str(hotkeys[i])[:16] + "...",
                "emission":  round(emissions[i], 8),
                "dividend":  round(dividends[i], 6),
                "incentive": round(incentives[i], 6),
                "stake":     round(stakes[i], 4),
            }
            for i, uid in enumerate(uids) if emissions[i] > 0
        ],
    }


# ── Persistence Logic ─────────────────────────────────────────────────────────

def append_daily_log(snapshot: dict) -> list:
    log = load_json(DAILY_LOG, [])
    log = [e for e in log if e["date"] != snapshot["date"]]  # replace if re-run same day
    log.append(snapshot)
    save_json(DAILY_LOG, log)
    return log


def enrich_daily_log_entry(entry: dict) -> bool:
    """Ensure subnet has entitlement fields from date + owner_share_alpha. Returns True if changed."""
    ds = entry.get("date", "")[:10]
    sub = entry.get("subnet") or {}
    try:
        owner = float(sub["owner_share_alpha"])
    except (KeyError, TypeError, ValueError):
        return False
    rate = entitlement_rate_for_snapshot_date(ds)
    our = round(owner * rate, 8)
    changed = sub.get("entitlement_rate") != rate or sub.get("our_entitled_alpha") != our
    sub["entitlement_rate"] = rate
    sub["our_entitled_alpha"] = our
    entry["subnet"] = sub
    return changed


def migrate_and_rebuild_from_logs() -> None:
    """
    Backfill entitlement on every row in daily_log from ownership schedule (from Feb 19),
    then rebuild owner_ledger cumulative totals from the log.
    Safe to call on every startup.
    """
    log = load_json(DAILY_LOG, [])
    if not log:
        return

    changed = False
    for e in log:
        if enrich_daily_log_entry(e):
            changed = True
    if changed:
        log.sort(key=lambda x: x["date"])
        save_json(DAILY_LOG, log)

    log = sorted(load_json(DAILY_LOG, []), key=lambda x: x["date"])
    entries_out: list[dict] = []
    run_full = 0.0
    run_our = 0.0

    for e in log:
        ds = e["date"]
        sub = e.get("subnet") or {}
        enrich_daily_log_entry(e)
        sub = e["subnet"]
        owner = float(sub["owner_share_alpha"])
        our = float(sub["our_entitled_alpha"])
        rate = float(sub["entitlement_rate"])
        alpha_price = sub.get("alpha_price_tao")
        tao_price = sub.get("tao_price_usd")
        run_full = round(run_full + owner, 8)
        run_our = round(run_our + our, 8)
        our_tao_est = round(our * alpha_price, 6) if alpha_price else None
        our_usd_est = (
            round(our * alpha_price * tao_price, 4) if (alpha_price and tao_price) else None
        )
        entries_out.append(
            {
                "date": ds,
                "owner_share_alpha": owner,
                "entitlement_rate": rate,
                "our_entitled_alpha": our,
                "alpha_price_tao": alpha_price,
                "tao_price_usd": tao_price,
                "owner_share_tao_est": round(owner * alpha_price, 6) if alpha_price else None,
                "owner_share_usd_est": (
                    round(owner * alpha_price * tao_price, 4)
                    if (alpha_price and tao_price)
                    else None
                ),
                "our_entitled_tao_est": our_tao_est,
                "our_entitled_usd_est": our_usd_est,
                "running_total_alpha": run_full,
                "running_total_our_alpha": run_our,
            }
        )

    save_json(
        OWNER_LEDGER,
        {
            "total_accumulated_alpha": run_full,
            "total_accumulated_our_alpha": run_our,
            "entries": entries_out,
        },
    )


def check_emission_drop(snapshot: dict, log: list) -> dict | None:
    """
    Compare today's emission vs prior day.
    Returns an alert dict or None.
    """
    prior = [e for e in log if e["date"] != snapshot["date"]]
    if not prior:
        return None

    yesterday = prior[-1]["subnet"]["total_alpha_emission"]
    if yesterday == 0:
        return None

    today = snapshot["subnet"]["total_alpha_emission"]
    change = (today - yesterday) / yesterday

    if abs(change) >= DROP_THRESHOLD:
        direction = "drop" if change < 0 else "surge"
        return {
            "type":      direction,
            "change_pct": round(change * 100, 1),
            "yesterday": yesterday,
            "today":     today,
        }
    return None


# ── Main Entry (used by scheduler + manual run) ───────────────────────────────

def run_collection() -> dict:
    logger.info("Starting daily SN21 collection...")
    snapshot = get_snapshot()
    log = append_daily_log(snapshot)
    migrate_and_rebuild_from_logs()
    ledger = load_json(OWNER_LEDGER, {"entries": []})
    alert = check_emission_drop(snapshot, log)

    logger.info(
        "Collection complete. Emission: %.6f ξ | Owner pool: %.6f ξ | Our share: %.6f ξ | Alert: %s",
        snapshot["subnet"]["total_alpha_emission"],
        snapshot["subnet"]["owner_share_alpha"],
        snapshot["subnet"].get("our_entitled_alpha") or 0,
        alert,
    )

    return {"snapshot": snapshot, "ledger": ledger, "alert": alert}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = run_collection()
    print(json.dumps(result["snapshot"]["subnet"], indent=2))
