"""
Digest orchestrator. One `DigestConfig` per registered digest; `run_digest`
executes the source → composer → channel pipeline with idempotency on date.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from collector import load_json, save_json
from config import DATA_DIR

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DigestConfig:
    kind: str                                 # short id, e.g. "sn21_daily"
    gather: Callable[[], dict[str, Any]]      # returns DigestInputs
    prompt_path: Path                         # path to prompt template (markdown)
    channel_send: Callable[[str], dict[str, Any]]  # ships text; returns sender result
    schedule_cron: tuple[int, int]            # (hour, minute) UTC
    state_filename: str                       # under DATA_DIR
    title: str                                # short human label for fallback header
    archive_filename: str | None = None       # under DATA_DIR; per-digest history
    archive_retention_days: int = 30          # cap on archive length

    @property
    def state_path(self) -> Path:
        return DATA_DIR / self.state_filename

    @property
    def archive_path(self) -> Path | None:
        if not self.archive_filename:
            return None
        return DATA_DIR / self.archive_filename


def _load_state(path: Path) -> dict[str, Any]:
    s = load_json(path, {})
    return s if isinstance(s, dict) else {}


def _save_state(path: Path, state: dict[str, Any]) -> None:
    save_json(path, state)


def _read_prompt(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.warning("Digest prompt missing at %s — using empty template", path)
        return ""


def _load_archive(path: Path | None) -> list[dict[str, Any]]:
    """Returns the archive list (each item: {date, composer, text}); empty if missing."""
    if path is None:
        return []
    arr = load_json(path, [])
    if not isinstance(arr, list):
        return []
    return arr


def _append_archive(path: Path | None, entry: dict[str, Any], retention_days: int) -> None:
    """Replace any prior entry for the same date; cap to retention_days."""
    if path is None:
        return
    archive = _load_archive(path)
    archive = [e for e in archive if isinstance(e, dict) and e.get("date") != entry.get("date")]
    archive.append(entry)
    archive.sort(key=lambda e: e.get("date") or "")
    if len(archive) > retention_days:
        archive = archive[-retention_days:]
    save_json(path, archive)


def run_digest(cfg: DigestConfig, *, force: bool = False, dry_run: bool = False) -> dict[str, Any]:
    """
    Execute one digest.

    - force=True bypasses the same-day idempotency guard.
    - dry_run=True composes but does NOT send and does NOT update state.
      (Used by /api/digest/preview.)
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    state = _load_state(cfg.state_path)

    if not force and not dry_run and state.get("last_sent_date") == today:
        logger.info("Digest %s already sent today (%s); skipping", cfg.kind, today)
        return {"skipped": True, "reason": "already_sent_today", "date": today, "kind": cfg.kind}

    if os.environ.get("DIGEST_ENABLED", "true").lower() in ("0", "false", "no", "off"):
        logger.info("Digest %s disabled via DIGEST_ENABLED", cfg.kind)
        return {"skipped": True, "reason": "disabled_via_env", "kind": cfg.kind}

    # 1. Gather inputs.
    try:
        inputs = cfg.gather()
    except Exception as e:
        logger.exception("Digest %s gather() failed", cfg.kind)
        return {"skipped": True, "reason": "gather_failed", "error": str(e), "kind": cfg.kind}

    # 2. Compose. Try LLM first; fall back to deterministic on any failure.
    from .composers import llm as llm_composer
    from .composers import fallback as fallback_composer

    prompt_text = _read_prompt(cfg.prompt_path)
    # Memory: last N digests as continuity context. Exclude any entry for today
    # (force=True re-runs would otherwise let the model reference its own prior
    # output for the same date, which is confusing).
    prior = [e for e in _load_archive(cfg.archive_path) if e.get("date") != today]

    composer_used = "llm"
    try:
        text = llm_composer.compose(
            inputs=inputs,
            prompt_template=prompt_text,
            title=cfg.title,
            prior_digests=prior,
        )
        if not text or not text.strip():
            raise RuntimeError("LLM composer returned empty text")
    except Exception as e:
        logger.warning("Digest %s LLM composer failed (%s); using fallback", cfg.kind, e)
        composer_used = "fallback"
        text = fallback_composer.compose(
            inputs=inputs, title=cfg.title, prior_digests=prior,
        )
        text = "[fallback]\n" + text

    # Telegram message cap is 4096 chars; hard-truncate with marker.
    text = _truncate(text, 3900)

    if dry_run:
        return {
            "skipped": False,
            "dry_run": True,
            "kind": cfg.kind,
            "date": today,
            "composer": composer_used,
            "text": text,
            "input_keys": sorted(list(inputs.keys())),
        }

    # 3. Send.
    try:
        send_result = cfg.channel_send(text)
    except Exception as e:
        logger.exception("Digest %s channel_send failed", cfg.kind)
        return {
            "skipped": False,
            "sent": False,
            "kind": cfg.kind,
            "date": today,
            "composer": composer_used,
            "error": str(e),
        }

    # 4. Persist state and append to the archive for future memory.
    state.update(
        last_sent_date=today,
        last_sent_at_utc=datetime.now(timezone.utc).isoformat(),
        last_composer=composer_used,
        last_channel_result=send_result,
    )
    _save_state(cfg.state_path, state)
    _append_archive(
        cfg.archive_path,
        {
            "date": today,
            "composer": composer_used,
            "text": text,
            "sent_at_utc": datetime.now(timezone.utc).isoformat(),
        },
        retention_days=cfg.archive_retention_days,
    )

    logger.info("Digest %s sent (%s composer); %d chars", cfg.kind, composer_used, len(text))
    return {
        "skipped": False,
        "sent": True,
        "kind": cfg.kind,
        "date": today,
        "composer": composer_used,
        "chars": len(text),
        "channel_result": send_result,
    }


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 24].rstrip() + "\n…\n[truncated]"


# Registered digests — populated lazily by importers to avoid circular imports.
REGISTERED_DIGESTS: list[DigestConfig] = []
