"""
Incremental Sync State
======================
Tracks last-sync timestamps per source so fetch scripts only pull
records modified since the previous successful run.

State files: data/cache/<source>_sync_state.json
"""

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CACHE_DIR = BASE_DIR / "data" / "cache"
RAW_DIR = BASE_DIR / "data" / "raw"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _state_path(source: str) -> Path:
    return CACHE_DIR / f"{source}_sync_state.json"


def load_sync_state(source: str) -> dict:
    """Load sync state for a source. Returns empty dict if none exists."""
    path = _state_path(source)
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_sync_state(source: str, state: dict):
    """Save sync state for a source."""
    path = _state_path(source)
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    tmp = path.with_suffix(".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, default=str)
        import os
        os.replace(str(tmp), str(path))
    except Exception as e:
        logger.warning(f"Failed to save sync state for {source}: {e}")
        if tmp.exists():
            tmp.unlink()


def get_last_sync_ms(source: str) -> Optional[int]:
    """Get last sync timestamp in milliseconds (for HubSpot filters).

    Returns None if no previous sync exists.
    """
    state = load_sync_state(source)
    return state.get("last_sync_ms")


def load_cached_records(source: str, object_type: str) -> List[dict]:
    """Load the most recent raw data file for a source/object type.

    Returns the 'results' list from the raw JSON file.
    """
    import glob as g
    pattern = str(RAW_DIR / f"{source}_{object_type}_*.json")
    files = sorted(g.glob(pattern))
    if not files:
        return []
    try:
        with open(files[-1], "r", encoding="utf-8") as f:
            data = json.load(f)
        results = data.get("results", [])
        if isinstance(results, list):
            return results
        return []
    except Exception as e:
        logger.warning(f"Failed to load cached {source}_{object_type}: {e}")
        return []


def merge_records(existing: List[dict], updated: List[dict]) -> List[dict]:
    """Merge updated records into existing dataset by ID.

    Updated records replace existing ones with the same ID.
    New records (not in existing) are appended.
    """
    index: Dict[str, dict] = {}
    for r in existing:
        rid = str(r.get("id", ""))
        if rid:
            index[rid] = r
    new_count = 0
    updated_count = 0
    for r in updated:
        rid = str(r.get("id", ""))
        if rid:
            if rid in index:
                updated_count += 1
            else:
                new_count += 1
            index[rid] = r
    if updated:
        logger.info(
            f"Merged {len(updated)} records: "
            f"{updated_count} updated, {new_count} new "
            f"(total: {len(index)})"
        )
    return list(index.values())
