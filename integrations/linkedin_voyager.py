"""
Annas AI Hub — LinkedIn Voyager API Client
=============================================

Implements LinkedIn's internal Voyager API for messaging operations.
Uses session-based authentication with li_at cookie and CSRF token.

Ported from AI Clawdon, adapted to use:
  - scripts.lib.logger instead of stdlib logging
  - scripts.lib.errors Voyager error classes
  - Circuit breaker state tracking

Security:
  - Rate limiting: 1 request per 2 seconds + random jitter
  - Exponential backoff for retries
  - Session validation before each request batch
  - Request headers mimic browser to avoid detection
"""
from __future__ import annotations

import asyncio
import random
from datetime import datetime
from typing import Any, Dict, Optional

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from scripts.lib.errors import VoyagerAPIError, VoyagerAuthError, VoyagerRateLimitError
from scripts.lib.logger import setup_logger

logger = setup_logger("linkedin_voyager")


class LinkedInVoyagerClient:
    """
    LinkedIn Voyager API client with rate limiting and session management.

    Usage:
        client = LinkedInVoyagerClient(li_at_cookie="...", csrf_token="...")
        if await client.validate_session():
            conversations = await client.fetch_conversations(count=20)
    """

    BASE_URL = "https://www.linkedin.com/voyager/api"

    def __init__(self, li_at_cookie: str, csrf_token: str):
        self.li_at_cookie = li_at_cookie
        self.csrf_token = csrf_token
        self._last_request_time: Optional[datetime] = None
        self._rate_limit_delay = 2.0  # Minimum seconds between requests

        # Browser-like headers to avoid detection
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept": "application/vnd.linkedin.normalized+json+2.1",
            "Accept-Language": "en-US,en;q=0.9",
            "x-restli-protocol-version": "2.0.0",
            "x-li-lang": "en_US",
            "x-li-page-instance": "urn:li:page:messaging_inbox;",
            "csrf-token": self.csrf_token,
            "Referer": "https://www.linkedin.com/messaging/",
            "Origin": "https://www.linkedin.com",
        }

        self.cookies = {
            "li_at": self.li_at_cookie,
            "JSESSIONID": f'"{self.csrf_token}"',
        }

    async def _rate_limit(self):
        """Enforce rate limiting with jitter to mimic human behaviour."""
        if self._last_request_time:
            elapsed = (datetime.now() - self._last_request_time).total_seconds()
            if elapsed < self._rate_limit_delay:
                jitter = random.uniform(0.5, 1.5)
                wait_time = (self._rate_limit_delay - elapsed) + jitter
                logger.debug("Rate limiting: waiting %.2fs", wait_time)
                await asyncio.sleep(wait_time)

        self._last_request_time = datetime.now()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(httpx.HTTPStatusError),
    )
    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        json_data: Optional[Dict] = None,
    ) -> Dict:
        """Make a rate-limited HTTP request with retries."""
        await self._rate_limit()

        url = f"{self.BASE_URL}/{endpoint}"

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=self.headers,
                    cookies=self.cookies,
                    params=params,
                    json=json_data,
                )

                if response.status_code == 401:
                    raise VoyagerAuthError("Session expired or invalid")

                if response.status_code == 429:
                    raise VoyagerRateLimitError()

                response.raise_for_status()
                return response.json()

            except httpx.HTTPStatusError:
                raise
            except (VoyagerAuthError, VoyagerRateLimitError):
                raise
            except Exception as e:
                logger.error("Voyager API request failed: %s", e)
                raise VoyagerAPIError(f"Request failed: {e}")

    async def validate_session(self) -> bool:
        """Validate the current session by fetching the user's own profile."""
        try:
            await self._request("GET", "me")
            return True
        except VoyagerAuthError:
            return False
        except Exception as e:
            logger.warning("Session validation failed: %s", e)
            return False

    async def fetch_conversations(
        self,
        count: int = 20,
        before_timestamp: Optional[int] = None,
    ) -> Dict:
        """
        Fetch conversation list.

        Args:
            count: Number of conversations to fetch (max 100).
            before_timestamp: Fetch conversations before this epoch ms (pagination).
        """
        params: Dict[str, Any] = {
            "keyVersion": "LEGACY_INBOX",
            "count": min(count, 100),
        }
        if before_timestamp:
            params["createdBefore"] = before_timestamp

        return await self._request("GET", "messaging/conversations", params=params)

    async def fetch_messages(
        self,
        conversation_id: str,
        count: int = 50,
        before_timestamp: Optional[int] = None,
    ) -> Dict:
        """Fetch messages for a specific conversation."""
        conv_id = conversation_id.split(":")[-1]
        params: Dict[str, Any] = {"count": min(count, 100)}
        if before_timestamp:
            params["createdBefore"] = before_timestamp

        return await self._request(
            "GET", f"messaging/conversations/{conv_id}/events", params=params
        )

    async def send_message(self, conversation_id: str, text: str) -> Dict:
        """Send a message to a conversation (max 8000 chars)."""
        conv_id = conversation_id.split(":")[-1]
        payload = {
            "eventCreate": {
                "value": {
                    "com.linkedin.voyager.messaging.create.MessageCreate": {
                        "body": text[:8000],
                        "attachments": [],
                    }
                }
            },
        }
        return await self._request(
            "POST", f"messaging/conversations/{conv_id}/events", json_data=payload
        )

    async def mark_as_read(self, conversation_id: str) -> Dict:
        """Mark a conversation as read."""
        conv_id = conversation_id.split(":")[-1]
        payload = {"patch": {"$set": {"read": True}}}
        return await self._request(
            "POST", f"messaging/conversations/{conv_id}", json_data=payload
        )

    async def search_messages(self, keywords: str) -> Dict:
        """Search messages by keywords."""
        params = {"q": "search", "keywords": keywords}
        return await self._request("GET", "messaging/conversations", params=params)

    async def fetch_profile(self, public_id: str) -> Dict:
        """Fetch a LinkedIn profile by public ID (vanity URL)."""
        return await self._request(
            "GET", f"identity/profiles/{public_id}/profileView"
        )
