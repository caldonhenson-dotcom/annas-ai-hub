"""
HubSpot API v3 Client
=====================
Reusable client with auth, rate limiting, pagination, and search.
Used by fetch_hubspot.py for both full and incremental fetching.
"""

import logging
import time
import requests
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

HUBSPOT_BASE_URL = "https://api.hubapi.com"
HUBSPOT_PAGE_LIMIT = 100
HUBSPOT_RATE_LIMIT = 100
HUBSPOT_RATE_WINDOW = 10  # seconds


class HubSpotClient:
    """HubSpot API v3 client with pagination, rate limiting, and search."""

    def __init__(self, api_key: str, base_url: str = HUBSPOT_BASE_URL):
        self.api_key = api_key
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        self._request_timestamps: List[float] = []
        self._hapikey_params = {}
        self._auth_mode = "bearer" if api_key.startswith("pat-") else "auto"
        self._setup_auth()

    def _setup_auth(self):
        if self._auth_mode in ("bearer", "auto"):
            self.session.headers["Authorization"] = f"Bearer {self.api_key}"
            self._hapikey_params = {}
        elif self._auth_mode == "hapikey":
            self.session.headers.pop("Authorization", None)
            self._hapikey_params = {"hapikey": self.api_key}

    def probe_auth(self):
        """Probe which auth method works (bearer vs hapikey)."""
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
            logger.info("Authentication: hapikey accepted")
            return
        logger.error("Authentication failed with both methods.")
        self._auth_mode = "bearer"
        self.session.headers["Authorization"] = f"Bearer {self.api_key}"

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

    def get(self, endpoint: str, params: dict = None, _retries: int = 0) -> Optional[dict]:
        """GET request with rate limiting and retry on 429."""
        self._rate_limit_wait()
        url = f"{self.base_url}{endpoint}"
        merged = dict(self._hapikey_params)
        if params:
            merged.update(params)
        try:
            resp = self.session.get(url, params=merged, timeout=30)
            if resp.status_code == 429:
                if _retries >= 3:
                    logger.error(f"GET {endpoint} rate-limited 3 times, giving up")
                    return None
                retry_after = int(resp.headers.get("Retry-After", 10))
                logger.warning(f"Rate limited (429). Waiting {retry_after}s (retry {_retries + 1}/3)")
                time.sleep(retry_after)
                return self.get(endpoint, params, _retries + 1)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            logger.error(f"GET {endpoint} failed: {e}")
            return None

    def post(self, endpoint: str, body: dict, _retries: int = 0) -> Optional[dict]:
        """POST request with rate limiting and retry on 429."""
        self._rate_limit_wait()
        url = f"{self.base_url}{endpoint}"
        try:
            resp = self.session.post(url, json=body, params=self._hapikey_params, timeout=30)
            if resp.status_code == 429:
                if _retries >= 3:
                    logger.error(f"POST {endpoint} rate-limited 3 times, giving up")
                    return None
                retry_after = int(resp.headers.get("Retry-After", 10))
                logger.warning(f"Rate limited (429). Waiting {retry_after}s (retry {_retries + 1}/3)")
                time.sleep(retry_after)
                return self.post(endpoint, body, _retries + 1)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            logger.error(f"POST {endpoint} failed: {e}")
            return None

    def paginate_all(self, endpoint: str, params: dict = None,
                     results_key: str = "results") -> List[dict]:
        """Paginate through a list endpoint collecting all results."""
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
            data = self.get(endpoint, params)
            if not data:
                break
            results = data.get(results_key, [])
            all_results.extend(results)
            logger.debug(f"Page {page}: {len(results)} records (total: {len(all_results)})")
            paging = data.get("paging", {})
            after = paging.get("next", {}).get("after")
            if not after:
                break
        return all_results

    def search_modified(self, object_type: str, since_ms: int,
                        properties: List[str]) -> List[dict]:
        """Search for records modified since a timestamp (ms).

        Uses the CRM Search API with lastmodifieddate filter.
        Much faster than paginating all records when few changed.
        """
        logger.info(f"Searching {object_type} modified since {since_ms}...")
        all_results = []
        after = 0
        page = 0
        while True:
            page += 1
            body = {
                "filterGroups": [{
                    "filters": [{
                        "propertyName": "lastmodifieddate",
                        "operator": "GTE",
                        "value": str(since_ms),
                    }]
                }],
                "properties": properties,
                "limit": HUBSPOT_PAGE_LIMIT,
                "after": after,
                "sorts": [{"propertyName": "lastmodifieddate", "direction": "ASCENDING"}],
            }
            data = self.post(f"/crm/v3/objects/{object_type}/search", body)
            if not data:
                break
            results = data.get("results", [])
            all_results.extend(results)
            total = data.get("total", "?")
            logger.debug(f"Search page {page}: {len(results)} (total available: {total})")
            paging = data.get("paging", {})
            after = paging.get("next", {}).get("after")
            if not after:
                break
        logger.info(f"Found {len(all_results)} modified {object_type}")
        return all_results

    def fetch_associations(self, from_type: str, to_type: str,
                           object_ids: List[str]) -> Dict[str, List[str]]:
        """Batch-fetch associations between object types."""
        associations: Dict[str, List[str]] = {}
        for i in range(0, len(object_ids), 100):
            batch = object_ids[i:i + 100]
            body = {"inputs": [{"id": oid} for oid in batch]}
            data = self.post(
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
