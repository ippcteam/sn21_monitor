"""
Versioned results log for lab runs.

`data/lab_runs.json` is an append-only list of run records — each one a dated,
decision-grade artefact (which mechanism, on what chain state, did the
reproduction gate pass, and the S1..S5 results). Unlike the 90-day scan
histories these are NOT pruned: they are the historical record of "what each
proposed Bittensor change would have done to SN21", kept next to the live
metrics it predicted.

Run records are kept lean (globals + the SN21 row + per-mechanism denominators +
the computed scenarios) rather than all 128 subnet rows, so the log stays small
while remaining reproducible for SN21.
"""

from __future__ import annotations

from datetime import datetime, timezone

from collector import load_json, save_json
from config import DATA_DIR
from . import mechanisms as M

LAB_RUNS = DATA_DIR / "lab_runs.json"


def _load() -> list:
    data = load_json(LAB_RUNS, [])
    return data if isinstance(data, list) else []


def append_run(record: dict) -> dict:
    runs = _load()
    seq = len(runs) + 1
    block = record.get("block")
    record.setdefault("run_id", f"{block or 'na'}-{seq:04d}")
    record.setdefault("seq", seq)
    runs.append(record)
    save_json(LAB_RUNS, runs)
    return record


def list_runs(limit: int = 50) -> list:
    """Most-recent-first run summaries (no heavy scenario tables)."""
    runs = _load()
    out = []
    for r in reversed(runs[-limit:]):
        out.append({
            "run_id": r.get("run_id"),
            "seq": r.get("seq"),
            "fetched_at_utc": r.get("fetched_at_utc"),
            "block": r.get("block"),
            "mechanism_version": r.get("mechanism_version"),
            "trusted": r.get("trusted"),
            "reproduction": r.get("reproduction"),
            "headline": r.get("headline"),
        })
    return out


def get_run(run_id: str) -> dict | None:
    for r in _load():
        if r.get("run_id") == run_id:
            return r
    return None


def latest_run() -> dict | None:
    runs = _load()
    return runs[-1] if runs else None


def registry_meta() -> list:
    """Serializable view of the mechanism registry for the dashboard selector."""
    return [
        {
            "id": m.id,
            "label": m.label,
            "pr_url": m.pr_url,
            "activation_block": m.activation_block,
            "notes": m.notes,
        }
        for m in M.REGISTRY.values()
    ]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
