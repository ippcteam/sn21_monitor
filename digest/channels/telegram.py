"""
Telegram bot channel. Sends a single text message via Bot API.

Env:
  TELEGRAM_BOT_TOKEN  — from @BotFather (e.g. "8123456789:AAH8...")
  TELEGRAM_CHAT_ID    — your numeric chat id (from /getUpdates)

Plain-text mode by default — no parse_mode escaping concerns. Telegram caps
single messages at 4096 chars; the orchestrator truncates before we get here.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import requests

logger = logging.getLogger(__name__)

API_BASE = "https://api.telegram.org"
TIMEOUT = 30


def _config() -> tuple[str, str]:
    token = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    chat_id = (os.environ.get("TELEGRAM_CHAT_ID") or "").strip()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN not set")
    if not chat_id:
        raise RuntimeError("TELEGRAM_CHAT_ID not set")
    return token, chat_id


def send(text: str) -> dict[str, Any]:
    """POST sendMessage. Returns the parsed JSON result on 2xx."""
    token, chat_id = _config()
    url = f"{API_BASE}/bot{token}/sendMessage"
    # disable_web_page_preview keeps any URLs from blowing up the message
    payload = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
    }
    r = requests.post(url, data=payload, timeout=TIMEOUT)
    if r.status_code >= 300:
        # Body is short JSON, safe to log.
        logger.warning("Telegram sendMessage non-2xx: %s %s", r.status_code, r.text[:300])
        r.raise_for_status()
    body = r.json()
    if not body.get("ok"):
        raise RuntimeError(f"Telegram sendMessage ok=false: {body!r}")
    result = body.get("result") or {}
    return {
        "ok": True,
        "message_id": result.get("message_id"),
        "chat_id": (result.get("chat") or {}).get("id"),
        "date": result.get("date"),
    }
