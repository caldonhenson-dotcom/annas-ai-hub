"""
HubSpot CRM Data Fetcher
========================

Connects to HubSpot API v3 via Private App token.
Pulls contacts, companies, deals, engagements (calls, emails, meetings,
tasks, notes), owners, pipelines, form submissions and web analytics.
Handles pagination (100 records/page) and rate limiting (100 req/10s).
"""

import json
import os
import sys
import time
import logging
import requests
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any

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

HUBSPOT_BASE_URL = "https://api.hubapi.com"
HUBSPOT_PAGE_LIMIT = 100
HUBSPOT_RATE_LIMIT = 100
HUBSPOT_RATE_WINDOW = 10  # seconds


class HubSpotClient:
    """HubSpot API v3 client with pagination and rate limiting."""

    def __init__(self, api_key: str, base_url: str = HUBSPOT_BASE_URL):
        self.api_key = api_key
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        self._request_timestamps: List[float] = []
        self._hapikey_params = {}

        if api_key.startswith("pat-"):
            self._auth_mode = "bearer"
        else:
            self._auth_mode = "auto"

        self._setup_auth()

    def _setup_auth(self):
        if self._auth_mode in ("bearer", "auto"):
            self.session.headers["Authorization"] = f"Bearer {self.api_key}"
            self._hapikey_params = {}
        elif self._auth_mode == "hapikey":
            self.session.headers.pop("Authorization", None)
            self._hapikey_params = {"hapikey": self.api_key}

    def _probe_auth(self):
        if self._auth_mode != "auto":
            return
        url = f"{self.base_url}/crm/v3/owners/?limit=1"
        resp = self.session.get(url, timeout=15)
        if resp.status_code != 401:
            self._auth_mode = "bearer"
            logger.info("Authentication: Bearer token accepted")
            return
        self.session.headers.pop("Authorization", None)
        resp = self.session.get(url, params={"hapikey": self.api_key}, timeout=15)
        if resp.status_code != 401:
            self._auth_mode = "hapikey"
            self._hapikey_params = {"hapikey": self.api_key}
            logger.info("Authentication: hapikey query parameter accepted")
            return
        logger.error("Authentication failed with both methods.")
        self._auth_mode = "bearer"
        self.session.headers["Authorization"] = f"Bearer {self.api_key}"
        self._hapikey_params = {}

    def _rate_limit_wait(self):
        now = time.time()
        self._request_timestamps = [
            t for t in self._request_timestamps if now - t < HUBSPOT_RATE_WINDOW
        ]
        if len(self._request_timestamps) >= HUBSPOT_RATE_LIMIT:
            sleep_time = HUBSPOT_RATE_WINDOW - (now - self._request_timestamps[0]) + 0.1
            logger.debug(f"Rate limit approaching, sleeping {sleep_time:.1f}s")
            time.sleep(sleep_time)
        self._request_timestamps.append(time.time())

    def _get(self, endpoint: str, params: dict = None) -> Optional[dict]:
        self._rate_limit_wait()
        url = f"{self.base_url}{endpoint}"
        merged = dict(self._hapikey_params)
        if params:
            merged.update(params)
        try:
            resp = self.session.get(url, params=merged, timeout=30)
            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", 10))
                logger.warning(f"Rate limited (429). Waiting {retry_after}s")
                time.sleep(retry_after)
                return self._get(endpoint, params)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            logger.error(f"GET {endpoint} failed: {e}")
            return None

    def _post(self, endpoint: str, body: dict) -> Optional[dict]:
        self._rate_limit_wait()
        url = f"{self.base_url}{endpoint}"
        try:
            resp = self.session.post(url, json=body, params=self._hapikey_params, timeout=30)
            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", 10))
                logger.warning(f"Rate limited (429). Waiting {retry_after}s")
                time.sleep(retry_after)
                return self._post(endpoint, body)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            logger.error(f"POST {endpoint} failed: {e}")
            return None

    def _paginate_all(self, endpoint: str, params: dict = None,
                      results_key: str = "results") -> List[dict]:
        all_results = []
        params = dict(params or {})
        params["limit"] = HUBSPOT_PAGE_LIMIT
        after = None
        page = 0
        while True:
            page += 1
            if after:
                params["after"] = after
            elif "after" in params:
                del params["after"]
            data = self._get(endpoint, params)
            if not data:
                break
            results = data.get(results_key, [])
            all_results.extend(results)
            logger.debug(f"Page {page}: {len(results)} records (total: {len(all_results)})")
            paging = data.get("paging", {})
            next_link = paging.get("next", {})
            after = next_link.get("after")
            if not after:
                break
        return all_results

    def fetch_contacts(self, properties: list = None) -> List[dict]:
        default_props = [
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
        props = properties or default_props
        logger.info(f"Fetching contacts ({len(props)} properties)...")
        contacts = self._paginate_all(
            "/crm/v3/objects/contacts",
            params={"properties": ",".join(props)}
        )
        logger.info(f"Fetched {len(contacts)} contacts")
        return contacts

    def fetch_companies(self, properties: list = None) -> List[dict]:
        default_props = [
            "name", "domain", "industry", "annualrevenue",
            "numberofemployees", "lifecyclestage", "hubspot_owner_id",
            "createdate", "num_associated_contacts", "num_associated_deals",
            "hs_analytics_source", "total_revenue",
        ]
        props = properties or default_props
        logger.info("Fetching companies...")
        companies = self._paginate_all(
            "/crm/v3/objects/companies",
            params={"properties": ",".join(props)}
        )
        logger.info(f"Fetched {len(companies)} companies")
        return companies

    def fetch_deals(self, properties: list = None) -> List[dict]:
        default_props = [
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
        props = properties or default_props
        logger.info("Fetching deals...")
        deals = self._paginate_all(
            "/crm/v3/objects/deals",
            params={"properties": ",".join(props)}
        )
        logger.info(f"Fetched {len(deals)} deals")
        return deals

    def fetch_engagements(self, engagement_type: str) -> List[dict]:
        type_props = {
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
        props = type_props.get(engagement_type, [])
        logger.info(f"Fetching {engagement_type}...")
        results = self._paginate_all(
            f"/crm/v3/objects/{engagement_type}",
            params={"properties": ",".join(props)}
        )
        logger.info(f"Fetched {len(results)} {engagement_type}")
        return results

    def fetch_owners(self) -> List[dict]:
        logger.info("Fetching owners...")
        owners = self._paginate_all("/crm/v3/owners/")
        logger.info(f"Fetched {len(owners)} owners")
        return owners

    def fetch_pipelines(self) -> List[dict]:
        logger.info("Fetching pipeline definitions...")
        data = self._get("/crm/v3/pipelines/deals")
        pipelines = data.get("results", []) if data else []
        logger.info(f"Fetched {len(pipelines)} pipelines")
        return pipelines

    def fetch_associations(self, from_type: str, to_type: str,
                           object_ids: List[str]) -> Dict[str, List[str]]:
        associations: Dict[str, List[str]] = {}
        for i in range(0, len(object_ids), 100):
            batch = object_ids[i:i + 100]
            body = {"inputs": [{"id": oid} for oid in batch]}
            data = self._post(
                f"/crm/v4/associations/{from_type}/{to_type}/batch/read", body
            )
            if data and "results" in data:
                for result in data["results"]:
                    from_id = result.get("from", {}).get("id")
                    to_ids = [str(t.get("toObjectId")) for t in result.get("to", [])]
                    if from_id:
                        associations[str(from_id)] = to_ids
        logger.info(f"Fetched {len(associations)} {from_type}->{to_type} associations")
        return associations

    def fetch_form_submissions(self) -> List[dict]:
        logger.info("Fetching forms...")
        forms = self._paginate_all("/marketing/v3/forms")
        logger.info(f"Found {len(forms)} forms")
        all_submissions = []
        for form in forms:
            form_id = form.get("id")
            form_name = form.get("name", "")
            subs = self._paginate_all(
                f"/form-integrations/v1/submissions/forms/{form_id}"
            )
            for sub in subs:
                sub["_form_id"] = form_id
                sub["_form_name"] = form_name
            all_submissions.extend(subs)
        logger.info(f"Fetched {len(all_submissions)} form submissions")
        return all_submissions


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


def fetch_hubspot():
    """Main entry: fetch all HubSpot data and write to raw JSON files."""
    api_key = os.getenv("HUBSPOT_API_KEY")
    if not api_key:
        logger.warning("Missing HUBSPOT_API_KEY environment variable")
        return

    logger.info("Starting HubSpot data extraction")
    client = HubSpotClient(api_key)
    client._probe_auth()
    date_stamp = time.strftime("%Y-%m-%d")

    owners = client.fetch_owners()
    _write_raw("hubspot_owners", date_stamp, owners)

    pipelines = client.fetch_pipelines()
    _write_raw("hubspot_pipelines", date_stamp, pipelines)

    contacts = client.fetch_contacts()
    _write_raw("hubspot_contacts", date_stamp, contacts)

    companies = client.fetch_companies()
    _write_raw("hubspot_companies", date_stamp, companies)

    deals = client.fetch_deals()
    _write_raw("hubspot_deals", date_stamp, deals)

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

    for eng_type in ["calls", "emails", "meetings", "tasks", "notes"]:
        data = client.fetch_engagements(eng_type)
        _write_raw(f"hubspot_{eng_type}", date_stamp, data)

    try:
        forms = client.fetch_form_submissions()
        _write_raw("hubspot_forms", date_stamp, forms)
    except Exception as e:
        logger.warning(f"Form submissions fetch failed: {e}")

    logger.info("HubSpot extraction complete")


if __name__ == "__main__":
    try:
        fetch_hubspot()
    except Exception as e:
        logger.error(f"HubSpot extraction failed: {e}", exc_info=True)
        sys.exit(1)
