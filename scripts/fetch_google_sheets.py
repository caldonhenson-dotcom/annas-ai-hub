"""
Google Sheets Data Fetcher
============================

Connects to the Google Sheets API via a service account to pull spreadsheet
data from all sheets shared with the service account.

Auto-discovers sheets (no hardcoded IDs), reads every tab, and writes raw
JSON to data/raw/gsheets_*.json.

Handles rate limiting (Google Sheets API: 60 req/min per user) and supports
per-sheet caching with a configurable TTL (default 1 hour).

Credentials:
    - GOOGLE_SERVICE_ACCOUNT_JSON  (path to the service-account key file)
    - OR inline: GOOGLE_SERVICE_ACCOUNT_EMAIL + GOOGLE_PRIVATE_KEY

Caching:
    Raw data is cached with a configurable TTL (default 1 hour).
    - Sheet list: always re-fetched (fast, single API call)
    - Tab data per sheet: cached individually, only re-fetched if stale
    - Use --force-refresh to bypass the cache entirely
    - Use --cache-hours N to set cache TTL (default 1)
    - Use --sheet-id SHEET_ID to fetch a specific sheet only

Usage:
    python scripts/fetch_google_sheets.py                        # uses cache
    python scripts/fetch_google_sheets.py --force-refresh        # full re-fetch
    python scripts/fetch_google_sheets.py --cache-hours 4        # 4-hour TTL
    python scripts/fetch_google_sheets.py --sheet-id ABC123      # single sheet
"""

import argparse
import json
import os
import sys
import time
import logging
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

GSHEETS_RATE_LIMIT = 55  # stay under 60 req/min
GSHEETS_RATE_WINDOW = 60  # seconds
DEFAULT_CACHE_HOURS = 1

# Google API scopes required
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.metadata.readonly",
]


# ---------------------------------------------------------------------------
# Credential helpers
# ---------------------------------------------------------------------------

def _build_credentials():
    """Build Google service-account credentials from env vars.

    Supports two modes:
      1. GOOGLE_SERVICE_ACCOUNT_JSON — path to the key JSON file
      2. GOOGLE_SERVICE_ACCOUNT_EMAIL + GOOGLE_PRIVATE_KEY — inline creds
    """
    from google.oauth2 import service_account

    json_path = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if json_path:
        path = Path(json_path)
        if not path.exists():
            logger.error(f"Service account JSON file not found: {json_path}")
            return None
        logger.info(f"Loading credentials from {json_path}")
        return service_account.Credentials.from_service_account_file(
            str(path), scopes=SCOPES,
        )

    email = os.getenv("GOOGLE_SERVICE_ACCOUNT_EMAIL", "").strip()
    private_key = os.getenv("GOOGLE_PRIVATE_KEY", "").strip()
    if email and private_key:
        # Handle escaped newlines from .env files
        private_key = private_key.replace("\\n", "\n")
        info = {
            "type": "service_account",
            "client_email": email,
            "token_uri": "https://oauth2.googleapis.com/token",
            "private_key": private_key,
        }
        logger.info(f"Loading inline credentials for {email}")
        return service_account.Credentials.from_service_account_info(
            info, scopes=SCOPES,
        )

    logger.warning(
        "No Google credentials found. Set GOOGLE_SERVICE_ACCOUNT_JSON "
        "or GOOGLE_SERVICE_ACCOUNT_EMAIL + GOOGLE_PRIVATE_KEY in .env"
    )
    return None


# ---------------------------------------------------------------------------
# Google Sheets Client
# ---------------------------------------------------------------------------

class GoogleSheetsClient:
    """Google Sheets + Drive API client with rate limiting."""

    def __init__(self, credentials):
        from googleapiclient.discovery import build

        self.sheets_service = build("sheets", "v4", credentials=credentials)
        self.drive_service = build("drive", "v3", credentials=credentials)
        self._request_timestamps: List[float] = []

    def _rate_limit_wait(self):
        now = time.time()
        self._request_timestamps = [
            t for t in self._request_timestamps if now - t < GSHEETS_RATE_WINDOW
        ]
        if len(self._request_timestamps) >= GSHEETS_RATE_LIMIT:
            sleep_time = GSHEETS_RATE_WINDOW - (now - self._request_timestamps[0]) + 0.5
            logger.debug(f"Rate limit approaching, sleeping {sleep_time:.1f}s")
            time.sleep(sleep_time)
        self._request_timestamps.append(time.time())

    def _execute_with_retry(self, request, description: str = "API request"):
        """Execute a Google API request with rate limiting and retry on 429."""
        self._rate_limit_wait()
        try:
            return request.execute()
        except Exception as e:
            error_str = str(e)
            # Handle rate-limit (429) errors
            if "429" in error_str or "RATE_LIMIT" in error_str.upper():
                logger.warning(f"Rate limited on {description}. Waiting 60s")
                time.sleep(60)
                return self._execute_with_retry(request, description)
            logger.error(f"{description} failed: {e}")
            return None

    def discover_sheets(self) -> List[dict]:
        """Auto-discover all Google Sheets shared with the service account.

        Uses the Drive API to list all spreadsheet files the service account
        can access. No hardcoded sheet IDs required.
        """
        logger.info("Discovering sheets shared with service account...")
        all_files: List[dict] = []
        page_token: Optional[str] = None

        while True:
            request = self.drive_service.files().list(
                q="mimeType='application/vnd.google-apps.spreadsheet'",
                fields="nextPageToken, files(id, name, modifiedTime, owners, shared)",
                pageSize=100,
                pageToken=page_token,
                orderBy="modifiedTime desc",
            )
            result = self._execute_with_retry(request, "Drive files.list")
            if not result:
                break

            files = result.get("files", [])
            all_files.extend(files)
            logger.debug(f"Found {len(files)} sheets (total: {len(all_files)})")

            page_token = result.get("nextPageToken")
            if not page_token:
                break

        logger.info(f"Discovered {len(all_files)} sheets")
        return all_files

    def fetch_sheet_metadata(self, sheet_id: str) -> Optional[dict]:
        """Fetch spreadsheet metadata (title, tabs/sheets info)."""
        request = self.sheets_service.spreadsheets().get(
            spreadsheetId=sheet_id,
            fields="spreadsheetId,properties.title,sheets.properties",
        )
        return self._execute_with_retry(request, f"spreadsheets.get({sheet_id})")

    def fetch_tab_data(self, sheet_id: str, tab_name: str) -> Optional[List[List[str]]]:
        """Fetch all data from a single tab/sheet within a spreadsheet."""
        request = self.sheets_service.spreadsheets().values().get(
            spreadsheetId=sheet_id,
            range=f"'{tab_name}'",
            valueRenderOption="FORMATTED_VALUE",
            dateTimeRenderOption="FORMATTED_STRING",
        )
        result = self._execute_with_retry(
            request, f"values.get({sheet_id}, {tab_name})",
        )
        if not result:
            return None
        return result.get("values", [])

    def fetch_full_sheet(self, sheet_id: str, sheet_name: str = "") -> Optional[dict]:
        """Fetch all tabs and data from a single spreadsheet.

        Returns a dict matching the output format:
          {
            "sheet_id": "...",
            "sheet_name": "...",
            "tabs": [ { "tab_name": ..., "headers": [...], "rows": [...], "row_count": N } ]
          }
        """
        display = sheet_name or sheet_id
        logger.info(f"Fetching sheet: {display} ({sheet_id})")

        metadata = self.fetch_sheet_metadata(sheet_id)
        if not metadata:
            logger.warning(f"Could not fetch metadata for sheet {sheet_id}")
            return None

        title = metadata.get("properties", {}).get("title", sheet_name or sheet_id)
        tab_properties = [
            s.get("properties", {})
            for s in metadata.get("sheets", [])
        ]

        tabs: List[dict] = []
        for tab_prop in tab_properties:
            tab_name = tab_prop.get("title", "Sheet1")
            tab_hidden = tab_prop.get("hidden", False)
            if tab_hidden:
                logger.debug(f"Skipping hidden tab: {tab_name}")
                continue

            raw_values = self.fetch_tab_data(sheet_id, tab_name)
            if not raw_values or len(raw_values) == 0:
                tabs.append({
                    "tab_name": tab_name,
                    "headers": [],
                    "rows": [],
                    "row_count": 0,
                })
                continue

            headers = raw_values[0]
            rows: List[dict] = []
            for row_values in raw_values[1:]:
                # Pad short rows with empty strings
                padded = row_values + [""] * (len(headers) - len(row_values))
                row_dict = {
                    headers[i]: padded[i] if i < len(padded) else ""
                    for i in range(len(headers))
                }
                rows.append(row_dict)

            tabs.append({
                "tab_name": tab_name,
                "headers": headers,
                "rows": rows,
                "row_count": len(rows),
            })
            logger.debug(
                f"  Tab '{tab_name}': {len(headers)} columns, {len(rows)} rows"
            )

        logger.info(
            f"Fetched {len(tabs)} tabs from '{title}' "
            f"({sum(t['row_count'] for t in tabs)} total rows)"
        )
        return {
            "sheet_id": sheet_id,
            "sheet_name": title,
            "tabs": tabs,
        }


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def _cache_path(sheet_id: str) -> Path:
    """Return the cache file path for a single sheet's data."""
    return CACHE_DIR / f"gsheet_{sheet_id}.json"


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
    """Read a cached sheet payload. Returns None on any error."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _cache_write(path: Path, sheet_data: dict):
    """Write a sheet's data to the cache."""
    payload = {
        "cached_at": datetime.now(timezone.utc).isoformat(),
        **sheet_data,
    }
    tmp = path.with_suffix(".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, default=str)
        os.replace(str(tmp), str(path))
    except Exception as e:
        logger.warning(f"Cache write failed for sheet {sheet_data.get('sheet_id')}: {e}")
        if tmp.exists():
            tmp.unlink()


# ---------------------------------------------------------------------------
# Raw-file writer (final output)
# ---------------------------------------------------------------------------

def _write_raw(sheet_data: dict, date_stamp: str):
    """Write a single sheet's data to data/raw/gsheets_<id>_<date>.json."""
    sheet_id = sheet_data.get("sheet_id", "unknown")
    payload = {
        "source": "google_sheets",
        "captured_at": date_stamp,
        "sheet_id": sheet_data.get("sheet_id"),
        "sheet_name": sheet_data.get("sheet_name"),
        "tabs": sheet_data.get("tabs", []),
    }
    out_path = RAW_DIR / f"gsheets_{sheet_id}_{date_stamp}.json"
    tmp_path = out_path.with_suffix(".tmp")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, default=str)
        os.replace(str(tmp_path), str(out_path))
        tab_count = len(sheet_data.get("tabs", []))
        row_count = sum(t.get("row_count", 0) for t in sheet_data.get("tabs", []))
        logger.info(
            f"Saved gsheets_{sheet_id}: {tab_count} tabs, "
            f"{row_count} rows -> {out_path}"
        )
    except Exception as e:
        logger.error(f"Failed to write gsheets_{sheet_id}: {e}")
        if tmp_path.exists():
            tmp_path.unlink()


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------

def fetch_google_sheets(
    force_refresh: bool = False,
    cache_hours: float = DEFAULT_CACHE_HOURS,
    sheet_id_filter: Optional[str] = None,
):
    """Main entry: fetch Google Sheets data and write to raw JSON files.

    Uses per-sheet caching to avoid re-fetching sheets whose data
    hasn't expired.  Pass *force_refresh=True* to bypass the cache.
    Optionally pass *sheet_id_filter* to only fetch a specific sheet.
    """
    creds = _build_credentials()
    if not creds:
        logger.warning("Cannot proceed without valid Google credentials")
        return

    logger.info("Starting Google Sheets data extraction")
    if force_refresh:
        logger.info("Force-refresh enabled -- ignoring cache")
    else:
        logger.info(f"Cache TTL: {cache_hours} hours")

    client = GoogleSheetsClient(creds)
    date_stamp = time.strftime("%Y-%m-%d")

    # 1. Discover sheets (or use the single sheet-id filter)
    if sheet_id_filter:
        logger.info(f"Fetching single sheet: {sheet_id_filter}")
        discovered = [{"id": sheet_id_filter, "name": ""}]
    else:
        discovered = client.discover_sheets()

    if not discovered:
        logger.warning("No sheets found. Ensure sheets are shared with the service account.")
        return

    # 2. Fetch each sheet — use cache where possible
    cached_count = 0
    fetched_count = 0
    error_count = 0

    for file_info in discovered:
        sid = file_info.get("id", "")
        sname = file_info.get("name", "")
        cp = _cache_path(sid)

        # Try cache first
        if not force_refresh and _cache_is_fresh(cp, cache_hours):
            cached_data = _cache_read(cp)
            if cached_data:
                # Write to raw from cache (so raw files always reflect latest run)
                sheet_payload = {
                    "sheet_id": cached_data.get("sheet_id", sid),
                    "sheet_name": cached_data.get("sheet_name", sname),
                    "tabs": cached_data.get("tabs", []),
                }
                _write_raw(sheet_payload, date_stamp)
                cached_count += 1
                continue

        # Cache miss / stale — fetch from API
        sheet_data = client.fetch_full_sheet(sid, sname)
        if not sheet_data:
            error_count += 1
            continue

        _write_raw(sheet_data, date_stamp)

        # Write to per-sheet cache
        _cache_write(cp, sheet_data)
        fetched_count += 1

    logger.info(
        f"Sheets: {fetched_count} fetched, {cached_count} from cache, "
        f"{error_count} errors"
    )
    logger.info("Google Sheets extraction complete")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args():
    parser = argparse.ArgumentParser(description="Fetch Google Sheets data")
    parser.add_argument(
        "--force-refresh", action="store_true",
        help="Bypass cache and re-fetch everything from the API",
    )
    parser.add_argument(
        "--cache-hours", type=float, default=DEFAULT_CACHE_HOURS,
        help=f"Cache TTL in hours (default {DEFAULT_CACHE_HOURS})",
    )
    parser.add_argument(
        "--sheet-id", type=str, default=None,
        help="Fetch a specific sheet by ID instead of auto-discovering all",
    )
    return parser.parse_args()


if __name__ == "__main__":
    try:
        args = _parse_args()
        fetch_google_sheets(
            force_refresh=args.force_refresh,
            cache_hours=args.cache_hours,
            sheet_id_filter=args.sheet_id,
        )
    except Exception as e:
        logger.error(f"Google Sheets extraction failed: {e}", exc_info=True)
        sys.exit(1)
