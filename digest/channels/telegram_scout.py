"""
Scout-channel Telegram sender. Mirrors digest.channels.telegram but reads its
bot token and chat id from `TELEGRAM_SCOUT_*` env vars so the Scout digest can
post to a different channel than the SN21 daily.

Env:
  TELEGRAM_SCOUT_BOT_TOKEN  — bot token for the Scout channel
  TELEGRAM_SCOUT_CHAT_ID    — chat id for the Scout channel
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
    token = (os.environ.get("TELEGRAM_SCOUT_BOT_TOKEN") or "").strip()
    chat_id = (os.environ.get("TELEGRAM_SCOUT_CHAT_ID") or "").strip()
    if not token:
        raise RuntimeError("TELEGRAM_SCOUT_BOT_TOKEN not set")
    if not chat_id:
        raise RuntimeError("TELEGRAM_SCOUT_CHAT_ID not set")
    return token, chat_id


def send(text: str) -> dict[str, Any]:
    """POST sendMessage to the Scout channel."""
    token, chat_id = _config()
    url = f"{API_BASE}/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
    }
    r = requests.post(url, data=payload, timeout=TIMEOUT)
    if r.status_code >= 300:
        logger.warning("Scout Telegram non-2xx: %s %s", r.status_code, r.text[:300])
        r.raise_for_status()
    body = r.json()
    if not body.get("ok"):
        raise RuntimeError(f"Scout Telegram ok=false: {body!r}")
    result = body.get("result") or {}
    return {
        "ok": True,
        "message_id": result.get("message_id"),
        "chat_id": (result.get("chat") or {}).get("id"),
        "date": result.get("date"),
    }
