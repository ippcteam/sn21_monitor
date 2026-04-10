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

def get_tao_price_usd() -> float | None:
    """Fetch TAO/USD from CoinGecko free API."""
    try:
        r = requests.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": "bittensor", "vs_currencies": "usd"},
            timeout=10,
        )
        r.raise_for_status()
        return r.json().get("bittensor", {}).get("usd")
    except Exception as e:
        logger.warning(f"TAO price fetch failed: {e}")
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

    return {
        "date":      datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "block":     int(mg.block),
        "subnet": {
            "total_alpha_emission":  round(total_emission, 8),
            "owner_share_alpha":     owner_share,
            "miner_validator_alpha": round(total_emission * 0.82, 8),
            "alpha_price_tao":       round(alpha_price_tao, 8) if alpha_price_tao else None,
            "alpha_price_usd":       alpha_price_usd,
            "tao_price_usd":         tao_usd,
            "tao_in_pool":           round(tao_in, 4) if tao_in else None,
            "alpha_in_pool":         round(alpha_in, 4) if alpha_in else None,
            "tempo":                 int(hparams.tempo) if hasattr(hparams, "tempo") else None,
        },
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


def update_owner_ledger(snapshot: dict) -> dict:
    ledger = load_json(OWNER_LEDGER, {"total_accumulated_alpha": 0.0, "entries": []})

    today_share = snapshot["subnet"]["owner_share_alpha"]
    alpha_price = snapshot["subnet"].get("alpha_price_tao")
    tao_price   = snapshot["subnet"].get("tao_price_usd")

    # Remove existing entry for today if re-running
    ledger["entries"] = [e for e in ledger["entries"] if e["date"] != snapshot["date"]]

    # Recompute running total from all entries after dedup
    ledger["total_accumulated_alpha"] = round(
        sum(e["owner_share_alpha"] for e in ledger["entries"]) + today_share, 8
    )

    ledger["entries"].append({
        "date":                  snapshot["date"],
        "owner_share_alpha":     today_share,
        "alpha_price_tao":       alpha_price,
        "tao_price_usd":         tao_price,
        "owner_share_tao_est":   round(today_share * alpha_price, 6)  if alpha_price else None,
        "owner_share_usd_est":   round(today_share * alpha_price * tao_price, 4) if (alpha_price and tao_price) else None,
        "running_total_alpha":   ledger["total_accumulated_alpha"],
    })

    save_json(OWNER_LEDGER, ledger)
    return ledger


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
    log      = append_daily_log(snapshot)
    ledger   = update_owner_ledger(snapshot)
    alert    = check_emission_drop(snapshot, log)

    logger.info(
        f"Collection complete. "
        f"Emission: {snapshot['subnet']['total_alpha_emission']:.6f} ξ | "
        f"Owner: {snapshot['subnet']['owner_share_alpha']:.6f} ξ | "
        f"Alert: {alert}"
    )

    return {"snapshot": snapshot, "ledger": ledger, "alert": alert}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = run_collection()
    print(json.dumps(result["snapshot"]["subnet"], indent=2))
