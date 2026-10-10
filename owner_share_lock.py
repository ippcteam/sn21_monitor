"""
Owner-share conviction lock — weekly Friday top-up of the SN21 lock, signed on Ledger.

Our owner-share coldkey (5DkEA99g…, Ledger) receives 648 α/day of owner emission. Policy
(2026-09-25): lock half of it, 324 α/day, accruing from 2026-09-21, to the SUBNET OWNER
HOTKEY (5EqAzb…) as a DECAYING lock, topped up once a week on Friday.

Why the owner hotkey: locks pointed at SubnetOwnerHotkey merge into OwnerLock, where
conviction == locked mass immediately (no maturity ramp), so a weekly top-up earns the
same conviction as a daily one. The lock is a coldkey-wide floor on SN21 — the alpha
stays staked on our validator hotkey and keeps earning; nothing moves.

Decaying (never call set_perpetual_lock): locked mass unlocks with UnlockRate's
~90-day half-life, so at 324 α/day the lock levels off around ~42k α.

Amount owed = 324 α × days from the day after the last recorded lock (or START_DATE)
through the Friday being run, inclusive. Each successful lock is appended to
data/owner_share_lock.json, which is what makes next Friday pick up where this left off.

Usage:
    python owner_share_lock.py              # preview only: pre-flight checks + amount
    python owner_share_lock.py --execute    # preview, confirm by typing the amount, sign on Ledger
    python owner_share_lock.py --remind     # macOS reminder if a lock is owed (run by launchd,
                                            # see ops/install_lock_reminder.sh)

The period always ends on the most recent Friday (today, if today is Friday), so a lock
missed on Friday is signed the next day for the same period.
"""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
from pathlib import Path
from datetime import date, datetime, timedelta, timezone
from typing import Any

from chain_compat import bal, get_subtensor
from collector import load_json, save_json
from config import DATA_DIR

logger = logging.getLogger(__name__)

NETUID = int(os.environ.get("SN21_NETUID", "21"))
OWNER_SHARE_COLDKEY = (
    os.environ.get("OWNER_SHARE_COLDKEY")
    or "5DkEA99gAAF2Ge6X3h76x98LbYtqT7gJ6h9VaApfMkKJCPJM"
).strip()
SUBNET_OWNER_HOTKEY = (
    os.environ.get("SUBNET_OWNER_HOTKEY")
    or "5EqAzby1upPkqpba5qrbDLZtFLmaTUe2PRbzih62voorQVHp"
).strip()

DAILY_LOCK_ALPHA = 324
START_DATE = date(2026, 9, 21)
LOCK_WEEKDAY = 4  # Friday
LEDGER_ACCOUNT = 1  # 5DkEA99g… derives at m/44'/354'/1'/0'/0' on our device
MIN_FREE_TAO = 0.005  # lock_stake fees are TAO-only (not in the alpha-fee call list)

LOCK_RECORD_STORE = DATA_DIR / "owner_share_lock.json"
REPO_DIR = Path(__file__).resolve().parent
EXECUTE_COMMAND = f"cd {REPO_DIR} && .venv/bin/python owner_share_lock.py --execute"


def last_lock_day(today: date) -> date:
    """The most recent Friday on or before `today`."""
    return today - timedelta(days=(today.weekday() - LOCK_WEEKDAY) % 7)


def owed_window(records: list[dict[str, Any]], through: date,
                start: date = START_DATE) -> tuple[date, int]:
    """(first uncovered day, number of days owed through `through` inclusive)."""
    if records:
        first = date.fromisoformat(max(r["covered_through"] for r in records)) + timedelta(days=1)
    else:
        first = start
    return first, max(0, (through - first).days + 1)


def preflight(state: dict[str, Any], amount_alpha: float) -> list[str]:
    """Blocking problems for locking `amount_alpha` given fetch_state() output."""
    problems: list[str] = []
    lock = state["lock"]
    if lock and lock["hotkey"] != SUBNET_OWNER_HOTKEY:
        problems.append(
            f"existing lock points at {lock['hotkey']}, not the owner hotkey — "
            "the chain would reject this top-up (LockHotkeyMismatch)"
        )
    if lock and lock["is_perpetual"]:
        problems.append("existing lock is PERPETUAL; policy is decaying — resolve before topping up")
    if state["available_alpha"] < amount_alpha:
        problems.append(
            f"only {state['available_alpha']:,.3f} α unlocked on SN{NETUID}, "
            f"need {amount_alpha:,.0f} α"
        )
    if state["free_tao"] < MIN_FREE_TAO:
        problems.append(
            f"coldkey has {state['free_tao']:.6f} τ free; fund it with ~0.05 τ for the fee"
        )
    return problems


def fetch_state(st) -> dict[str, Any]:
    positions = [p for p in st.staking.positions(OWNER_SHARE_COLDKEY) if p.netuid == NETUID]
    total = sum(bal(p.stake) or 0.0 for p in positions)
    raw_lock = st.locks.coldkey_lock(OWNER_SHARE_COLDKEY, NETUID)
    lock = None
    if raw_lock:
        lock = {
            "hotkey": raw_lock["hotkey"],
            "locked_alpha": bal(raw_lock["locked_alpha"]) or 0.0,
            "is_perpetual": bool(raw_lock["is_perpetual"]),
        }
    locked = lock["locked_alpha"] if lock else 0.0
    return {
        "block": st.block(),
        "free_tao": bal(st.balances.get(OWNER_SHARE_COLDKEY)) or 0.0,
        "total_alpha": total,
        "locked_alpha": locked,
        "available_alpha": total - locked,
        "lock": lock,
        "positions": {p.hotkey: bal(p.stake) for p in positions},
    }


def _print_plan(state: dict[str, Any], first: date, through: date, days: int,
                amount: int, problems: list[str]) -> None:
    lock = state["lock"]
    print(f"\nSN{NETUID} owner-share lock — block {state['block']}")
    print(f"  Coldkey (Ledger):  {OWNER_SHARE_COLDKEY}")
    print(f"  Lock hotkey:       {SUBNET_OWNER_HOTKEY} (subnet owner hotkey)")
    print(f"  Free TAO:          {state['free_tao']:.6f} τ")
    print(f"  SN{NETUID} stake:        {state['total_alpha']:,.3f} α")
    print(f"  Currently locked:  {state['locked_alpha']:,.3f} α"
          + (f" ({'perpetual' if lock['is_perpetual'] else 'decaying'})" if lock else " (no lock yet)"))
    print(f"\n  Period:  {first.isoformat()} → {through.isoformat()}  ({days} days)")
    print(f"  Amount:  {days} × {DAILY_LOCK_ALPHA} α = {amount:,} α")
    print(f"  After:   ~{state['locked_alpha'] + amount:,.3f} α locked, decaying")
    if problems:
        print("\n  BLOCKED:")
        for p in problems:
            print(f"    ✗ {p}")
    else:
        print("\n  Pre-flight: all checks pass")


def _execute(st, amount: int, first: date, through: date, days: int,
             ledger_account: int, ledger_index: int) -> int:
    from bittensor import LedgerSigner
    from bittensor.intents.lock import LockStake

    signer = LedgerSigner(account=ledger_account, index=ledger_index)
    if signer.ss58_address != OWNER_SHARE_COLDKEY:
        print(f"\nLedger path m/44'/354'/{ledger_account}'/0'/{ledger_index}' is "
              f"{signer.ss58_address}, not {OWNER_SHARE_COLDKEY}. "
              "Try --ledger-account / --ledger-index.")
        return 1

    intent = LockStake(netuid=NETUID, amount_alpha=str(amount), hotkey_ss58=SUBNET_OWNER_HOTKEY)
    plan = st.plan(intent, signer)
    print(f"\n  Chain dry-run: {plan.summary}; est. fee {plan.fee}")
    for w in plan.warnings:
        print(f"    ! {w}")
    if not plan.ok:
        print(f"  Policy violations: {plan.violations}")
        return 1

    typed = input(f"\nType {amount} to lock {amount:,} α (anything else aborts): ").strip()
    if typed != str(amount):
        print("Aborted — nothing signed.")
        return 1

    print("Approve the transaction on the Ledger screen…")
    result = st.execute(intent, signer)
    if not result.success:
        print(f"\nLock FAILED: {result.message}")
        return 1

    after = fetch_state(st)
    records = load_json(LOCK_RECORD_STORE, [])
    records.append({
        "locked_at": datetime.now(timezone.utc).isoformat(),
        "covered_from": first.isoformat(),
        "covered_through": through.isoformat(),
        "days": days,
        "amount_alpha": amount,
        "extrinsic_id": result.extrinsic_id,
        "block_hash": result.block_hash,
        "explorer_url": result.explorer_url,
        "locked_alpha_after": round(after["locked_alpha"], 6),
    })
    save_json(LOCK_RECORD_STORE, records)
    print(f"\nLocked {amount:,} α — extrinsic {result.extrinsic_id}")
    if result.explorer_url:
        print(f"  {result.explorer_url}")
    print(f"  Now locked: {after['locked_alpha']:,.3f} α (recorded in {LOCK_RECORD_STORE})")
    return 0


def _osascript(script: str, timeout: float | None = None) -> str:
    out = subprocess.run(["osascript", "-e", script], capture_output=True, text=True,
                         timeout=timeout)
    return out.stdout.strip()


def _applescript_str(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def remind(first: date, through: date, amount: int, problems: list[str]) -> None:
    """macOS reminder. Blocked → notification naming the problem. Ready → dialog whose
    'Lock now' button opens Terminal on the --execute command (signing still needs the
    typed confirmation and the Ledger approval)."""
    period = f"{first:%-d %b} – {through:%-d %b}"
    if problems:
        _osascript(
            f"display notification {_applescript_str('; '.join(problems))} "
            f"with title \"SN{NETUID} lock BLOCKED\" subtitle {_applescript_str(f'{amount:,} α due ({period})')} "
            "sound name \"Basso\""
        )
        return
    msg = (f"{amount:,} α is due for {period}.\n\n"
           "Plug in and unlock the Ledger, open the Polkadot app, then click Lock now.")
    choice = _osascript(
        f"display dialog {_applescript_str(msg)} with title \"SN{NETUID} owner-share lock\" "
        "buttons {\"Later\", \"Lock now\"} default button \"Lock now\" giving up after 3600",
        timeout=3700,
    )
    if "Lock now" in choice:
        _osascript(
            f"tell application \"Terminal\" to do script {_applescript_str(EXECUTE_COMMAND)}\n"
            "tell application \"Terminal\" to activate"
        )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--execute", action="store_true",
                    help="after the preview, confirm and sign the lock on the Ledger")
    ap.add_argument("--remind", action="store_true",
                    help="show a macOS reminder if a lock is owed (silent otherwise)")
    ap.add_argument("--through", type=date.fromisoformat,
                    help="last day to cover (YYYY-MM-DD); default the most recent Friday")
    ap.add_argument("--ledger-account", type=int, default=LEDGER_ACCOUNT)
    ap.add_argument("--ledger-index", type=int, default=0)
    args = ap.parse_args(argv)

    through = args.through or last_lock_day(date.today())
    records = load_json(LOCK_RECORD_STORE, [])
    first, days = owed_window(records, through)
    if days == 0:
        print(f"Nothing owed: already covered through {first - timedelta(days=1)}.")
        return 0
    amount = days * DAILY_LOCK_ALPHA

    st = get_subtensor()
    state = fetch_state(st)
    problems = preflight(state, amount)
    _print_plan(state, first, through, days, amount, problems)
    if args.remind:
        remind(first, through, amount, problems)
        return 0
    if problems:
        return 1
    if not args.execute:
        print("\nPreview only. Re-run with --execute to confirm and sign on the Ledger.")
        return 0
    return _execute(st, amount, first, through, days, args.ledger_account, args.ledger_index)


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    sys.exit(main())
