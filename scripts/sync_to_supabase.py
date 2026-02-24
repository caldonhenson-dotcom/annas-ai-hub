"""
Supabase Sync Script
====================
Uploads processed metrics JSON files to Supabase Storage so the
dashboard can fetch live data via public URLs.

Usage:
    python scripts/sync_to_supabase.py              # sync all sources
    python scripts/sync_to_supabase.py --source hubspot_sales
    python scripts/sync_to_supabase.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Dict

import requests
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("sync_to_supabase")

# ---------------------------------------------------------------------------
# Supabase config
# ---------------------------------------------------------------------------
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")

BUCKET = "dashboard-data"

# Map of storage filename → local processed JSON file
SOURCES: Dict[str, Path] = {
    "hubspot_sales_metrics.json": BASE_DIR / "data" / "processed" / "hubspot_sales_metrics.json",
    "monday_metrics.json":        BASE_DIR / "data" / "processed" / "monday_metrics.json",
    "inbound_queue.json":         BASE_DIR / "data" / "processed" / "inbound_queue.json",
    "email_actions.json":         BASE_DIR / "data" / "processed" / "email_actions.json",
    "weekly_summary.json":        BASE_DIR / "data" / "processed" / "weekly_summary.json",
}


def _get_key() -> str:
    """Return the best available Supabase key."""
    key = SUPABASE_SERVICE_KEY or SUPABASE_ANON_KEY
    if not SUPABASE_URL or not key:
        logger.error("Missing SUPABASE_URL or SUPABASE_SERVICE_KEY in .env")
        sys.exit(1)
    return key


def _ensure_bucket(key: str) -> None:
    """Create the storage bucket if it doesn't exist."""
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    r = requests.get(f"{SUPABASE_URL}/storage/v1/bucket/{BUCKET}",
                     headers=headers, timeout=10)
    if r.status_code == 404:
        logger.info("Creating storage bucket '%s'...", BUCKET)
        r2 = requests.post(f"{SUPABASE_URL}/storage/v1/bucket",
                           headers=headers,
                           json={"id": BUCKET, "name": BUCKET, "public": True},
                           timeout=10)
        r2.raise_for_status()
        logger.info("Bucket created.")
    elif r.status_code == 200:
        logger.info("Bucket '%s' exists.", BUCKET)
    else:
        r.raise_for_status()


def sync_file(key: str, filename: str, local_path: Path) -> bool:
    """Upload a single JSON file to Supabase Storage."""
    if not local_path.exists():
        logger.warning("File not found, skipping: %s", local_path)
        return False

    with open(local_path, "rb") as f:
        data = f.read()

    r = requests.post(
        f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/{filename}",
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "x-upsert": "true",
        },
        data=data,
        timeout=30,
    )

    if r.status_code in (200, 201):
        size_kb = len(data) / 1024
        logger.info("Uploaded %s (%.0f KB)", filename, size_kb)
        return True

    logger.error("Failed to upload %s: %s %s", filename, r.status_code, r.text[:200])
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync metrics to Supabase Storage")
    parser.add_argument("--source", choices=[
        p.stem for p in SOURCES.values()
    ], help="Sync only files matching this stem (e.g. hubspot_sales_metrics)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be synced without uploading")
    args = parser.parse_args()

    logger.info("=== Supabase Storage Sync ===")
    logger.info("URL: %s", SUPABASE_URL)
    logger.info("Bucket: %s", BUCKET)

    if args.dry_run:
        logger.info("DRY RUN — no changes will be made")
        for filename, path in SOURCES.items():
            exists = path.exists()
            size = path.stat().st_size / 1024 if exists else 0
            status = f"{size:.0f} KB" if exists else "MISSING"
            logger.info("  %s: %s", filename, status)
        return

    key = _get_key()
    _ensure_bucket(key)

    # Sync
    success = 0
    for filename, path in SOURCES.items():
        if args.source and path.stem != args.source:
            continue
        if sync_file(key, filename, path):
            success += 1

    total = len(SOURCES) if not args.source else 1
    logger.info("Synced %d/%d files", success, total)
    logger.info("Public URL pattern: %s/storage/v1/object/public/%s/<filename>",
                SUPABASE_URL, BUCKET)
    logger.info("=== Sync complete ===")


if __name__ == "__main__":
    main()
