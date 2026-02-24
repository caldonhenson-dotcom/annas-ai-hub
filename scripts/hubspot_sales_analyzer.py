"""
HubSpot Sales Data Analyzer
============================
Reads raw HubSpot JSON exports from data/raw/ and produces a comprehensive
sales metrics file at data/processed/hubspot_sales_metrics.json.

Exports:
    LeadAnalyzer, PipelineAnalyzer, ActivityAnalyzer, ContactAnalyzer,
    WebSignalsAnalyzer, InsightsAnalyzer, ReverseEngineeringModel,
    run_hubspot_analysis
"""

from __future__ import annotations

import glob
import json
import logging
import os
import re
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
RAW_DIR = BASE_DIR / "data" / "raw"
PROCESSED_DIR = BASE_DIR / "data" / "processed"

load_dotenv(BASE_DIR / ".env")

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default configuration
# ---------------------------------------------------------------------------
DEFAULT_CONFIG: Dict[str, Any] = {
    "revenue_target": {
        "monthly": 100_000,
        "quarterly": 300_000,
        "annual": 1_200_000,
    },
    "stale_deal_threshold_days": 30,
    "activity_targets": {
        "calls_per_rep_per_day": 15,
        "emails_per_rep_per_day": 25,
        "meetings_per_rep_per_week": 5,
    },
}

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _prop(obj: dict, key: str, default=None):
    """Safely retrieve a property from a HubSpot object."""
    return obj.get("properties", {}).get(key, default)


def _parse_ts(ts_str: Optional[str]) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp string to a timezone-aware datetime."""
    if not ts_str:
        return None
    try:
        # Handle ISO format with or without trailing Z / offset
        cleaned = ts_str.replace("Z", "+00:00")
        return datetime.fromisoformat(cleaned)
    except (ValueError, TypeError):
        return None


def _safe_float(val, default: float = 0.0) -> float:
    """Safely convert a value to float."""
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _safe_int(val, default: int = 0) -> int:
    """Safely convert a value to int."""
    if val is None:
        return default
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return default


def _days_between(dt1: Optional[datetime], dt2: Optional[datetime]) -> Optional[float]:
    """Return the number of days between two datetimes, or None."""
    if dt1 is None or dt2 is None:
        return None
    delta = abs((dt2 - dt1).total_seconds())
    return delta / 86400.0


def _date_key(dt: Optional[datetime]) -> Optional[str]:
    """Format a datetime as a 'YYYY-MM' string."""
    if dt is None:
        return None
    return dt.strftime("%Y-%m")


def _date_key_day(dt: Optional[datetime]) -> Optional[str]:
    """Format a datetime as a 'YYYY-MM-DD' string."""
    if dt is None:
        return None
    return dt.strftime("%Y-%m-%d")


def _safe_div(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Zero-safe division."""
    if denominator == 0:
        return default
    return numerator / denominator


def _now_utc() -> datetime:
    """Current UTC time, timezone-aware."""
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _find_latest_file(object_type: str) -> Optional[Path]:
    """Find the most recent date-stamped file for a given HubSpot object type.

    Pattern: hubspot_{object_type}_YYYY-MM-DD.json
    """
    pattern = str(RAW_DIR / f"hubspot_{object_type}_*.json")
    files = glob.glob(pattern)
    if not files:
        logger.warning("No files found for object type '%s' with pattern %s", object_type, pattern)
        return None

    # Extract dates and sort
    dated: List[Tuple[str, Path]] = []
    date_re = re.compile(r"hubspot_" + re.escape(object_type) + r"_(\d{4}-\d{2}-\d{2})\.json$")
    for fp in files:
        m = date_re.search(os.path.basename(fp))
        if m:
            dated.append((m.group(1), Path(fp)))

    if not dated:
        # Fall back to first match if no date pattern found
        return Path(files[0])

    dated.sort(key=lambda x: x[0], reverse=True)
    return dated[0][1]


def _load_json(object_type: str) -> Dict[str, Any]:
    """Load the most recent raw JSON file for a given HubSpot object type."""
    path = _find_latest_file(object_type)
    if path is None:
        logger.warning("No data file found for '%s'; returning empty result set.", object_type)
        return {"source": "hubspot", "object_type": object_type, "results": []}
    logger.info("Loading %s from %s", object_type, path)
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _build_owners_map(owners_data: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
    """Build a lookup dict  owner_id -> {id, firstName, lastName, email, name}."""
    owners_map: Dict[str, Dict[str, str]] = {}
    for owner in owners_data.get("results", []):
        oid = str(owner.get("id", ""))
        first = owner.get("firstName", "")
        last = owner.get("lastName", "")
        owners_map[oid] = {
            "id": oid,
            "firstName": first,
            "lastName": last,
            "email": owner.get("email", ""),
            "name": f"{first} {last}".strip(),
        }
    return owners_map


def _build_stage_map(pipelines_data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Build a lookup  stage_id -> {label, probability, isClosed, pipeline_id, pipeline_label}."""
    stage_map: Dict[str, Dict[str, Any]] = {}
    for pipeline in pipelines_data.get("results", []):
        pid = pipeline.get("id", "")
        plabel = pipeline.get("label", "")
        for stage in pipeline.get("stages", []):
            sid = stage.get("id", "")
            meta = stage.get("metadata", {})
            stage_map[sid] = {
                "label": stage.get("label", sid),
                "probability": _safe_float(meta.get("probability", "0")),
                "isClosed": meta.get("isClosed", "false") == "true",
                "displayOrder": stage.get("displayOrder", 0),
                "pipeline_id": pid,
                "pipeline_label": plabel,
            }
    return stage_map


# ============================================================================
# Analyzer Classes
# ============================================================================

class LeadAnalyzer:
    """Analyze lead generation, conversion, and funnel metrics."""

    def analyze(self, contacts: List[dict], owners_map: Dict[str, dict]) -> Dict[str, Any]:
        now = _now_utc()
        thirty_days_ago = now - timedelta(days=30)

        total_leads = len(contacts)
        new_leads_30d = 0
        leads_by_source: Counter = Counter()
        lead_status_dist: Counter = Counter()
        mql_count = 0
        sql_count = 0
        lead_to_mql_times: List[float] = []
        mql_to_sql_times: List[float] = []
        sql_to_opp_times: List[float] = []
        opp_to_customer_times: List[float] = []
        leads_over_time: Counter = Counter()
        lead_response_hours: List[float] = []

        # Known lifecycle stages (HubSpot may use labels or numeric IDs)
        lifecycle_mql_keywords = {"marketingqualifiedlead", "mql"}
        lifecycle_sql_keywords = {"salesqualifiedlead", "sql"}

        for c in contacts:
            create_dt = _parse_ts(_prop(c, "createdate"))
            if create_dt and create_dt >= thirty_days_ago:
                new_leads_30d += 1

            # Leads over time bucketed by month
            month_key = _date_key(create_dt)
            if month_key:
                leads_over_time[month_key] += 1

            # Source distribution
            source = _prop(c, "hs_analytics_source") or "UNKNOWN"
            leads_by_source[source] += 1

            # Lead status
            status = _prop(c, "hs_lead_status")
            if status:
                lead_status_dist[status] += 1

            # Lifecycle stage analysis for MQL / SQL counting
            lifecycle = (_prop(c, "lifecyclestage") or "").lower()
            if lifecycle in lifecycle_mql_keywords:
                mql_count += 1
            if lifecycle in lifecycle_sql_keywords:
                sql_count += 1
            # Also count anyone who has ever reached MQL/SQL dates
            mql_date = _parse_ts(_prop(c, "hs_lifecyclestage_marketingqualifiedlead_date"))
            sql_date = _parse_ts(_prop(c, "hs_lifecyclestage_salesqualifiedlead_date"))
            opp_date = _parse_ts(_prop(c, "hs_lifecyclestage_opportunity_date"))
            cust_date = _parse_ts(_prop(c, "hs_lifecyclestage_customer_date"))
            lead_date = _parse_ts(_prop(c, "hs_lifecyclestage_lead_date"))

            if mql_date:
                mql_count = max(mql_count, 1)  # ensure we count at least this one
            if sql_date:
                sql_count = max(sql_count, 1)

            # Time between stages
            if lead_date and mql_date:
                days = _days_between(lead_date, mql_date)
                if days is not None and days >= 0:
                    lead_to_mql_times.append(days)
            if mql_date and sql_date:
                days = _days_between(mql_date, sql_date)
                if days is not None and days >= 0:
                    mql_to_sql_times.append(days)
            if sql_date and opp_date:
                days = _days_between(sql_date, opp_date)
                if days is not None and days >= 0:
                    sql_to_opp_times.append(days)
            if opp_date and cust_date:
                days = _days_between(opp_date, cust_date)
                if days is not None and days >= 0:
                    opp_to_customer_times.append(days)

            # Lead response time: time from createdate to first conversion
            first_conv = _parse_ts(_prop(c, "first_conversion_date"))
            if create_dt and first_conv:
                hours = _days_between(create_dt, first_conv)
                if hours is not None:
                    lead_response_hours.append(hours * 24)

        # Deduplicate MQL/SQL counts -- the counter approach above can double-count.
        # Re-count properly:
        mql_count_actual = 0
        sql_count_actual = 0
        for c in contacts:
            mql_d = _parse_ts(_prop(c, "hs_lifecyclestage_marketingqualifiedlead_date"))
            sql_d = _parse_ts(_prop(c, "hs_lifecyclestage_salesqualifiedlead_date"))
            lc = (_prop(c, "lifecyclestage") or "").lower()
            if mql_d or lc in lifecycle_mql_keywords:
                mql_count_actual += 1
            if sql_d or lc in lifecycle_sql_keywords:
                sql_count_actual += 1

        mql_count = mql_count_actual
        sql_count = sql_count_actual

        lead_to_mql_rate = _safe_div(mql_count, total_leads)

        # Source effectiveness: for each source, what fraction became MQL
        source_mql: Counter = Counter()
        source_total: Counter = Counter()
        for c in contacts:
            src = _prop(c, "hs_analytics_source") or "UNKNOWN"
            source_total[src] += 1
            mql_d = _parse_ts(_prop(c, "hs_lifecyclestage_marketingqualifiedlead_date"))
            lc = (_prop(c, "lifecyclestage") or "").lower()
            if mql_d or lc in lifecycle_mql_keywords:
                source_mql[src] += 1

        source_effectiveness = {}
        for src in source_total:
            source_effectiveness[src] = {
                "total": source_total[src],
                "mqls": source_mql[src],
                "conversion_rate": _safe_div(source_mql[src], source_total[src]),
            }

        # Time in stage averages
        time_in_stage = {
            "lead_to_mql_days": _safe_div(sum(lead_to_mql_times), len(lead_to_mql_times)) if lead_to_mql_times else None,
            "mql_to_sql_days": _safe_div(sum(mql_to_sql_times), len(mql_to_sql_times)) if mql_to_sql_times else None,
            "sql_to_opp_days": _safe_div(sum(sql_to_opp_times), len(sql_to_opp_times)) if sql_to_opp_times else None,
            "opp_to_customer_days": _safe_div(sum(opp_to_customer_times), len(opp_to_customer_times)) if opp_to_customer_times else None,
        }

        avg_lead_response_hours = (
            _safe_div(sum(lead_response_hours), len(lead_response_hours))
            if lead_response_hours
            else None
        )

        # Conversion rates through the funnel
        conversion_rates = {
            "lead_to_mql": _safe_div(mql_count, total_leads),
            "mql_to_sql": _safe_div(sql_count, mql_count),
            "total_lead_to_sql": _safe_div(sql_count, total_leads),
        }

        return {
            "total_leads": total_leads,
            "new_leads_30d": new_leads_30d,
            "leads_by_source": dict(leads_by_source.most_common()),
            "lead_status_distribution": dict(lead_status_dist.most_common()),
            "lead_to_mql_rate": lead_to_mql_rate,
            "mql_count": mql_count,
            "sql_count": sql_count,
            "source_effectiveness": source_effectiveness,
            "time_in_stage": time_in_stage,
            "leads_over_time": dict(sorted(leads_over_time.items())),
            "avg_lead_response_hours": avg_lead_response_hours,
            "conversion_rates": conversion_rates,
        }


class PipelineAnalyzer:
    """Analyze the sales pipeline: velocity, value, stages, win rates."""

    def analyze(
        self,
        deals: List[dict],
        pipelines: Dict[str, Any],
        owners_map: Dict[str, dict],
        config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        config = config or DEFAULT_CONFIG
        now = _now_utc()
        stage_map = _build_stage_map(pipelines)
        stale_threshold = config.get("stale_deal_threshold_days", 30)

        total_pipeline_value = 0.0
        weighted_pipeline_value = 0.0
        deals_by_stage: Dict[str, Dict[str, Any]] = {}
        won_deals: List[dict] = []
        lost_deals: List[dict] = []
        open_deals: List[dict] = []
        sales_cycle_days: List[float] = []
        pipeline_by_owner: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {"name": "", "deal_count": 0, "total_value": 0.0, "weighted_value": 0.0}
        )
        stale_deals: List[dict] = []
        close_date_dist: Counter = Counter()

        for deal in deals:
            amount = _safe_float(_prop(deal, "amount"))
            stage_id = _prop(deal, "dealstage") or ""
            is_closed_won = (_prop(deal, "hs_is_closed_won") or "").lower() == "true"
            is_closed = (_prop(deal, "hs_is_closed") or "").lower() == "true"
            create_dt = _parse_ts(_prop(deal, "createdate"))
            close_dt = _parse_ts(_prop(deal, "closedate"))
            owner_id = _prop(deal, "hubspot_owner_id") or ""

            stage_info = stage_map.get(stage_id, {"label": stage_id, "probability": 0.0, "isClosed": is_closed})
            stage_label = stage_info["label"]
            probability = stage_info["probability"]

            # Classify deal
            if is_closed_won:
                won_deals.append(deal)
                if create_dt and close_dt:
                    days = _days_between(create_dt, close_dt)
                    if days is not None:
                        sales_cycle_days.append(days)
            elif is_closed:
                lost_deals.append(deal)
            else:
                open_deals.append(deal)
                total_pipeline_value += amount
                weighted_pipeline_value += amount * probability

                # Stale deal detection
                last_mod = _parse_ts(_prop(deal, "hs_lastmodifieddate"))
                if last_mod:
                    days_stale = _days_between(last_mod, now)
                    if days_stale is not None and days_stale > stale_threshold:
                        stale_deals.append({
                            "deal_id": deal.get("id"),
                            "dealname": _prop(deal, "dealname"),
                            "stage": stage_label,
                            "amount": amount,
                            "days_since_update": round(days_stale, 1),
                            "owner": owners_map.get(owner_id, {}).get("name", owner_id),
                        })

            # Deals by stage
            if stage_label not in deals_by_stage:
                deals_by_stage[stage_label] = {"count": 0, "total_value": 0.0, "probability": probability}
            deals_by_stage[stage_label]["count"] += 1
            deals_by_stage[stage_label]["total_value"] += amount

            # Pipeline by owner
            if owner_id:
                owner_info = owners_map.get(owner_id, {})
                entry = pipeline_by_owner[owner_id]
                entry["name"] = owner_info.get("name", owner_id)
                entry["deal_count"] += 1
                entry["total_value"] += amount
                if not is_closed:
                    entry["weighted_value"] += amount * probability

            # Close date distribution by month
            if close_dt:
                mk = _date_key(close_dt)
                if mk:
                    close_date_dist[mk] += 1

        total_closed = len(won_deals) + len(lost_deals)
        win_rate = _safe_div(len(won_deals), total_closed)

        won_amounts = [_safe_float(_prop(d, "amount")) for d in won_deals]
        avg_deal_size = _safe_div(sum(won_amounts), len(won_amounts)) if won_amounts else 0.0

        avg_sales_cycle_days = (
            _safe_div(sum(sales_cycle_days), len(sales_cycle_days))
            if sales_cycle_days
            else 0.0
        )

        # Pipeline velocity = (# open deals * avg deal size * win rate) / avg sales cycle days
        pipeline_velocity = _safe_div(
            len(open_deals) * avg_deal_size * win_rate,
            avg_sales_cycle_days,
        )

        # Pipeline coverage = total pipeline value / monthly revenue target
        monthly_target = config.get("revenue_target", {}).get("monthly", 100_000)
        pipeline_coverage = _safe_div(total_pipeline_value, monthly_target)

        return {
            "total_pipeline_value": round(total_pipeline_value, 2),
            "weighted_pipeline_value": round(weighted_pipeline_value, 2),
            "deals_by_stage": deals_by_stage,
            "win_rate": round(win_rate, 4),
            "avg_deal_size": round(avg_deal_size, 2),
            "avg_sales_cycle_days": round(avg_sales_cycle_days, 1),
            "pipeline_velocity": round(pipeline_velocity, 2),
            "pipeline_by_owner": dict(pipeline_by_owner),
            "stale_deals": stale_deals,
            "close_date_distribution": dict(sorted(close_date_dist.items())),
            "pipeline_coverage": round(pipeline_coverage, 2),
            "open_deals_count": len(open_deals),
            "won_deals_count": len(won_deals),
            "lost_deals_count": len(lost_deals),
        }


class ActivityAnalyzer:
    """Analyze sales team activity: calls, emails, meetings, tasks, notes."""

    def analyze(
        self,
        calls: List[dict],
        emails: List[dict],
        meetings: List[dict],
        tasks: List[dict],
        notes: List[dict],
        owners_map: Dict[str, dict],
    ) -> Dict[str, Any]:
        total_activities = len(calls) + len(emails) + len(meetings) + len(tasks) + len(notes)

        by_type = {
            "calls": len(calls),
            "emails": len(emails),
            "meetings": len(meetings),
            "tasks": len(tasks),
            "notes": len(notes),
        }

        # Aggregate by rep
        by_rep: Dict[str, Dict[str, int]] = defaultdict(
            lambda: {"calls": 0, "emails": 0, "meetings": 0, "tasks": 0, "notes": 0, "total": 0}
        )

        def _tally(items: List[dict], activity_type: str):
            for item in items:
                owner_id = _prop(item, "hubspot_owner_id") or "unassigned"
                owner_name = owners_map.get(owner_id, {}).get("name", owner_id)
                by_rep[owner_name][activity_type] += 1
                by_rep[owner_name]["total"] += 1

        _tally(calls, "calls")
        _tally(emails, "emails")
        _tally(meetings, "meetings")
        _tally(tasks, "tasks")
        _tally(notes, "notes")

        # Daily trend (aggregate all activity types by date)
        daily_trend: Counter = Counter()
        all_activities = (
            [(c, "hs_timestamp") for c in calls]
            + [(e, "hs_timestamp") for e in emails]
            + [(m, "hs_timestamp") for m in meetings]
            + [(t, "hs_timestamp") for t in tasks]
            + [(n, "hs_timestamp") for n in notes]
        )
        for item, ts_field in all_activities:
            ts = _parse_ts(_prop(item, ts_field))
            if ts is None:
                ts = _parse_ts(_prop(item, "hs_createdate"))
            if ts:
                day_key = ts.strftime("%Y-%m-%d")
                daily_trend[day_key] += 1

        # Touches per won deal -- placeholder: requires association data
        # Will be populated by the orchestrator if associations are available
        touches_per_won_deal: Optional[float] = None

        return {
            "total_activities": total_activities,
            "by_type": by_type,
            "by_rep": dict(by_rep),
            "daily_trend": dict(sorted(daily_trend.items())),
            "touches_per_won_deal": touches_per_won_deal,
        }


class ContactAnalyzer:
    """Analyze contacts and companies."""

    def analyze(
        self,
        contacts: List[dict],
        companies: List[dict],
        associations: Dict[str, Any],
        owners_map: Dict[str, dict],
    ) -> Dict[str, Any]:
        now = _now_utc()
        thirty_days_ago = now - timedelta(days=30)

        # Lifecycle distribution
        by_lifecycle: Counter = Counter()
        new_contacts_30d = 0
        engagement_scores: List[Tuple[str, str, int]] = []  # (id, name, score)

        for c in contacts:
            lc = _prop(c, "lifecyclestage") or "unknown"
            by_lifecycle[lc] += 1

            create_dt = _parse_ts(_prop(c, "createdate"))
            if create_dt and create_dt >= thirty_days_ago:
                new_contacts_30d += 1

            # Engagement score: page views + visits + event completions
            views = _safe_int(_prop(c, "hs_analytics_num_page_views"))
            visits = _safe_int(_prop(c, "hs_analytics_num_visits"))
            events = _safe_int(_prop(c, "hs_analytics_num_event_completions"))
            score = views + visits * 2 + events * 3
            if score > 0:
                name = f"{_prop(c, 'firstname', '')} {_prop(c, 'lastname', '')}".strip()
                engagement_scores.append((c.get("id", ""), name, score))

        # Top engaged contacts
        engagement_scores.sort(key=lambda x: x[2], reverse=True)
        top_engaged = [
            {"id": eid, "name": name, "engagement_score": score}
            for eid, name, score in engagement_scores[:25]
        ]

        # Companies summary
        industries: Counter = Counter()
        sizes: Counter = Counter()
        companies_with_deals = 0
        deal_to_company = associations.get("deal_to_company", {})
        company_ids_with_deals = set()
        for deal_id, company_ids in deal_to_company.items():
            if isinstance(company_ids, list):
                company_ids_with_deals.update(company_ids)
            else:
                company_ids_with_deals.add(str(company_ids))

        for comp in companies:
            ind = _prop(comp, "industry")
            if ind:
                industries[ind] += 1
            emp = _safe_int(_prop(comp, "numberofemployees"))
            if emp > 0:
                if emp <= 10:
                    sizes["1-10"] += 1
                elif emp <= 50:
                    sizes["11-50"] += 1
                elif emp <= 200:
                    sizes["51-200"] += 1
                elif emp <= 1000:
                    sizes["201-1000"] += 1
                else:
                    sizes["1000+"] += 1
            if comp.get("id") in company_ids_with_deals:
                companies_with_deals += 1

        companies_summary = {
            "total": len(companies),
            "with_deals": companies_with_deals,
            "by_industry": dict(industries.most_common(20)),
            "by_size": dict(sizes),
        }

        return {
            "by_lifecycle": dict(by_lifecycle.most_common()),
            "new_contacts_30d": new_contacts_30d,
            "top_engaged": top_engaged,
            "companies_summary": companies_summary,
        }


class WebSignalsAnalyzer:
    """Analyze web engagement signals: forms, page views, content attribution."""

    def analyze(
        self,
        contacts: List[dict],
        forms: List[dict],
        deals: List[dict],
        associations: Dict[str, Any],
    ) -> Dict[str, Any]:
        # Form submissions summary
        form_summary: Dict[str, Any] = {"total_forms": len(forms), "submissions": []}
        for form in forms:
            form_summary["submissions"].append({
                "id": form.get("id"),
                "name": _prop(form, "name") or form.get("name", "Unknown"),
            })

        # High-intent pages from first conversion events
        conversion_pages: Counter = Counter()
        visits_of_contacts_with_deals: List[int] = []
        contact_to_deal = associations.get("contact_to_deal", {})
        contact_ids_with_deals = set(contact_to_deal.keys())

        content_conversions: Counter = Counter()

        for c in contacts:
            first_conv = _prop(c, "first_conversion_event_name")
            if first_conv:
                conversion_pages[first_conv] += 1

            # Visits before deal for contacts associated with deals
            cid = c.get("id", "")
            if str(cid) in contact_ids_with_deals:
                visits = _safe_int(_prop(c, "hs_analytics_num_visits"))
                visits_of_contacts_with_deals.append(visits)

            # Content driving pipeline: first URL that led to a conversion
            first_url = _prop(c, "hs_analytics_first_url")
            if first_url and str(cid) in contact_ids_with_deals:
                content_conversions[first_url] += 1

        high_intent_pages = [
            {"page": page, "conversions": count}
            for page, count in conversion_pages.most_common(20)
        ]

        avg_visits_before_deal = (
            _safe_div(sum(visits_of_contacts_with_deals), len(visits_of_contacts_with_deals))
            if visits_of_contacts_with_deals
            else None
        )

        content_driving_pipeline = [
            {"url": url, "associated_deals_contacts": count}
            for url, count in content_conversions.most_common(20)
        ]

        return {
            "form_summary": form_summary,
            "high_intent_pages": high_intent_pages,
            "avg_visits_before_deal": avg_visits_before_deal,
            "content_driving_pipeline": content_driving_pipeline,
        }


class InsightsAnalyzer:
    """Generate actionable sales insights: win/loss, forecasts, cohort analysis."""

    def analyze(
        self,
        deals: List[dict],
        contacts: List[dict],
        owners_map: Dict[str, dict],
        pipelines: Dict[str, Any],
    ) -> Dict[str, Any]:
        stage_map = _build_stage_map(pipelines)

        # ----- Win / Loss Analysis -----
        won_deals = []
        lost_deals = []
        for d in deals:
            if (_prop(d, "hs_is_closed_won") or "").lower() == "true":
                won_deals.append(d)
            elif (_prop(d, "hs_is_closed") or "").lower() == "true":
                lost_deals.append(d)

        won_sources: Counter = Counter()
        for d in won_deals:
            won_sources[_prop(d, "hs_analytics_source") or "UNKNOWN"] += 1

        lost_reasons: Counter = Counter()
        for d in lost_deals:
            reason = _prop(d, "closed_lost_reason")
            if reason:
                lost_reasons[reason] += 1
            else:
                lost_reasons["Not specified"] += 1

        won_reasons: Counter = Counter()
        for d in won_deals:
            reason = _prop(d, "closed_won_reason")
            if reason:
                won_reasons[reason] += 1

        win_loss_analysis = {
            "won_count": len(won_deals),
            "lost_count": len(lost_deals),
            "won_by_source": dict(won_sources.most_common()),
            "lost_reasons": dict(lost_reasons.most_common()),
            "won_reasons": dict(won_reasons.most_common()),
            "win_rate": _safe_div(len(won_deals), len(won_deals) + len(lost_deals)),
        }

        # ----- Sales Cycle Trend -----
        # Group won deals by close month and compute avg cycle length
        cycle_by_month: Dict[str, List[float]] = defaultdict(list)
        for d in won_deals:
            create_dt = _parse_ts(_prop(d, "createdate"))
            close_dt = _parse_ts(_prop(d, "closedate"))
            if create_dt and close_dt:
                days = _days_between(create_dt, close_dt)
                mk = _date_key(close_dt)
                if days is not None and mk:
                    cycle_by_month[mk].append(days)

        sales_cycle_trend = {
            month: round(_safe_div(sum(vals), len(vals)), 1)
            for month, vals in sorted(cycle_by_month.items())
        }

        # ----- Deal Size Distribution -----
        all_amounts = [_safe_float(_prop(d, "amount")) for d in deals if _safe_float(_prop(d, "amount")) > 0]
        buckets = {"0-1000": 0, "1000-5000": 0, "5000-10000": 0, "10000-25000": 0, "25000-50000": 0, "50000+": 0}
        for a in all_amounts:
            if a < 1000:
                buckets["0-1000"] += 1
            elif a < 5000:
                buckets["1000-5000"] += 1
            elif a < 10000:
                buckets["5000-10000"] += 1
            elif a < 25000:
                buckets["10000-25000"] += 1
            elif a < 50000:
                buckets["25000-50000"] += 1
            else:
                buckets["50000+"] += 1

        deal_size_distribution = buckets

        # ----- Revenue Forecast -----
        # Simple forecast: open deals * probability
        forecast_total = 0.0
        forecast_by_month: Dict[str, float] = defaultdict(float)
        for d in deals:
            is_closed = (_prop(d, "hs_is_closed") or "").lower() == "true"
            if is_closed:
                continue
            amount = _safe_float(_prop(d, "amount"))
            stage_id = _prop(d, "dealstage") or ""
            prob = stage_map.get(stage_id, {}).get("probability", 0.0)
            weighted = amount * prob
            forecast_total += weighted
            close_dt = _parse_ts(_prop(d, "closedate"))
            mk = _date_key(close_dt) if close_dt else "unscheduled"
            forecast_by_month[mk] += weighted

        revenue_forecast = {
            "weighted_forecast_total": round(forecast_total, 2),
            "by_expected_close_month": {k: round(v, 2) for k, v in sorted(forecast_by_month.items())},
        }

        # ----- Rep Performance -----
        rep_deals: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {
                "name": "",
                "won": 0,
                "lost": 0,
                "open": 0,
                "total_won_value": 0.0,
                "total_pipeline_value": 0.0,
                "avg_cycle_days": [],
                "win_rate": 0.0,
            }
        )
        for d in deals:
            owner_id = _prop(d, "hubspot_owner_id") or "unassigned"
            owner_name = owners_map.get(owner_id, {}).get("name", owner_id)
            entry = rep_deals[owner_id]
            entry["name"] = owner_name

            is_won = (_prop(d, "hs_is_closed_won") or "").lower() == "true"
            is_closed = (_prop(d, "hs_is_closed") or "").lower() == "true"

            if is_won:
                entry["won"] += 1
                entry["total_won_value"] += _safe_float(_prop(d, "amount"))
                create_dt = _parse_ts(_prop(d, "createdate"))
                close_dt = _parse_ts(_prop(d, "closedate"))
                if create_dt and close_dt:
                    days = _days_between(create_dt, close_dt)
                    if days is not None:
                        entry["avg_cycle_days"].append(days)
            elif is_closed:
                entry["lost"] += 1
            else:
                entry["open"] += 1
                entry["total_pipeline_value"] += _safe_float(_prop(d, "amount"))

        rep_performance = {}
        for rid, data in rep_deals.items():
            cycle_list = data.pop("avg_cycle_days")
            data["avg_cycle_days"] = round(_safe_div(sum(cycle_list), len(cycle_list)), 1) if cycle_list else None
            total_closed = data["won"] + data["lost"]
            data["win_rate"] = round(_safe_div(data["won"], total_closed), 4)
            data["total_won_value"] = round(data["total_won_value"], 2)
            data["total_pipeline_value"] = round(data["total_pipeline_value"], 2)
            rep_performance[rid] = data

        # ----- Cohort Analysis -----
        # Group deals by creation month; show outcome distribution
        cohort_data: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {"created": 0, "won": 0, "lost": 0, "open": 0, "total_value": 0.0}
        )
        for d in deals:
            create_dt = _parse_ts(_prop(d, "createdate"))
            mk = _date_key(create_dt) if create_dt else "unknown"
            cohort_data[mk]["created"] += 1
            cohort_data[mk]["total_value"] += _safe_float(_prop(d, "amount"))
            is_won = (_prop(d, "hs_is_closed_won") or "").lower() == "true"
            is_closed = (_prop(d, "hs_is_closed") or "").lower() == "true"
            if is_won:
                cohort_data[mk]["won"] += 1
            elif is_closed:
                cohort_data[mk]["lost"] += 1
            else:
                cohort_data[mk]["open"] += 1

        cohort_analysis = {
            k: {**v, "total_value": round(v["total_value"], 2), "win_rate": round(_safe_div(v["won"], v["won"] + v["lost"]), 4)}
            for k, v in sorted(cohort_data.items())
        }

        return {
            "win_loss_analysis": win_loss_analysis,
            "sales_cycle_trend": sales_cycle_trend,
            "deal_size_distribution": deal_size_distribution,
            "revenue_forecast": revenue_forecast,
            "rep_performance": rep_performance,
            "cohort_analysis": cohort_analysis,
        }


class ReverseEngineeringModel:
    """Reverse-engineer the required top-of-funnel volume to hit revenue targets.

    Math:
        Required Deals  = Target / Avg Deal Size
        Required Opps   = Deals / Win Rate
        Required SQLs   = Opps / SQL-to-Opp Rate
        Required MQLs   = SQLs / MQL-to-SQL Rate
        Required Leads  = MQLs / Lead-to-MQL Rate
    """

    def compute_targets(
        self,
        pipeline_metrics: Dict[str, Any],
        lead_metrics: Dict[str, Any],
        config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        config = config or DEFAULT_CONFIG
        revenue_targets = config.get("revenue_target", DEFAULT_CONFIG["revenue_target"])

        # Extract rates from metrics
        avg_deal_size = pipeline_metrics.get("avg_deal_size", 0)
        win_rate = pipeline_metrics.get("win_rate", 0)
        conversion_rates = lead_metrics.get("conversion_rates", {})
        lead_to_mql = conversion_rates.get("lead_to_mql", 0)
        mql_to_sql = conversion_rates.get("mql_to_sql", 0)
        # Estimate SQL-to-Opp rate: if we don't have explicit data, use a reasonable proxy
        # In many funnels SQL ~= Opp, so default to 0.5 if unknown
        sql_to_opp = conversion_rates.get("sql_to_opp", 0.5)

        annual_target = revenue_targets.get("annual", 1_200_000)
        quarterly_target = revenue_targets.get("quarterly", 300_000)
        monthly_target = revenue_targets.get("monthly", 100_000)

        def _funnel(target: float) -> Dict[str, Any]:
            required_deals = _safe_div(target, avg_deal_size) if avg_deal_size > 0 else 0
            required_opps = _safe_div(required_deals, win_rate) if win_rate > 0 else 0
            required_sqls = _safe_div(required_opps, sql_to_opp) if sql_to_opp > 0 else 0
            required_mqls = _safe_div(required_sqls, mql_to_sql) if mql_to_sql > 0 else 0
            required_leads = _safe_div(required_mqls, lead_to_mql) if lead_to_mql > 0 else 0
            return {
                "revenue_target": target,
                "required_deals": round(required_deals, 1),
                "required_opps": round(required_opps, 1),
                "required_sqls": round(required_sqls, 1),
                "required_mqls": round(required_mqls, 1),
                "required_leads": round(required_leads, 1),
            }

        annual = _funnel(annual_target)
        quarterly = _funnel(quarterly_target)
        monthly = _funnel(monthly_target)

        # Gap analysis: compare current metrics to requirements
        current_leads = lead_metrics.get("total_leads", 0)
        current_mqls = lead_metrics.get("mql_count", 0)
        current_sqls = lead_metrics.get("sql_count", 0)
        current_pipeline = pipeline_metrics.get("total_pipeline_value", 0)
        current_won = pipeline_metrics.get("won_deals_count", 0)

        gap_analysis = {
            "leads_gap_annual": round(annual["required_leads"] - current_leads, 1),
            "mqls_gap_annual": round(annual["required_mqls"] - current_mqls, 1),
            "sqls_gap_annual": round(annual["required_sqls"] - current_sqls, 1),
            "pipeline_gap_annual": round(annual_target - current_pipeline, 2),
            "current_vs_required": {
                "leads": {"current": current_leads, "required_annual": annual["required_leads"]},
                "mqls": {"current": current_mqls, "required_annual": annual["required_mqls"]},
                "sqls": {"current": current_sqls, "required_annual": annual["required_sqls"]},
                "pipeline_value": {"current": current_pipeline, "required_annual": annual_target},
                "won_deals": {"current": current_won, "required_annual": annual["required_deals"]},
            },
        }

        # Daily and weekly requirements (based on monthly target, ~22 working days/month)
        working_days_per_month = 22
        weeks_per_month = 4.33

        daily_requirements = {
            "leads": round(_safe_div(monthly["required_leads"], working_days_per_month), 1),
            "mqls": round(_safe_div(monthly["required_mqls"], working_days_per_month), 1),
            "sqls": round(_safe_div(monthly["required_sqls"], working_days_per_month), 1),
            "deals_to_close": round(_safe_div(monthly["required_deals"], working_days_per_month), 1),
        }

        weekly_requirements = {
            "leads": round(_safe_div(monthly["required_leads"], weeks_per_month), 1),
            "mqls": round(_safe_div(monthly["required_mqls"], weeks_per_month), 1),
            "sqls": round(_safe_div(monthly["required_sqls"], weeks_per_month), 1),
            "deals_to_close": round(_safe_div(monthly["required_deals"], weeks_per_month), 1),
        }

        # What-if scenarios: impact of 10%, 20%, 30% improvement in conversion rates
        what_if_scenarios = []
        for improvement_pct in [10, 20, 30]:
            factor = 1 + improvement_pct / 100.0
            improved_lead_to_mql = min(lead_to_mql * factor, 1.0)
            improved_mql_to_sql = min(mql_to_sql * factor, 1.0)
            improved_win_rate = min(win_rate * factor, 1.0)

            # Recalculate with improved rates for monthly target
            imp_deals = _safe_div(monthly_target, avg_deal_size) if avg_deal_size > 0 else 0
            imp_opps = _safe_div(imp_deals, improved_win_rate) if improved_win_rate > 0 else 0
            imp_sqls = _safe_div(imp_opps, sql_to_opp) if sql_to_opp > 0 else 0
            imp_mqls = _safe_div(imp_sqls, improved_mql_to_sql) if improved_mql_to_sql > 0 else 0
            imp_leads = _safe_div(imp_mqls, improved_lead_to_mql) if improved_lead_to_mql > 0 else 0

            lead_reduction = monthly["required_leads"] - imp_leads
            lead_reduction_pct = _safe_div(lead_reduction, monthly["required_leads"]) * 100

            what_if_scenarios.append({
                "improvement_pct": improvement_pct,
                "improved_rates": {
                    "lead_to_mql": round(improved_lead_to_mql, 4),
                    "mql_to_sql": round(improved_mql_to_sql, 4),
                    "win_rate": round(improved_win_rate, 4),
                },
                "required_leads_monthly": round(imp_leads, 1),
                "required_mqls_monthly": round(imp_mqls, 1),
                "lead_reduction_vs_baseline": round(lead_reduction, 1),
                "lead_reduction_pct": round(lead_reduction_pct, 1),
            })

        return {
            "revenue_target": revenue_targets,
            "required_deals": annual["required_deals"],
            "required_opps": annual["required_opps"],
            "required_sqls": annual["required_sqls"],
            "required_mqls": annual["required_mqls"],
            "required_leads": annual["required_leads"],
            "gap_analysis": gap_analysis,
            "daily_requirements": daily_requirements,
            "weekly_requirements": weekly_requirements,
            "what_if_scenarios": what_if_scenarios,
            "funnel_detail": {
                "annual": annual,
                "quarterly": quarterly,
                "monthly": monthly,
            },
            "assumptions": {
                "avg_deal_size": avg_deal_size,
                "win_rate": win_rate,
                "lead_to_mql_rate": lead_to_mql,
                "mql_to_sql_rate": mql_to_sql,
                "sql_to_opp_rate": sql_to_opp,
            },
        }


class TimeSeriesCollector:
    """Collect daily- and monthly-bucketed time-series data for all key metrics.

    The output powers interactive time-period filtering (This Week, Last Week,
    MTD, YTD, Last Year) and YoY comparisons in the dashboard.
    """

    def collect(
        self,
        contacts: List[dict],
        companies: List[dict],
        deals: List[dict],
        calls: List[dict],
        emails: List[dict],
        meetings: List[dict],
        tasks: List[dict],
        notes: List[dict],
        forms: List[dict],
        associations: Dict[str, Any],
        owners_map: Dict[str, dict],
        pipelines_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        # ---- Leads / contacts by day ----
        leads_by_day: Counter = Counter()
        contacts_created_by_day: Counter = Counter()
        leads_by_source_by_month: Dict[str, Counter] = defaultdict(Counter)
        mqls_by_day: Counter = Counter()
        sqls_by_day: Counter = Counter()

        lifecycle_mql_keywords = {"marketingqualifiedlead", "mql"}
        lifecycle_sql_keywords = {"salesqualifiedlead", "sql"}

        for c in contacts:
            create_dt = _parse_ts(_prop(c, "createdate"))
            day_key = _date_key_day(create_dt)
            month_key = _date_key(create_dt)

            if day_key:
                leads_by_day[day_key] += 1
                contacts_created_by_day[day_key] += 1

            # Source by month
            if month_key:
                source = _prop(c, "hs_analytics_source") or "UNKNOWN"
                leads_by_source_by_month[month_key][source] += 1

            # MQLs by day
            mql_date = _parse_ts(
                _prop(c, "hs_lifecyclestage_marketingqualifiedlead_date")
            )
            lc = (_prop(c, "lifecyclestage") or "").lower()
            if mql_date:
                mql_day = _date_key_day(mql_date)
                if mql_day:
                    mqls_by_day[mql_day] += 1
            elif lc in lifecycle_mql_keywords and day_key:
                # Fallback: use createdate if no explicit MQL date
                mqls_by_day[day_key] += 1

            # SQLs by day
            sql_date = _parse_ts(
                _prop(c, "hs_lifecyclestage_salesqualifiedlead_date")
            )
            if sql_date:
                sql_day = _date_key_day(sql_date)
                if sql_day:
                    sqls_by_day[sql_day] += 1
            elif lc in lifecycle_sql_keywords and day_key:
                sqls_by_day[day_key] += 1

        # ---- Deals: created, won, lost by day; revenue & pipeline by month ----
        deals_created_by_day: Counter = Counter()
        deals_won_by_day: Counter = Counter()
        deals_won_value_by_day: Dict[str, float] = defaultdict(float)
        deals_lost_by_day: Counter = Counter()
        revenue_won_by_month: Dict[str, float] = defaultdict(float)
        pipeline_value_by_month: Dict[str, float] = defaultdict(float)
        deals_by_stage_by_month: Dict[str, Dict[str, Dict[str, Any]]] = defaultdict(
            lambda: defaultdict(lambda: {"count": 0, "value": 0.0})
        )

        stage_map = _build_stage_map(pipelines_data)

        for deal in deals:
            amount = _safe_float(_prop(deal, "amount"))
            create_dt = _parse_ts(_prop(deal, "createdate"))
            close_dt = _parse_ts(_prop(deal, "closedate"))
            is_closed_won = (_prop(deal, "hs_is_closed_won") or "").lower() == "true"
            is_closed = (_prop(deal, "hs_is_closed") or "").lower() == "true"
            stage_id = _prop(deal, "dealstage") or ""
            stage_info = stage_map.get(
                stage_id, {"label": stage_id, "probability": 0.0, "isClosed": is_closed}
            )
            stage_label = stage_info["label"]

            # Created by day
            create_day = _date_key_day(create_dt)
            if create_day:
                deals_created_by_day[create_day] += 1

            # Won / lost by day (use closedate)
            if is_closed_won and close_dt:
                close_day = _date_key_day(close_dt)
                close_month = _date_key(close_dt)
                if close_day:
                    deals_won_by_day[close_day] += 1
                    deals_won_value_by_day[close_day] += amount
                if close_month:
                    revenue_won_by_month[close_month] += amount
            elif is_closed and close_dt:
                close_day = _date_key_day(close_dt)
                if close_day:
                    deals_lost_by_day[close_day] += 1

            # Pipeline value by month (open deals grouped by create month)
            if not is_closed:
                create_month = _date_key(create_dt)
                if create_month:
                    pipeline_value_by_month[create_month] += amount

            # Deals by stage by month (use create month)
            create_month = _date_key(create_dt)
            if create_month:
                entry = deals_by_stage_by_month[create_month][stage_label]
                entry["count"] += 1
                entry["value"] = round(entry["value"] + amount, 2)

        # ---- Activities by type by day & by rep by month ----
        activities_by_type_by_day: Dict[str, Dict[str, int]] = defaultdict(
            lambda: {"calls": 0, "emails": 0, "meetings": 0, "tasks": 0, "notes": 0}
        )
        activities_by_rep_by_month: Dict[str, Dict[str, Dict[str, int]]] = defaultdict(
            lambda: defaultdict(
                lambda: {"calls": 0, "emails": 0, "meetings": 0, "tasks": 0, "notes": 0}
            )
        )

        activity_sets = [
            (calls, "calls"),
            (emails, "emails"),
            (meetings, "meetings"),
            (tasks, "tasks"),
            (notes, "notes"),
        ]

        for items, activity_type in activity_sets:
            for item in items:
                ts = _parse_ts(_prop(item, "hs_timestamp"))
                if ts is None:
                    ts = _parse_ts(_prop(item, "hs_createdate"))
                if ts is None:
                    continue

                day_key = _date_key_day(ts)
                month_key = _date_key(ts)

                if day_key:
                    activities_by_type_by_day[day_key][activity_type] += 1

                # By rep by month
                if month_key:
                    owner_id = _prop(item, "hubspot_owner_id") or "unassigned"
                    owner_name = owners_map.get(owner_id, {}).get("name", owner_id)
                    activities_by_rep_by_month[month_key][owner_name][activity_type] += 1

        # ---- Assemble & sort all dicts chronologically ----
        # Convert defaultdicts with nested structures to plain sorted dicts
        sorted_leads_by_source_by_month = dict(sorted(
            (month, dict(sorted(sources.items())))
            for month, sources in leads_by_source_by_month.items()
        ))

        sorted_activities_by_type_by_day = dict(sorted(
            (day, dict(counts))
            for day, counts in activities_by_type_by_day.items()
        ))

        sorted_activities_by_rep_by_month = dict(sorted(
            (month, dict(sorted(
                (rep, dict(counts))
                for rep, counts in reps.items()
            )))
            for month, reps in activities_by_rep_by_month.items()
        ))

        sorted_deals_by_stage_by_month = dict(sorted(
            (month, dict(sorted(
                (stage, dict(info))
                for stage, info in stages.items()
            )))
            for month, stages in deals_by_stage_by_month.items()
        ))

        sorted_deals_won_value_by_day = dict(sorted(
            (day, round(val, 2))
            for day, val in deals_won_value_by_day.items()
        ))

        sorted_revenue_won_by_month = dict(sorted(
            (month, round(val, 2))
            for month, val in revenue_won_by_month.items()
        ))

        sorted_pipeline_value_by_month = dict(sorted(
            (month, round(val, 2))
            for month, val in pipeline_value_by_month.items()
        ))

        return {
            "leads_by_day": dict(sorted(leads_by_day.items())),
            "leads_by_source_by_month": sorted_leads_by_source_by_month,
            "deals_created_by_day": dict(sorted(deals_created_by_day.items())),
            "deals_won_by_day": dict(sorted(deals_won_by_day.items())),
            "deals_won_value_by_day": sorted_deals_won_value_by_day,
            "deals_lost_by_day": dict(sorted(deals_lost_by_day.items())),
            "activities_by_type_by_day": sorted_activities_by_type_by_day,
            "contacts_created_by_day": dict(sorted(contacts_created_by_day.items())),
            "revenue_won_by_month": sorted_revenue_won_by_month,
            "pipeline_value_by_month": sorted_pipeline_value_by_month,
            "activities_by_rep_by_month": sorted_activities_by_rep_by_month,
            "deals_by_stage_by_month": sorted_deals_by_stage_by_month,
            "mqls_by_day": dict(sorted(mqls_by_day.items())),
            "sqls_by_day": dict(sorted(sqls_by_day.items())),
        }


def _compute_yoy_summary(time_series: Dict[str, Any]) -> Dict[str, Any]:
    """Pre-compute Year-over-Year comparisons from time-series data.

    Compares Jan 1 to today of the current year vs Jan 1 to the same
    calendar date of the previous year.
    """
    now = _now_utc()
    current_year = now.year
    previous_year = current_year - 1

    # Build date boundaries
    current_ytd_start = f"{current_year}-01-01"
    current_ytd_end = now.strftime("%Y-%m-%d")
    previous_ytd_start = f"{previous_year}-01-01"
    # Same month-day in previous year
    previous_ytd_end = f"{previous_year}-{now.strftime('%m-%d')}"

    def _sum_daily(series: Dict[str, Any], start: str, end: str) -> float:
        """Sum values in a daily-keyed dict between start and end (inclusive)."""
        total = 0.0
        for date_str, val in series.items():
            if start <= date_str <= end:
                total += _safe_float(val)
        return total

    def _count_daily(series: Dict[str, Any], start: str, end: str) -> int:
        """Count entries in a daily-keyed dict between start and end (inclusive)."""
        total = 0
        for date_str, val in series.items():
            if start <= date_str <= end:
                total += int(val) if isinstance(val, (int, float)) else 0
        return total

    def _sum_activities_daily(series: Dict[str, Dict[str, int]], start: str, end: str) -> int:
        """Sum all activity counts in the activities_by_type_by_day series."""
        total = 0
        for date_str, type_counts in series.items():
            if start <= date_str <= end:
                total += sum(type_counts.values())
        return total

    def _change_pct(current: float, previous: float) -> Optional[float]:
        """Calculate percentage change, returning None if previous is zero."""
        if previous == 0:
            return None if current == 0 else 100.0
        return round(((current - previous) / previous) * 100, 1)

    # Leads (contacts created)
    leads_current = _count_daily(
        time_series.get("leads_by_day", {}), current_ytd_start, current_ytd_end
    )
    leads_previous = _count_daily(
        time_series.get("leads_by_day", {}), previous_ytd_start, previous_ytd_end
    )

    # Deals won
    deals_won_current = _count_daily(
        time_series.get("deals_won_by_day", {}), current_ytd_start, current_ytd_end
    )
    deals_won_previous = _count_daily(
        time_series.get("deals_won_by_day", {}), previous_ytd_start, previous_ytd_end
    )

    # Revenue won
    revenue_current = _sum_daily(
        time_series.get("deals_won_value_by_day", {}), current_ytd_start, current_ytd_end
    )
    revenue_previous = _sum_daily(
        time_series.get("deals_won_value_by_day", {}), previous_ytd_start, previous_ytd_end
    )

    # Activities
    activities_current = _sum_activities_daily(
        time_series.get("activities_by_type_by_day", {}), current_ytd_start, current_ytd_end
    )
    activities_previous = _sum_activities_daily(
        time_series.get("activities_by_type_by_day", {}), previous_ytd_start, previous_ytd_end
    )

    # Contacts created
    contacts_current = _count_daily(
        time_series.get("contacts_created_by_day", {}), current_ytd_start, current_ytd_end
    )
    contacts_previous = _count_daily(
        time_series.get("contacts_created_by_day", {}), previous_ytd_start, previous_ytd_end
    )

    # MQLs
    mqls_current = _count_daily(
        time_series.get("mqls_by_day", {}), current_ytd_start, current_ytd_end
    )
    mqls_previous = _count_daily(
        time_series.get("mqls_by_day", {}), previous_ytd_start, previous_ytd_end
    )

    # Average deal size (revenue / deals won)
    avg_deal_current = round(
        _safe_div(revenue_current, deals_won_current), 2
    ) if deals_won_current > 0 else 0.0
    avg_deal_previous = round(
        _safe_div(revenue_previous, deals_won_previous), 2
    ) if deals_won_previous > 0 else 0.0

    return {
        "leads": {
            "current_ytd": leads_current,
            "previous_ytd": leads_previous,
            "change_pct": _change_pct(leads_current, leads_previous),
        },
        "deals_won": {
            "current_ytd": deals_won_current,
            "previous_ytd": deals_won_previous,
            "change_pct": _change_pct(deals_won_current, deals_won_previous),
        },
        "revenue_won": {
            "current_ytd": round(revenue_current, 2),
            "previous_ytd": round(revenue_previous, 2),
            "change_pct": _change_pct(revenue_current, revenue_previous),
        },
        "activities": {
            "current_ytd": activities_current,
            "previous_ytd": activities_previous,
            "change_pct": _change_pct(activities_current, activities_previous),
        },
        "contacts_created": {
            "current_ytd": contacts_current,
            "previous_ytd": contacts_previous,
            "change_pct": _change_pct(contacts_current, contacts_previous),
        },
        "mqls": {
            "current_ytd": mqls_current,
            "previous_ytd": mqls_previous,
            "change_pct": _change_pct(mqls_current, mqls_previous),
        },
        "avg_deal_size": {
            "current_ytd": avg_deal_current,
            "previous_ytd": avg_deal_previous,
            "change_pct": _change_pct(avg_deal_current, avg_deal_previous),
        },
    }


# ============================================================================
# Main orchestration
# ============================================================================

def run_hubspot_analysis(config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Load all HubSpot data, run every analyzer, and save the output.

    Returns the full metrics dictionary.
    """
    config = config or DEFAULT_CONFIG
    logger.info("Starting HubSpot sales analysis")

    # ------------------------------------------------------------------
    # 1. Load raw data
    # ------------------------------------------------------------------
    logger.info("Loading raw data files from %s", RAW_DIR)
    contacts_data = _load_json("contacts")
    companies_data = _load_json("companies")
    deals_data = _load_json("deals")
    owners_data = _load_json("owners")
    pipelines_data = _load_json("pipelines")
    calls_data = _load_json("calls")
    emails_data = _load_json("emails")
    meetings_data = _load_json("meetings")
    tasks_data = _load_json("tasks")
    notes_data = _load_json("notes")
    forms_data = _load_json("forms")
    associations_data = _load_json("associations")

    contacts = contacts_data.get("results", [])
    companies = companies_data.get("results", [])
    deals = deals_data.get("results", [])
    calls = calls_data.get("results", [])
    emails = emails_data.get("results", [])
    meetings = meetings_data.get("results", [])
    tasks = tasks_data.get("results", [])
    notes = notes_data.get("results", [])
    forms = forms_data.get("results", [])
    associations = associations_data.get("results", {})
    if isinstance(associations, list):
        associations = {}

    owners_map = _build_owners_map(owners_data)

    logger.info(
        "Loaded: %d contacts, %d companies, %d deals, %d owners, "
        "%d calls, %d emails, %d meetings, %d tasks, %d notes, %d forms",
        len(contacts), len(companies), len(deals), len(owners_map),
        len(calls), len(emails), len(meetings), len(tasks), len(notes), len(forms),
    )

    # ------------------------------------------------------------------
    # 2. Run analyzers
    # ------------------------------------------------------------------
    logger.info("Running LeadAnalyzer...")
    lead_metrics = LeadAnalyzer().analyze(contacts, owners_map)

    logger.info("Running PipelineAnalyzer...")
    pipeline_metrics = PipelineAnalyzer().analyze(deals, pipelines_data, owners_map, config)

    logger.info("Running ActivityAnalyzer...")
    activity_metrics = ActivityAnalyzer().analyze(calls, emails, meetings, tasks, notes, owners_map)

    logger.info("Running ContactAnalyzer...")
    contact_metrics = ContactAnalyzer().analyze(contacts, companies, associations, owners_map)

    logger.info("Running WebSignalsAnalyzer...")
    web_metrics = WebSignalsAnalyzer().analyze(contacts, forms, deals, associations)

    logger.info("Running InsightsAnalyzer...")
    insights_metrics = InsightsAnalyzer().analyze(deals, contacts, owners_map, pipelines_data)

    logger.info("Running ReverseEngineeringModel...")
    reverse_eng = ReverseEngineeringModel().compute_targets(pipeline_metrics, lead_metrics, config)

    logger.info("Running TimeSeriesCollector...")
    time_series = TimeSeriesCollector().collect(
        contacts, companies, deals, calls, emails, meetings, tasks, notes,
        forms, associations, owners_map, pipelines_data,
    )

    logger.info("Computing YoY summary...")
    yoy_summary = _compute_yoy_summary(time_series)

    # ------------------------------------------------------------------
    # 3. Assemble output
    # ------------------------------------------------------------------
    output = {
        "generated_at": _now_utc().isoformat(),
        "data_source": "hubspot",
        "record_counts": {
            "contacts": len(contacts),
            "companies": len(companies),
            "deals": len(deals),
            "owners": len(owners_map),
            "calls": len(calls),
            "emails": len(emails),
            "meetings": len(meetings),
            "tasks": len(tasks),
            "notes": len(notes),
            "forms": len(forms),
        },
        "lead_metrics": lead_metrics,
        "pipeline_metrics": pipeline_metrics,
        "activity_metrics": activity_metrics,
        "contact_metrics": contact_metrics,
        "web_signals": web_metrics,
        "insights": insights_metrics,
        "reverse_engineering": reverse_eng,
        "time_series": time_series,
        "yoy_summary": yoy_summary,
        "config_used": config,
    }

    # ------------------------------------------------------------------
    # 4. Save to processed directory
    # ------------------------------------------------------------------
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    output_path = PROCESSED_DIR / "hubspot_sales_metrics.json"
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(output, fh, indent=2, default=str)

    logger.info("Analysis complete. Output saved to %s", output_path)

    # ------------------------------------------------------------------
    # 5. Sync to normalised Supabase tables
    # ------------------------------------------------------------------
    try:
        from scripts.lib.data_sync import sync_hubspot_to_supabase
        sync_results = sync_hubspot_to_supabase()
        logger.info("Normalised sync: %s", sync_results)
    except Exception as e:
        logger.warning("Normalised data sync failed (non-fatal): %s", e)

    return output


# ============================================================================
# Standalone entry point
# ============================================================================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    results = run_hubspot_analysis()
    print(f"\nAnalysis complete. {results['record_counts']['deals']} deals processed.")
    print(f"Output: {PROCESSED_DIR / 'hubspot_sales_metrics.json'}")
