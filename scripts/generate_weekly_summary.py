"""
Weekly Team Summary Generator
================================
Reads processed HubSpot and Monday.com data and generates a compact weekly
summary covering per-person activity, department-level rollups, upcoming
items, and attention flags.

Designed for a small business team (4-10 people). The owner reads this
on Monday morning, so it is kept scannable and action-oriented.

Outputs:
    - data/processed/weekly_summary.json   (structured data)
    - reports/WEEKLY_SUMMARY.html          (self-contained HTML email/report)

Usage:
    python scripts/generate_weekly_summary.py
    python scripts/generate_weekly_summary.py --week-offset -1
    python scripts/generate_weekly_summary.py --output-dir reports/archive
    python scripts/generate_weekly_summary.py --json-only
"""

from __future__ import annotations

import argparse
import html
import json
import logging
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent          # Annas Ai Hub/
PROCESSED_DIR = BASE_DIR / "data" / "processed"
DEFAULT_OUTPUT_DIR = BASE_DIR / "reports"

load_dotenv(BASE_DIR / ".env")

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("generate_weekly_summary")

# ---------------------------------------------------------------------------
# Brand constants
# ---------------------------------------------------------------------------
BRAND = {
    "teal":       "#3CB4AD",
    "dark":       "#242833",
    "white":      "#ffffff",
    "card_bg":    "#ffffff",
    "bg":         "#f7f8fa",
    "border":     "#e2e5ea",
    "text":       "#242833",
    "text_muted": "#6b7280",
    "success":    "#22c55e",
    "danger":     "#ef4444",
    "warning":    "#f59e0b",
}


# ============================================================================
# Reusable helper functions
# ============================================================================

def _now_utc() -> datetime:
    """Current UTC time, timezone-aware."""
    return datetime.now(timezone.utc)


def _parse_dt(val: Any) -> Optional[datetime]:
    """Parse a date/datetime string into a timezone-aware datetime."""
    if not val:
        return None
    if isinstance(val, datetime):
        return val if val.tzinfo else val.replace(tzinfo=timezone.utc)
    s = str(val).strip()
    for fmt in (
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            dt = datetime.strptime(s[:26], fmt)
            return dt.replace(tzinfo=timezone.utc) if not dt.tzinfo else dt
        except (ValueError, IndexError):
            continue
    # Try fromisoformat as a last resort
    try:
        cleaned = s.replace("Z", "+00:00")
        return datetime.fromisoformat(cleaned)
    except (ValueError, TypeError):
        return None


def _esc(text: Any) -> str:
    """HTML-escape a value; converts None to empty string."""
    if text is None:
        return ""
    return html.escape(str(text))


def _fmt_currency(value: Any, symbol: str = "\u00a3") -> str:
    """Format a number as GBP currency."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return f"{symbol}0"
    if abs(v) >= 1_000_000:
        return f"{symbol}{v / 1_000_000:,.1f}M"
    if abs(v) >= 1_000:
        return f"{symbol}{v / 1_000:,.1f}K"
    return f"{symbol}{v:,.0f}"


def _fmt_number(value: Any) -> str:
    """Format a number with commas."""
    try:
        v = float(value)
        if v == int(v):
            return f"{int(v):,}"
        return f"{v:,.1f}"
    except (TypeError, ValueError):
        return "0"


def _safe_div(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Zero-safe division."""
    if denominator == 0:
        return default
    return numerator / denominator


def _pct_change(current: float, previous: float) -> Optional[float]:
    """Calculate percentage change from previous to current. Returns None if no base."""
    if previous == 0:
        return None
    return ((current - previous) / previous) * 100


def _week_boundaries(week_offset: int = 0) -> Tuple[datetime, datetime]:
    """Return (start, end) of the target week as timezone-aware datetimes.

    week_offset=0  -> current week (Mon-Sun)
    week_offset=-1 -> last week
    """
    now = _now_utc()
    # Snap to Monday 00:00 of the current week
    days_since_monday = now.weekday()  # Monday = 0
    this_monday = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(
        days=days_since_monday
    )
    target_monday = this_monday + timedelta(weeks=week_offset)
    target_sunday = target_monday + timedelta(days=6, hours=23, minutes=59, seconds=59)
    return target_monday, target_sunday


def _prev_week_boundaries(week_start: datetime) -> Tuple[datetime, datetime]:
    """Return the boundaries of the week immediately before `week_start`."""
    prev_monday = week_start - timedelta(weeks=1)
    prev_sunday = prev_monday + timedelta(days=6, hours=23, minutes=59, seconds=59)
    return prev_monday, prev_sunday


# ---------------------------------------------------------------------------
# Core reusable helpers (exported for other scripts)
# ---------------------------------------------------------------------------

def filter_by_date_range(
    data: Dict[str, Any], start: datetime, end: datetime
) -> Dict[str, Any]:
    """Filter a {date_string: value} dict to entries within [start, end].

    Works with both daily (YYYY-MM-DD) and monthly (YYYY-MM) keys.
    Handles values that are int, float, or nested dicts.
    """
    start_str = start.strftime("%Y-%m-%d")
    end_str = end.strftime("%Y-%m-%d")
    filtered = {}
    for key, value in data.items():
        # Daily key: YYYY-MM-DD
        if len(key) == 10:
            if start_str <= key <= end_str:
                filtered[key] = value
        # Monthly key: YYYY-MM
        elif len(key) == 7:
            month_start = key + "-01"
            # Last day of month approximation: use the 28th+ for comparison
            if start_str[:7] <= key <= end_str[:7]:
                filtered[key] = value
    return filtered


def group_by_owner(items: List[dict], owner_key: str = "owner") -> Dict[str, List[dict]]:
    """Group a list of items by their owner/person field.

    Returns a dict of {owner_name: [items...]}.
    """
    groups: Dict[str, List[dict]] = defaultdict(list)
    for item in items:
        owner = item.get(owner_key) or "Unassigned"
        groups[owner].append(item)
    return dict(groups)


def calculate_trends(
    this_week: Dict[str, Any], last_week: Dict[str, Any]
) -> Dict[str, Any]:
    """Compare two week-summary dicts and compute trend metrics.

    Both dicts should have numeric values at the top level.
    Returns a dict with the same keys plus _pct_change suffix.
    """
    trends = {}
    all_keys = set(list(this_week.keys()) + list(last_week.keys()))
    for key in sorted(all_keys):
        curr = this_week.get(key, 0)
        prev = last_week.get(key, 0)
        if isinstance(curr, (int, float)) and isinstance(prev, (int, float)):
            trends[key] = curr
            trends[f"{key}_prev"] = prev
            change = _pct_change(curr, prev)
            trends[f"{key}_pct_change"] = round(change, 1) if change is not None else None
            if prev > 0:
                trends[f"{key}_direction"] = "up" if curr > prev else ("down" if curr < prev else "flat")
            else:
                trends[f"{key}_direction"] = "new" if curr > 0 else "flat"
    return trends


# ============================================================================
# Data loaders
# ============================================================================

def _load_json(path: Path) -> Optional[Dict[str, Any]]:
    """Load a JSON file, returning None on failure."""
    if not path.exists():
        logger.warning("File not found: %s", path)
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("Failed to load %s: %s", path, exc)
        return None


def _load_hubspot() -> Optional[Dict[str, Any]]:
    """Load the processed HubSpot sales metrics."""
    path = PROCESSED_DIR / "hubspot_sales_metrics.json"
    data = _load_json(path)
    if data:
        logger.info("Loaded HubSpot data from %s", path)
    return data


def _load_monday() -> Optional[Dict[str, Any]]:
    """Load the processed Monday.com metrics."""
    path = PROCESSED_DIR / "monday_metrics.json"
    data = _load_json(path)
    if data:
        logger.info("Loaded Monday.com data from %s", path)
    return data


# ============================================================================
# HubSpot weekly extraction
# ============================================================================

def _sum_daily_series(series: Dict[str, Any], start_str: str, end_str: str) -> float:
    """Sum numeric values from a daily series within a date range."""
    total = 0.0
    for day_key, value in series.items():
        if len(day_key) == 10 and start_str <= day_key <= end_str:
            if isinstance(value, (int, float)):
                total += value
            elif isinstance(value, dict):
                # Sum all sub-values (e.g. activities_by_type_by_day)
                total += sum(v for v in value.values() if isinstance(v, (int, float)))
    return total


def _sum_activity_types(
    activities_by_type_by_day: Dict[str, Dict[str, int]],
    start_str: str,
    end_str: str,
) -> Dict[str, int]:
    """Sum activity types within a date range."""
    totals: Dict[str, int] = defaultdict(int)
    for day_key, types in activities_by_type_by_day.items():
        if len(day_key) == 10 and start_str <= day_key <= end_str:
            for activity_type, count in types.items():
                totals[activity_type] += count
    return dict(totals)


def _extract_hubspot_week(
    hubspot: Dict[str, Any],
    start: datetime,
    end: datetime,
) -> Dict[str, Any]:
    """Extract HubSpot metrics for a single week."""
    start_str = start.strftime("%Y-%m-%d")
    end_str = end.strftime("%Y-%m-%d")
    ts = hubspot.get("time_series", {})

    # Daily series sums
    leads = _sum_daily_series(ts.get("leads_by_day", {}), start_str, end_str)
    contacts_created = _sum_daily_series(
        ts.get("contacts_created_by_day", {}), start_str, end_str
    )
    deals_created = _sum_daily_series(
        ts.get("deals_created_by_day", {}), start_str, end_str
    )
    deals_won = _sum_daily_series(ts.get("deals_won_by_day", {}), start_str, end_str)
    deals_won_value = _sum_daily_series(
        ts.get("deals_won_value_by_day", {}), start_str, end_str
    )
    deals_lost = _sum_daily_series(ts.get("deals_lost_by_day", {}), start_str, end_str)
    mqls = _sum_daily_series(ts.get("mqls_by_day", {}), start_str, end_str)
    sqls = _sum_daily_series(ts.get("sqls_by_day", {}), start_str, end_str)

    # Activity breakdown
    activity_types = _sum_activity_types(
        ts.get("activities_by_type_by_day", {}), start_str, end_str
    )
    total_activities = sum(activity_types.values())

    # Per-rep activity from activities_by_rep_by_month
    # Note: this is monthly, so we approximate by looking at the month(s) the
    # week falls into. For a true per-rep weekly breakdown we would need the
    # daily data correlated to owners -- we use what is available.
    rep_activity = _approximate_rep_weekly(
        ts.get("activities_by_rep_by_month", {}), start, end
    )

    # Pipeline metrics (point-in-time from the processed snapshot)
    pipeline = hubspot.get("pipeline_metrics", {})
    stale_deals = pipeline.get("stale_deals", [])

    return {
        "leads": int(leads),
        "contacts_created": int(contacts_created),
        "deals_created": int(deals_created),
        "deals_won": int(deals_won),
        "deals_won_value": round(deals_won_value, 2),
        "deals_lost": int(deals_lost),
        "mqls": int(mqls),
        "sqls": int(sqls),
        "total_activities": total_activities,
        "activity_breakdown": activity_types,
        "rep_activity": rep_activity,
        "pipeline_value": pipeline.get("total_pipeline_value", 0),
        "weighted_pipeline": pipeline.get("weighted_pipeline_value", 0),
        "win_rate": pipeline.get("win_rate", 0),
        "avg_deal_size": pipeline.get("avg_deal_size", 0),
        "avg_sales_cycle_days": pipeline.get("avg_sales_cycle_days", 0),
        "open_deals": pipeline.get("open_deals_count", 0),
        "stale_deals": stale_deals,
        "pipeline_by_owner": pipeline.get("pipeline_by_owner", {}),
    }


def _approximate_rep_weekly(
    by_rep_by_month: Dict[str, Dict[str, Dict[str, int]]],
    start: datetime,
    end: datetime,
) -> Dict[str, Dict[str, int]]:
    """Approximate per-rep weekly activity from monthly rollups.

    For the month(s) overlapping the target week, we prorate by the fraction
    of the month that falls within the week.
    """
    result: Dict[str, Dict[str, int]] = defaultdict(
        lambda: {"calls": 0, "emails": 0, "meetings": 0, "tasks": 0, "notes": 0, "total": 0}
    )

    # Determine months that overlap with our week
    month_keys = set()
    current = start
    while current <= end:
        month_keys.add(current.strftime("%Y-%m"))
        current += timedelta(days=1)

    for month_key in month_keys:
        month_data = by_rep_by_month.get(month_key, {})
        if not month_data:
            continue

        # Determine the fraction of this month that falls within our week
        year, month = int(month_key[:4]), int(month_key[5:7])
        month_start = datetime(year, month, 1, tzinfo=timezone.utc)
        if month == 12:
            month_end = datetime(year + 1, 1, 1, tzinfo=timezone.utc) - timedelta(seconds=1)
        else:
            month_end = datetime(year, month + 1, 1, tzinfo=timezone.utc) - timedelta(seconds=1)

        days_in_month = (month_end - month_start).days + 1
        overlap_start = max(start, month_start)
        overlap_end = min(end, month_end)
        overlap_days = (overlap_end - overlap_start).days + 1
        fraction = overlap_days / days_in_month if days_in_month > 0 else 0

        for rep_name, activities in month_data.items():
            for act_type, count in activities.items():
                if isinstance(count, (int, float)):
                    prorated = round(count * fraction)
                    result[rep_name][act_type] = result[rep_name].get(act_type, 0) + prorated
                    if act_type != "total":
                        result[rep_name]["total"] = result[rep_name].get("total", 0) + prorated

    return dict(result)


# ============================================================================
# Monday.com weekly extraction
# ============================================================================

def _find_status_column(item: dict) -> Optional[str]:
    """Find the first status column text on a Monday.com item."""
    for cv in item.get("column_values", []):
        if cv.get("type") == "status":
            return cv.get("text") or None
    return None


def _find_person_column(item: dict) -> Optional[str]:
    """Find the person/people column text on a Monday.com item."""
    for cv in item.get("column_values", []):
        if cv.get("type") in ("people", "person"):
            text = cv.get("text") or None
            if text:
                return text
    return None


def _extract_monday_week(
    monday: Dict[str, Any],
    start: datetime,
    end: datetime,
) -> Dict[str, Any]:
    """Extract Monday.com metrics for a single week."""
    start_str = start.strftime("%Y-%m-%d")
    end_str = end.strftime("%Y-%m-%d")
    now = _now_utc()

    # M&A pipeline
    ma = monday.get("ma_metrics", {})
    ma_projects = ma.get("projects", [])
    ma_active = [p for p in ma_projects if p.get("is_active")]
    ma_updated_this_week = [
        p for p in ma_projects
        if p.get("updated_at") and start_str <= (p["updated_at"][:10] or "") <= end_str
    ]
    ma_stale = ma.get("stale_projects", [])

    # IC items
    ic = monday.get("ic_metrics", {})
    ic_items = ic.get("items", [])
    ic_updated_this_week = [
        item for item in ic_items
        if item.get("updated_at") and start_str <= (item["updated_at"][:10] or "") <= end_str
    ]
    ic_upcoming = _find_upcoming_ic_reviews(ic_items, end)

    # AI workspace items
    ai = monday.get("ai_metrics", {})
    ai_items = ai.get("items", [])
    ai_updated_this_week = [
        item for item in ai_items
        if item.get("updated_at") and start_str <= (item["updated_at"][:10] or "") <= end_str
    ]

    # Board overview: collect all items across all workspaces
    overview = monday.get("board_overview", {})
    all_monday_items = _collect_all_board_items(overview)

    # Per-person task tracking
    person_tasks = _build_person_tasks(
        ma_projects, ic_items, ai_items, start_str, end_str
    )

    # Items completed this week (status = Done/Complete)
    completed_items = _find_completed_items(
        ma_projects + ic_items + ai_items, start_str, end_str
    )

    # Stale items (no update in 14+ days)
    stale_items = _find_stale_items(ma_projects + ic_items + ai_items, now, days=14)

    return {
        "ma_active_count": len(ma_active),
        "ma_total_value": ma.get("total_value", 0),
        "ma_updated_this_week": len(ma_updated_this_week),
        "ma_stale": ma_stale,
        "ma_stage_distribution": ma.get("stage_distribution", {}),
        "ic_scored_items": ic.get("total_scored_items", 0),
        "ic_updated_this_week": len(ic_updated_this_week),
        "ic_upcoming_reviews": ic_upcoming,
        "ai_total_items": ai.get("total_items", 0),
        "ai_updated_this_week": len(ai_updated_this_week),
        "person_tasks": person_tasks,
        "completed_items": completed_items,
        "stale_items": stale_items,
        "total_boards": overview.get("total_boards", 0),
        "total_items": overview.get("total_items", 0),
    }


def _collect_all_board_items(overview: Dict[str, Any]) -> List[dict]:
    """Flatten all items from board_overview.workspaces[].boards[]."""
    items = []
    for ws in overview.get("workspaces", []):
        for board in ws.get("boards", []):
            # The overview does not include raw items -- just counts and status
            items.append({
                "board_name": board.get("name", ""),
                "item_count": board.get("item_count", 0),
                "status_breakdown": board.get("status_breakdown", {}),
            })
    return items


def _build_person_tasks(
    ma_projects: List[dict],
    ic_items: List[dict],
    ai_items: List[dict],
    start_str: str,
    end_str: str,
) -> Dict[str, Dict[str, Any]]:
    """Build per-person task summary from Monday.com items."""
    persons: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {
            "items_updated": 0,
            "items_completed": 0,
            "items_created": 0,
            "comments_posted": 0,
            "active_items": [],
        }
    )

    all_items = ma_projects + ic_items + ai_items

    for item in all_items:
        owner = item.get("owner") or "Unassigned"
        updated_at = item.get("updated_at", "")
        created_at = item.get("created_at", "")
        status = (item.get("status") or "").lower()

        # Items updated this week
        if updated_at and start_str <= updated_at[:10] <= end_str:
            persons[owner]["items_updated"] += 1

        # Items created this week
        if created_at and start_str <= created_at[:10] <= end_str:
            persons[owner]["items_created"] += 1

        # Items completed this week
        if status in ("done", "complete", "completed", "closed"):
            if updated_at and start_str <= updated_at[:10] <= end_str:
                persons[owner]["items_completed"] += 1

        # Count comments/updates posted this week
        for update in item.get("recent_updates", []) + item.get("updates", []):
            update_date = (update.get("created_at") or "")[:10]
            if start_str <= update_date <= end_str:
                creator = update.get("creator", owner)
                persons[creator]["comments_posted"] += 1

        # Track active items per person
        if item.get("is_active", True) and status not in (
            "done", "complete", "completed", "closed", "passed", "rejected",
        ):
            persons[owner]["active_items"].append({
                "name": item.get("name", ""),
                "status": item.get("status", ""),
                "board": item.get("board", ""),
            })

    return dict(persons)


def _find_completed_items(
    items: List[dict], start_str: str, end_str: str
) -> List[dict]:
    """Find items whose status became Done/Complete within the date range."""
    completed = []
    for item in items:
        status = (item.get("status") or "").lower()
        updated_at = item.get("updated_at", "")
        if status in ("done", "complete", "completed", "closed"):
            if updated_at and start_str <= updated_at[:10] <= end_str:
                completed.append({
                    "name": item.get("name", ""),
                    "owner": item.get("owner", "Unassigned"),
                    "board": item.get("board", ""),
                    "completed_at": updated_at[:10],
                })
    return completed


def _find_stale_items(
    items: List[dict], now: datetime, days: int = 14
) -> List[dict]:
    """Find items with no update in `days`+ days that are still active."""
    stale = []
    for item in items:
        status = (item.get("status") or "").lower()
        if status in ("done", "complete", "completed", "closed", "passed", "rejected"):
            continue
        updated_at = _parse_dt(item.get("updated_at"))
        if updated_at:
            days_since = (now - updated_at).days
            if days_since >= days:
                stale.append({
                    "name": item.get("name", ""),
                    "owner": item.get("owner", "Unassigned"),
                    "board": item.get("board", ""),
                    "days_since_update": days_since,
                    "stage": item.get("stage", item.get("status", "")),
                })
    stale.sort(key=lambda x: x["days_since_update"], reverse=True)
    return stale


def _find_upcoming_ic_reviews(ic_items: List[dict], week_end: datetime) -> List[dict]:
    """Find IC items with upcoming review dates in the next 7 days from week_end."""
    upcoming = []
    cutoff = week_end + timedelta(days=7)
    cutoff_str = cutoff.strftime("%Y-%m-%d")
    week_end_str = week_end.strftime("%Y-%m-%d")

    for item in ic_items:
        # Check for target_close or any date column that indicates a review
        for key in ("target_close", "updated_at"):
            dt_val = item.get(key, "")
            if dt_val and week_end_str <= dt_val[:10] <= cutoff_str:
                upcoming.append({
                    "name": item.get("name", ""),
                    "owner": item.get("owner", "Unassigned"),
                    "date": dt_val[:10],
                    "scores": item.get("scores", {}),
                    "status": item.get("status", ""),
                })
                break
    return upcoming


# ============================================================================
# Flags & Alerts
# ============================================================================

def _generate_flags(
    hubspot_week: Dict[str, Any],
    monday_week: Dict[str, Any],
    week_start: datetime,
    week_end: datetime,
) -> List[dict]:
    """Generate attention flags and alerts."""
    flags: List[dict] = []

    # --- Flag: Reps with unusually low activity ---
    rep_activity = hubspot_week.get("rep_activity", {})
    if rep_activity:
        totals = [
            info.get("total", 0) for info in rep_activity.values()
            if isinstance(info, dict)
        ]
        if totals:
            avg_total = sum(totals) / len(totals)
            low_threshold = max(avg_total * 0.4, 3)  # 40% of average or min 3
            for rep_name, info in rep_activity.items():
                if isinstance(info, dict) and info.get("total", 0) < low_threshold:
                    flags.append({
                        "type": "low_activity",
                        "severity": "warning",
                        "title": f"Low activity: {rep_name}",
                        "detail": (
                            f"{rep_name} had {info.get('total', 0)} activities this week "
                            f"(team avg: {avg_total:.0f})"
                        ),
                        "person": rep_name,
                    })

    # --- Flag: Deals stuck in a stage too long ---
    stale_deals = hubspot_week.get("stale_deals", [])
    for deal in stale_deals[:10]:  # Limit to top 10
        days = deal.get("days_since_update", 0)
        if days >= 30:
            severity = "danger" if days >= 60 else "warning"
            flags.append({
                "type": "stuck_deal",
                "severity": severity,
                "title": f"Stuck deal: {deal.get('dealname', 'Unknown')}",
                "detail": (
                    f"No update in {days:.0f} days. Stage: {deal.get('stage', '?')}. "
                    f"Value: {_fmt_currency(deal.get('amount', 0))}"
                ),
                "person": deal.get("owner", "Unknown"),
            })

    # --- Flag: Overdue tasks (Monday.com stale items) ---
    stale_items = monday_week.get("stale_items", [])
    for item in stale_items[:10]:
        days = item.get("days_since_update", 0)
        if days >= 14:
            flags.append({
                "type": "overdue_task",
                "severity": "warning" if days < 30 else "danger",
                "title": f"Stale: {item.get('name', 'Unknown')}",
                "detail": (
                    f"No update in {days} days. Owner: {item.get('owner', '?')}. "
                    f"Board: {item.get('board', '?')}"
                ),
                "person": item.get("owner", "Unknown"),
            })

    # --- Flag: No deals closed this week ---
    if hubspot_week.get("deals_won", 0) == 0:
        flags.append({
            "type": "no_wins",
            "severity": "info",
            "title": "No deals closed this week",
            "detail": "Zero deals marked as won during this reporting period.",
            "person": None,
        })

    # --- Flag: Conversion rate drop ---
    win_rate = hubspot_week.get("win_rate", 0)
    if 0 < win_rate < 0.15:
        flags.append({
            "type": "low_win_rate",
            "severity": "warning",
            "title": f"Win rate is low: {win_rate:.0%}",
            "detail": "Overall pipeline win rate is below 15%.",
            "person": None,
        })

    # Sort: danger first, then warning, then info
    severity_order = {"danger": 0, "warning": 1, "info": 2}
    flags.sort(key=lambda f: severity_order.get(f.get("severity", "info"), 3))

    return flags


# ============================================================================
# Upcoming / Next Week Preview
# ============================================================================

def _build_upcoming(
    hubspot_week: Dict[str, Any],
    monday_week: Dict[str, Any],
    week_end: datetime,
) -> Dict[str, Any]:
    """Build the upcoming/next-week preview section."""
    next_7_days_end = week_end + timedelta(days=7)
    end_str = next_7_days_end.strftime("%Y-%m-%d")
    week_end_str = week_end.strftime("%Y-%m-%d")

    # Deals with close dates in the next 7 days
    # We can infer from pipeline_by_owner or stale_deals; the full deals list
    # is not available at this level. We signal what we can.
    upcoming_deals = []
    pipeline_by_owner = hubspot_week.get("pipeline_by_owner", {})
    # Note: the processed metrics don't expose individual deal close dates,
    # so we flag the pipeline status instead.

    return {
        "deals_closing_soon": upcoming_deals,
        "stale_items_needing_attention": monday_week.get("stale_items", [])[:10],
        "ic_reviews_upcoming": monday_week.get("ic_upcoming_reviews", []),
        "open_pipeline_value": hubspot_week.get("pipeline_value", 0),
        "open_deals_count": hubspot_week.get("open_deals", 0),
    }


# ============================================================================
# Summary assembly
# ============================================================================

def build_weekly_summary(
    week_offset: int = 0,
) -> Dict[str, Any]:
    """Build the complete weekly summary data structure."""
    logger.info("=== Weekly Summary Generation Starting ===")

    # Determine date range
    week_start, week_end = _week_boundaries(week_offset)
    prev_start, prev_end = _prev_week_boundaries(week_start)
    logger.info(
        "Target week: %s to %s",
        week_start.strftime("%Y-%m-%d"),
        week_end.strftime("%Y-%m-%d"),
    )
    logger.info(
        "Comparison week: %s to %s",
        prev_start.strftime("%Y-%m-%d"),
        prev_end.strftime("%Y-%m-%d"),
    )

    # Load data sources
    hubspot = _load_hubspot()
    monday = _load_monday()

    # Extract weekly slices
    hubspot_week: Dict[str, Any] = {}
    hubspot_prev: Dict[str, Any] = {}
    if hubspot:
        hubspot_week = _extract_hubspot_week(hubspot, week_start, week_end)
        hubspot_prev = _extract_hubspot_week(hubspot, prev_start, prev_end)
        logger.info("HubSpot week extracted: %d activities, %d deals won",
                     hubspot_week.get("total_activities", 0),
                     hubspot_week.get("deals_won", 0))
    else:
        logger.warning("No HubSpot data available; HubSpot sections will be empty")

    monday_week: Dict[str, Any] = {}
    if monday:
        monday_week = _extract_monday_week(monday, week_start, week_end)
        logger.info(
            "Monday.com week extracted: %d M&A active, %d items completed",
            monday_week.get("ma_active_count", 0),
            len(monday_week.get("completed_items", [])),
        )
    else:
        logger.warning("No Monday.com data available; Monday sections will be empty")

    # Compute trends (this week vs last week)
    trend_keys = {
        "leads", "contacts_created", "deals_created", "deals_won",
        "deals_won_value", "deals_lost", "mqls", "sqls", "total_activities",
    }
    this_week_nums = {k: hubspot_week.get(k, 0) for k in trend_keys}
    last_week_nums = {k: hubspot_prev.get(k, 0) for k in trend_keys}
    trends = calculate_trends(this_week_nums, last_week_nums)

    # Build per-person combined view
    per_person = _build_per_person_combined(hubspot_week, monday_week)

    # Flags and alerts
    flags = _generate_flags(hubspot_week, monday_week, week_start, week_end)

    # Upcoming
    upcoming = _build_upcoming(hubspot_week, monday_week, week_end)

    # Key numbers (top 6 metrics for the header)
    key_numbers = _build_key_numbers(hubspot_week, monday_week, trends)

    summary = {
        "generated_at": _now_utc().isoformat(),
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "week_label": (
            f"Week of {week_start.strftime('%b %d')} - "
            f"{week_end.strftime('%b %d, %Y')}"
        ),
        "key_numbers": key_numbers,
        "hubspot_week": hubspot_week,
        "monday_week": monday_week,
        "trends": trends,
        "per_person": per_person,
        "flags": flags,
        "upcoming": upcoming,
        "comparison": {
            "this_week": this_week_nums,
            "last_week": last_week_nums,
        },
    }

    logger.info("Weekly summary built: %d flags, %d persons tracked",
                len(flags), len(per_person))
    return summary


def _build_per_person_combined(
    hubspot_week: Dict[str, Any],
    monday_week: Dict[str, Any],
) -> Dict[str, Dict[str, Any]]:
    """Merge HubSpot rep activity with Monday.com person tasks."""
    combined: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
        "hubspot": {
            "emails": 0, "calls": 0, "meetings": 0, "tasks": 0, "notes": 0, "total": 0,
        },
        "monday": {
            "items_updated": 0, "items_completed": 0,
            "items_created": 0, "comments_posted": 0,
            "active_items": [],
        },
    })

    # HubSpot rep data
    rep_activity = hubspot_week.get("rep_activity", {})
    for rep_name, activity in rep_activity.items():
        if isinstance(activity, dict):
            combined[rep_name]["hubspot"] = {
                "emails": activity.get("emails", 0),
                "calls": activity.get("calls", 0),
                "meetings": activity.get("meetings", 0),
                "tasks": activity.get("tasks", 0),
                "notes": activity.get("notes", 0),
                "total": activity.get("total", 0),
            }

    # Monday.com person tasks
    person_tasks = monday_week.get("person_tasks", {})
    for person_name, tasks in person_tasks.items():
        if person_name == "Unassigned":
            continue
        combined[person_name]["monday"] = {
            "items_updated": tasks.get("items_updated", 0),
            "items_completed": tasks.get("items_completed", 0),
            "items_created": tasks.get("items_created", 0),
            "comments_posted": tasks.get("comments_posted", 0),
            "active_items": tasks.get("active_items", [])[:5],  # Limit for report
        }

    # Remove "Unassigned" from combined view
    combined.pop("Unassigned", None)
    combined.pop("unassigned", None)

    return dict(combined)


def _build_key_numbers(
    hubspot_week: Dict[str, Any],
    monday_week: Dict[str, Any],
    trends: Dict[str, Any],
) -> List[dict]:
    """Build the 5-6 key numbers for the report header."""
    numbers = []

    # Revenue this week
    revenue = hubspot_week.get("deals_won_value", 0)
    revenue_pct = trends.get("deals_won_value_pct_change")
    numbers.append({
        "label": "Revenue Closed",
        "value": _fmt_currency(revenue),
        "raw": revenue,
        "change_pct": revenue_pct,
        "direction": trends.get("deals_won_value_direction", "flat"),
    })

    # Deals won
    deals_won = hubspot_week.get("deals_won", 0)
    numbers.append({
        "label": "Deals Won",
        "value": str(int(deals_won)),
        "raw": deals_won,
        "change_pct": trends.get("deals_won_pct_change"),
        "direction": trends.get("deals_won_direction", "flat"),
    })

    # New leads
    leads = hubspot_week.get("leads", 0)
    numbers.append({
        "label": "New Leads",
        "value": _fmt_number(leads),
        "raw": leads,
        "change_pct": trends.get("leads_pct_change"),
        "direction": trends.get("leads_direction", "flat"),
    })

    # Total activities
    activities = hubspot_week.get("total_activities", 0)
    numbers.append({
        "label": "Team Activities",
        "value": _fmt_number(activities),
        "raw": activities,
        "change_pct": trends.get("total_activities_pct_change"),
        "direction": trends.get("total_activities_direction", "flat"),
    })

    # Open pipeline
    pipeline = hubspot_week.get("pipeline_value", 0)
    numbers.append({
        "label": "Open Pipeline",
        "value": _fmt_currency(pipeline),
        "raw": pipeline,
        "change_pct": None,
        "direction": "flat",
    })

    # M&A active projects
    ma_active = monday_week.get("ma_active_count", 0)
    numbers.append({
        "label": "Active M&A Projects",
        "value": str(ma_active),
        "raw": ma_active,
        "change_pct": None,
        "direction": "flat",
    })

    return numbers


# ============================================================================
# HTML Report Generator
# ============================================================================

def generate_html_report(summary: Dict[str, Any]) -> str:
    """Generate a self-contained HTML email/report from the weekly summary."""
    week_label = _esc(summary.get("week_label", "Weekly Summary"))
    generated_at = summary.get("generated_at", "")[:19].replace("T", " ")
    key_numbers = summary.get("key_numbers", [])
    per_person = summary.get("per_person", {})
    flags = summary.get("flags", [])
    upcoming = summary.get("upcoming", {})
    hubspot_week = summary.get("hubspot_week", {})
    monday_week = summary.get("monday_week", {})
    trends = summary.get("trends", {})

    # Build key numbers cards
    key_numbers_html = _render_key_numbers(key_numbers)

    # Build per-person section
    per_person_html = _render_per_person(per_person)

    # Build department rollup
    department_html = _render_department_rollup(hubspot_week, monday_week, trends)

    # Build flags / needs attention
    flags_html = _render_flags(flags)

    # Build upcoming
    upcoming_html = _render_upcoming(upcoming)

    # Completed items
    completed_html = _render_completed(monday_week.get("completed_items", []))

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{week_label} - eComplete Weekly Summary</title>
<style>
/* Reset & Base */
body {{
    margin: 0;
    padding: 0;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
    background: {BRAND['bg']};
    color: {BRAND['text']};
    font-size: 14px;
    line-height: 1.5;
    -webkit-font-smoothing: antialiased;
}}
.container {{
    max-width: 720px;
    margin: 0 auto;
    padding: 24px 16px;
}}
/* Header */
.header {{
    background: {BRAND['dark']};
    color: {BRAND['white']};
    padding: 28px 24px 20px;
    border-radius: 8px 8px 0 0;
    text-align: center;
}}
.header h1 {{
    margin: 0 0 4px;
    font-size: 22px;
    font-weight: 700;
    letter-spacing: -0.3px;
}}
.header .week-range {{
    font-size: 15px;
    color: {BRAND['teal']};
    font-weight: 600;
}}
.header .generated {{
    font-size: 11px;
    color: #888;
    margin-top: 8px;
}}
/* Cards */
.card {{
    background: {BRAND['card_bg']};
    border: 1px solid {BRAND['border']};
    border-radius: 8px;
    margin: 16px 0;
    overflow: hidden;
}}
.card-header {{
    background: {BRAND['dark']};
    color: {BRAND['white']};
    padding: 10px 16px;
    font-size: 13px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}}
.card-body {{
    padding: 16px;
}}
/* Key Numbers Grid */
.key-grid {{
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 12px;
    padding: 16px;
}}
.key-item {{
    text-align: center;
    padding: 12px 8px;
    border-radius: 6px;
    background: {BRAND['bg']};
}}
.key-item .value {{
    font-size: 24px;
    font-weight: 700;
    color: {BRAND['dark']};
    line-height: 1.2;
}}
.key-item .label {{
    font-size: 11px;
    color: {BRAND['text_muted']};
    text-transform: uppercase;
    letter-spacing: 0.3px;
    margin-top: 2px;
}}
.key-item .change {{
    font-size: 11px;
    font-weight: 600;
    margin-top: 2px;
}}
.change-up {{ color: {BRAND['success']}; }}
.change-down {{ color: {BRAND['danger']}; }}
.change-flat {{ color: {BRAND['text_muted']}; }}
/* Person Section */
.person-block {{
    border-bottom: 1px solid {BRAND['border']};
    padding: 12px 16px;
}}
.person-block:last-child {{
    border-bottom: none;
}}
.person-name {{
    font-size: 15px;
    font-weight: 600;
    color: {BRAND['dark']};
    margin-bottom: 6px;
}}
.person-stats {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(100px, 1fr));
    gap: 6px;
    font-size: 12px;
}}
.stat {{
    display: inline-block;
    padding: 3px 8px;
    background: {BRAND['bg']};
    border-radius: 4px;
    color: {BRAND['text_muted']};
}}
.stat strong {{
    color: {BRAND['dark']};
}}
.person-tasks {{
    margin-top: 6px;
    font-size: 12px;
    color: {BRAND['text_muted']};
}}
.person-tasks ul {{
    margin: 4px 0 0 16px;
    padding: 0;
}}
.person-tasks li {{
    margin-bottom: 2px;
}}
/* Flags */
.flag {{
    padding: 10px 14px;
    border-left: 4px solid;
    margin-bottom: 8px;
    border-radius: 0 4px 4px 0;
    font-size: 13px;
    background: {BRAND['bg']};
}}
.flag-danger {{
    border-color: {BRAND['danger']};
}}
.flag-warning {{
    border-color: {BRAND['warning']};
}}
.flag-info {{
    border-color: {BRAND['teal']};
}}
.flag-title {{
    font-weight: 600;
    color: {BRAND['dark']};
}}
.flag-detail {{
    color: {BRAND['text_muted']};
    font-size: 12px;
    margin-top: 2px;
}}
/* Rollup table */
.rollup-table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
}}
.rollup-table th {{
    text-align: left;
    padding: 6px 10px;
    border-bottom: 2px solid {BRAND['border']};
    color: {BRAND['text_muted']};
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.3px;
}}
.rollup-table td {{
    padding: 6px 10px;
    border-bottom: 1px solid {BRAND['border']};
}}
.rollup-table tr:last-child td {{
    border-bottom: none;
}}
/* Completed list */
.completed-item {{
    display: flex;
    align-items: center;
    padding: 4px 0;
    font-size: 13px;
}}
.check {{
    color: {BRAND['success']};
    margin-right: 8px;
    font-weight: bold;
}}
.completed-owner {{
    color: {BRAND['text_muted']};
    margin-left: 4px;
    font-size: 12px;
}}
/* Footer */
.footer {{
    text-align: center;
    padding: 16px;
    font-size: 11px;
    color: {BRAND['text_muted']};
}}
.teal {{ color: {BRAND['teal']}; }}
/* Responsive for email */
@media screen and (max-width: 600px) {{
    .key-grid {{ grid-template-columns: repeat(2, 1fr); }}
    .person-stats {{ grid-template-columns: repeat(2, 1fr); }}
}}
</style>
</head>
<body>
<div class="container">

<!-- Header -->
<div class="header">
    <h1>eComplete Weekly Summary</h1>
    <div class="week-range">{week_label}</div>
    <div class="generated">Generated {_esc(generated_at)} UTC</div>
</div>

<!-- Key Numbers -->
<div class="card">
    <div class="card-header">Key Numbers</div>
    <div class="key-grid">
        {key_numbers_html}
    </div>
</div>

<!-- Department Rollup -->
<div class="card">
    <div class="card-header">Department Rollup</div>
    <div class="card-body">
        {department_html}
    </div>
</div>

<!-- Per Person Activity -->
<div class="card">
    <div class="card-header">Per-Person Activity</div>
    {per_person_html}
</div>

<!-- Completed This Week -->
{f'''<div class="card">
    <div class="card-header">Completed This Week</div>
    <div class="card-body">
        {completed_html}
    </div>
</div>''' if completed_html else ''}

<!-- Needs Attention -->
{f'''<div class="card">
    <div class="card-header" style="background:{BRAND['danger']}">Needs Attention</div>
    <div class="card-body">
        {flags_html}
    </div>
</div>''' if flags else ''}

<!-- Upcoming / Next Week -->
<div class="card">
    <div class="card-header" style="background:{BRAND['teal']}">Coming Up Next Week</div>
    <div class="card-body">
        {upcoming_html}
    </div>
</div>

<!-- Footer -->
<div class="footer">
    <span class="teal">eComplete</span> &middot; Weekly Team Summary &middot; Auto-generated
</div>

</div>
</body>
</html>"""


def _render_key_numbers(key_numbers: List[dict]) -> str:
    """Render the key numbers grid items."""
    items = []
    for kn in key_numbers:
        change_html = ""
        pct = kn.get("change_pct")
        direction = kn.get("direction", "flat")
        if pct is not None:
            arrow = "&#9650;" if direction == "up" else ("&#9660;" if direction == "down" else "&#8212;")
            css_class = f"change-{direction}"
            change_html = f'<div class="change {css_class}">{arrow} {abs(pct):.0f}% vs last week</div>'
        elif direction == "new":
            change_html = '<div class="change change-up">NEW</div>'

        items.append(f"""
        <div class="key-item">
            <div class="value">{_esc(kn.get('value', '0'))}</div>
            <div class="label">{_esc(kn.get('label', ''))}</div>
            {change_html}
        </div>""")
    return "\n".join(items)


def _render_per_person(per_person: Dict[str, Dict[str, Any]]) -> str:
    """Render per-person activity blocks."""
    if not per_person:
        return '<div class="card-body"><p style="color:#6b7280">No person-level data available.</p></div>'

    blocks = []
    # Sort by total activity descending
    sorted_persons = sorted(
        per_person.items(),
        key=lambda x: (
            x[1].get("hubspot", {}).get("total", 0) +
            x[1].get("monday", {}).get("items_updated", 0)
        ),
        reverse=True,
    )

    for person_name, data in sorted_persons:
        hs = data.get("hubspot", {})
        mn = data.get("monday", {})

        # HubSpot stats
        stats_parts = []
        if hs.get("emails", 0):
            stats_parts.append(f'<span class="stat"><strong>{hs["emails"]}</strong> emails</span>')
        if hs.get("calls", 0):
            stats_parts.append(f'<span class="stat"><strong>{hs["calls"]}</strong> calls</span>')
        if hs.get("meetings", 0):
            stats_parts.append(f'<span class="stat"><strong>{hs["meetings"]}</strong> meetings</span>')
        if hs.get("tasks", 0):
            stats_parts.append(f'<span class="stat"><strong>{hs["tasks"]}</strong> tasks</span>')
        if hs.get("notes", 0):
            stats_parts.append(f'<span class="stat"><strong>{hs["notes"]}</strong> notes</span>')

        # Monday.com stats
        if mn.get("items_updated", 0):
            stats_parts.append(
                f'<span class="stat"><strong>{mn["items_updated"]}</strong> items updated</span>'
            )
        if mn.get("items_completed", 0):
            stats_parts.append(
                f'<span class="stat"><strong>{mn["items_completed"]}</strong> completed</span>'
            )
        if mn.get("items_created", 0):
            stats_parts.append(
                f'<span class="stat"><strong>{mn["items_created"]}</strong> created</span>'
            )
        if mn.get("comments_posted", 0):
            stats_parts.append(
                f'<span class="stat"><strong>{mn["comments_posted"]}</strong> comments</span>'
            )

        stats_html = "\n".join(stats_parts) if stats_parts else '<span class="stat">No activity recorded</span>'

        # Active items list (up to 5)
        active_items = mn.get("active_items", [])
        tasks_html = ""
        if active_items:
            items_li = "\n".join(
                f"<li>{_esc(ai.get('name', ''))} "
                f"<span style='color:{BRAND['text_muted']};font-size:11px'>"
                f"({_esc(ai.get('status', ''))})</span></li>"
                for ai in active_items[:5]
            )
            more = f"<li style='color:{BRAND['text_muted']}'>+{len(active_items) - 5} more...</li>" if len(active_items) > 5 else ""
            tasks_html = f"""
            <div class="person-tasks">
                Active items:
                <ul>{items_li}{more}</ul>
            </div>"""

        blocks.append(f"""
        <div class="person-block">
            <div class="person-name">{_esc(person_name)}</div>
            <div class="person-stats">{stats_html}</div>
            {tasks_html}
        </div>""")

    return "\n".join(blocks)


def _render_department_rollup(
    hubspot_week: Dict[str, Any],
    monday_week: Dict[str, Any],
    trends: Dict[str, Any],
) -> str:
    """Render the department-level rollup table."""
    def _trend_badge(key: str) -> str:
        direction = trends.get(f"{key}_direction", "flat")
        pct = trends.get(f"{key}_pct_change")
        if pct is None:
            return ""
        arrow = "&#9650;" if direction == "up" else ("&#9660;" if direction == "down" else "")
        css = f"change-{direction}"
        return f' <span class="{css}" style="font-size:11px">{arrow}{abs(pct):.0f}%</span>'

    activity_breakdown = hubspot_week.get("activity_breakdown", {})
    ma_stage_dist = monday_week.get("ma_stage_distribution", {})

    rows = []

    # Activity rows
    rows.append(_rollup_row("Total Team Activities",
                            _fmt_number(hubspot_week.get("total_activities", 0)),
                            _trend_badge("total_activities")))
    rows.append(_rollup_row("Emails",
                            _fmt_number(activity_breakdown.get("emails", 0)), ""))
    rows.append(_rollup_row("Calls",
                            _fmt_number(activity_breakdown.get("calls", 0)), ""))
    rows.append(_rollup_row("Meetings",
                            _fmt_number(activity_breakdown.get("meetings", 0)), ""))

    # Pipeline rows
    rows.append(_rollup_row("New Leads",
                            _fmt_number(hubspot_week.get("leads", 0)),
                            _trend_badge("leads")))
    rows.append(_rollup_row("New Deals Created",
                            _fmt_number(hubspot_week.get("deals_created", 0)),
                            _trend_badge("deals_created")))
    rows.append(_rollup_row("Deals Won",
                            _fmt_number(hubspot_week.get("deals_won", 0)),
                            _trend_badge("deals_won")))
    rows.append(_rollup_row("Revenue Closed",
                            _fmt_currency(hubspot_week.get("deals_won_value", 0)),
                            _trend_badge("deals_won_value")))
    rows.append(_rollup_row("Deals Lost",
                            _fmt_number(hubspot_week.get("deals_lost", 0)),
                            _trend_badge("deals_lost")))
    rows.append(_rollup_row("Win Rate",
                            f"{hubspot_week.get('win_rate', 0):.0%}", ""))
    rows.append(_rollup_row("Open Pipeline",
                            _fmt_currency(hubspot_week.get("pipeline_value", 0)), ""))

    # M&A rows
    rows.append(_rollup_row("M&A Active Projects",
                            _fmt_number(monday_week.get("ma_active_count", 0)), ""))
    rows.append(_rollup_row("M&A Pipeline Value",
                            _fmt_currency(monday_week.get("ma_total_value", 0)), ""))
    rows.append(_rollup_row("M&A Updated This Week",
                            _fmt_number(monday_week.get("ma_updated_this_week", 0)), ""))

    table_rows = "\n".join(rows)

    return f"""
    <table class="rollup-table">
        <thead>
            <tr>
                <th>Metric</th>
                <th style="text-align:right">This Week</th>
                <th style="text-align:right">vs Last Week</th>
            </tr>
        </thead>
        <tbody>
            {table_rows}
        </tbody>
    </table>"""


def _rollup_row(label: str, value: str, trend: str) -> str:
    """Build a single rollup table row."""
    return (
        f'<tr><td>{_esc(label)}</td>'
        f'<td style="text-align:right;font-weight:600">{value}</td>'
        f'<td style="text-align:right">{trend}</td></tr>'
    )


def _render_flags(flags: List[dict]) -> str:
    """Render the attention flags section."""
    if not flags:
        return '<p style="color:#22c55e;font-weight:600">All clear this week!</p>'

    items = []
    for flag in flags:
        severity = flag.get("severity", "info")
        items.append(f"""
        <div class="flag flag-{severity}">
            <div class="flag-title">{_esc(flag.get('title', ''))}</div>
            <div class="flag-detail">{_esc(flag.get('detail', ''))}</div>
        </div>""")
    return "\n".join(items)


def _render_upcoming(upcoming: Dict[str, Any]) -> str:
    """Render the upcoming/next-week preview section."""
    parts = []

    # IC reviews
    ic_reviews = upcoming.get("ic_reviews_upcoming", [])
    if ic_reviews:
        items_html = "\n".join(
            f"<li><strong>{_esc(r.get('name', ''))}</strong> "
            f"({_esc(r.get('owner', ''))}) - {_esc(r.get('date', ''))}</li>"
            for r in ic_reviews[:5]
        )
        parts.append(f"<p style='font-weight:600;margin-bottom:4px'>IC Reviews Coming Up:</p><ul>{items_html}</ul>")

    # Stale items needing attention
    stale = upcoming.get("stale_items_needing_attention", [])
    if stale:
        items_html = "\n".join(
            f"<li><strong>{_esc(s.get('name', ''))}</strong> "
            f"({_esc(s.get('owner', ''))}) - {s.get('days_since_update', 0)} days stale</li>"
            for s in stale[:5]
        )
        parts.append(f"<p style='font-weight:600;margin-bottom:4px'>Stale Items Needing Attention:</p><ul>{items_html}</ul>")

    # Pipeline snapshot
    open_deals = upcoming.get("open_deals_count", 0)
    pipeline_val = upcoming.get("open_pipeline_value", 0)
    if open_deals or pipeline_val:
        parts.append(
            f"<p><strong>{open_deals}</strong> open deals with "
            f"<strong>{_fmt_currency(pipeline_val)}</strong> in pipeline.</p>"
        )

    if not parts:
        parts.append(
            f'<p style="color:{BRAND["text_muted"]}">No upcoming items flagged.</p>'
        )

    return "\n".join(parts)


def _render_completed(completed_items: List[dict]) -> str:
    """Render the completed items list."""
    if not completed_items:
        return ""

    items = []
    for ci in completed_items[:15]:
        items.append(
            f'<div class="completed-item">'
            f'<span class="check">&#10003;</span>'
            f'{_esc(ci.get("name", ""))}'
            f'<span class="completed-owner"> - {_esc(ci.get("owner", ""))}</span>'
            f'</div>'
        )
    more = ""
    if len(completed_items) > 15:
        more = f'<p style="color:{BRAND["text_muted"]};font-size:12px;margin-top:8px">+{len(completed_items) - 15} more items completed</p>'
    return "\n".join(items) + more


# ============================================================================
# Output writers
# ============================================================================

def _write_json(summary: Dict[str, Any], output_dir: Path) -> Path:
    """Write the weekly summary JSON file."""
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = PROCESSED_DIR / "weekly_summary.json"
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    try:
        with open(json_path, "w", encoding="utf-8") as fh:
            json.dump(summary, fh, indent=2, default=str, ensure_ascii=False)
        logger.info("JSON summary written to %s", json_path)
    except OSError as exc:
        logger.error("Failed to write JSON: %s", exc)

    return json_path


def _write_html(summary: Dict[str, Any], output_dir: Path) -> Path:
    """Write the weekly summary HTML report."""
    output_dir.mkdir(parents=True, exist_ok=True)
    html_path = output_dir / "WEEKLY_SUMMARY.html"

    try:
        html_content = generate_html_report(summary)
        with open(html_path, "w", encoding="utf-8") as fh:
            fh.write(html_content)
        logger.info("HTML report written to %s", html_path)
    except Exception as exc:
        logger.error("Failed to write HTML report: %s", exc)
        raise

    return html_path


# ============================================================================
# CLI
# ============================================================================

def _parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Generate a weekly team summary from HubSpot and Monday.com data",
    )
    parser.add_argument(
        "--week-offset",
        type=int,
        default=0,
        help="Week offset (0 = current week, -1 = last week). Default: 0",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(DEFAULT_OUTPUT_DIR),
        help=f"Output directory for the HTML report. Default: {DEFAULT_OUTPUT_DIR}",
    )
    parser.add_argument(
        "--json-only",
        action="store_true",
        help="Only generate the JSON output; skip HTML report",
    )
    return parser.parse_args()


def main():
    """Main entry point."""
    args = _parse_args()
    output_dir = Path(args.output_dir)

    logger.info("Weekly summary generator starting")
    logger.info("  Week offset: %d", args.week_offset)
    logger.info("  Output dir: %s", output_dir)
    logger.info("  JSON only: %s", args.json_only)

    summary = build_weekly_summary(week_offset=args.week_offset)

    # Write JSON output (always)
    json_path = _write_json(summary, output_dir)

    # Write HTML report (unless --json-only)
    html_path = None
    if not args.json_only:
        html_path = _write_html(summary, output_dir)

    # Final summary
    logger.info("=== Weekly Summary Generation Complete ===")
    logger.info("  Period: %s", summary.get("week_label", ""))
    logger.info("  Key numbers: %d", len(summary.get("key_numbers", [])))
    logger.info("  Persons tracked: %d", len(summary.get("per_person", {})))
    logger.info("  Flags raised: %d", len(summary.get("flags", [])))
    logger.info("  JSON: %s", json_path)
    if html_path:
        logger.info("  HTML: %s", html_path)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        logger.error("Weekly summary generation failed: %s", exc, exc_info=True)
        sys.exit(1)
