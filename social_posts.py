"""
Social posts — thin read-only client for our X Listen service (ippcteam/map_listen_x).

X Listen tracks our own managed X accounts and samples each post's metrics every 15 min
(view_count, likes, replies, reposts, quotes). We reuse its open read endpoints here so the
dashboard's Social tab can show how our own posts are performing as the data backfills.

Read endpoints only (no auth needed; only mutations on X Listen require its admin key):
  GET /api/influence/dashboard                          — managed accounts (id, handle, followers, score)
  GET /api/influence/managed-accounts/{id}/posts        — that account's posts + latest metrics

Config: X_LISTEN_BASE_URL (default the live Render service).
"""

from __future__ import annotations

import json
import logging
import os
import urllib.request
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

BASE_URL = os.environ.get("X_LISTEN_BASE_URL", "https://map-listen-x.onrender.com").rstrip("/")
_TIMEOUT = int(os.environ.get("X_LISTEN_TIMEOUT", "30"))


def _get(path: str) -> Any:
    url = f"{BASE_URL}{path}"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
        return json.load(r)


def own_posts() -> dict[str, Any]:
    """Merge every managed account's posts into one list (newest first), tagged with the
    account handle. Degrades to an error payload the UI can render if X Listen is unreachable."""
    try:
        dash = _get("/api/influence/dashboard")
    except Exception as e:
        logger.warning("X Listen dashboard unavailable: %s", e)
        return {"error": f"X Listen unreachable: {e}", "base_url": BASE_URL, "accounts": [], "posts": []}

    accounts = [
        {
            "id": a.get("managed_account_id"),
            "handle": a.get("handle"),
            "profile_url": a.get("profile_url"),
            "followers_count": a.get("followers_count"),
            "influence_score": a.get("influence_score"),
        }
        for a in (dash.get("accounts") or [])
    ]

    posts: list[dict[str, Any]] = []
    for acct in accounts:
        if acct["id"] is None:
            continue
        try:
            data = _get(f"/api/influence/managed-accounts/{acct['id']}/posts")
        except Exception as e:
            logger.warning("X Listen posts for account %s failed: %s", acct["id"], e)
            continue
        for p in data.get("posts") or []:
            posts.append({**p, "handle": acct["handle"], "managed_account_id": acct["id"]})

    posts.sort(key=lambda p: p.get("published_at") or "", reverse=True)
    return {
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "base_url": BASE_URL,
        "accounts": accounts,
        "posts": posts,
    }
