"""
Inbound Signal Queue
====================

Aggregates inbound signals from multiple data sources into a single
prioritized action queue for the dashboard.  Reads processed metrics from
HubSpot, Monday.com, email actions, and the weekly summary, then generates
a unified inbox of items that need attention with AI-recommended next actions.

Data sources:
    - data/processed/hubspot_sales_metrics.json
    - data/processed/monday_metrics.json
    - data/processed/email_actions.json
    - data/processed/weekly_summary.json

Output:
    - data/processed/inbound_queue.json

Usage:
    python scripts/inbound_queue.py               # generate full queue
    python scripts/inbound_queue.py --summary      # print summary only
    python scripts/inbound_queue.py --top 10       # show top N items
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
PROCESSED_DIR = BASE_DIR / "data" / "processed"

load_dotenv(BASE_DIR / ".env")

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
PRIORITY_SCORES = {
    "critical": 100,
    "high": 75,
    "medium": 50,
    "low": 25,
}

# Stages considered "early" in the M&A pipeline where NDA is typically needed
EARLY_MA_STAGES = {
    "not started",
    "im received",
    "pending nda",
    "pending info",
    "gate 0",
    "partial data",
    "new outreach",
}

OUTPUT_PATH = PROCESSED_DIR / "inbound_queue.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_json(path: Path) -> dict:
    """Load a JSON file and return its contents, or empty dict on failure."""
    if not path.exists():
        logger.warning("Data file not found: %s", path)
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        logger.error("Failed to load %s: %s", path, exc)
        return {}


def _make_id(source: str, category: str, entity: str) -> str:
    """Generate a deterministic item ID from source + category + entity."""
    raw = f"{source}|{category}|{entity}".lower().strip()
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:12]


def _now_iso() -> str:
    """Current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat()


def _make_item(
    source: str,
    category: str,
    priority: str,
    title: str,
    detail: str,
    entity: str,
    recommended_action: str,
    action_type: str,
    action_data: Optional[Dict[str, Any]] = None,
    age_hours: float = 0.0,
) -> Dict[str, Any]:
    """Build a single queue item dict."""
    return {
        "id": _make_id(source, category, entity),
        "timestamp": _now_iso(),
        "source": source,
        "category": category,
        "priority": priority,
        "title": title,
        "detail": detail,
        "entity": entity,
        "recommended_action": recommended_action,
        "action_type": action_type,
        "action_data": action_data or {},
        "status": "new",
        "age_hours": round(age_hours, 1),
    }


# ---------------------------------------------------------------------------
# Signal generators
# ---------------------------------------------------------------------------

def _hubspot_signals(hs_data: dict) -> List[Dict[str, Any]]:
    """Extract queue items from HubSpot sales metrics."""
    items: List[Dict[str, Any]] = []
    if not hs_data:
        return items

    lead_metrics = hs_data.get("lead_metrics", {})
    pipeline_metrics = hs_data.get("pipeline_metrics", {})
    web_signals = hs_data.get("web_signals", {})

    # -----------------------------------------------------------------------
    # 1. New Leads (last 7 days approximation from leads_over_time)
    # -----------------------------------------------------------------------
    leads_over_time = lead_metrics.get("leads_over_time", {})
    now = datetime.now(timezone.utc)
    current_month_key = now.strftime("%Y-%m")

    recent_lead_count = leads_over_time.get(current_month_key, 0)
    if recent_lead_count == 0:
        recent_lead_count = lead_metrics.get("new_leads_30d", 0)

    if recent_lead_count > 0:
        # Determine priority by dominant lead source
        leads_by_source = lead_metrics.get("leads_by_source", {})
        high_value_sources = {"ORGANIC_SEARCH", "REFERRALS"}
        medium_value_sources = {"PAID_SEARCH"}

        high_count = sum(
            v for k, v in leads_by_source.items() if k in high_value_sources
        )
        medium_count = sum(
            v for k, v in leads_by_source.items() if k in medium_value_sources
        )
        total_non_offline = sum(
            v for k, v in leads_by_source.items() if k != "OFFLINE"
        )

        if high_count > 0 and (total_non_offline == 0 or high_count / max(total_non_offline, 1) > 0.3):
            priority = "high"
        elif medium_count > 0 and (total_non_offline == 0 or medium_count / max(total_non_offline, 1) > 0.3):
            priority = "medium"
        else:
            priority = "low"

        items.append(_make_item(
            source="hubspot",
            category="new_lead",
            priority=priority,
            title=f"{recent_lead_count} new leads this month",
            detail=(
                f"Lead sources: {', '.join(f'{k}: {v}' for k, v in leads_by_source.items() if v > 0)}. "
                f"Total leads: {lead_metrics.get('total_leads', 'N/A')}."
            ),
            entity="All Leads",
            recommended_action="Review new leads and assign for outreach",
            action_type="review",
            action_data={"source_breakdown": leads_by_source},
        ))

    # -----------------------------------------------------------------------
    # 2. Stale Deals
    # -----------------------------------------------------------------------
    stale_deals = pipeline_metrics.get("stale_deals", [])
    for deal in stale_deals:
        days = deal.get("days_since_update", 0)
        if days > 30:
            priority = "high"
        elif days > 14:
            priority = "medium"
        else:
            continue

        deal_name = deal.get("dealname", "Unknown Deal")
        amount = deal.get("amount", 0)
        stage = deal.get("stage", "Unknown")
        owner = deal.get("owner", "Unassigned")
        age_hours = days * 24.0

        items.append(_make_item(
            source="hubspot",
            category="stale_follow_up",
            priority=priority,
            title=f"Stale deal: {deal_name}",
            detail=(
                f"No update in {int(days)} days. Stage: {stage}. "
                f"Value: \u00a3{amount:,.0f}. Owner: {owner}."
            ),
            entity=deal_name,
            recommended_action=f"Follow up with {owner} on deal status and next steps",
            action_type="call" if days > 60 else "email",
            action_data={
                "deal_id": deal.get("deal_id", ""),
                "owner": owner,
                "template_key": "follow_up",
            },
            age_hours=age_hours,
        ))

    # -----------------------------------------------------------------------
    # 3. High-Value Pipeline Deals (>50k)
    # -----------------------------------------------------------------------
    deals_by_stage = pipeline_metrics.get("deals_by_stage", {})
    for stage_name, stage_info in deals_by_stage.items():
        if stage_name in ("Closed Won", "Closed Lost", "Disqualified"):
            continue
        total_value = stage_info.get("total_value", 0)
        count = stage_info.get("count", 0)
        if total_value > 50000:
            items.append(_make_item(
                source="hubspot",
                category="deal_update",
                priority="high",
                title=f"High-value pipeline: {stage_name}",
                detail=(
                    f"{count} deal(s) worth \u00a3{total_value:,.0f} "
                    f"in stage '{stage_name}'."
                ),
                entity=stage_name,
                recommended_action=f"Review {count} deal(s) in {stage_name} and ensure progression",
                action_type="review",
                action_data={"stage": stage_name, "value": total_value, "count": count},
            ))

    # -----------------------------------------------------------------------
    # 4. Web Signals
    # -----------------------------------------------------------------------
    high_intent_pages = web_signals.get("high_intent_pages", [])
    for page in high_intent_pages:
        page_name = page.get("page", "Unknown Page")
        conversions = page.get("conversions", 0)
        if conversions < 1:
            continue
        items.append(_make_item(
            source="hubspot",
            category="web_signal",
            priority="medium",
            title=f"Web signal: {conversions} conversion(s)",
            detail=f"Page: {page_name}. {conversions} form submission(s) detected.",
            entity=page_name,
            recommended_action="Review form submissions and follow up with new contacts",
            action_type="review",
            action_data={"page": page_name, "conversions": conversions},
        ))

    form_summary = web_signals.get("form_summary", {})
    submissions = form_summary.get("submissions", [])
    for sub in submissions:
        items.append(_make_item(
            source="hubspot",
            category="web_signal",
            priority="medium",
            title=f"Form submission: {sub.get('form_name', 'Unknown')}",
            detail=f"New form submission received from {sub.get('contact', 'unknown contact')}.",
            entity=sub.get("form_name", "Unknown Form"),
            recommended_action="Review submission and respond within 24 hours",
            action_type="email",
            action_data={"submission": sub},
        ))

    # -----------------------------------------------------------------------
    # 5. Pipeline Coverage Warning
    # -----------------------------------------------------------------------
    pipeline_coverage = pipeline_metrics.get("pipeline_coverage", None)
    if pipeline_coverage is not None and pipeline_coverage < 2.0:
        if pipeline_coverage < 1.0:
            priority = "critical"
        else:
            priority = "critical"
        items.append(_make_item(
            source="hubspot",
            category="alert",
            priority=priority,
            title=f"Pipeline coverage low: {pipeline_coverage:.1f}x",
            detail=(
                f"Pipeline coverage is {pipeline_coverage:.1f}x (target: 3.0x minimum). "
                f"Weighted pipeline: \u00a3{pipeline_metrics.get('weighted_pipeline_value', 0):,.0f}."
            ),
            entity="Pipeline Coverage",
            recommended_action="Increase prospecting activity and review lead sources",
            action_type="review",
            action_data={"coverage": pipeline_coverage},
        ))

    return items


def _monday_signals(monday_data: dict) -> List[Dict[str, Any]]:
    """Extract queue items from Monday.com metrics."""
    items: List[Dict[str, Any]] = []
    if not monday_data:
        return items

    ma_metrics = monday_data.get("ma_metrics", {})
    ic_metrics = monday_data.get("ic_metrics", {})

    # -----------------------------------------------------------------------
    # 6. Stale M&A Projects
    # -----------------------------------------------------------------------
    stale_projects = ma_metrics.get("stale_projects", [])
    for project in stale_projects:
        days_stale = project.get("days_stale", 0)
        if days_stale > 60:
            priority = "critical"
        elif days_stale > 30:
            priority = "high"
        else:
            continue

        name = project.get("name", "Unknown Project")
        stage = project.get("stage", "Unknown")
        age_hours = days_stale * 24.0

        items.append(_make_item(
            source="monday",
            category="stale_follow_up",
            priority=priority,
            title=f"Stale M&A project: {name}",
            detail=f"No update in {days_stale} days. Stage: {stage}.",
            entity=name,
            recommended_action=f"Review project status and update or archive '{name}'",
            action_type="call" if days_stale > 90 else "email",
            action_data={"project_name": name, "stage": stage, "template_key": "follow_up"},
            age_hours=age_hours,
        ))

    # -----------------------------------------------------------------------
    # 7. IC Items Without Decisions
    # -----------------------------------------------------------------------
    # The ic_metrics structure uses "top_scored" as the items list
    ic_items = ic_metrics.get("top_scored", [])
    # Also check for an "items" key if present
    if not ic_items:
        ic_items = ic_metrics.get("items", [])

    for item in ic_items:
        decisions = item.get("decisions")
        # Skip items that already have decisions
        if decisions:
            continue

        name = item.get("name", "Unknown")
        total_score = item.get("total_score", 0)
        avg_score = item.get("avg_score", 0)
        status = item.get("status", "Unknown")

        # Skip completed items
        if status and status.lower() in ("completed", "closed", "passed"):
            continue

        if avg_score > 70:
            priority = "high"
        else:
            priority = "medium"

        items.append(_make_item(
            source="monday",
            category="ic_review",
            priority=priority,
            title=f"IC review needed: {name}",
            detail=(
                f"Total score: {total_score}. Avg score: {avg_score}. "
                f"Status: {status}. No IC decision recorded."
            ),
            entity=name,
            recommended_action=f"Schedule IC review meeting for '{name}'",
            action_type="schedule",
            action_data={"project_name": name, "score": total_score},
        ))

    # -----------------------------------------------------------------------
    # 8. Active M&A projects needing NDA (early-stage projects)
    # -----------------------------------------------------------------------
    projects = ma_metrics.get("projects", [])
    for project in projects:
        if not project.get("is_active", False):
            continue
        stage = (project.get("stage") or "").lower().strip()
        if stage not in EARLY_MA_STAGES:
            continue

        name = project.get("name", "Unknown")
        items.append(_make_item(
            source="monday",
            category="nda_request",
            priority="medium",
            title=f"NDA may be needed: {name}",
            detail=(
                f"Active project in early stage: '{project.get('stage', stage)}'. "
                f"Owner: {project.get('owner', 'Unassigned')}."
            ),
            entity=name,
            recommended_action=f"Send NDA to counterparty for '{name}'",
            action_type="email",
            action_data={
                "project_id": project.get("id", ""),
                "project_name": name,
                "template_key": "nda_request",
            },
        ))

    return items


def _weekly_flags(weekly_data: dict) -> List[Dict[str, Any]]:
    """Extract queue items from the weekly summary flags."""
    items: List[Dict[str, Any]] = []
    if not weekly_data:
        return items

    flags = weekly_data.get("flags", [])
    severity_map = {
        "danger": "high",
        "critical": "critical",
        "warning": "medium",
        "info": "low",
    }

    for flag in flags:
        flag_type = flag.get("type", "unknown")
        severity = flag.get("severity", "info")
        priority = severity_map.get(severity, "low")
        title = flag.get("title", "Flag")
        detail = flag.get("detail", "")
        person = flag.get("person", "")

        # Map flag type to a recommended action
        if flag_type == "stuck_deal":
            action = f"Contact {person} about this stuck deal"
            action_type = "call"
        elif flag_type == "overdue_task":
            action = f"Review and reassign or close this overdue item"
            action_type = "review"
        elif flag_type == "low_activity":
            action = f"Check in with {person} about activity levels"
            action_type = "call"
        else:
            action = "Review and take appropriate action"
            action_type = "review"

        items.append(_make_item(
            source="system",
            category="alert",
            priority=priority,
            title=title,
            detail=detail,
            entity=person or title,
            recommended_action=action,
            action_type=action_type,
            action_data={"flag_type": flag_type, "severity": severity},
        ))

    return items


def _system_alerts(hs_data: dict, monday_data: dict) -> List[Dict[str, Any]]:
    """Generate system-level alerts from cross-source analysis."""
    items: List[Dict[str, Any]] = []

    # -----------------------------------------------------------------------
    # 10. Pipeline Target Gap
    # -----------------------------------------------------------------------
    pipeline_metrics = (hs_data or {}).get("pipeline_metrics", {})
    weighted_pipeline = pipeline_metrics.get("weighted_pipeline_value", 0)

    # Use a reasonable annual target estimate: avg_deal_size * expected deals
    # or fall back to a simple heuristic based on won deals
    avg_deal_size = pipeline_metrics.get("avg_deal_size", 0)
    won_count = pipeline_metrics.get("won_deals_count", 0)
    win_rate = pipeline_metrics.get("win_rate", 0)

    # Estimate quarterly target from historical performance
    # If we have won deals and avg deal size, project a quarterly target
    if avg_deal_size > 0 and won_count > 0:
        # Annualise based on available data, then take quarterly
        quarterly_target = (avg_deal_size * won_count) / 4.0
    else:
        quarterly_target = 0

    if quarterly_target > 0:
        gap_pct = ((quarterly_target - weighted_pipeline) / quarterly_target) * 100

        if gap_pct > 30:
            priority = "critical"
        elif gap_pct > 15:
            priority = "high"
        else:
            priority = None

        if priority:
            items.append(_make_item(
                source="system",
                category="alert",
                priority=priority,
                title=f"Pipeline target gap: {gap_pct:.0f}%",
                detail=(
                    f"Weighted pipeline: \u00a3{weighted_pipeline:,.0f}. "
                    f"Estimated quarterly target: \u00a3{quarterly_target:,.0f}. "
                    f"Gap: {gap_pct:.1f}%."
                ),
                entity="Pipeline Target",
                recommended_action="Increase pipeline generation activities to close the gap",
                action_type="review",
                action_data={
                    "weighted_pipeline": weighted_pipeline,
                    "quarterly_target": quarterly_target,
                    "gap_pct": round(gap_pct, 1),
                },
            ))

    # Check M&A pipeline health
    ma_metrics = (monday_data or {}).get("ma_metrics", {})
    active_projects = ma_metrics.get("active_projects", 0)
    stale_projects = ma_metrics.get("stale_projects", [])
    stale_count = len(stale_projects)

    if active_projects > 0 and stale_count > 0:
        stale_ratio = stale_count / active_projects
        if stale_ratio > 0.3:
            items.append(_make_item(
                source="system",
                category="alert",
                priority="high" if stale_ratio > 0.5 else "medium",
                title=f"M&A pipeline hygiene: {stale_count} stale projects",
                detail=(
                    f"{stale_count} of {active_projects} active M&A projects "
                    f"({stale_ratio:.0%}) are stale. Consider archiving or updating."
                ),
                entity="M&A Pipeline",
                recommended_action="Run pipeline review session to clean up stale projects",
                action_type="schedule",
                action_data={
                    "active_projects": active_projects,
                    "stale_count": stale_count,
                    "stale_ratio": round(stale_ratio, 2),
                },
            ))

    return items


# ---------------------------------------------------------------------------
# Priority scoring & deduplication
# ---------------------------------------------------------------------------

def _assign_priority_score(item: Dict[str, Any]) -> int:
    """Compute a numeric priority score for sorting.

    Base score from priority level, plus an age bonus (older items get
    slightly higher scores to prevent them from being buried).
    """
    base = PRIORITY_SCORES.get(item.get("priority", "low"), 25)
    age_hours = item.get("age_hours", 0)

    # Age bonus: +1 per 24 hours, capped at +20
    age_bonus = min(int(age_hours / 24), 20)

    # Category bonus: certain categories are inherently more urgent
    category_bonus = {
        "alert": 10,
        "new_lead": 5,
        "deal_update": 5,
        "ic_review": 3,
        "stale_follow_up": 2,
        "nda_request": 1,
        "web_signal": 0,
        "meeting_request": 0,
    }.get(item.get("category", ""), 0)

    return base + age_bonus + category_bonus


def _deduplicate(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Remove near-duplicate items based on entity + category.

    When duplicates exist, keep the one with the highest priority score.
    """
    seen: Dict[str, Dict[str, Any]] = {}

    for item in items:
        key = f"{item.get('entity', '').lower().strip()}|{item.get('category', '')}"
        if key in seen:
            existing_score = _assign_priority_score(seen[key])
            new_score = _assign_priority_score(item)
            if new_score > existing_score:
                seen[key] = item
        else:
            seen[key] = item

    return list(seen.values())


# ---------------------------------------------------------------------------
# Main queue generation
# ---------------------------------------------------------------------------

def generate_queue() -> Dict[str, Any]:
    """Generate the full inbound signal queue.

    Returns a dict with:
        - items: list of queue items, sorted by priority score descending
        - summary: count statistics by priority, category, and source
        - generated_at: ISO timestamp
    """
    logger.info("Generating inbound signal queue...")

    # Load data sources
    hs_data = _load_json(PROCESSED_DIR / "hubspot_sales_metrics.json")
    monday_data = _load_json(PROCESSED_DIR / "monday_metrics.json")
    _email_data = _load_json(PROCESSED_DIR / "email_actions.json")
    weekly_data = _load_json(PROCESSED_DIR / "weekly_summary.json")

    # Collect signals from all sources
    all_items: List[Dict[str, Any]] = []

    hs_items = _hubspot_signals(hs_data)
    logger.info("HubSpot signals: %d items", len(hs_items))
    all_items.extend(hs_items)

    mon_items = _monday_signals(monday_data)
    logger.info("Monday.com signals: %d items", len(mon_items))
    all_items.extend(mon_items)

    flag_items = _weekly_flags(weekly_data)
    logger.info("Weekly flags: %d items", len(flag_items))
    all_items.extend(flag_items)

    sys_items = _system_alerts(hs_data, monday_data)
    logger.info("System alerts: %d items", len(sys_items))
    all_items.extend(sys_items)

    # Incorporate existing suggested actions from email_actions.json
    suggested = _email_data.get("suggested_actions", []) if _email_data else []
    for action in suggested:
        action_type_map = {
            "schedule_call": "call",
            "schedule_meeting": "schedule",
            "send_email": "email",
        }
        all_items.append(_make_item(
            source="email",
            category=action.get("type", "alert"),
            priority=action.get("priority", "medium"),
            title=action.get("title", "Suggested action"),
            detail=action.get("detail", ""),
            entity=action.get("title", "").replace("Follow up: ", "").replace("IC review needed: ", ""),
            recommended_action=action.get("title", ""),
            action_type=action_type_map.get(action.get("action", ""), "review"),
            action_data={"original_action": action.get("action", "")},
        ))

    # Deduplicate
    before_dedup = len(all_items)
    all_items = _deduplicate(all_items)
    dedup_removed = before_dedup - len(all_items)
    if dedup_removed:
        logger.info("Deduplication removed %d items", dedup_removed)

    # Sort by priority score descending
    all_items.sort(key=lambda x: _assign_priority_score(x), reverse=True)

    # Attach computed priority score to each item for transparency
    for item in all_items:
        item["priority_score"] = _assign_priority_score(item)

    # Build summary
    by_priority = dict(Counter(i["priority"] for i in all_items))
    by_category = dict(Counter(i["category"] for i in all_items))
    by_source = dict(Counter(i["source"] for i in all_items))

    summary = {
        "total_items": len(all_items),
        "by_priority": by_priority,
        "by_category": by_category,
        "by_source": by_source,
    }

    result = {
        "generated_at": _now_iso(),
        "summary": summary,
        "items": all_items,
    }

    # Write output
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str, ensure_ascii=False)

    logger.info(
        "Queue written to %s (%d items: %s)",
        OUTPUT_PATH,
        len(all_items),
        ", ".join(f"{k}={v}" for k, v in by_priority.items()),
    )

    return result


# ---------------------------------------------------------------------------
# CLI display helpers
# ---------------------------------------------------------------------------

def _print_summary(result: Dict[str, Any]) -> None:
    """Print a compact summary of the queue."""
    summary = result.get("summary", {})
    print(f"\n{'=' * 60}")
    print(f"  INBOUND QUEUE SUMMARY  ({result.get('generated_at', 'N/A')})")
    print(f"{'=' * 60}")
    print(f"  Total items: {summary.get('total_items', 0)}")

    print(f"\n  By Priority:")
    for pri in ("critical", "high", "medium", "low"):
        count = summary.get("by_priority", {}).get(pri, 0)
        if count:
            marker = "!!!" if pri == "critical" else (" !!" if pri == "high" else ("  !" if pri == "medium" else "   "))
            print(f"    {marker} {pri:10s} {count}")

    print(f"\n  By Category:")
    for cat, count in sorted(summary.get("by_category", {}).items(), key=lambda x: -x[1]):
        print(f"    {cat:20s} {count}")

    print(f"\n  By Source:")
    for src, count in sorted(summary.get("by_source", {}).items(), key=lambda x: -x[1]):
        print(f"    {src:12s} {count}")

    print(f"{'=' * 60}\n")


def _print_top_items(result: Dict[str, Any], n: int) -> None:
    """Print the top N queue items."""
    items = result.get("items", [])[:n]
    print(f"\n{'=' * 60}")
    print(f"  TOP {n} INBOUND ITEMS")
    print(f"{'=' * 60}")

    for i, item in enumerate(items, 1):
        pri = item.get("priority", "?")
        score = item.get("priority_score", 0)
        pri_tag = {
            "critical": "[CRITICAL]",
            "high": "[HIGH]    ",
            "medium": "[MEDIUM]  ",
            "low": "[LOW]     ",
        }.get(pri, "[?]       ")

        print(f"\n  {i:2d}. {pri_tag} (score: {score})")
        print(f"      {item.get('title', 'No title')}")
        print(f"      Source: {item.get('source', '?')} | Category: {item.get('category', '?')}")
        if item.get("detail"):
            detail = item["detail"]
            if len(detail) > 120:
                detail = detail[:117] + "..."
            print(f"      {detail}")
        print(f"      Action: {item.get('recommended_action', 'N/A')} [{item.get('action_type', 'none')}]")

    print(f"\n{'=' * 60}\n")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inbound Signal Queue — aggregate and prioritize action items"
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Print queue summary only (still generates the queue)",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=0,
        metavar="N",
        help="Show top N items after generation",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()

    result = generate_queue()

    if args.summary:
        _print_summary(result)
    elif args.top:
        _print_top_items(result, args.top)
        _print_summary(result)
    else:
        _print_summary(result)
        _print_top_items(result, min(10, len(result.get("items", []))))
