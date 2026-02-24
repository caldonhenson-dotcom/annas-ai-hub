"""
Annas AI Hub — Message Sender
================================

Sends approved outreach messages via LinkedIn Voyager API or email (Resend).
Updates message status, advances enrollment step, calculates next_step_at.

Functions:
  send_message()           - Send a single approved message
  send_batch()             - Send all approved messages ready to go
  calculate_next_step_at() - Calculate when the next sequence step should fire
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from scripts.lib.logger import setup_logger
from scripts.lib.supabase_client import get_client

logger = setup_logger("message_sender")


async def send_message(message_id: int) -> dict:
    """
    Send an approved outreach message.

    Routes to LinkedIn Voyager or email based on the message channel.
    Updates message status, enrollment step, and next_step_at.

    Args:
        message_id: The outreach_messages ID to send.

    Returns:
        Dict with send result and updated message.
    """
    client = get_client()

    # Load the message
    msg_result = (
        client.table("outreach_messages")
        .select("*")
        .eq("id", message_id)
        .limit(1)
        .execute()
    )
    if not msg_result.data:
        raise ValueError(f"Message {message_id} not found")

    message = msg_result.data[0]

    if message["status"] != "approved":
        raise ValueError(
            f"Message {message_id} is '{message['status']}', expected 'approved'"
        )

    # Load prospect for routing info
    prospect_result = (
        client.table("outreach_prospects")
        .select("*")
        .eq("id", message["prospect_id"])
        .limit(1)
        .execute()
    )
    if not prospect_result.data:
        raise ValueError(f"Prospect {message['prospect_id']} not found")

    prospect = prospect_result.data[0]
    channel = message.get("channel", "linkedin")
    now = datetime.now(timezone.utc).isoformat()

    try:
        if channel == "linkedin":
            result = await _send_linkedin(message, prospect)
        elif channel == "email":
            result = await _send_email(message, prospect)
        else:
            raise ValueError(f"Unsupported channel: {channel}")

        # Update message status to sent
        client.table("outreach_messages").update({
            "status": "sent",
            "sent_at": now,
            "external_id": result.get("external_id"),
        }).eq("id", message_id).execute()

        # Advance enrollment if applicable
        if message.get("enrollment_id"):
            _advance_enrollment(client, message["enrollment_id"], message.get("sequence_step", 1))

        logger.info(
            "Message %d sent via %s to prospect %d",
            message_id, channel, message["prospect_id"],
        )

        return {
            "status": "sent",
            "message_id": message_id,
            "channel": channel,
            "prospect_id": message["prospect_id"],
            "external_id": result.get("external_id"),
        }

    except Exception as e:
        logger.error("Send failed for message %d: %s", message_id, e)

        client.table("outreach_messages").update({
            "status": "failed",
            "updated_at": now,
        }).eq("id", message_id).execute()

        raise


async def _send_linkedin(message: dict, prospect: dict) -> dict:
    """Send a message via LinkedIn Voyager API."""
    from integrations.linkedin_session import LinkedInSessionManager
    from integrations.linkedin_voyager import LinkedInVoyagerClient

    session_mgr = LinkedInSessionManager()
    credentials = session_mgr.get_active_session()
    if not credentials:
        raise RuntimeError("No active LinkedIn session — cannot send message")

    li_at, csrf_token = credentials
    voyager = LinkedInVoyagerClient(li_at, csrf_token)

    if not await voyager.validate_session():
        session_mgr.invalidate_session()
        raise RuntimeError("LinkedIn session expired — cannot send message")

    # Find the LinkedIn thread for this prospect
    thread_id = _resolve_linkedin_thread(prospect)
    if not thread_id:
        raise ValueError(
            f"No LinkedIn thread found for prospect {prospect['id']} "
            f"({prospect.get('first_name', '')} {prospect.get('last_name', '')})"
        )

    body = message.get("body", "")
    result = await voyager.send_message(thread_id, body)

    return {"external_id": thread_id, "voyager_response": result}


def _resolve_linkedin_thread(prospect: dict) -> str | None:
    """
    Find the LinkedIn thread ID for a prospect.

    Checks:
    1. Direct linkedin_thread_id on the prospect
    2. Linked linkedin_contact → thread lookup
    3. LinkedIn URL match against contacts
    """
    client = get_client()

    # Check direct thread ID
    if prospect.get("linkedin_thread_id"):
        return prospect["linkedin_thread_id"]

    # Check linked contact
    contact_result = (
        client.table("linkedin_contacts")
        .select("id")
        .eq("prospect_id", prospect["id"])
        .limit(1)
        .execute()
    )
    if contact_result.data:
        contact_id = contact_result.data[0]["id"]
        # Find threads where this contact is a participant
        thread_result = (
            client.table("linkedin_threads")
            .select("id, participants")
            .execute()
        )
        for thread in (thread_result.data or []):
            participants = thread.get("participants", "[]")
            if isinstance(participants, str):
                try:
                    participants = json.loads(participants)
                except (json.JSONDecodeError, TypeError):
                    participants = []
            for p in participants:
                if contact_id in str(p.get("id", "")):
                    return thread["id"]

    # Try matching by LinkedIn URL
    linkedin_url = prospect.get("linkedin_url", "")
    if linkedin_url:
        # Extract public identifier from URL
        public_id = linkedin_url.rstrip("/").split("/")[-1]
        if public_id:
            thread_result = (
                client.table("linkedin_threads")
                .select("id, participants")
                .execute()
            )
            for thread in (thread_result.data or []):
                participants = thread.get("participants", "[]")
                if isinstance(participants, str):
                    try:
                        participants = json.loads(participants)
                    except (json.JSONDecodeError, TypeError):
                        participants = []
                for p in participants:
                    if public_id in str(p.get("profile_url", "")):
                        return thread["id"]

    return None


async def _send_email(message: dict, prospect: dict) -> dict:
    """Send a message via email using Resend API."""
    resend_api_key = os.getenv("RESEND_API_KEY")
    if not resend_api_key:
        raise RuntimeError("RESEND_API_KEY not configured — cannot send email")

    import httpx

    email_to = prospect.get("email")
    if not email_to:
        raise ValueError(f"Prospect {prospect['id']} has no email address")

    from_email = os.getenv("OUTREACH_FROM_EMAIL", "outreach@ecomplete.co.uk")
    from_name = os.getenv("OUTREACH_FROM_NAME", "eComplete")

    body = message.get("body", "")
    subject = _extract_email_subject(body)

    payload = {
        "from": f"{from_name} <{from_email}>",
        "to": [email_to],
        "subject": subject,
        "text": body,
    }

    async with httpx.AsyncClient(timeout=30.0) as http:
        response = await http.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {resend_api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        response.raise_for_status()
        data = response.json()

    return {"external_id": data.get("id", ""), "resend_response": data}


def _extract_email_subject(body: str) -> str:
    """Extract subject from first line or generate one."""
    lines = body.strip().split("\n")
    first_line = lines[0].strip() if lines else ""

    # If first line looks like a subject (short, no punctuation ending)
    if first_line and len(first_line) < 80 and not first_line.endswith((".", "!", "?")):
        return first_line

    # Generate from body
    preview = body[:60].strip()
    if len(body) > 60:
        preview = preview.rsplit(" ", 1)[0] + "..."
    return preview


def _advance_enrollment(client, enrollment_id: int, current_step: int) -> None:
    """
    Advance an enrollment to the next step after a message is sent.

    Calculates next_step_at based on the sequence timing configuration.
    """
    now = datetime.now(timezone.utc)

    # Load the enrollment
    enrollment_result = (
        client.table("outreach_enrollments")
        .select("*")
        .eq("id", enrollment_id)
        .limit(1)
        .execute()
    )
    if not enrollment_result.data:
        logger.warning("Enrollment %d not found, cannot advance", enrollment_id)
        return

    enrollment = enrollment_result.data[0]
    sequence_id = enrollment.get("sequence_id")

    # Load the sequence to get total steps and timing
    seq_result = (
        client.table("outreach_sequences")
        .select("*")
        .eq("id", sequence_id)
        .limit(1)
        .execute()
    )
    if not seq_result.data:
        logger.warning("Sequence %d not found", sequence_id)
        return

    sequence = seq_result.data[0]
    total_steps = sequence.get("total_steps", 4)
    next_step = current_step + 1

    if next_step > total_steps:
        # Sequence complete
        client.table("outreach_enrollments").update({
            "status": "completed",
            "current_step": current_step,
            "completed_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }).eq("id", enrollment_id).execute()

        # Update prospect status
        client.table("outreach_prospects").update({
            "status": "sequence_complete",
            "updated_at": now.isoformat(),
        }).eq("id", enrollment.get("prospect_id")).execute()

        logger.info("Enrollment %d completed (all %d steps done)", enrollment_id, total_steps)
        return

    # Calculate next_step_at from template delay
    next_step_at = _calculate_next_step_at(client, sequence_id, next_step, now)

    client.table("outreach_enrollments").update({
        "current_step": next_step,
        "next_step_at": next_step_at.isoformat(),
        "updated_at": now.isoformat(),
    }).eq("id", enrollment_id).execute()

    logger.info(
        "Enrollment %d advanced to step %d (next at %s)",
        enrollment_id, next_step, next_step_at.isoformat(),
    )


def _calculate_next_step_at(
    client,
    sequence_id: int,
    step_number: int,
    from_time: datetime,
) -> datetime:
    """
    Calculate when the next sequence step should fire.

    Reads delay_days from the template for that step. Defaults to 3 days.
    """
    template_result = (
        client.table("outreach_templates")
        .select("delay_days")
        .eq("sequence_id", sequence_id)
        .eq("step_number", step_number)
        .limit(1)
        .execute()
    )

    delay_days = 3  # Default delay
    if template_result.data:
        delay_days = template_result.data[0].get("delay_days", 3)

    return from_time + timedelta(days=delay_days)


async def send_batch(limit: int = 20) -> dict:
    """
    Send all approved messages that are ready.

    Args:
        limit: Maximum number to send in one batch.

    Returns:
        Summary with sent/failed counts.
    """
    client = get_client()

    # Get approved messages
    approved = (
        client.table("outreach_messages")
        .select("id")
        .eq("status", "approved")
        .order("created_at", desc=False)
        .limit(limit)
        .execute()
    )

    if not approved.data:
        return {"sent": 0, "failed": 0, "total": 0}

    results = {"sent": 0, "failed": 0, "total": len(approved.data)}

    for msg in approved.data:
        try:
            await send_message(msg["id"])
            results["sent"] += 1
        except Exception as e:
            logger.error("Batch send failed for message %d: %s", msg["id"], e)
            results["failed"] += 1

    logger.info(
        "Batch send complete: %d sent, %d failed out of %d",
        results["sent"], results["failed"], results["total"],
    )
    return results
