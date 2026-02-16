"""Tests for the HubSpot integration."""

from unittest.mock import patch

import pytest

from integrations.hubspot import HubSpotIntegration


class TestHubSpotIntegration:
    def test_not_configured_without_key(self):
        with patch.dict("os.environ", {"HUBSPOT_API_KEY": ""}, clear=False):
            hub = HubSpotIntegration()
            assert hub.is_configured is False

    def test_configured_with_api_key(self):
        with patch.dict("os.environ", {"HUBSPOT_API_KEY": "test-key"}, clear=False):
            hub = HubSpotIntegration()
            assert hub.is_configured is True

    def test_configured_with_oauth(self):
        with patch.dict("os.environ", {
            "HUBSPOT_API_KEY": "",
            "HUBSPOT_CLIENT_ID": "id",
            "HUBSPOT_CLIENT_SECRET": "secret",
        }, clear=False):
            hub = HubSpotIntegration()
            assert hub.is_configured is True

    def test_status_returns_correct_structure(self):
        with patch.dict("os.environ", {"HUBSPOT_API_KEY": "test"}, clear=False):
            hub = HubSpotIntegration()
            status = hub.get_status()
            assert status["name"] == "HubSpot"
            assert status["configured"] is True
            assert "contacts" in status["features"]
            assert "deals" in status["features"]

    @pytest.mark.asyncio
    async def test_get_contacts_unconfigured(self):
        with patch.dict("os.environ", {"HUBSPOT_API_KEY": ""}, clear=False):
            hub = HubSpotIntegration()
            contacts = await hub.get_contacts()
            assert contacts == []

    @pytest.mark.asyncio
    async def test_get_deals_unconfigured(self):
        with patch.dict("os.environ", {"HUBSPOT_API_KEY": ""}, clear=False):
            hub = HubSpotIntegration()
            deals = await hub.get_deals()
            assert deals == []
