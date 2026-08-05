"""
Mechanism PR watcher — assisted authoring.

Polls the opentensor/subtensor GitHub repo for new releases (and, optionally,
emission-relevant PRs). When something new appears it:
  1. sends a Telegram notice (reusing the digest channel), and
  2. drafts a STUB mechanism file under lab/mechanisms/_drafts/.

The stub is never auto-registered or auto-run — a human reads the PR diff, writes
the real pure mechanism function, and promotes it into lab/mechanisms/. This is
the §4.0 "read the code, not the blog" gate in operational form: no money-modeling
code touches the lab unreviewed.

Env:
  SUBTENSOR_REPO     default "opentensor/subtensor"
  GITHUB_TOKEN       optional, raises the unauthenticated rate limit
  LAB_WATCH_DISABLED set to "1" to skip (e.g. in CI)
State:
  data/lab_watch_state.json  — last-seen release tag + drafted ids (idempotency)
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import requests

from collector import load_json, save_json
from config import DATA_DIR

logger = logging.getLogger(__name__)

# Org migrated opentensor -> RaoFoundation (PR #2834, 2026-07-07); GitHub
# redirects the old slug but poll the canonical one.
REPO = os.environ.get("SUBTENSOR_REPO", "RaoFoundation/subtensor")
WATCH_STATE = DATA_DIR / "lab_watch_state.json"
DRAFTS_DIR = Path(__file__).resolve().parent / "mechanisms" / "_drafts"
TIMEOUT = 30

# Open PRs whose title/body mention any of these are surfaced as "proposed" changes
# (the Consider-this lane) — emission-relevant only, to keep the watchlist signal-rich.
EMISSION_KEYWORDS = (
    "emission", "emissions", "tao_weight", "tao weight", "root_prop", "root prop",
    "burn", "incentive", "dynamic tao", "dtao", "subnet weight", "alpha", "yuma",
    "consensus", "owner cut", "owner_cut", "halving",
)


def _headers() -> dict:
    h = {"Accept": "application/vnd.github+json", "User-Agent": "SN21-Lab-Watcher/1.0"}
    tok = (os.environ.get("GITHUB_TOKEN") or "").strip()
    if tok:
        h["Authorization"] = f"Bearer {tok}"
    return h


def _latest_release() -> dict | None:
    """Most recent published release (tag + url + body). None on any failure."""
    try:
        r = requests.get(f"https://api.github.com/repos/{REPO}/releases?per_page=5",
                         headers=_headers(), timeout=TIMEOUT)
        r.raise_for_status()
        rels = r.json()
        return rels[0] if rels else None
    except Exception as e:  # noqa: BLE001
        logger.warning("GitHub release fetch failed: %s", e)
        return None


def _open_prs() -> list:
    """Open PRs (most-recently-updated first). Empty list on any failure."""
    try:
        r = requests.get(
            f"https://api.github.com/repos/{REPO}/pulls"
            "?state=open&per_page=50&sort=updated&direction=desc",
            headers=_headers(), timeout=TIMEOUT)
        r.raise_for_status()
        prs = r.json()
        return prs if isinstance(prs, list) else []
    except Exception as e:  # noqa: BLE001
        logger.warning("GitHub PR fetch failed: %s", e)
        return []


def _is_emission_pr(pr: dict) -> bool:
    text = ((pr.get("title") or "") + " " + (pr.get("body") or "")[:600]).lower()
    return any(k in text for k in EMISSION_KEYWORDS)


def _scan_proposed_prs(state: dict) -> tuple[list, list]:
    """Refresh the proposed-change watchlist from open emission-relevant PRs.

    Returns (all_current, fresh) where `fresh` are PRs not previously seen — these
    drive the Telegram notice. The watchlist is awareness-only ("Consider this"): it
    records the PR, it does not draft or run anything.
    """
    known = {p.get("number") for p in state.get("proposed_prs", []) if isinstance(p, dict)}
    current, fresh = [], []
    for pr in _open_prs():
        if not _is_emission_pr(pr):
            continue
        entry = {
            "number": pr.get("number"),
            "title": (pr.get("title") or "").strip(),
            "url": pr.get("html_url"),
            "updated_at": pr.get("updated_at"),
            "merged": False,
            "deploy_stage": "proposed",
            "stance": "Consider this",
        }
        current.append(entry)
        if entry["number"] not in known:
            fresh.append(entry)
    current.sort(key=lambda e: e.get("updated_at") or "", reverse=True)
    return current, fresh


def proposed_changes() -> list:
    """The current proposed-PR watchlist (Consider-this lane) from watch state."""
    state = load_json(WATCH_STATE, {})
    if not isinstance(state, dict):
        return []
    prs = state.get("proposed_prs", [])
    return prs if isinstance(prs, list) else []


def _slug(tag: str) -> str:
    """Turn a release tag into a python-safe mechanism module id."""
    s = re.sub(r"[^0-9a-zA-Z]+", "_", tag.strip().lower()).strip("_")
    return s or "unknown"


def _write_stub(tag: str, url: str) -> Path:
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    slug = _slug(tag)
    path = DRAFTS_DIR / f"{slug}.py"
    if path.exists():
        return path
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    path.write_text(f'''"""
DRAFT mechanism stub — auto-generated by lab/watcher.py on {stamp}
Release: {tag}
Source:  {url}

DO NOT TRUST until a human:
  1. reads the PR/source diff and confirms the exact emission_share formula
     (Action 1 / §4.0 — "read the code, not the blog"),
  2. fills in score() below,
  3. moves this file up to lab/mechanisms/ and adds the `register(...)` call,
  4. re-runs the reproduction gate.
Files in _drafts/ are NOT imported by lab/mechanisms/__init__.py.
"""

from __future__ import annotations


def score(sub: dict, state: dict) -> float:
    """Per-subnet emission score for release {tag}. SN21's share is this
    normalised across all subnets. FILL THIS IN from the source diff.

    Available per-subnet (see lab/chain_pull.py): alpha_in, tao_in, alpha_issued,
    spot_price, ema_price, alpha_out_emission, tao_in_emission, tempo.
    Global state: tao_weight, root_stake_tao, owner_cut, sn21_miner_burn.
    """
    raise NotImplementedError("Draft stub for {tag} — implement from source, then promote.")
''', encoding="utf-8")
    return path


def check_for_updates(notify: bool = True) -> dict:
    """Poll for a new subtensor release. On a new tag: draft a stub + (optionally)
    send a Telegram notice. Idempotent via data/lab_watch_state.json."""
    if (os.environ.get("LAB_WATCH_DISABLED") or "").strip() == "1":
        return {"checked": False, "reason": "disabled"}

    state = load_json(WATCH_STATE, {})
    if not isinstance(state, dict):
        state = {}
    seen = set(state.get("drafted_tags", []))
    last = state.get("last_seen_tag")

    # Refresh the proposed-change watchlist (Consider-this lane) on every poll.
    proposed, fresh_prs = _scan_proposed_prs(state)
    state["proposed_prs"] = proposed
    if fresh_prs:
        state["proposed_checked_utc"] = datetime.now(timezone.utc).isoformat()
        save_json(WATCH_STATE, state)
        if notify:
            lines = "\n".join(f"• #{p['number']} {p['title']}\n  {p['url']}" for p in fresh_prs[:5])
            try:
                from digest.channels import telegram as telegram_channel
                telegram_channel.send(
                    f"🧪 SN21 Lab — {len(fresh_prs)} new proposed emission PR(s) "
                    f"(Consider this — modelling not started):\n\n{lines}")
            except Exception as e:  # noqa: BLE001
                logger.warning("Lab watch proposed-PR notice failed: %s", e)

    rel = _latest_release()
    if not rel:
        save_json(WATCH_STATE, state)
        return {"checked": True, "new": False, "reason": "no release data",
                "proposed": len(proposed), "fresh_prs": len(fresh_prs)}

    tag = rel.get("tag_name") or rel.get("name") or "unknown"
    url = rel.get("html_url") or f"https://github.com/{REPO}/releases"
    if tag == last or tag in seen:
        save_json(WATCH_STATE, state)
        return {"checked": True, "new": False, "last_seen_tag": tag,
                "proposed": len(proposed), "fresh_prs": len(fresh_prs)}

    draft_path = _write_stub(tag, url)
    seen.add(tag)
    state.update({
        "last_seen_tag": tag,
        "last_checked_utc": datetime.now(timezone.utc).isoformat(),
        "drafted_tags": sorted(seen),
    })
    save_json(WATCH_STATE, state)

    msg = (
        f"🧪 SN21 Lab — new subtensor release detected\n\n"
        f"Release: {tag}\n{url}\n\n"
        f"A draft mechanism stub was written to lab/mechanisms/_drafts/{draft_path.name}. "
        f"It is NOT registered or run. Next: read the diff, implement score(), "
        f"promote into lab/mechanisms/, then re-run the reproduction gate before trusting "
        f"any projection."
    )
    sent = False
    if notify:
        try:
            from digest.channels import telegram as telegram_channel
            telegram_channel.send(msg)
            sent = True
        except Exception as e:  # noqa: BLE001
            logger.warning("Lab watch Telegram notice failed: %s", e)

    logger.info("Lab watch: new release %s -> draft %s (notified=%s)", tag, draft_path.name, sent)
    return {"checked": True, "new": True, "tag": tag, "draft": str(draft_path), "notified": sent,
            "proposed": len(proposed), "fresh_prs": len(fresh_prs)}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    print(check_for_updates(notify=False))
