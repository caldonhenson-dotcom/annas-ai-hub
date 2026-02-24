"""
Supabase Client Helper for Annas AI Hub.
Provides connection, snapshot management, and table query functions.

Usage:
    from scripts.lib.supabase_client import get_client, upsert_snapshot, query_table

    client = get_client()
    upsert_snapshot("hubspot_sales", data)
    rows = query_table("deals", filters={"stage": "Proposal Shared"}, limit=50)
"""
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

from scripts.lib.logger import setup_logger

logger = setup_logger(__name__)

# Load .env from project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = (
    os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    or os.environ.get("SUPABASE_KEY", "")
)

_client = None


def get_client():
    """Create and return a Supabase client (singleton)."""
    global _client
    if _client is not None:
        return _client

    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in .env"
        )

    from supabase import create_client
    _client = create_client(SUPABASE_URL, SUPABASE_KEY)
    logger.info("Supabase client connected to %s", SUPABASE_URL)
    return _client


def upsert_snapshot(source: str, data: Dict) -> bool:
    """
    Insert a new dashboard snapshot for a given source.

    Args:
        source: Source identifier (e.g. "hubspot_sales", "monday").
        data: Full processed metrics dict.

    Returns:
        True on success, False on failure.
    """
    try:
        client = get_client()
        row = {
            "source": source,
            "data": data,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        client.table("dashboard_snapshots").insert(row).execute()
        logger.info("Snapshot inserted for source: %s", source)
        return True
    except Exception as e:
        logger.error("Supabase snapshot insert failed for %s: %s", source, e)
        return False


def get_latest_snapshot(source: str) -> Optional[Dict]:
    """
    Fetch the latest snapshot for a source.

    Args:
        source: Source identifier.

    Returns:
        The data dict from the latest snapshot, or None.
    """
    try:
        client = get_client()
        result = (
            client.table("dashboard_snapshots")
            .select("data, generated_at")
            .eq("source", source)
            .order("generated_at", desc=True)
            .limit(1)
            .execute()
        )
        if result.data:
            return result.data[0].get("data")
        return None
    except Exception as e:
        logger.error("Supabase fetch failed for %s: %s", source, e)
        return None


def query_table(
    table: str,
    select: str = "*",
    filters: Dict[str, Any] = None,
    order_by: str = None,
    desc: bool = True,
    limit: int = 100,
    offset: int = 0,
) -> List[Dict]:
    """
    Query a Supabase table with optional filters, ordering, and pagination.

    Args:
        table: Table name.
        select: Columns to select (default "*").
        filters: Dict of column=value equality filters.
        order_by: Column to order by.
        desc: Descending order (default True).
        limit: Max rows to return.
        offset: Rows to skip.

    Returns:
        List of row dicts.
    """
    try:
        client = get_client()
        query = client.table(table).select(select)

        if filters:
            for col, val in filters.items():
                query = query.eq(col, val)

        if order_by:
            query = query.order(order_by, desc=desc)

        query = query.range(offset, offset + limit - 1)
        result = query.execute()
        return result.data or []
    except Exception as e:
        logger.error("Supabase query failed on %s: %s", table, e)
        return []


def execute_sql(sql: str, params: dict = None) -> Optional[List[Dict]]:
    """
    Execute raw SQL via Supabase RPC (requires a Postgres function or direct connection).
    Used by the AI query engine for text-to-SQL.

    Args:
        sql: SQL query string.
        params: Optional parameters.

    Returns:
        List of row dicts, or None on error.
    """
    try:
        client = get_client()
        result = client.rpc("execute_readonly_query", {"query_text": sql}).execute()
        return result.data
    except Exception as e:
        logger.error("SQL execution failed: %s", e)
        return None


def upsert_row(table: str, row: Dict, on_conflict: str = None) -> bool:
    """
    Upsert a single row into a table.

    Args:
        table: Table name.
        row: Dict of column=value pairs.
        on_conflict: Conflict resolution column(s) for upsert.

    Returns:
        True on success, False on failure.
    """
    try:
        client = get_client()
        query = client.table(table)
        if on_conflict:
            query.upsert(row, on_conflict=on_conflict).execute()
        else:
            query.insert(row).execute()
        return True
    except Exception as e:
        logger.error("Supabase upsert failed on %s: %s", table, e)
        return False


def upsert_rows(table: str, rows: List[Dict], on_conflict: str = None) -> bool:
    """
    Upsert multiple rows into a table.

    Args:
        table: Table name.
        rows: List of row dicts.
        on_conflict: Conflict resolution column(s).

    Returns:
        True on success, False on failure.
    """
    if not rows:
        return True

    try:
        client = get_client()
        query = client.table(table)
        if on_conflict:
            query.upsert(rows, on_conflict=on_conflict).execute()
        else:
            query.insert(rows).execute()
        logger.info("Upserted %d rows into %s", len(rows), table)
        return True
    except Exception as e:
        logger.error("Supabase bulk upsert failed on %s: %s", table, e)
        return False


def update_data_freshness(source: str, record_count: int, status: str = "ok") -> bool:
    """Update the data_freshness table after a successful fetch."""
    return upsert_row(
        "data_freshness",
        {
            "source": source,
            "last_fetch_at": datetime.now(timezone.utc).isoformat(),
            "record_count": record_count,
            "status": status,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
        on_conflict="source",
    )
