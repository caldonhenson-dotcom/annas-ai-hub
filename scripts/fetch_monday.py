"""
Monday.com Data Fetcher — Incremental Sync
============================================

Default mode: incremental — checks each board for recent activity before
re-fetching items. Dormant boards use cached data (no API calls).
First run is always a full fetch.

Caching:
    - Per-board cache in data/cache/board_<id>.json
    - Activity check: 1 API call per board to detect changes
    - Dormant boards skip items fetch entirely
    - Use --force-refresh to bypass cache and re-fetch everything

Usage:
    python scripts/fetch_monday.py                    # incremental
    python scripts/fetch_monday.py --force-refresh    # full re-fetch
    python scripts/fetch_monday.py --cache-hours 12   # custom TTL
"""

import argparse
import json
import os
import sys
import time
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent.parent
RAW_DIR = BASE_DIR / "data" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR = BASE_DIR / "data" / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_CACHE_HOURS = 24  # Increased from 4h — boards rarely change hourly

sys.path.insert(0, str(BASE_DIR))
from scripts.lib.monday_client import MondayClient
from scripts.lib.sync_state import save_sync_state


# ---------- Cache helpers ----------------------------------------------------

def _cache_path(board_id: str) -> Path:
    return CACHE_DIR / f"board_{board_id}.json"


def _cache_read(path: Path) -> Optional[dict]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _cache_is_fresh(path: Path, max_age_hours: float) -> bool:
    if not path.exists():
        return False
    try:
        with open(path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        cached_at = datetime.fromisoformat(meta.get("cached_at", ""))
        age_hours = (datetime.now(timezone.utc) - cached_at).total_seconds() / 3600
        return age_hours < max_age_hours
    except Exception:
        return False


def _cache_get_timestamp(path: Path) -> Optional[str]:
    """Get the ISO timestamp when this cache was written."""
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        return meta.get("cached_at")
    except Exception:
        return None


def _cache_write(path: Path, board_id: str, board_name: str,
                 items: list, activity_logs: list):
    payload = {
        "cached_at": datetime.now(timezone.utc).isoformat(),
        "board_id": board_id,
        "board_name": board_name,
        "items": items,
        "activity_logs": activity_logs,
    }
    tmp = path.with_suffix(".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, default=str)
        os.replace(str(tmp), str(path))
    except Exception as e:
        logger.warning(f"Cache write failed for board {board_id}: {e}")
        if tmp.exists():
            tmp.unlink()


# ---------- Raw-file writer --------------------------------------------------

def _write_raw(name: str, date_stamp: str, data: Any):
    payload = {
        "source": "monday",
        "object_type": name.replace("monday_", ""),
        "captured_at": date_stamp,
        "record_count": len(data) if isinstance(data, list) else None,
        "results": data,
    }
    out_path = RAW_DIR / f"{name}_{date_stamp}.json"
    tmp_path = out_path.with_suffix(".tmp")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, default=str)
        os.replace(str(tmp_path), str(out_path))
        count = len(data) if isinstance(data, list) else "N/A"
        logger.info(f"Saved {name}: {count} records -> {out_path}")
    except Exception as e:
        logger.error(f"Failed to write {name}: {e}")
        if tmp_path.exists():
            tmp_path.unlink()


# ---------- Main orchestration -----------------------------------------------

def fetch_monday(force_refresh: bool = False,
                 cache_hours: float = DEFAULT_CACHE_HOURS):
    """Fetch Monday.com data with incremental activity-based caching.

    For each board:
      1. If cache exists and is fresh (< cache_hours) -> use cache
      2. If cache exists but stale -> check activity_logs for changes
      3. If no recent activity -> use cache (board is dormant)
      4. If recent activity or no cache -> full fetch board items + logs
    """
    api_key = os.getenv("MONDAY_API_KEY")
    if not api_key:
        logger.warning("Missing MONDAY_API_KEY environment variable")
        return

    logger.info("Starting Monday.com data extraction")
    mode = "FULL" if force_refresh else "INCREMENTAL"
    logger.info(f"Mode: {mode} | Cache TTL: {cache_hours}h")

    client = MondayClient(api_key)
    date_stamp = time.strftime("%Y-%m-%d")

    # 1. Users (always — cheap, 1 API call)
    users = client.fetch_users()
    _write_raw("monday_users", date_stamp, users)

    # 2. Boards metadata (always — ~15 API calls)
    boards = client.fetch_boards()
    _write_raw("monday_boards", date_stamp, boards)

    # 3. Items per board — incremental with activity check
    all_board_items: Dict[str, dict] = {}
    cached_count = 0
    dormant_count = 0
    fetched_count = 0
    skipped_count = 0

    for board in boards:
        board_id = board.get("id")
        board_name = board.get("name", "")

        if board.get("state") != "active":
            skipped_count += 1
            continue

        cp = _cache_path(board_id)

        # Fresh cache? Use it directly
        if not force_refresh and _cache_is_fresh(cp, cache_hours):
            cached_data = _cache_read(cp)
            if cached_data:
                all_board_items[str(board_id)] = {
                    "board_id": board_id,
                    "board_name": board_name,
                    "items": cached_data.get("items", []),
                    "activity_logs": cached_data.get("activity_logs", []),
                }
                cached_count += 1
                continue

        # Stale cache? Check if board has activity since cache time
        if not force_refresh and cp.exists():
            cache_ts = _cache_get_timestamp(cp)
            if cache_ts and not client.check_board_activity(board_id, cache_ts):
                cached_data = _cache_read(cp)
                if cached_data:
                    all_board_items[str(board_id)] = {
                        "board_id": board_id,
                        "board_name": board_name,
                        "items": cached_data.get("items", []),
                        "activity_logs": cached_data.get("activity_logs", []),
                    }
                    dormant_count += 1
                    continue

        # Need to fetch: cache miss, stale with activity, or force refresh
        columns = board.get("columns", [])
        items = client.fetch_board_items(board_id, board_name, columns=columns)
        logs = client.fetch_activity_logs(board_id) if items else []

        all_board_items[str(board_id)] = {
            "board_id": board_id,
            "board_name": board_name,
            "items": items,
            "activity_logs": logs,
        }
        _cache_write(cp, board_id, board_name, items, logs)
        fetched_count += 1

    logger.info(
        f"Board items: {fetched_count} fetched, {cached_count} cached (fresh), "
        f"{dormant_count} cached (dormant), {skipped_count} skipped (inactive)"
    )

    _write_raw("monday_items", date_stamp, all_board_items)
    save_sync_state("monday", {"last_sync_ms": int(time.time() * 1000)})
    logger.info("Monday.com extraction complete")


# ---------- CLI --------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch Monday.com data")
    parser.add_argument(
        "--force-refresh", action="store_true",
        help="Bypass cache and re-fetch everything from the API",
    )
    parser.add_argument(
        "--cache-hours", type=float, default=DEFAULT_CACHE_HOURS,
        help=f"Cache TTL in hours (default {DEFAULT_CACHE_HOURS})",
    )
    args = parser.parse_args()
    try:
        fetch_monday(
            force_refresh=args.force_refresh,
            cache_hours=args.cache_hours,
        )
    except Exception as e:
        logger.error(f"Monday.com extraction failed: {e}", exc_info=True)
        sys.exit(1)
