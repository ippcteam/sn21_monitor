"""
Shared paths for JSON logs. Prefer /data (Render disk); fall back to ./data if /data is not writable.
"""

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


def _try_use_dir(path: Path) -> Path | None:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".sn21_write_probe"
        probe.write_text("", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return path.resolve()
    except (OSError, PermissionError):
        return None


def resolve_data_dir() -> Path:
    candidates: list[Path] = []
    if env := os.environ.get("SN21_DATA_DIR"):
        candidates.append(Path(env))
    candidates.append(Path("/data"))
    candidates.append(Path(__file__).resolve().parent / "data")

    for p in candidates:
        got = _try_use_dir(p)
        if got is not None:
            if got.name == "data" and got.parent == Path(__file__).resolve().parent:
                logger.warning(
                    "Using repo-local %s — attach a Render disk at /data for persistence across deploys",
                    got,
                )
            return got

    raise RuntimeError(
        "No writable data directory; set SN21_DATA_DIR or attach a disk at /data on Render"
    )


DATA_DIR = resolve_data_dir()
DAILY_LOG = DATA_DIR / "daily_log.json"
OWNER_LEDGER = DATA_DIR / "owner_ledger.json"
