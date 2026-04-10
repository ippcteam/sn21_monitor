"""
On-chain backfill for daily_log.json using an *archive* subtensor.

Light Finney nodes discard state after ~300 blocks; use network=archive
(override with SUBTENSOR_ARCHIVE_NETWORK).

TAO/USD per day: CoinGecko `market_chart/range` (one HTTP call) with forward-fill.

CLI:
  python -m backfill_chain --start 2026-02-19 --end 2026-04-10

Or authenticated POST /api/backfill (runs as a background task).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import time
from datetime import date, datetime, timedelta, timezone
from typing import Callable

import requests

from collector import (
    NETUID,
    _configure_chain_ssl,
    _HTTP_HEADERS,
    get_tao_price_usd,
    load_json,
    migrate_and_rebuild_from_logs,
    save_json,
    snapshot_from_metagraph,
)
from config import DAILY_LOG
from ownership import OWNERSHIP_START

logger = logging.getLogger(__name__)

ARCHIVE_ENV = "SUBTENSOR_ARCHIVE_NETWORK"
DEFAULT_ARCHIVE = "archive"


def _ts_ms_subtensor(subtensor, block: int) -> int:
    bh = subtensor.get_block_hash(block)
    raw = subtensor.substrate.query("Timestamp", "Now", block_hash=bh)
    v = getattr(raw, "value", raw)
    return int(v)


def block_at_or_before_eod_utc(subtensor, day: date) -> int:
    """Largest block whose chain timestamp is <= end of `day` UTC."""
    end = datetime(day.year, day.month, day.day, 23, 59, 59, tzinfo=timezone.utc)
    target_ms = int(end.timestamp() * 1000)
    lo, hi = 0, subtensor.get_current_block()
    best = 0
    while lo <= hi:
        mid = (lo + hi) // 2
        try:
            ts = _ts_ms_subtensor(subtensor, mid)
        except Exception:
            hi = mid - 1
            continue
        if ts <= target_ms:
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1
    return best


def fetch_tao_usd_by_day(start: date, end: date) -> dict[str, float]:
    """Daily TAO/USD from CoinGecko market_chart/range."""
    t0 = datetime(start.year, start.month, start.day, tzinfo=timezone.utc)
    t1 = datetime(end.year, end.month, end.day, 23, 59, 59, tzinfo=timezone.utc)
    url = "https://api.coingecko.com/api/v3/coins/bittensor/market_chart/range"
    params = {
        "vs_currency": "usd",
        "from": int(t0.timestamp()),
        "to": int(t1.timestamp()),
    }
    r = requests.get(url, params=params, headers=_HTTP_HEADERS, timeout=60)
    r.raise_for_status()
    prices = r.json().get("prices") or []
    if not prices:
        spot = get_tao_price_usd()
        out: dict[str, float] = {}
        cur = start
        while cur <= end and spot is not None:
            out[cur.isoformat()] = spot
            cur += timedelta(days=1)
        return out

    by_day: dict[str, list[float]] = {}
    for ts_ms, px in prices:
        d = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc).date().isoformat()
        by_day.setdefault(d, []).append(float(px))

    daily: dict[str, float] = {d: sum(v) / len(v) for d, v in by_day.items()}
    out: dict[str, float] = {}
    cur = start
    last: float | None = None
    while cur <= end:
        ds = cur.isoformat()
        if ds in daily:
            last = daily[ds]
        if last is not None:
            out[ds] = last
        else:
            spot = get_tao_price_usd()
            if spot is not None:
                out[ds] = spot
                last = spot
        cur += timedelta(days=1)
    return out


def run_chain_backfill(
    start: date | None = None,
    end: date | None = None,
    *,
    progress: Callable[[str], None] | None = None,
    sleep_s: float = 0.35,
) -> dict:
    _configure_chain_ssl()
    import bittensor as bt

    start = start or OWNERSHIP_START
    end = end or date.today()
    if end < start:
        raise ValueError("end before start")

    def notify(msg: str) -> None:
        logger.info(msg)
        print(msg, flush=True)
        if progress:
            progress(msg)

    net = os.environ.get(ARCHIVE_ENV, DEFAULT_ARCHIVE)
    notify(f"Subtensor {net!r} (archive) — backfill {start} .. {end}")

    st = bt.Subtensor(network=net, log_verbose=False)
    notify("Fetching TAO/USD history (CoinGecko)")
    tao_by_day = fetch_tao_usd_by_day(start, end)

    added = 0
    updated = 0
    cur = start
    max_attempts = int(os.environ.get("BACKFILL_RETRIES_PER_DAY", "5"))

    def fresh_subtensor():
        nonlocal st
        st = bt.Subtensor(network=net, log_verbose=False)

    try:
        while cur <= end:
            ds = cur.isoformat()
            tao_usd = tao_by_day.get(ds) or get_tao_price_usd()
            last_err: Exception | None = None
            for attempt in range(max_attempts):
                try:
                    if attempt > 0:
                        notify(f"{ds} retry {attempt + 1}/{max_attempts} (reconnecting…)")
                        time.sleep(min(8 * attempt, 45))
                        fresh_subtensor()
                    blk = block_at_or_before_eod_utc(st, cur)
                    mg = bt.Metagraph(
                        netuid=NETUID,
                        network=net,
                        lite=True,
                        sync=False,
                        subtensor=st,
                    )
                    mg.sync(block=blk, lite=True, subtensor=st)
                    snap = snapshot_from_metagraph(mg, ds, tao_usd=tao_usd)
                    line = f"{ds} block={blk} owner_α={snap['subnet']['owner_share_alpha']}"
                    notify(line)

                    log_data = load_json(DAILY_LOG, [])
                    idx = next((i for i, e in enumerate(log_data) if e.get("date") == ds), None)
                    if idx is not None:
                        log_data[idx] = snap
                        updated += 1
                    else:
                        log_data.append(snap)
                        added += 1
                    log_data.sort(key=lambda e: e["date"])
                    save_json(DAILY_LOG, log_data)
                    break
                except Exception as e:
                    last_err = e
                    logger.warning("Backfill day %s attempt %s failed: %s", ds, attempt + 1, e)
            else:
                raise RuntimeError(f"Giving up on {ds} after {max_attempts} attempts") from last_err

            cur += timedelta(days=1)
            time.sleep(sleep_s)
    finally:
        notify("Rebuilding ledger from daily_log…")
        migrate_and_rebuild_from_logs()

    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "days_added": added,
        "days_updated": updated,
        "network": net,
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    p = argparse.ArgumentParser(description="Backfill daily_log from archive chain")
    p.add_argument("--start", type=str, default=OWNERSHIP_START.isoformat())
    p.add_argument("--end", type=str, default=date.today().isoformat())
    args = p.parse_args()
    out = run_chain_backfill(date.fromisoformat(args.start), date.fromisoformat(args.end))
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
