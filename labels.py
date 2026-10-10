"""
Wallet labels — flag SN21 keys as "House" or "bot".

Storage: data/wallet_labels.json
  { "labels": { "<ss58>": { "kind": "coldkey"|"hotkey",
                            "label": "house"|"bot",
                            "note": str | None,
                            "added_at": ISO-8601 UTC } },
    "seeded_from_env": bool }

House lookups join coldkey OR hotkey: a UID is House only when a key is
labeled "house". Bot keys live in the same file and are not House.
"""

from __future__ import annotations

import logging
import os
import threading
from datetime import datetime, timezone
from typing import Any

from collector import load_json, save_json
from config import DATA_DIR

logger = logging.getLogger(__name__)

WALLET_LABELS_STORE = DATA_DIR / "wallet_labels.json"
HOUSE_LABEL = "house"
BOT_LABEL = "bot"
VALID_KINDS = {"coldkey", "hotkey"}

# Known in-house keys, version-controlled so they are marked House on every
# instance (incl. production's /data disk) without env/dashboard fiddling. Each
# is ensured-present on load unless explicitly removed via remove_label (tracked
# in store["removed"], so the dashboard "unstar" still sticks).
# UID 221 added 2026-10-10 (hotkey + coldkey confirmed by operator).
DEFAULT_HOUSE_KEYS: list[tuple[str, str, str]] = [
    ("hotkey",  "5G6N3zP3h42qF3xHfFvy8qqu1ZQQh9n7GegctfPFjfuPdxDf", "in-house miner UID 1"),
    ("hotkey",  "5DemVP2S5LpdnCk4VoewRPRJDvVTYuZ5c4Kqcf7S46ChfwHT", "in-house miner UID 147 (formerly UID 166)"),
    ("hotkey",  "5Gx5Vu9qXtwrcz78NKrMrq8iSGj1UXvEV3ZhddWirea5gA5e", "in-house miner UID 154"),
    ("hotkey",  "5GZZKNfGjpFRQmkEfedUbzjRVwj6xcSAp75h9SEkiFKPFpGR", "in-house miner UID 221"),
    ("coldkey", "5F9i7LjCW6C8ExBy3mH9jWDWwAwPwCg5UdzY2WzzTHS8LQjH", "in-house miner coldkey (UID 1 & 147)"),
    ("coldkey", "5DJ1wjWyfKo2mpiV8mGBdXzEsJweG63xVfWiejdDqrvyQ5vs", "in-house miner coldkey (UID 154)"),
    ("coldkey", "5HpzYUZXJkgSH9PTNEa5MFgcCipVKLYVgfu64JUfL4vTSxke", "in-house miner coldkey (UID 221)"),
]

# Flow-followers and scalp bots around Siam's 25τ buy at 2026-10-10 00:45:24 UTC
# (block 9249210, coldkey 5DDDdan…5551gu). The ~75τ "faster" cluster was included
# in the preceding block; the ~95τ "slower" cluster landed 5–6 minutes later.
# 5Edf8EkS… (25.84τ into DSV Vali) was in that candle and is not listed: one
# stake, still open, not a repeat pattern.
DEFAULT_BOT_KEYS: list[tuple[str, str, str]] = [
    ("coldkey", "5D31yczGiq9tVJwGgX87sWBks1g6RST5Tju5aajGycvvrijb",
     "flow-follow bot. Slower wave 00:51 (10+5+5τ, sold 20.15τ next block). Also copied the 9 Oct 21:11 30τ clip and the 10 Oct 11:18 25τ clip."),
    ("coldkey", "5Gb23Q7n115ypiHr6jAMRhkhADhEkRFYa5ovgipVApqMt3FV",
     "round-size bot (10/15/20/30τ). 30τ of the slower 95τ wave; 20τ again 24s before the 11:18 25τ buy."),
    ("coldkey", "5GCcH9R6SS7xtobP3EvrgSBXuowAtpjgMBP6FVTLWfqGbZ9g",
     "faster cluster: 2×20τ on Taostats in the block before the 25τ. Sold 42.85τ at 07:11. Only episode in the prior 3 weeks."),
    ("coldkey", "5GW9Nb89AR9SVvAuQW2b62KZkTYAcbJ2yAW4UGWx8bxrVoPD",
     "tao.bot scalp bot. 10τ in the faster cluster, sold 10.14τ next block. 26 round-trips of 5–15τ since 2 Oct, net flat."),
    ("coldkey", "5Gy3ybnsXLe4HSArvQLdBDK2zn53xH77cQ7Bt78dnihQ268b",
     "tao.bot scalp bot. 7τ in and out during the slower wave. Serial 20τ round-trips, net flat."),
    ("coldkey", "5GSKU7VbmEiUid22SfXojQkBcpXnVTXQQNCMsbz5b3xF9ZQ3",
     "slower wave: 20.77τ on tao.bot at 00:50, plus 16.82τ at 01:02. No other SN21 history, still open."),
    ("coldkey", "5G23mT5EiZKy5zn1PdpJsHqtTbwW9cU5gQ6FDh5oY5uSnbek",
     "slower wave: 34.84τ on tao.bot. Accumulates and does not sell (243τ net since 8 Oct, including 75+75)."),
]

_lock = threading.Lock()


def _empty_store() -> dict[str, Any]:
    return {"labels": {}, "seeded_from_env": False, "removed": []}


def _normalise_store(store: Any) -> dict[str, Any]:
    if not isinstance(store, dict):
        return _empty_store()
    if "labels" not in store or not isinstance(store["labels"], dict):
        store["labels"] = {}
    if "seeded_from_env" not in store:
        store["seeded_from_env"] = False
    if "removed" not in store or not isinstance(store["removed"], list):
        store["removed"] = []
    return store


def _ensure_named(store: dict[str, Any], keys: list[tuple[str, str, str]], label: str) -> bool:
    """Add known keys not already present and not explicitly removed.
    Idempotent union — never deletes or overwrites. Returns True if anything was added."""
    removed = set(store.get("removed", []))
    now = datetime.now(timezone.utc).isoformat()
    added = False
    for kind, ss58, note in keys:
        if ss58 in store["labels"] or ss58 in removed:
            continue
        store["labels"][ss58] = {
            "kind": kind,
            "label": label,
            "note": note,
            "added_at": now,
        }
        added = True
    return added


def _ensure_defaults(store: dict[str, Any]) -> bool:
    """Add known House and bot keys. Idempotent union — never deletes."""
    added = _ensure_named(store, DEFAULT_HOUSE_KEYS, HOUSE_LABEL)
    return _ensure_named(store, DEFAULT_BOT_KEYS, BOT_LABEL) or added


def _load() -> dict[str, Any]:
    return _normalise_store(load_json(WALLET_LABELS_STORE, _empty_store()))


def _save(store: dict[str, Any]) -> None:
    save_json(WALLET_LABELS_STORE, store)


def _split_env_list(name: str) -> list[str]:
    raw = os.environ.get(name) or ""
    return [p.strip() for p in raw.replace("\n", ",").split(",") if p.strip()]


def _seed_from_env(store: dict[str, Any]) -> bool:
    """One-shot env seed on first run. Returns True if anything was added."""
    if store.get("seeded_from_env"):
        return False
    added = False
    now = datetime.now(timezone.utc).isoformat()
    for ss58 in _split_env_list("HOUSE_COLDKEYS"):
        if ss58 not in store["labels"]:
            store["labels"][ss58] = {
                "kind": "coldkey",
                "label": HOUSE_LABEL,
                "note": "seeded from HOUSE_COLDKEYS",
                "added_at": now,
            }
            added = True
    for ss58 in _split_env_list("HOUSE_HOTKEYS"):
        if ss58 not in store["labels"]:
            store["labels"][ss58] = {
                "kind": "hotkey",
                "label": HOUSE_LABEL,
                "note": "seeded from HOUSE_HOTKEYS",
                "added_at": now,
            }
            added = True
    store["seeded_from_env"] = True
    return added


def load_labels() -> dict[str, Any]:
    """Load store and apply env seed once."""
    with _lock:
        store = _load()
        changed = _seed_from_env(store)
        if changed:
            logger.info("wallet_labels seeded from env (HOUSE_COLDKEYS/HOUSE_HOTKEYS)")
        changed = _ensure_defaults(store) or changed
        if changed or not WALLET_LABELS_STORE.exists():
            _save(store)
        return store


def list_labels() -> list[dict[str, Any]]:
    store = load_labels()
    out = []
    for ss58, meta in sorted(store["labels"].items()):
        out.append({"ss58": ss58, **meta})
    return out


def set_label(ss58: str, kind: str, note: str | None = None) -> dict[str, Any]:
    if not ss58:
        raise ValueError("ss58 is required")
    if kind not in VALID_KINDS:
        raise ValueError(f"kind must be one of {sorted(VALID_KINDS)}")
    with _lock:
        store = _load()
        _seed_from_env(store)
        store["labels"][ss58] = {
            "kind": kind,
            "label": HOUSE_LABEL,
            "note": (note or "").strip() or None,
            "added_at": datetime.now(timezone.utc).isoformat(),
        }
        if ss58 in store["removed"]:
            store["removed"].remove(ss58)
        _save(store)
        return {"ss58": ss58, **store["labels"][ss58]}


def remove_label(ss58: str) -> bool:
    with _lock:
        store = _load()
        _seed_from_env(store)
        existed = ss58 in store["labels"]
        if existed:
            del store["labels"][ss58]
        # Record removal so a default in-house key isn't re-added on next load.
        if ss58 not in store["removed"]:
            store["removed"].append(ss58)
        _save(store)
        return existed


def _labeled(label: str) -> set[str]:
    store = load_labels()
    return {
        ss58 for ss58, meta in store["labels"].items()
        if meta.get("label", HOUSE_LABEL) == label
    }


def house_set() -> set[str]:
    """Keys labeled house. Bot keys in the same file are excluded."""
    return _labeled(HOUSE_LABEL)


def bot_set() -> set[str]:
    return _labeled(BOT_LABEL)


def is_house(coldkey: str | None = None, hotkey: str | None = None,
             house: set[str] | None = None) -> bool:
    """A UID is House if either its coldkey or hotkey is labeled house."""
    s = house if house is not None else house_set()
    if coldkey and coldkey in s:
        return True
    if hotkey and hotkey in s:
        return True
    return False


def auto_label_owner_hotkey(hotkey: str | None) -> bool:
    """Mark the SN21 owner hotkey as House on first sight (idempotent)."""
    if not hotkey:
        return False
    with _lock:
        store = _load()
        _seed_from_env(store)
        if hotkey in store["labels"]:
            return False
        store["labels"][hotkey] = {
            "kind": "hotkey",
            "label": HOUSE_LABEL,
            "note": "auto-labeled (is_owner_hotkey=true on metagraph)",
            "added_at": datetime.now(timezone.utc).isoformat(),
        }
        _save(store)
        logger.info("auto-labeled owner hotkey as House: %s", hotkey)
        return True
