"""
Annas AI Hub — Correspondence Monitor
=========================================

Runs after LinkedIn sync to match inbound messages to prospects,
create outreach_messages records, auto-classify intent with AI,
update enrollment status, recalculate lead scores, and broadcast
WebSocket events.

Functions:
  process_new_inbound()     - Main entry: process all unmatched inbound messages
  match_message_to_prospect() - Link a LinkedIn message to a prospect
  process_single_inbound()  - Process one inbound message (classify + score + enroll update)
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from scripts.lib.logger import setup_logger
from scripts.lib.supabase_client import get_client

logger = setup_logger("correspondence_monitor")


async def process_new_inbound(
    since_minutes: int = 60,
    ws_broadcast=None,
) -> dict:
    """
    Process new inbound LinkedIn messages that haven't been matched to prospects yet.

    Steps per message:
    1. Match to a prospect (by linkedin_contact or URL)
    2. Create an outreach_messages record (direction='inbound')
    3. Classify intent via AI
    4. Update enrollment status based on intent
    5. Recalculate lead score
    6. Broadcast WebSocket event

    Args:
        since_minutes: Only look at messages from the last N minutes.
        ws_broadcast: Optional async callback to broadcast events.

    Returns:
        Summary dict with processed/matched/classified/errors counts.
    """
    client = get_client()
    stats = {
        "processed": 0,
        "matched": 0,
        "classified": 0,
        "score_updated": 0,
        "errors": 0,
    }

    # Find recent inbound LinkedIn messages not yet in outreach_messages
    cutoff = datetime.now(timezone.utc)
    from datetime import timedelta
    cutoff = cutoff - timedelta(minutes=since_minutes)

    inbound_msgs = (
        client.table("linkedin_messages")
        .select("*")
        .eq("is_inbound", True)
        .gte("sent_at", cutoff.isoformat())
        .order("sent_at", desc=False)
        .execute()
    )

    if not inbound_msgs.data:
        logger.debug("No new inbound messages to process")
        return stats

    for li_msg in inbound_msgs.data:
        try:
            # Check if already tracked in outreach_messages
            existing = (
                client.table("outreach_messages")
                .select("id")
                .eq("external_id", li_msg["id"])
                .limit(1)
                .execute()
            )
            if existing.data:
                continue  # Already processed

            stats["processed"] += 1

            # Match to prospect
            prospect = _match_message_to_prospect(client, li_msg)
            if not prospect:
                # Create unmatched outreach_message for visibility
                _create_unmatched_message(client, li_msg)
                continue

            stats["matched"] += 1

            # Create outreach_messages record
            outreach_msg = _create_inbound_message(client, li_msg, prospect)

            # Classify intent via AI
            intent_result = await _classify_inbound(
                li_msg["body"], prospect, outreach_msg["id"]
            )
            if intent_result:
                stats["classified"] += 1

                # Update message with classification
                client.table("outreach_messages").update({
                    "intent": intent_result.get("intent"),
                    "intent_confidence": intent_result.get("confidence"),
                    "intent_signals": json.dumps(intent_result),
                }).eq("id", outreach_msg["id"]).execute()

                # Update enrollment based on intent
                _update_enrollment_from_intent(client, prospect, intent_result)

                # Recalculate engagement score
                _recalculate_engagement_score(client, prospect["id"])
                stats["score_updated"] += 1

            # Broadcast
            if ws_broadcast:
                await ws_broadcast({
                    "event": "inbound_message",
                    "data": {
                        "prospect_id": prospect["id"],
                        "prospect_name": f"{prospect.get('first_name', '')} {prospect.get('last_name', '')}",
                        "message_preview": (li_msg.get("body", ""))[:100],
                        "intent": intent_result.get("intent") if intent_result else None,
                        "confidence": intent_result.get("confidence") if intent_result else None,
                    },
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })

        except Exception as e:
            logger.error("Error processing inbound message %s: %s", li_msg.get("id"), e)
            stats["errors"] += 1

    logger.info(
        "Correspondence monitor: %d processed, %d matched, %d classified, %d errors",
        stats["processed"], stats["matched"], stats["classified"], stats["errors"],
    )
    return stats


def _match_message_to_prospect(client, li_msg: dict) -> dict | None:
    """
    Match a LinkedIn message to an outreach prospect.

    Strategy:
    1. Sender ID → linkedin_contacts.prospect_id
    2. Thread ID → linkedin_contacts from thread participants
    3. Sender name fuzzy match against prospects
    """
    sender_id = li_msg.get("sender_id", "")
    thread_id = li_msg.get("thread_id", "")

    # Strategy 1: Direct contact link
    if sender_id:
        contact_result = (
            client.table("linkedin_contacts")
            .select("prospect_id")
            .eq("id", sender_id)
            .limit(1)
            .execute()
        )
        if contact_result.data and contact_result.data[0].get("prospect_id"):
            prospect_id = contact_result.data[0]["prospect_id"]
            return _load_prospect(client, prospect_id)

    # Strategy 2: Thread participants → contact → prospect
    if thread_id:
        thread_result = (
            client.table("linkedin_threads")
            .select("participants")
            .eq("id", thread_id)
            .limit(1)
            .execute()
        )
        if thread_result.data:
            participants = thread_result.data[0].get("participants", "[]")
            if isinstance(participants, str):
                try:
                    participants = json.loads(participants)
                except (json.JSONDecodeError, TypeError):
                    participants = []

            for p in participants:
                p_id = str(p.get("id", ""))
                if p_id and p_id != sender_id:
                    continue  # Skip non-senders
                if not p_id:
                    continue

                contact_result = (
                    client.table("linkedin_contacts")
                    .select("prospect_id")
                    .eq("id", p_id)
                    .limit(1)
                    .execute()
                )
                if contact_result.data and contact_result.data[0].get("prospect_id"):
                    return _load_prospect(client, contact_result.data[0]["prospect_id"])

    # Strategy 3: Sender name match
    sender_name = li_msg.get("sender_name", "").strip()
    if sender_name and " " in sender_name:
        parts = sender_name.split(" ", 1)
        first_name = parts[0]
        last_name = parts[1] if len(parts) > 1 else ""

        prospect_result = (
            client.table("outreach_prospects")
            .select("*")
            .ilike("first_name", first_name)
            .ilike("last_name", last_name)
            .limit(1)
            .execute()
        )
        if prospect_result.data:
            return prospect_result.data[0]

    return None


def _load_prospect(client, prospect_id: int) -> dict | None:
    """Load a prospect by ID."""
    result = (
        client.table("outreach_prospects")
        .select("*")
        .eq("id", prospect_id)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def _create_inbound_message(client, li_msg: dict, prospect: dict) -> dict:
    """Create an outreach_messages record for an inbound message."""
    now = datetime.now(timezone.utc).isoformat()

    # Find active enrollment
    enrollment_result = (
        client.table("outreach_enrollments")
        .select("id")
        .eq("prospect_id", prospect["id"])
        .eq("status", "active")
        .limit(1)
        .execute()
    )
    enrollment_id = enrollment_result.data[0]["id"] if enrollment_result.data else None

    msg_data = {
        "prospect_id": prospect["id"],
        "enrollment_id": enrollment_id,
        "direction": "inbound",
        "channel": "linkedin",
        "body": li_msg.get("body", ""),
        "status": "received",
        "external_id": li_msg["id"],
        "created_at": li_msg.get("sent_at", now),
    }

    result = client.table("outreach_messages").insert(msg_data).execute()
    return result.data[0] if result.data else msg_data


def _create_unmatched_message(client, li_msg: dict) -> None:
    """Create an outreach_messages record for an unmatched inbound message."""
    msg_data = {
        "direction": "inbound",
        "channel": "linkedin",
        "body": li_msg.get("body", ""),
        "status": "received",
        "external_id": li_msg["id"],
        "created_at": li_msg.get("sent_at", datetime.now(timezone.utc).isoformat()),
    }
    try:
        client.table("outreach_messages").insert(msg_data).execute()
    except Exception as e:
        logger.warning("Failed to create unmatched message record: %s", e)


async def _classify_inbound(
    message_text: str,
    prospect: dict,
    outreach_message_id: int,
) -> dict | None:
    """Classify the intent of an inbound message using AI."""
    if not message_text or len(message_text.strip()) < 5:
        return None

    try:
        from scripts.outreach.message_drafter import classify_intent

        # Load pillar context
        pillar_context = None
        if prospect.get("pillar_id"):
            client = get_client()
            pillar_result = (
                client.table("outreach_pillars")
                .select("*")
                .eq("id", prospect["pillar_id"])
                .limit(1)
                .execute()
            )
            if pillar_result.data:
                pillar_context = pillar_result.data[0]

        # Load recent conversation history
        client = get_client()
        history_result = (
            client.table("outreach_messages")
            .select("direction, body, created_at")
            .eq("prospect_id", prospect["id"])
            .order("created_at", desc=True)
            .limit(10)
            .execute()
        )
        conversation_history = [
            {"role": "them" if h["direction"] == "inbound" else "us", "text": h["body"]}
            for h in reversed(history_result.data or [])
        ]

        result = await classify_intent(
            message_text=message_text,
            conversation_history=conversation_history,
            pillar_context=pillar_context,
            prospect_id=prospect["id"],
        )
        return result

    except Exception as e:
        logger.error("Intent classification failed for message: %s", e)
        return None


def _update_enrollment_from_intent(client, prospect: dict, intent_result: dict) -> None:
    """Update enrollment status based on classified intent."""
    intent = intent_result.get("intent", "unknown")
    now = datetime.now(timezone.utc).isoformat()

    # Find active enrollment
    enrollment_result = (
        client.table("outreach_enrollments")
        .select("*")
        .eq("prospect_id", prospect["id"])
        .eq("status", "active")
        .limit(1)
        .execute()
    )
    if not enrollment_result.data:
        return

    enrollment = enrollment_result.data[0]

    # Determine action based on intent
    if intent == "interested":
        client.table("outreach_enrollments").update({
            "status": "replied",
            "updated_at": now,
        }).eq("id", enrollment["id"]).execute()

        client.table("outreach_prospects").update({
            "status": "interested",
            "updated_at": now,
        }).eq("id", prospect["id"]).execute()

    elif intent == "unsubscribe":
        client.table("outreach_enrollments").update({
            "status": "cancelled",
            "updated_at": now,
        }).eq("id", enrollment["id"]).execute()

        client.table("outreach_prospects").update({
            "status": "opted_out",
            "updated_at": now,
        }).eq("id", prospect["id"]).execute()

    elif intent == "not_now":
        client.table("outreach_enrollments").update({
            "status": "paused",
            "updated_at": now,
        }).eq("id", enrollment["id"]).execute()

        client.table("outreach_prospects").update({
            "status": "nurture",
            "updated_at": now,
        }).eq("id", prospect["id"]).execute()

    elif intent in ("question", "referral", "objection"):
        # Keep enrollment active but flag for human review
        client.table("outreach_enrollments").update({
            "status": "replied",
            "updated_at": now,
        }).eq("id", enrollment["id"]).execute()

        client.table("outreach_prospects").update({
            "status": "replied",
            "updated_at": now,
        }).eq("id", prospect["id"]).execute()


def _recalculate_engagement_score(client, prospect_id: int) -> None:
    """
    Recalculate engagement score based on all message interactions.

    Scoring:
      +15 per inbound response
      +20 if any intent is 'interested'
      +10 for 'question' intent
      +10 for 'referral' intent
      +5 per exchange beyond first (max +15)
      -10 for 'not_now'
      -20 for 'unsubscribe'
    """
    # Load all messages for this prospect
    messages_result = (
        client.table("outreach_messages")
        .select("direction, intent, intent_confidence")
        .eq("prospect_id", prospect_id)
        .execute()
    )
    messages = messages_result.data or []

    inbound = [m for m in messages if m.get("direction") == "inbound"]
    engagement_score = 0

    # Base response score
    engagement_score += min(len(inbound) * 15, 30)

    # Intent-based scoring
    intents = [m.get("intent") for m in inbound if m.get("intent")]
    if "interested" in intents:
        engagement_score += 20
    if "question" in intents:
        engagement_score += 10
    if "referral" in intents:
        engagement_score += 10
    if "not_now" in intents:
        engagement_score -= 10
    if "unsubscribe" in intents:
        engagement_score -= 20

    # Multi-exchange bonus
    exchanges = len(inbound)
    if exchanges > 1:
        engagement_score += min((exchanges - 1) * 5, 15)

    # Clamp 0-50
    engagement_score = max(0, min(engagement_score, 50))

    # Load current fit score
    prospect_result = (
        client.table("outreach_prospects")
        .select("fit_score")
        .eq("id", prospect_id)
        .limit(1)
        .execute()
    )
    fit_score = prospect_result.data[0].get("fit_score", 0) if prospect_result.data else 0

    total = fit_score + engagement_score
    now = datetime.now(timezone.utc).isoformat()

    client.table("outreach_prospects").update({
        "engagement_score": engagement_score,
        "lead_score": total,
        "updated_at": now,
    }).eq("id", prospect_id).execute()

    # Record score history
    client.table("outreach_score_history").insert({
        "prospect_id": prospect_id,
        "fit_score": fit_score,
        "engagement_score": engagement_score,
        "lead_score": total,
        "reason": "inbound_response",
    }).execute()

    logger.debug(
        "Prospect %d engagement score: %d (fit: %d, total: %d)",
        prospect_id, engagement_score, fit_score, total,
    )
