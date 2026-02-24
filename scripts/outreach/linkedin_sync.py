"""
Annas AI Hub — LinkedIn Sync Engine
======================================

Background synchronization service for LinkedIn messages.
Polls Voyager API for new conversations/messages and stores in Supabase.
Broadcasts updates via WebSocket for real-time frontend updates.

Browser presence guard: sync only runs when a heartbeat confirms
the user's browser is open, preventing LinkedIn from flagging API
activity when the user isn't actually online.

Ported from AI Clawdon, converted from SQLAlchemy to Supabase.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Awaitable, Callable, Dict, Optional, Tuple

from integrations.linkedin_voyager import LinkedInVoyagerClient
from integrations.linkedin_session import LinkedInSessionManager
from scripts.lib.errors import VoyagerAuthError
from scripts.lib.logger import setup_logger
from scripts.lib.supabase_client import get_client

logger = setup_logger("linkedin_sync")

HEARTBEAT_MAX_AGE_SECONDS = int(os.getenv("LINKEDIN_HEARTBEAT_MAX_AGE", "120"))


class LinkedInSyncEngine:
    """Handles background synchronization of LinkedIn messages."""

    def __init__(self):
        self.session_manager = LinkedInSessionManager()
        self._ws_broadcast: Optional[Callable[[Dict], Awaitable[None]]] = None
        self._browser_active = False
        self._last_heartbeat: Optional[datetime] = None

    def set_broadcast_callback(self, callback: Callable[[Dict], Awaitable[None]]):
        """Set WebSocket broadcast callback for real-time updates."""
        self._ws_broadcast = callback

    async def _broadcast(self, event_type: str, data: Dict):
        """Broadcast update to WebSocket clients."""
        if self._ws_broadcast:
            await self._ws_broadcast({
                "event": f"linkedin_{event_type}",
                "data": data,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

    def update_heartbeat(self):
        """Called by the API when the refresh script pings."""
        self._last_heartbeat = datetime.now(timezone.utc)
        self._browser_active = True
        logger.debug("Browser heartbeat received")

    def check_browser_active(self) -> bool:
        """Check if browser is active via heartbeat."""
        if self._last_heartbeat:
            age = (datetime.now(timezone.utc) - self._last_heartbeat).total_seconds()
            if age < HEARTBEAT_MAX_AGE_SECONDS:
                self._browser_active = True
                return True

        if self._browser_active:
            logger.info("Browser heartbeat stale — pausing LinkedIn sync")
        self._browser_active = False
        return False

    def get_browser_status(self) -> Dict:
        """Return current browser presence status."""
        active = self.check_browser_active()
        return {
            "browser_active": active,
            "last_heartbeat": self._last_heartbeat.isoformat() if self._last_heartbeat else None,
            "sync_enabled": active,
        }

    async def sync_conversations(self, full_sync: bool = False) -> Dict:
        """
        Sync conversations from LinkedIn.

        Args:
            full_sync: If True, fetch all conversations. Otherwise incremental.

        Returns:
            Dict with sync statistics.
        """
        # Guard: only sync when browser is confirmed active
        if not self.check_browser_active():
            logger.debug("Skipping sync — browser not active")
            return {"skipped": True, "reason": "Browser not active"}

        credentials = self.session_manager.get_active_session()
        if not credentials:
            logger.warning("No active LinkedIn session found")
            return {"error": "No active session"}

        li_at, csrf_token = credentials
        client = LinkedInVoyagerClient(li_at, csrf_token)

        if not await client.validate_session():
            self.session_manager.invalidate_session()
            await self._broadcast("session_invalid", {
                "message": "LinkedIn session expired. Please re-authenticate."
            })
            return {"error": "Session invalid"}

        stats = {
            "threads_updated": 0,
            "threads_created": 0,
            "messages_created": 0,
            "errors": 0,
        }

        try:
            conv_data = await client.fetch_conversations(count=50)
            supabase = get_client()

            for conversation in conv_data.get("elements", []):
                try:
                    thread_id = conversation.get("entityUrn", "").split(":")[-1]
                    if not thread_id:
                        continue

                    # Extract participants
                    participants = []
                    for p in conversation.get("participants", []):
                        member = p.get("com.linkedin.voyager.messaging.MessagingMember", {})
                        mini = member.get("miniProfile", {})
                        participants.append({
                            "id": mini.get("entityUrn", ""),
                            "name": f"{mini.get('firstName', '')} {mini.get('lastName', '')}".strip(),
                            "profile_url": f"https://linkedin.com/in/{mini.get('publicIdentifier', '')}",
                            "photo_url": "",
                        })

                    last_activity = conversation.get("lastActivityAt", 0)
                    last_msg_at = (
                        datetime.fromtimestamp(last_activity / 1000, tz=timezone.utc).isoformat()
                        if last_activity
                        else datetime.now(timezone.utc).isoformat()
                    )

                    preview = conversation.get("lastMessage", {}).get("text", "")
                    unread = conversation.get("unreadCount", 0)

                    # Check if thread exists
                    existing = (
                        supabase.table("linkedin_threads")
                        .select("id")
                        .eq("id", thread_id)
                        .limit(1)
                        .execute()
                    )

                    thread_row = {
                        "id": thread_id,
                        "participants": json.dumps(participants),
                        "last_message_at": last_msg_at,
                        "last_message_preview": preview[:500] if preview else None,
                        "unread_count": unread,
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }

                    if existing.data:
                        supabase.table("linkedin_threads").update(
                            thread_row
                        ).eq("id", thread_id).execute()
                        stats["threads_updated"] += 1
                    else:
                        supabase.table("linkedin_threads").insert(
                            thread_row
                        ).execute()
                        stats["threads_created"] += 1

                    # Sync messages for this thread
                    msg_count = await self._sync_thread_messages(client, supabase, thread_id)
                    stats["messages_created"] += msg_count

                except Exception as e:
                    logger.error("Error syncing thread: %s", e)
                    stats["errors"] += 1

            await self._broadcast("sync_complete", stats)

        except VoyagerAuthError:
            self.session_manager.invalidate_session()
            stats["error"] = "Authentication failed"
            await self._broadcast("session_invalid", {
                "message": "LinkedIn session expired during sync."
            })
        except Exception as e:
            logger.error("Sync failed: %s", e)
            stats["error"] = str(e)

        return stats

    async def _sync_thread_messages(
        self,
        client: LinkedInVoyagerClient,
        supabase,
        thread_id: str,
    ) -> int:
        """Sync messages for a specific thread. Returns count of new messages."""
        created = 0
        try:
            messages_data = await client.fetch_messages(thread_id, count=50)

            for message in messages_data.get("elements", []):
                message_id = message.get("entityUrn", "").split(":")[-1]
                if not message_id:
                    continue

                # Skip if already exists
                existing = (
                    supabase.table("linkedin_messages")
                    .select("id")
                    .eq("id", message_id)
                    .limit(1)
                    .execute()
                )
                if existing.data:
                    continue

                sender = message.get("from", {}).get(
                    "com.linkedin.voyager.messaging.MessagingMember", {}
                )
                mini = sender.get("miniProfile", {})

                created_at = message.get("createdAt", 0)
                ts = (
                    datetime.fromtimestamp(created_at / 1000, tz=timezone.utc).isoformat()
                    if created_at
                    else datetime.now(timezone.utc).isoformat()
                )

                is_from_me = message.get("from", {}).get("isSelf", False)

                msg_row = {
                    "id": message_id,
                    "thread_id": thread_id,
                    "sender_id": mini.get("entityUrn", ""),
                    "sender_name": f"{mini.get('firstName', '')} {mini.get('lastName', '')}".strip(),
                    "body": message.get("body", {}).get("text", ""),
                    "is_inbound": not is_from_me,
                    "sent_at": ts,
                    "attachments": json.dumps(message.get("attachments", [])),
                }

                supabase.table("linkedin_messages").insert(msg_row).execute()
                created += 1

        except Exception as e:
            logger.error("Error syncing messages for thread %s: %s", thread_id, e)

        return created


# Singleton
linkedin_sync_engine = LinkedInSyncEngine()
