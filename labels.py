"""
Wallet labels — flag SN21 keys as "House" so dashboards can split House vs Other.

Storage: data/wallet_labels.json
  { "labels": { "<ss58>": { "kind": "coldkey"|"hotkey",
                            "label": "house",
                            "note": str | None,
                            "added_at": ISO-8601 UTC } },
    "seeded_from_env": bool }

Lookups always join coldkey OR hotkey: a UID is House if either ss58 is labeled.
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
VALID_KINDS = {"coldkey", "hotkey"}

_lock = threading.Lock()


def _empty_store() -> dict[str, Any]:
    return {"labels": {}, "seeded_from_env": False}


def _normalise_store(store: Any) -> dict[str, Any]:
    if not isinstance(store, dict):
        return _empty_store()
    if "labels" not in store or not isinstance(store["labels"], dict):
        store["labels"] = {}
    if "seeded_from_env" not in store:
        store["seeded_from_env"] = False
    return store


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
        if _seed_from_env(store):
            _save(store)
            logger.info("wallet_labels seeded from env (HOUSE_COLDKEYS/HOUSE_HOTKEYS)")
        elif not WALLET_LABELS_STORE.exists():
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
        _save(store)
        return {"ss58": ss58, **store["labels"][ss58]}


def remove_label(ss58: str) -> bool:
    with _lock:
        store = _load()
        _seed_from_env(store)
        existed = ss58 in store["labels"]
        if existed:
            del store["labels"][ss58]
            _save(store)
        return existed


def house_set() -> set[str]:
    store = load_labels()
    return {ss58 for ss58 in store["labels"]}


def is_house(coldkey: str | None = None, hotkey: str | None = None,
             house: set[str] | None = None) -> bool:
    """A UID is House if either its coldkey or hotkey is labeled."""
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
