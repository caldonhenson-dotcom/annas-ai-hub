"""
HubSpot Integration
====================

Connects to HubSpot CRM for:
- Contact management
- Deal tracking
- Company information
- Activity logging

Setup:
1. Get API key from HubSpot -> Settings -> Integrations -> API Key
2. Set HUBSPOT_API_KEY in .env (or use OAuth with CLIENT_ID/SECRET)
"""

import logging
import os
from typing import Any, Dict, List, Optional

import aiohttp

logger = logging.getLogger(__name__)

HUBSPOT_API_URL = "https://api.hubapi.com"


class HubSpotIntegration:
    """HubSpot CRM connector."""

    def __init__(self):
        self.api_key = os.getenv("HUBSPOT_API_KEY")
        self.client_id = os.getenv("HUBSPOT_CLIENT_ID")
        self.client_secret = os.getenv("HUBSPOT_CLIENT_SECRET")

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key or (self.client_id and self.client_secret))

    def _headers(self) -> Dict[str, str]:
        """Build authorization headers."""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def _request(self, method: str, path: str, json_body: dict = None) -> Optional[Dict]:
        """Make an authenticated request to the HubSpot API."""
        if not self.is_configured:
            logger.warning("HubSpot is not configured — set HUBSPOT_API_KEY in .env")
            return None

        url = f"{HUBSPOT_API_URL}{path}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.request(method, url, headers=self._headers(), json=json_body) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    else:
                        text = await resp.text()
                        logger.error(f"HubSpot API {method} {path} returned {resp.status}: {text}")
                        return None
        except Exception as e:
            logger.error(f"HubSpot API error: {e}")
            return None

    async def get_contacts(self, limit: int = 50) -> List[Dict]:
        """Fetch contacts from HubSpot."""
        data = await self._request("GET", f"/crm/v3/objects/contacts?limit={limit}")
        if data and "results" in data:
            return data["results"]
        return []

    async def get_contact(self, contact_id: str) -> Optional[Dict]:
        """Fetch a specific contact."""
        return await self._request("GET", f"/crm/v3/objects/contacts/{contact_id}")

    async def get_deals(self, limit: int = 50) -> List[Dict]:
        """Fetch deals from HubSpot."""
        data = await self._request("GET", f"/crm/v3/objects/deals?limit={limit}")
        if data and "results" in data:
            return data["results"]
        return []

    async def get_companies(self, limit: int = 50) -> List[Dict]:
        """Fetch companies from HubSpot."""
        data = await self._request("GET", f"/crm/v3/objects/companies?limit={limit}")
        if data and "results" in data:
            return data["results"]
        return []

    async def search_contacts(self, query: str) -> List[Dict]:
        """Search contacts by name or email."""
        body = {
            "filterGroups": [{
                "filters": [{
                    "propertyName": "email",
                    "operator": "CONTAINS_TOKEN",
                    "value": query,
                }]
            }],
            "limit": 20,
        }
        data = await self._request("POST", "/crm/v3/objects/contacts/search", json_body=body)
        if data and "results" in data:
            return data["results"]
        return []

    async def log_activity(self, contact_id: str, activity_type: str, details: str) -> bool:
        """Log an activity against a contact."""
        body = {
            "properties": {
                "hs_note_body": details,
                "hs_timestamp": None,  # current time
            },
            "associations": [{
                "to": {"id": contact_id},
                "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 202}],
            }],
        }
        result = await self._request("POST", "/crm/v3/objects/notes", json_body=body)
        if result:
            logger.info(f"Logged activity for contact {contact_id}: {activity_type}")
            return True
        return False

    def get_status(self) -> Dict[str, Any]:
        return {
            "name": "HubSpot",
            "configured": self.is_configured,
            "features": ["contacts", "deals", "companies", "activities"],
        }
