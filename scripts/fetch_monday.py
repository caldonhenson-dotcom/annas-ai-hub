"""
Monday.com Data Fetcher
========================

Connects to Monday.com GraphQL API v2 to pull board data for M&A project
tracking and IC (Investment Committee) scorecard progressions.

Handles pagination, rate limiting (60 req/min), and writes raw JSON to
data/raw/monday_*.json.

Caching:
    Raw data is cached with a configurable TTL (default 4 hours).
    - Boards metadata: always re-fetched (fast, ~15 API calls)
    - Items per board: cached individually, only re-fetched if stale
    - Use --force-refresh to bypass the cache entirely
    - Use --cache-hours N to set cache TTL (default 4)

Usage:
    python scripts/fetch_monday.py                    # uses cache
    python scripts/fetch_monday.py --force-refresh    # full re-fetch
    python scripts/fetch_monday.py --cache-hours 12   # 12-hour TTL
"""

import argparse
import json
import os
import sys
import time
import logging
import requests
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

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

MONDAY_API_URL = "https://api.monday.com/v2"
MONDAY_RATE_LIMIT = 55  # stay under 60 req/min
MONDAY_RATE_WINDOW = 60  # seconds
DEFAULT_CACHE_HOURS = 4

# GraphQL fragment for item fields (no 'title' on column_values - removed in 2024-10 API)
ITEM_FIELDS = """
    id
    name
    state
    created_at
    updated_at
    group { id title }
    column_values { id type text value }
    subitems {
        id name state
        column_values { id type text value }
    }
    updates (limit: 5) {
        id body created_at
        creator { id name }
    }
"""


class MondayClient:
    """Monday.com GraphQL API v2 client with pagination and rate limiting."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "Authorization": api_key,
            "API-Version": "2024-10",
        })
        self._request_timestamps: List[float] = []

    def _rate_limit_wait(self):
        now = time.time()
        self._request_timestamps = [
            t for t in self._request_timestamps if now - t < MONDAY_RATE_WINDOW
        ]
        if len(self._request_timestamps) >= MONDAY_RATE_LIMIT:
            sleep_time = MONDAY_RATE_WINDOW - (now - self._request_timestamps[0]) + 0.5
            logger.debug(f"Rate limit approaching, sleeping {sleep_time:.1f}s")
            time.sleep(sleep_time)
        self._request_timestamps.append(time.time())

    def _query(self, query: str, variables: Optional[dict] = None) -> Optional[dict]:
        self._rate_limit_wait()
        body: Dict[str, Any] = {"query": query}
        if variables:
            body["variables"] = variables
        try:
            resp = self.session.post(MONDAY_API_URL, json=body, timeout=30)
            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", 30))
                logger.warning(f"Rate limited (429). Waiting {retry_after}s")
                time.sleep(retry_after)
                return self._query(query, variables)
            resp.raise_for_status()
            data = resp.json()
            if "errors" in data:
                logger.error(f"GraphQL errors: {data['errors']}")
                return None
            return data.get("data")
        except requests.RequestException as e:
            logger.error(f"Monday.com API request failed: {e}")
            return None

    def fetch_boards(self) -> List[dict]:
        """Fetch all boards with basic info."""
        logger.info("Fetching boards...")
        all_boards = []
        page = 1
        while True:
            query = """
            query ($page: Int!) {
                boards (page: $page, limit: 50) {
                    id name description state board_kind
                    workspace { id name }
                    columns { id title type settings_str }
                    groups { id title color }
                    owners { id name email }
                }
            }
            """
            data = self._query(query, {"page": page})
            if not data or not data.get("boards"):
                break
            boards = data["boards"]
            all_boards.extend(boards)
            logger.debug(f"Page {page}: {len(boards)} boards (total: {len(all_boards)})")
            if len(boards) < 50:
                break
            page += 1
        logger.info(f"Fetched {len(all_boards)} boards")
        return all_boards

    @staticmethod
    def _inject_column_titles(items: List[dict], columns: List[dict]) -> List[dict]:
        """Map column id -> title from board definition into each item's column_values."""
        col_map = {c.get("id"): c.get("title", c.get("id", "")) for c in columns}
        for item in items:
            for cv in item.get("column_values", []):
                cv["title"] = col_map.get(cv.get("id"), cv.get("id", ""))
            for si in item.get("subitems", []):
                for cv in si.get("column_values", []):
                    cv["title"] = col_map.get(cv.get("id"), cv.get("id", ""))
        return items

    def fetch_board_items(self, board_id: str, board_name: str = "",
                          columns: Optional[List[dict]] = None) -> List[dict]:
        """Fetch all items from a board with column values, using cursor pagination."""
        logger.info(f"Fetching items for board {board_id} ({board_name})...")
        all_items = []
        cursor = None
        page = 0

        while True:
            page += 1
            if cursor:
                query = f"""
                query ($cursor: String!) {{
                    next_items_page (cursor: $cursor, limit: 100) {{
                        cursor
                        items {{ {ITEM_FIELDS} }}
                    }}
                }}
                """
                data = self._query(query, {"cursor": cursor})
                if not data or not data.get("next_items_page"):
                    break
                items = data["next_items_page"].get("items", [])
                cursor = data["next_items_page"].get("cursor")
            else:
                query = f"""
                query ($boardId: [ID!]!) {{
                    boards (ids: $boardId) {{
                        items_page (limit: 100) {{
                            cursor
                            items {{ {ITEM_FIELDS} }}
                        }}
                    }}
                }}
                """
                data = self._query(query, {"boardId": [str(board_id)]})
                if not data or not data.get("boards") or not data["boards"]:
                    break
                page_data = data["boards"][0].get("items_page", {})
                items = page_data.get("items", [])
                cursor = page_data.get("cursor")

            all_items.extend(items)
            logger.debug(f"Page {page}: {len(items)} items (total: {len(all_items)})")

            if not cursor or len(items) == 0:
                break

        # Inject column titles from board definition
        if columns:
            self._inject_column_titles(all_items, columns)

        logger.info(f"Fetched {len(all_items)} items from board {board_id}")
        return all_items

    def fetch_activity_logs(self, board_id: str) -> List[dict]:
        """Fetch activity logs for a board (status changes, updates)."""
        logger.info(f"Fetching activity logs for board {board_id}...")
        query = """
        query ($boardId: [ID!]!) {
            boards (ids: $boardId) {
                activity_logs (limit: 100) {
                    id event data created_at user_id
                }
            }
        }
        """
        data = self._query(query, {"boardId": [str(board_id)]})
        if not data or not data.get("boards") or not data["boards"]:
            return []
        logs = data["boards"][0].get("activity_logs", [])
        logger.info(f"Fetched {len(logs)} activity log entries")
        return logs

    def fetch_users(self) -> List[dict]:
        """Fetch all users in the account."""
        logger.info("Fetching users...")
        query = """
        query {
            users {
                id name email title
                is_admin is_guest enabled
                photo_thumb_small
            }
        }
        """
        data = self._query(query)
        if not data or not data.get("users"):
            return []
        users = data["users"]
        logger.info(f"Fetched {len(users)} users")
        return users


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def _cache_path(board_id: str) -> Path:
    """Return the cache file path for a single board's items + activity logs."""
    return CACHE_DIR / f"board_{board_id}.json"


def _cache_is_fresh(path: Path, max_age_hours: float) -> bool:
    """Check whether a cache file exists and is younger than *max_age_hours*."""
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


def _cache_read(path: Path) -> Optional[dict]:
    """Read a cached board payload. Returns None on any error."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _cache_write(path: Path, board_id: str, board_name: str,
                 items: list, activity_logs: list):
    """Write a board's items + activity logs to the cache."""
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


# ---------------------------------------------------------------------------
# Raw-file writer (final output)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------

def fetch_monday(force_refresh: bool = False, cache_hours: float = DEFAULT_CACHE_HOURS):
    """Main entry: fetch all Monday.com data and write to raw JSON files.

    Uses per-board caching to avoid re-fetching boards whose data
    hasn't expired.  Pass *force_refresh=True* to bypass the cache.
    """
    api_key = os.getenv("MONDAY_API_KEY")
    if not api_key:
        logger.warning("Missing MONDAY_API_KEY environment variable")
        return

    logger.info("Starting Monday.com data extraction")
    if force_refresh:
        logger.info("Force-refresh enabled – ignoring cache")
    else:
        logger.info(f"Cache TTL: {cache_hours} hours")

    client = MondayClient(api_key)
    date_stamp = time.strftime("%Y-%m-%d")

    # 1. Users (always re-fetch – cheap, single API call)
    users = client.fetch_users()
    _write_raw("monday_users", date_stamp, users)

    # 2. Boards metadata (always re-fetch – ~15 API calls)
    boards = client.fetch_boards()
    _write_raw("monday_boards", date_stamp, boards)

    # 3. Items per board – use cache where possible
    all_board_items: Dict[str, dict] = {}
    cached_count = 0
    fetched_count = 0
    skipped_count = 0

    # Filter: skip "Subitems of" boards (child views, not real boards)
    # and inactive boards
    for board in boards:
        board_id = board.get("id")
        board_name = board.get("name", "")

        if board.get("state") != "active":
            skipped_count += 1
            continue

        cp = _cache_path(board_id)

        # Try cache first
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

        # Cache miss / stale – fetch from API
        columns = board.get("columns", [])
        items = client.fetch_board_items(board_id, board_name, columns=columns)
        logs = client.fetch_activity_logs(board_id) if items else []

        all_board_items[str(board_id)] = {
            "board_id": board_id,
            "board_name": board_name,
            "items": items,
            "activity_logs": logs,
        }

        # Write to per-board cache
        _cache_write(cp, board_id, board_name, items, logs)
        fetched_count += 1

    logger.info(
        f"Board items: {fetched_count} fetched, {cached_count} from cache, "
        f"{skipped_count} skipped (inactive)"
    )

    _write_raw("monday_items", date_stamp, all_board_items)
    logger.info("Monday.com extraction complete")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args():
    parser = argparse.ArgumentParser(description="Fetch Monday.com data")
    parser.add_argument(
        "--force-refresh", action="store_true",
        help="Bypass cache and re-fetch everything from the API",
    )
    parser.add_argument(
        "--cache-hours", type=float, default=DEFAULT_CACHE_HOURS,
        help=f"Cache TTL in hours (default {DEFAULT_CACHE_HOURS})",
    )
    return parser.parse_args()


if __name__ == "__main__":
    try:
        args = _parse_args()
        fetch_monday(
            force_refresh=args.force_refresh,
            cache_hours=args.cache_hours,
        )
    except Exception as e:
        logger.error(f"Monday.com extraction failed: {e}", exc_info=True)
        sys.exit(1)
