"""
Monday.com GraphQL API v2 Client
=================================
Reusable client with rate limiting, pagination, and board fetching.
Used by fetch_monday.py for both full and incremental fetching.
"""

import logging
import time
import requests
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

MONDAY_API_URL = "https://api.monday.com/v2"
MONDAY_RATE_LIMIT = 55  # stay under 60 req/min
MONDAY_RATE_WINDOW = 60  # seconds

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

    def query(self, gql: str, variables: Optional[dict] = None,
              _retries: int = 0) -> Optional[dict]:
        """Execute a GraphQL query with rate limiting and retry."""
        self._rate_limit_wait()
        body: Dict[str, Any] = {"query": gql}
        if variables:
            body["variables"] = variables
        try:
            resp = self.session.post(MONDAY_API_URL, json=body, timeout=30)
            if resp.status_code == 429:
                if _retries >= 3:
                    logger.error("Monday.com rate-limited 3 times, giving up")
                    return None
                retry_after = int(resp.headers.get("Retry-After", 30))
                logger.warning(
                    f"Rate limited (429). Waiting {retry_after}s "
                    f"(retry {_retries + 1}/3)"
                )
                time.sleep(retry_after)
                return self.query(gql, variables, _retries + 1)
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
            gql = """
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
            data = self.query(gql, {"page": page})
            if not data or not data.get("boards"):
                break
            boards = data["boards"]
            all_boards.extend(boards)
            if len(boards) < 50:
                break
            page += 1
        logger.info(f"Fetched {len(all_boards)} boards")
        return all_boards

    @staticmethod
    def inject_column_titles(items: List[dict], columns: List[dict]):
        """Map column id -> title into each item's column_values."""
        col_map = {c.get("id"): c.get("title", "") for c in columns}
        for item in items:
            for cv in item.get("column_values", []):
                cv["title"] = col_map.get(cv.get("id"), cv.get("id", ""))
            for si in item.get("subitems", []):
                for cv in si.get("column_values", []):
                    cv["title"] = col_map.get(cv.get("id"), cv.get("id", ""))

    def fetch_board_items(self, board_id: str, board_name: str = "",
                          columns: Optional[List[dict]] = None) -> List[dict]:
        """Fetch all items from a board with cursor pagination."""
        logger.info(f"Fetching items for board {board_id} ({board_name})...")
        all_items = []
        cursor = None
        page = 0
        while True:
            page += 1
            if cursor:
                gql = f"""
                query ($cursor: String!) {{
                    next_items_page (cursor: $cursor, limit: 100) {{
                        cursor
                        items {{ {ITEM_FIELDS} }}
                    }}
                }}
                """
                data = self.query(gql, {"cursor": cursor})
                if not data or not data.get("next_items_page"):
                    break
                items = data["next_items_page"].get("items", [])
                cursor = data["next_items_page"].get("cursor")
            else:
                gql = f"""
                query ($boardId: [ID!]!) {{
                    boards (ids: $boardId) {{
                        items_page (limit: 100) {{
                            cursor
                            items {{ {ITEM_FIELDS} }}
                        }}
                    }}
                }}
                """
                data = self.query(gql, {"boardId": [str(board_id)]})
                if not data or not data.get("boards") or not data["boards"]:
                    break
                page_data = data["boards"][0].get("items_page", {})
                items = page_data.get("items", [])
                cursor = page_data.get("cursor")
            all_items.extend(items)
            if not cursor or len(items) == 0:
                break
        if columns:
            self.inject_column_titles(all_items, columns)
        logger.info(f"Fetched {len(all_items)} items from board {board_id}")
        return all_items

    def fetch_activity_logs(self, board_id: str) -> List[dict]:
        """Fetch activity logs for a board."""
        gql = """
        query ($boardId: [ID!]!) {
            boards (ids: $boardId) {
                activity_logs (limit: 100) {
                    id event data created_at user_id
                }
            }
        }
        """
        data = self.query(gql, {"boardId": [str(board_id)]})
        if not data or not data.get("boards") or not data["boards"]:
            return []
        logs = data["boards"][0].get("activity_logs", [])
        logger.debug(f"Board {board_id}: {len(logs)} activity log entries")
        return logs

    def check_board_activity(self, board_id: str, since_iso: str) -> bool:
        """Quick check if a board has any activity since a timestamp.

        Returns True if there is recent activity (needs re-fetch),
        False if dormant (cache is still valid).
        """
        gql = """
        query ($boardId: [ID!]!) {
            boards (ids: $boardId) {
                activity_logs (limit: 1) {
                    created_at
                }
            }
        }
        """
        data = self.query(gql, {"boardId": [str(board_id)]})
        if not data or not data.get("boards") or not data["boards"]:
            return True  # Assume active if we can't check
        logs = data["boards"][0].get("activity_logs", [])
        if not logs:
            return False  # No activity at all
        return logs[0].get("created_at", "") >= since_iso

    def fetch_users(self) -> List[dict]:
        """Fetch all users in the account."""
        logger.info("Fetching users...")
        gql = """
        query {
            users {
                id name email title
                is_admin is_guest enabled
                photo_thumb_small
            }
        }
        """
        data = self.query(gql)
        if not data or not data.get("users"):
            return []
        users = data["users"]
        logger.info(f"Fetched {len(users)} users")
        return users
