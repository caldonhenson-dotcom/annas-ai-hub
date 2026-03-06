"""
HubSpot CRM Data Fetcher — Incremental Sync
=============================================

Default mode: incremental — only fetches records modified since last sync,
merges them into the cached dataset. First run is always a full fetch.

Use --force-refresh for a complete re-fetch of all records.

Supports: contacts, companies, deals, engagements (calls, emails, meetings,
tasks, notes), owners, pipelines, associations, form submissions.
"""

import argparse
import json
import os
import sys
import time
import logging
from pathlib import Path
from typing import Any, List

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

sys.path.insert(0, str(BASE_DIR))
from scripts.lib.hubspot_client import HubSpotClient
from scripts.lib.sync_state import (
    get_last_sync_ms, load_cached_records, merge_records, save_sync_state,
)

# ---------- Property lists --------------------------------------------------

CONTACT_PROPS = [
    "firstname", "lastname", "email", "phone", "company",
    "lifecyclestage", "hs_lead_status", "hubspot_owner_id",
    "createdate", "lastmodifieddate",
    "hs_analytics_source", "hs_analytics_source_data_1",
    "hs_analytics_source_data_2",
    "hs_analytics_num_page_views", "hs_analytics_num_visits",
    "hs_analytics_num_event_completions",
    "hs_analytics_first_visit_timestamp",
    "hs_analytics_last_visit_timestamp",
    "hs_analytics_first_url", "hs_analytics_last_url",
    "hs_email_last_open_date", "hs_email_last_click_date",
    "hs_latest_meeting_activity", "notes_last_updated",
    "num_associated_deals",
    "hs_lifecyclestage_lead_date",
    "hs_lifecyclestage_marketingqualifiedlead_date",
    "hs_lifecyclestage_salesqualifiedlead_date",
    "hs_lifecyclestage_opportunity_date",
    "hs_lifecyclestage_customer_date",
    "first_conversion_event_name", "first_conversion_date",
    "recent_conversion_event_name", "recent_conversion_date",
]

COMPANY_PROPS = [
    "name", "domain", "industry", "annualrevenue",
    "numberofemployees", "lifecyclestage", "hubspot_owner_id",
    "createdate", "num_associated_contacts", "num_associated_deals",
    "hs_analytics_source", "total_revenue",
]

DEAL_PROPS = [
    "dealname", "dealstage", "pipeline", "amount",
    "closedate", "createdate", "hubspot_owner_id",
    "hs_deal_stage_probability", "hs_is_closed_won",
    "hs_is_closed", "hs_analytics_source",
    "hs_analytics_source_data_1", "dealtype",
    "hs_closed_amount", "hs_forecast_amount",
    "hs_forecast_probability", "hs_projected_amount",
    "hs_date_entered_appointmentscheduled",
    "hs_date_entered_qualifiedtobuy",
    "hs_date_entered_presentationscheduled",
    "hs_date_entered_decisionmakerboughtin",
    "hs_date_entered_contractsent",
    "hs_date_entered_closedwon",
    "hs_date_entered_closedlost",
    "hs_time_in_appointmentscheduled",
    "hs_time_in_qualifiedtobuy",
    "hs_time_in_presentationscheduled",
    "hs_time_in_decisionmakerboughtin",
    "hs_time_in_contractsent",
    "notes_last_updated",
    "closed_lost_reason", "closed_won_reason",
]

ENGAGEMENT_PROPS = {
    "calls": ["hs_call_title", "hs_call_duration", "hs_call_disposition",
              "hs_call_direction", "hs_timestamp", "hubspot_owner_id"],
    "emails": ["hs_email_subject", "hs_email_direction", "hs_email_status",
               "hs_timestamp", "hubspot_owner_id"],
    "meetings": ["hs_meeting_title", "hs_meeting_outcome",
                 "hs_meeting_start_time", "hs_meeting_end_time",
                 "hs_timestamp", "hubspot_owner_id"],
    "tasks": ["hs_task_subject", "hs_task_status", "hs_task_priority",
              "hs_timestamp", "hs_task_completion_date", "hubspot_owner_id"],
    "notes": ["hs_note_body", "hs_timestamp", "hubspot_owner_id"],
}


# ---------- Helpers ----------------------------------------------------------

def _write_raw(name: str, date_stamp: str, data: Any):
    payload = {
        "source": "hubspot",
        "object_type": name.replace("hubspot_", ""),
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


def _fetch_object_incremental(
    client: HubSpotClient, obj_type: str, props: List[str],
    since_ms: int, date_stamp: str, raw_name: str,
) -> List[dict]:
    """Fetch modified records and merge with cached full dataset."""
    updated = client.search_modified(obj_type, since_ms, props)
    if not updated:
        logger.info(f"No {obj_type} modified since last sync — using cache")
        cached = load_cached_records("hubspot", obj_type)
        if cached:
            _write_raw(raw_name, date_stamp, cached)
            return cached
    existing = load_cached_records("hubspot", obj_type)
    merged = merge_records(existing, updated)
    _write_raw(raw_name, date_stamp, merged)
    return merged


def _fetch_object_full(
    client: HubSpotClient, obj_type: str, props: List[str],
    date_stamp: str, raw_name: str,
) -> List[dict]:
    """Full-fetch all records for an object type."""
    logger.info(f"Fetching all {obj_type} ({len(props)} properties)...")
    records = client.paginate_all(
        f"/crm/v3/objects/{obj_type}",
        params={"properties": ",".join(props)},
    )
    logger.info(f"Fetched {len(records)} {obj_type}")
    _write_raw(raw_name, date_stamp, records)
    return records


# ---------- Main entry -------------------------------------------------------

def fetch_hubspot(force_refresh: bool = False):
    """Fetch HubSpot data. Incremental by default, full on --force-refresh."""
    api_key = os.getenv("HUBSPOT_API_KEY")
    if not api_key:
        logger.warning("Missing HUBSPOT_API_KEY environment variable")
        return

    client = HubSpotClient(api_key)
    client.probe_auth()
    date_stamp = time.strftime("%Y-%m-%d")
    sync_start_ms = int(time.time() * 1000)

    # Owners + pipelines: always full (cheap — 1-2 API calls)
    owners = client.paginate_all("/crm/v3/owners/")
    _write_raw("hubspot_owners", date_stamp, owners)
    logger.info(f"Fetched {len(owners)} owners")

    pipelines_data = client.get("/crm/v3/pipelines/deals")
    pipelines = pipelines_data.get("results", []) if pipelines_data else []
    _write_raw("hubspot_pipelines", date_stamp, pipelines)
    logger.info(f"Fetched {len(pipelines)} pipelines")

    # Determine sync mode
    last_sync = None if force_refresh else get_last_sync_ms("hubspot")
    incremental = last_sync is not None

    if incremental:
        logger.info(f"INCREMENTAL mode — fetching changes since {last_sync}")
        contacts = _fetch_object_incremental(
            client, "contacts", CONTACT_PROPS, last_sync, date_stamp, "hubspot_contacts")
        companies = _fetch_object_incremental(
            client, "companies", COMPANY_PROPS, last_sync, date_stamp, "hubspot_companies")
        deals = _fetch_object_incremental(
            client, "deals", DEAL_PROPS, last_sync, date_stamp, "hubspot_deals")
    else:
        logger.info("FULL mode — fetching all records")
        contacts = _fetch_object_full(client, "contacts", CONTACT_PROPS, date_stamp, "hubspot_contacts")
        companies = _fetch_object_full(client, "companies", COMPANY_PROPS, date_stamp, "hubspot_companies")
        deals = _fetch_object_full(client, "deals", DEAL_PROPS, date_stamp, "hubspot_deals")

    # Associations — only for modified records in incremental mode
    contact_ids = [str(c.get("id")) for c in contacts if c.get("id")]
    deal_ids = [str(d.get("id")) for d in deals if d.get("id")]
    contact_deal_assoc = client.fetch_associations("contacts", "deals", contact_ids)
    contact_company_assoc = client.fetch_associations("contacts", "companies", contact_ids)
    deal_company_assoc = client.fetch_associations("deals", "companies", deal_ids)
    _write_raw("hubspot_associations", date_stamp, {
        "contact_to_deal": contact_deal_assoc,
        "contact_to_company": contact_company_assoc,
        "deal_to_company": deal_company_assoc,
    })

    # Engagements
    for eng_type, props in ENGAGEMENT_PROPS.items():
        if incremental:
            _fetch_object_incremental(
                client, eng_type, props, last_sync, date_stamp, f"hubspot_{eng_type}")
        else:
            _fetch_object_full(client, eng_type, props, date_stamp, f"hubspot_{eng_type}")

    # Form submissions (always full — no lastmodifieddate filter available)
    try:
        logger.info("Fetching forms...")
        forms = client.paginate_all("/marketing/v3/forms")
        logger.info(f"Found {len(forms)} forms")
        all_subs = []
        for form in forms:
            fid = form.get("id")
            subs = client.paginate_all(f"/form-integrations/v1/submissions/forms/{fid}")
            for sub in subs:
                sub["_form_id"] = fid
                sub["_form_name"] = form.get("name", "")
            all_subs.extend(subs)
        _write_raw("hubspot_forms", date_stamp, all_subs)
        logger.info(f"Fetched {len(all_subs)} form submissions")
    except Exception as e:
        logger.warning(f"Form submissions fetch failed: {e}")

    # Save sync state
    save_sync_state("hubspot", {"last_sync_ms": sync_start_ms})
    logger.info("HubSpot extraction complete")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch HubSpot CRM data")
    parser.add_argument(
        "--force-refresh", action="store_true",
        help="Full re-fetch (ignore incremental cache)",
    )
    args = parser.parse_args()
    try:
        fetch_hubspot(force_refresh=args.force_refresh)
    except Exception as e:
        logger.error(f"HubSpot extraction failed: {e}", exc_info=True)
        sys.exit(1)
