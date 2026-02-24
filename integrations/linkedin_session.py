"""
Annas AI Hub — LinkedIn Session Manager
==========================================

Handles encryption/decryption of LinkedIn session credentials
and session lifecycle management via Supabase.

Ported from AI Clawdon, adapted from SQLAlchemy to Supabase.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from cryptography.fernet import Fernet

from scripts.lib.logger import setup_logger
from scripts.lib.supabase_client import get_client

logger = setup_logger("linkedin_session")


class LinkedInSessionManager:
    """Manages encrypted session credentials for LinkedIn Voyager API access."""

    def __init__(self):
        key = os.getenv("LINKEDIN_ENCRYPTION_KEY")
        if not key:
            logger.warning(
                "LINKEDIN_ENCRYPTION_KEY not set. Generating a temporary key "
                "(credentials will NOT survive restarts)."
            )
            key = Fernet.generate_key().decode()

        self.cipher = Fernet(key.encode() if isinstance(key, str) else key)

    def encrypt_credential(self, credential: str) -> str:
        """Encrypt a credential string."""
        return self.cipher.encrypt(credential.encode()).decode()

    def decrypt_credential(self, encrypted: str) -> str:
        """Decrypt a credential string."""
        try:
            return self.cipher.decrypt(encrypted.encode()).decode()
        except Exception as e:
            logger.error("Failed to decrypt credential: %s", e)
            raise ValueError("Invalid or corrupted credential")

    @staticmethod
    def validate_session_format(li_at: str, csrf_token: str) -> bool:
        """Basic format validation for session credentials."""
        if not li_at or len(li_at) < 50:
            return False
        if not csrf_token or len(csrf_token) < 10:
            return False
        return True

    @staticmethod
    def calculate_expiry(creation_date: datetime) -> datetime:
        """Calculate session expiry (LinkedIn sessions last ~1 year)."""
        return creation_date + timedelta(days=365)

    # ─── Supabase Session Operations ────────────────────────────

    def get_active_session(self) -> Optional[Tuple[str, str]]:
        """Retrieve and decrypt the active LinkedIn session credentials."""
        client = get_client()
        result = (
            client.table("linkedin_sessions")
            .select("*")
            .eq("is_valid", True)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )

        if not result.data:
            return None

        session = result.data[0]
        try:
            li_at = self.decrypt_credential(session["li_at"])
            csrf = self.decrypt_credential(session["csrf_token"])
            return (li_at, csrf)
        except Exception as e:
            logger.error("Failed to decrypt session: %s", e)
            return None

    def store_session(
        self,
        li_at: str,
        csrf_token: str,
        profile_id: str | None = None,
        display_name: str | None = None,
    ) -> dict:
        """
        Encrypt and store new session, invalidating all previous sessions.

        Returns:
            The created session row.
        """
        client = get_client()
        now = datetime.now(timezone.utc).isoformat()

        # Invalidate old sessions
        client.table("linkedin_sessions").update(
            {"is_valid": False}
        ).eq("is_valid", True).execute()

        # Create new session
        row = {
            "li_at": self.encrypt_credential(li_at),
            "csrf_token": self.encrypt_credential(csrf_token),
            "profile_id": profile_id,
            "display_name": display_name,
            "is_valid": True,
            "expires_at": self.calculate_expiry(datetime.now(timezone.utc)).isoformat(),
            "last_validated": now,
        }

        result = client.table("linkedin_sessions").insert(row).execute()
        logger.info("New LinkedIn session stored")
        return result.data[0] if result.data else row

    def invalidate_session(self) -> None:
        """Mark the current active session as invalid."""
        client = get_client()
        client.table("linkedin_sessions").update(
            {"is_valid": False}
        ).eq("is_valid", True).execute()
        logger.info("LinkedIn session invalidated")

    def get_session_status(self) -> dict:
        """Get current session status."""
        client = get_client()
        result = (
            client.table("linkedin_sessions")
            .select("*")
            .eq("is_valid", True)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )

        if not result.data:
            return {
                "authenticated": False,
                "session_valid": False,
                "last_validated": None,
                "expires_at": None,
            }

        session = result.data[0]
        return {
            "authenticated": True,
            "session_valid": session["is_valid"],
            "last_validated": session.get("last_validated"),
            "expires_at": session.get("expires_at"),
            "display_name": session.get("display_name"),
        }
