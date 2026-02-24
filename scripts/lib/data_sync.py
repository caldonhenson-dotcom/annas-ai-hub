"""
Annas AI Hub — Data Sync Module
================================
Transforms raw JSON data from fetch scripts into normalised Supabase tables.
Called by analyzers after they write processed metrics.

Usage:
    from scripts.lib.data_sync import sync_hubspot_to_supabase, sync_monday_to_supabase

    sync_hubspot_to_supabase()   # reads latest raw files, upserts to normalised tables
    sync_monday_to_supabase()    # reads latest Monday raw files, upserts to tables
    refresh_views()              # refresh all materialised views
    compute_snapshot_diff("hubspot_sales")  # compare latest two snapshots
"""
from __future__ import annotations

import glob
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from scripts.lib.logger import setup_logger
from scripts.lib.supabase_client import (
    get_client,
    update_data_freshness,
    upsert_rows,
)

logger = setup_logger("data_sync")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

# Batch size for upserts (Supabase recommends ≤1000)
BATCH_SIZE = 500


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_latest_file(prefix: str) -> Optional[Path]:
    """Find the latest file matching a prefix in the raw data directory."""
    pattern = str(RAW_DIR / f"{prefix}_*.json")
    files = sorted(glob.glob(pattern), reverse=True)
    if files:
        return Path(files[0])
    return None


def _load_json(file_path: Path) -> Optional[Dict]:
    """Load JSON from a file path."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error("Failed to load %s: %s", file_path, e)
        return None


def _safe_float(val: Any) -> Optional[float]:
    """Convert a value to float, returning None on failure."""
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _safe_int(val: Any) -> Optional[int]:
    """Convert a value to int, returning None on failure."""
    if val is None or val == "":
        return None
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None


def _safe_bool(val: Any) -> bool:
    """Convert a value to boolean."""
    if val is None:
        return False
    if isinstance(val, bool):
        return val
    return str(val).lower() in ("true", "1", "yes")


def _safe_timestamp(val: Any) -> Optional[str]:
    """Convert a HubSpot timestamp (ms or ISO string) to ISO format."""
    if val is None or val == "":
        return None
    if isinstance(val, str):
        # Already ISO format
        if "T" in val or "-" in val:
            return val
        # Millisecond timestamp as string
        try:
            ts = int(val) / 1000
            return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
        except (ValueError, TypeError, OSError):
            return val
    if isinstance(val, (int, float)):
        try:
            ts = val / 1000 if val > 1e12 else val
            return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
        except (ValueError, TypeError, OSError):
            return None
    return None


def _safe_date(val: Any) -> Optional[str]:
    """Convert to date string (YYYY-MM-DD)."""
    if val is None or val == "":
        return None
    ts = _safe_timestamp(val)
    if ts:
        return ts[:10]
    return None


def _batched(items: list, size: int = BATCH_SIZE):
    """Yield successive batches from a list."""
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _upsert_batched(table: str, rows: List[Dict], on_conflict: str) -> int:
    """Upsert rows in batches. Returns count of successfully upserted rows."""
    if not rows:
        return 0
    total = 0
    for batch in _batched(rows):
        if upsert_rows(table, batch, on_conflict=on_conflict):
            total += len(batch)
        else:
            logger.warning("Batch upsert failed for %s (%d rows)", table, len(batch))
    return total


# ---------------------------------------------------------------------------
# HubSpot transformers
# ---------------------------------------------------------------------------

def _transform_owners(raw: Dict) -> List[Dict]:
    """Transform raw owner records into normalised owner rows."""
    rows = []
    for record in raw.get("results", []):
        first = record.get("firstName", "")
        last = record.get("lastName", "")
        name = f"{first} {last}".strip() or record.get("email", "Unknown")
        rows.append({
            "id": str(record.get("id", "")),
            "name": name,
            "email": record.get("email"),
            "source": "hubspot",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        })
    return rows


def _transform_pipeline_stages(raw: Dict) -> List[Dict]:
    """Transform raw pipeline data into normalised stage rows."""
    rows = []
    for pipeline in raw.get("results", []):
        pipeline_id = str(pipeline.get("id", ""))
        for stage in pipeline.get("stages", []):
            rows.append({
                "id": str(stage.get("id", "")),
                "pipeline_id": pipeline_id,
                "label": stage.get("label", ""),
                "display_order": _safe_int(stage.get("displayOrder")),
                "probability": _safe_float(stage.get("metadata", {}).get("probability")),
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            })
    return rows


def _transform_deals(raw: Dict, owners_map: Dict[str, str], stages_map: Dict[str, str]) -> List[Dict]:
    """Transform raw deal records into normalised deal rows."""
    rows = []
    for record in raw.get("results", []):
        props = record.get("properties", {})
        deal_id = str(record.get("id", ""))
        owner_id = props.get("hubspot_owner_id")
        stage_id = props.get("dealstage", "")

        amount = _safe_float(props.get("amount"))
        probability = _safe_int(props.get("hs_deal_stage_probability"))
        weighted = round(amount * (probability / 100), 2) if amount and probability else None

        rows.append({
            "id": deal_id,
            "name": props.get("dealname"),
            "stage": stage_id,
            "stage_label": stages_map.get(stage_id, stage_id),
            "pipeline": props.get("pipeline"),
            "amount": amount,
            "weighted_amount": weighted,
            "probability": probability,
            "owner_id": owner_id,
            "owner_name": owners_map.get(owner_id, "Unassigned"),
            "close_date": _safe_date(props.get("closedate")),
            "create_date": _safe_timestamp(props.get("createdate")),
            "last_modified": _safe_timestamp(record.get("updatedAt")),
            "is_closed_won": _safe_bool(props.get("hs_is_closed_won")),
            "is_closed": _safe_bool(props.get("hs_is_closed")),
            "source": props.get("hs_analytics_source"),
            "deal_type": props.get("dealtype"),
            "days_in_stage": None,  # computed separately if needed
            "closed_won_reason": props.get("closed_won_reason"),
            "closed_lost_reason": props.get("closed_lost_reason"),
            "forecast_amount": _safe_float(props.get("hs_forecast_amount")),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        })
    return rows


def _transform_contacts(raw: Dict, owners_map: Dict[str, str]) -> List[Dict]:
    """Transform raw contact records into normalised contact rows."""
    rows = []
    for record in raw.get("results", []):
        props = record.get("properties", {})
        owner_id = props.get("hubspot_owner_id")

        rows.append({
            "id": str(record.get("id", "")),
            "email": props.get("email"),
            "first_name": props.get("firstname"),
            "last_name": props.get("lastname"),
            "company": props.get("company"),
            "phone": props.get("phone"),
            "lifecycle_stage": props.get("lifecyclestage"),
            "lead_status": props.get("hs_lead_status"),
            "source": props.get("hs_analytics_source"),
            "owner_id": owner_id,
            "owner_name": owners_map.get(owner_id, "Unassigned"),
            "create_date": _safe_timestamp(props.get("createdate")),
            "last_modified": _safe_timestamp(record.get("updatedAt")),
            "page_views": _safe_int(props.get("hs_analytics_num_page_views")),
            "visits": _safe_int(props.get("hs_analytics_num_visits")),
            "first_conversion": props.get("first_conversion_event_name"),
            "recent_conversion": props.get("recent_conversion_event_name"),
            "num_deals": _safe_int(props.get("num_associated_deals")),
            "lead_date": _safe_timestamp(props.get("hs_lifecyclestage_lead_date")),
            "mql_date": _safe_timestamp(
                props.get("hs_lifecyclestage_marketingqualifiedlead_date")
            ),
            "sql_date": _safe_timestamp(
                props.get("hs_lifecyclestage_salesqualifiedlead_date")
            ),
            "opportunity_date": _safe_timestamp(
                props.get("hs_lifecyclestage_opportunity_date")
            ),
            "customer_date": _safe_timestamp(
                props.get("hs_lifecyclestage_customer_date")
            ),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        })
    return rows


def _transform_companies(raw: Dict) -> List[Dict]:
    """Transform raw company records into normalised company rows."""
    rows = []
    for record in raw.get("results", []):
        props = record.get("properties", {})

        rows.append({
            "id": str(record.get("id", "")),
            "name": props.get("name"),
            "domain": props.get("domain"),
            "industry": props.get("industry"),
            "annual_revenue": _safe_float(props.get("annualrevenue")),
            "num_employees": _safe_int(props.get("numberofemployees")),
            "lifecycle_stage": props.get("lifecyclestage"),
            "owner_id": props.get("hubspot_owner_id"),
            "create_date": _safe_timestamp(props.get("createdate")),
            "num_contacts": _safe_int(props.get("num_associated_contacts")),
            "num_deals": _safe_int(props.get("num_associated_deals")),
            "source": props.get("hs_analytics_source"),
            "total_revenue": _safe_float(props.get("total_revenue")),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        })
    return rows


def _transform_activities(
    calls_raw: Optional[Dict],
    emails_raw: Optional[Dict],
    meetings_raw: Optional[Dict],
    tasks_raw: Optional[Dict],
    notes_raw: Optional[Dict],
    owners_map: Dict[str, str],
) -> List[Dict]:
    """Transform all engagement types into unified activity rows."""
    rows = []
    now = datetime.now(timezone.utc).isoformat()

    # Calls
    if calls_raw:
        for record in calls_raw.get("results", []):
            props = record.get("properties", {})
            owner_id = props.get("hubspot_owner_id")
            rows.append({
                "id": str(record.get("id", "")),
                "type": "call",
                "owner_id": owner_id,
                "owner_name": owners_map.get(owner_id, "Unassigned"),
                "subject": props.get("hs_call_title"),
                "direction": props.get("hs_call_direction"),
                "status": props.get("hs_call_disposition"),
                "duration_ms": _safe_int(props.get("hs_call_duration")),
                "activity_date": _safe_timestamp(props.get("hs_timestamp")),
                "created_at": _safe_timestamp(record.get("createdAt")),
                "fetched_at": now,
            })

    # Emails
    if emails_raw:
        for record in emails_raw.get("results", []):
            props = record.get("properties", {})
            owner_id = props.get("hubspot_owner_id")
            rows.append({
                "id": str(record.get("id", "")),
                "type": "email",
                "owner_id": owner_id,
                "owner_name": owners_map.get(owner_id, "Unassigned"),
                "subject": props.get("hs_email_subject"),
                "direction": props.get("hs_email_direction"),
                "status": props.get("hs_email_status"),
                "duration_ms": None,
                "activity_date": _safe_timestamp(props.get("hs_timestamp")),
                "created_at": _safe_timestamp(record.get("createdAt")),
                "fetched_at": now,
            })

    # Meetings
    if meetings_raw:
        for record in meetings_raw.get("results", []):
            props = record.get("properties", {})
            owner_id = props.get("hubspot_owner_id")
            # Compute duration from start/end if available
            start = _safe_timestamp(props.get("hs_meeting_start_time"))
            end = _safe_timestamp(props.get("hs_meeting_end_time"))
            duration = None
            if start and end:
                try:
                    from datetime import datetime as dt
                    s = dt.fromisoformat(start.replace("Z", "+00:00"))
                    e = dt.fromisoformat(end.replace("Z", "+00:00"))
                    duration = int((e - s).total_seconds() * 1000)
                except Exception:
                    pass

            rows.append({
                "id": str(record.get("id", "")),
                "type": "meeting",
                "owner_id": owner_id,
                "owner_name": owners_map.get(owner_id, "Unassigned"),
                "subject": props.get("hs_meeting_title"),
                "direction": None,
                "status": props.get("hs_meeting_outcome"),
                "duration_ms": duration,
                "activity_date": _safe_timestamp(props.get("hs_timestamp")),
                "created_at": _safe_timestamp(record.get("createdAt")),
                "fetched_at": now,
            })

    # Tasks
    if tasks_raw:
        for record in tasks_raw.get("results", []):
            props = record.get("properties", {})
            owner_id = props.get("hubspot_owner_id")
            rows.append({
                "id": str(record.get("id", "")),
                "type": "task",
                "owner_id": owner_id,
                "owner_name": owners_map.get(owner_id, "Unassigned"),
                "subject": props.get("hs_task_subject"),
                "direction": None,
                "status": props.get("hs_task_status"),
                "duration_ms": None,
                "activity_date": _safe_timestamp(props.get("hs_timestamp")),
                "created_at": _safe_timestamp(record.get("createdAt")),
                "fetched_at": now,
            })

    # Notes
    if notes_raw:
        for record in notes_raw.get("results", []):
            props = record.get("properties", {})
            owner_id = props.get("hubspot_owner_id")
            body = props.get("hs_note_body", "")
            # Truncate for subject
            subject = body[:200] if body else None
            rows.append({
                "id": str(record.get("id", "")),
                "type": "note",
                "owner_id": owner_id,
                "owner_name": owners_map.get(owner_id, "Unassigned"),
                "subject": subject,
                "direction": None,
                "status": None,
                "duration_ms": None,
                "activity_date": _safe_timestamp(props.get("hs_timestamp")),
                "created_at": _safe_timestamp(record.get("createdAt")),
                "fetched_at": now,
            })

    return rows


def _transform_associations(raw: Dict) -> List[Dict]:
    """Transform raw association data into normalised association rows."""
    rows = []
    results = raw.get("results", {})

    mapping = {
        "contact_to_deal": ("contact", "deal"),
        "contact_to_company": ("contact", "company"),
        "deal_to_company": ("deal", "company"),
    }

    for key, (from_type, to_type) in mapping.items():
        assoc_data = results.get(key, {})
        for from_id, to_ids in assoc_data.items():
            if isinstance(to_ids, list):
                for to_id in to_ids:
                    rows.append({
                        "from_type": from_type,
                        "from_id": str(from_id),
                        "to_type": to_type,
                        "to_id": str(to_id),
                        "fetched_at": datetime.now(timezone.utc).isoformat(),
                    })
    return rows


# ---------------------------------------------------------------------------
# Monday.com transformers
# ---------------------------------------------------------------------------

def _transform_monday_boards(board_overview: Dict) -> List[Dict]:
    """Transform board overview into normalised board rows."""
    rows = []
    for ws in board_overview.get("workspaces", []):
        ws_id = ws.get("id", "")
        ws_name = ws.get("name", "")
        for board in ws.get("boards", []):
            rows.append({
                "id": str(board.get("id", "")),
                "name": board.get("name"),
                "workspace_id": str(ws_id),
                "workspace_name": ws_name,
                "state": "active",
                "board_kind": None,
                "item_count": _safe_int(board.get("item_count")),
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            })
    return rows


def _transform_monday_projects(ma_metrics: Dict) -> List[Dict]:
    """Transform M&A project data into normalised project rows."""
    rows = []
    for project in ma_metrics.get("projects", []):
        rows.append({
            "id": str(project.get("id", "")),
            "name": project.get("name"),
            "board_id": str(project.get("board_id", "")),
            "board_name": project.get("board"),
            "workspace": project.get("workspace"),
            "stage": project.get("stage"),
            "status": project.get("status"),
            "owner": project.get("owner", "Unassigned"),
            "value": _safe_float(project.get("value")),
            "target_close": _safe_date(project.get("target_close")),
            "is_active": project.get("is_active", True),
            "group_name": project.get("group"),
            "subitems_count": _safe_int(project.get("subitems_count", 0)),
            "subitems_complete": _safe_int(project.get("subitems_complete", 0)),
            "created_at": _safe_timestamp(project.get("created_at")),
            "updated_at": _safe_timestamp(project.get("updated_at")),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        })
    return rows


def _transform_monday_ic_scores(ic_metrics: Dict) -> List[Dict]:
    """Transform IC score items into normalised IC score rows."""
    rows = []
    for item in ic_metrics.get("items", []):
        rows.append({
            "id": str(item.get("name", "")) + "_" + str(item.get("board", "")),
            "item_name": item.get("name"),
            "board_name": item.get("board"),
            "workspace": item.get("workspace"),
            "total_score": _safe_float(item.get("total_score")),
            "avg_score": _safe_float(item.get("avg_score")),
            "status": item.get("status"),
            "owner": item.get("owner", "Unassigned"),
            "scores": json.dumps(item.get("scores", {})),
            "decisions": json.dumps(item.get("decisions", {})),
            "created_at": _safe_timestamp(item.get("created_at")),
            "updated_at": _safe_timestamp(item.get("updated_at")),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        })
    return rows


# ---------------------------------------------------------------------------
# Snapshot diffing
# ---------------------------------------------------------------------------

def compute_snapshot_diff(source: str) -> Optional[Dict]:
    """
    Compare the two most recent snapshots for a source and store the diff.

    Returns:
        Dict of changes, or None if fewer than 2 snapshots exist.
    """
    try:
        client = get_client()
        result = (
            client.table("dashboard_snapshots")
            .select("id, data, generated_at")
            .eq("source", source)
            .order("generated_at", desc=True)
            .limit(2)
            .execute()
        )

        if not result.data or len(result.data) < 2:
            logger.info("Fewer than 2 snapshots for %s — skipping diff", source)
            return None

        current = result.data[0]
        previous = result.data[1]

        changes = _diff_snapshots(previous.get("data", {}), current.get("data", {}))

        if changes:
            client.table("snapshot_diffs").insert({
                "source": source,
                "previous_id": previous["id"],
                "current_id": current["id"],
                "changes": changes,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }).execute()
            logger.info("Snapshot diff stored for %s: %d changes", source, len(changes))

        return changes

    except Exception as e:
        logger.error("Snapshot diff failed for %s: %s", source, e)
        return None


def _diff_snapshots(old: Dict, new: Dict, prefix: str = "") -> Dict:
    """
    Recursively diff two snapshot dicts.
    Only tracks numeric changes (counts, values, rates).

    Returns:
        Dict of {metric_path: {old, new, change_pct}}.
    """
    changes = {}

    # Key metrics to track at top level
    tracked_keys = {
        "record_counts", "lead_metrics", "pipeline_metrics",
        "activity_metrics", "yoy_summary",
    }

    keys_to_check = set(old.keys()) | set(new.keys())

    for key in keys_to_check:
        if prefix == "" and key not in tracked_keys:
            continue

        path = f"{prefix}.{key}" if prefix else key
        old_val = old.get(key)
        new_val = new.get(key)

        if isinstance(old_val, dict) and isinstance(new_val, dict):
            nested = _diff_snapshots(old_val, new_val, path)
            changes.update(nested)
        elif isinstance(old_val, (int, float)) and isinstance(new_val, (int, float)):
            if old_val != new_val:
                change_pct = None
                if old_val != 0:
                    change_pct = round((new_val - old_val) / old_val * 100, 2)
                changes[path] = {
                    "old": old_val,
                    "new": new_val,
                    "change_pct": change_pct,
                }

    return changes


# ---------------------------------------------------------------------------
# View refresh
# ---------------------------------------------------------------------------

def refresh_views() -> bool:
    """
    Refresh all materialised views via the database function.

    Returns:
        True on success, False on failure.
    """
    try:
        client = get_client()
        client.rpc("refresh_all_views", {}).execute()
        logger.info("All materialised views refreshed")
        return True
    except Exception as e:
        logger.error("Failed to refresh views: %s", e)
        return False


# ---------------------------------------------------------------------------
# Main sync functions
# ---------------------------------------------------------------------------

def sync_hubspot_to_supabase() -> Dict[str, int]:
    """
    Read latest raw HubSpot files and sync to normalised Supabase tables.

    Returns:
        Dict of {table_name: rows_synced}.
    """
    logger.info("Starting HubSpot data sync to normalised tables")
    results = {}

    # Load raw data files
    owners_raw = _load_json(_find_latest_file("hubspot_owners")) if _find_latest_file("hubspot_owners") else None
    pipelines_raw = _load_json(_find_latest_file("hubspot_pipelines")) if _find_latest_file("hubspot_pipelines") else None
    deals_raw = _load_json(_find_latest_file("hubspot_deals")) if _find_latest_file("hubspot_deals") else None
    contacts_raw = _load_json(_find_latest_file("hubspot_contacts")) if _find_latest_file("hubspot_contacts") else None
    companies_raw = _load_json(_find_latest_file("hubspot_companies")) if _find_latest_file("hubspot_companies") else None
    calls_raw = _load_json(_find_latest_file("hubspot_calls")) if _find_latest_file("hubspot_calls") else None
    emails_raw = _load_json(_find_latest_file("hubspot_emails")) if _find_latest_file("hubspot_emails") else None
    meetings_raw = _load_json(_find_latest_file("hubspot_meetings")) if _find_latest_file("hubspot_meetings") else None
    tasks_raw = _load_json(_find_latest_file("hubspot_tasks")) if _find_latest_file("hubspot_tasks") else None
    notes_raw = _load_json(_find_latest_file("hubspot_notes")) if _find_latest_file("hubspot_notes") else None
    associations_raw = _load_json(_find_latest_file("hubspot_associations")) if _find_latest_file("hubspot_associations") else None

    # Build lookup maps
    owners_map: Dict[str, str] = {}
    if owners_raw:
        for record in owners_raw.get("results", []):
            oid = str(record.get("id", ""))
            first = record.get("firstName", "")
            last = record.get("lastName", "")
            owners_map[oid] = f"{first} {last}".strip() or "Unknown"

    stages_map: Dict[str, str] = {}
    if pipelines_raw:
        for pipeline in pipelines_raw.get("results", []):
            for stage in pipeline.get("stages", []):
                stages_map[str(stage.get("id", ""))] = stage.get("label", "")

    # Sync owners
    if owners_raw:
        rows = _transform_owners(owners_raw)
        results["owners"] = _upsert_batched("owners", rows, on_conflict="id")
        logger.info("Synced %d owners", results["owners"])

    # Sync pipeline stages
    if pipelines_raw:
        rows = _transform_pipeline_stages(pipelines_raw)
        results["pipeline_stages"] = _upsert_batched("pipeline_stages", rows, on_conflict="id")
        logger.info("Synced %d pipeline stages", results["pipeline_stages"])

    # Sync deals
    if deals_raw:
        rows = _transform_deals(deals_raw, owners_map, stages_map)
        results["deals"] = _upsert_batched("deals", rows, on_conflict="id")
        logger.info("Synced %d deals", results["deals"])

    # Sync contacts
    if contacts_raw:
        rows = _transform_contacts(contacts_raw, owners_map)
        results["contacts"] = _upsert_batched("contacts", rows, on_conflict="id")
        logger.info("Synced %d contacts", results["contacts"])

    # Sync companies
    if companies_raw:
        rows = _transform_companies(companies_raw)
        results["companies"] = _upsert_batched("companies", rows, on_conflict="id")
        logger.info("Synced %d companies", results["companies"])

    # Sync activities (unified)
    activity_rows = _transform_activities(
        calls_raw, emails_raw, meetings_raw, tasks_raw, notes_raw, owners_map
    )
    if activity_rows:
        results["activities"] = _upsert_batched("activities", activity_rows, on_conflict="id")
        logger.info("Synced %d activities", results["activities"])

    # Sync associations
    if associations_raw:
        rows = _transform_associations(associations_raw)
        results["associations"] = _upsert_batched(
            "associations", rows,
            on_conflict="from_type,from_id,to_type,to_id"
        )
        logger.info("Synced %d associations", results["associations"])

    # Update data freshness
    total_records = sum(results.values())
    update_data_freshness("hubspot", total_records)

    logger.info(
        "HubSpot sync complete: %s",
        ", ".join(f"{k}={v}" for k, v in results.items()),
    )
    return results


def sync_monday_to_supabase() -> Dict[str, int]:
    """
    Read latest processed Monday metrics and sync to normalised Supabase tables.

    Returns:
        Dict of {table_name: rows_synced}.
    """
    logger.info("Starting Monday.com data sync to normalised tables")
    results = {}

    # Load the processed metrics (Monday analyzer output)
    metrics_path = PROCESSED_DIR / "monday_metrics.json"
    if not metrics_path.exists():
        logger.warning("Monday metrics file not found: %s", metrics_path)
        return results

    metrics = _load_json(metrics_path)
    if not metrics:
        return results

    # Sync boards
    board_overview = metrics.get("board_overview", {})
    if board_overview:
        rows = _transform_monday_boards(board_overview)
        results["monday_boards"] = _upsert_batched("monday_boards", rows, on_conflict="id")
        logger.info("Synced %d Monday boards", results["monday_boards"])

    # Sync M&A projects
    ma_metrics = metrics.get("ma_metrics", {})
    if ma_metrics:
        rows = _transform_monday_projects(ma_metrics)
        results["monday_projects"] = _upsert_batched("monday_projects", rows, on_conflict="id")
        logger.info("Synced %d Monday projects", results["monday_projects"])

    # Sync IC scores
    ic_metrics = metrics.get("ic_metrics", {})
    if ic_metrics:
        rows = _transform_monday_ic_scores(ic_metrics)
        results["monday_ic_scores"] = _upsert_batched("monday_ic_scores", rows, on_conflict="id")
        logger.info("Synced %d IC scores", results["monday_ic_scores"])

    # Update data freshness
    total_records = sum(results.values())
    update_data_freshness("monday", total_records)

    logger.info(
        "Monday sync complete: %s",
        ", ".join(f"{k}={v}" for k, v in results.items()),
    )
    return results
