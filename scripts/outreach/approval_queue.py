"""
Annas AI Hub — Approval Queue
================================

Human-in-the-loop approval system for all AI-drafted outreach messages.
Every message must be approved before sending.

Functions:
  get_pending_approvals()   - List pending items with full context
  approve_message()         - Approve a message (optionally edit)
  reject_message()          - Reject with reviewer notes
  get_approval_stats()      - Queue metrics
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from scripts.lib.logger import setup_logger
from scripts.lib.supabase_client import get_client

logger = setup_logger("approval_queue")


def get_pending_approvals(
    limit: int = 50,
    offset: int = 0,
    pillar_name: str | None = None,
) -> dict:
    """
    Get pending approval items with prospect context.

    Returns:
        Dict with results list and pagination info.
    """
    client = get_client()
    query = (
        client.table("outreach_approvals")
        .select("*")
        .eq("status", "pending")
    )
    if pillar_name:
        query = query.eq("pillar_name", pillar_name)

    query = query.order("submitted_at", desc=True).range(offset, offset + limit - 1)
    result = query.execute()
    approvals = result.data or []

    # Enrich with message body
    enriched = []
    for approval in approvals:
        msg_result = (
            client.table("outreach_messages")
            .select("body, channel, direction, ai_model, template_id")
            .eq("id", approval["message_id"])
            .limit(1)
            .execute()
        )
        message = msg_result.data[0] if msg_result.data else {}

        snapshot = approval.get("prospect_snapshot")
        if isinstance(snapshot, str):
            try:
                snapshot = json.loads(snapshot)
            except (json.JSONDecodeError, TypeError):
                snapshot = {}

        enriched.append({
            **approval,
            "prospect_snapshot": snapshot,
            "message_body": message.get("body", ""),
            "message_channel": message.get("channel", "linkedin"),
            "ai_model": message.get("ai_model"),
        })

    # Count total pending
    count_result = (
        client.table("outreach_approvals")
        .select("id", count="exact")
        .eq("status", "pending")
        .execute()
    )

    return {
        "results": enriched,
        "count": len(enriched),
        "total_pending": count_result.count or 0,
        "offset": offset,
        "limit": limit,
    }


def approve_message(
    approval_id: int,
    reviewer_notes: str | None = None,
    edited_body: str | None = None,
) -> dict:
    """
    Approve a message. Optionally edit the body before approval.

    Args:
        approval_id: The approval queue entry ID.
        reviewer_notes: Optional notes from the reviewer.
        edited_body: If provided, replaces the AI-drafted body.

    Returns:
        The updated approval record.
    """
    client = get_client()
    now = datetime.now(timezone.utc).isoformat()

    # Get the approval
    approval_result = (
        client.table("outreach_approvals")
        .select("*")
        .eq("id", approval_id)
        .limit(1)
        .execute()
    )
    if not approval_result.data:
        raise ValueError(f"Approval {approval_id} not found")

    approval = approval_result.data[0]
    if approval["status"] != "pending":
        raise ValueError(f"Approval {approval_id} is already {approval['status']}")

    # Update the approval
    status = "edited" if edited_body else "approved"
    update = {
        "status": status,
        "reviewer_notes": reviewer_notes,
        "reviewed_at": now,
    }
    if edited_body:
        update["edited_body"] = edited_body

    client.table("outreach_approvals").update(update).eq("id", approval_id).execute()

    # Update the message status and body
    msg_update = {
        "status": "approved",
        "approved_at": now,
    }
    if edited_body:
        msg_update["body"] = edited_body

    client.table("outreach_messages").update(msg_update).eq("id", approval["message_id"]).execute()

    logger.info(
        "Message %d approved (approval_id=%d, edited=%s)",
        approval["message_id"], approval_id, bool(edited_body),
    )

    return {**approval, **update}


def reject_message(
    approval_id: int,
    reviewer_notes: str | None = None,
) -> dict:
    """
    Reject a message draft.

    Args:
        approval_id: The approval queue entry ID.
        reviewer_notes: Reason for rejection.

    Returns:
        The updated approval record.
    """
    client = get_client()
    now = datetime.now(timezone.utc).isoformat()

    approval_result = (
        client.table("outreach_approvals")
        .select("*")
        .eq("id", approval_id)
        .limit(1)
        .execute()
    )
    if not approval_result.data:
        raise ValueError(f"Approval {approval_id} not found")

    approval = approval_result.data[0]
    if approval["status"] != "pending":
        raise ValueError(f"Approval {approval_id} is already {approval['status']}")

    # Update approval
    update = {
        "status": "rejected",
        "reviewer_notes": reviewer_notes,
        "reviewed_at": now,
    }
    client.table("outreach_approvals").update(update).eq("id", approval_id).execute()

    # Update message status
    client.table("outreach_messages").update({
        "status": "failed",
    }).eq("id", approval["message_id"]).execute()

    logger.info(
        "Message %d rejected (approval_id=%d, reason: %s)",
        approval["message_id"], approval_id, reviewer_notes or "none",
    )

    return {**approval, **update}


def get_approval_stats() -> dict:
    """Get approval queue statistics."""
    client = get_client()

    statuses = ["pending", "approved", "rejected", "edited"]
    counts = {}
    for status in statuses:
        result = (
            client.table("outreach_approvals")
            .select("id", count="exact")
            .eq("status", status)
            .execute()
        )
        counts[status] = result.count or 0

    # Average review time (for reviewed items)
    reviewed = (
        client.table("outreach_approvals")
        .select("submitted_at, reviewed_at")
        .neq("status", "pending")
        .order("reviewed_at", desc=True)
        .limit(100)
        .execute()
    )

    avg_review_minutes = 0
    if reviewed.data:
        review_times = []
        for r in reviewed.data:
            if r.get("submitted_at") and r.get("reviewed_at"):
                try:
                    submitted = datetime.fromisoformat(r["submitted_at"].replace("Z", "+00:00"))
                    reviewed_at = datetime.fromisoformat(r["reviewed_at"].replace("Z", "+00:00"))
                    diff = (reviewed_at - submitted).total_seconds() / 60
                    review_times.append(diff)
                except (ValueError, TypeError):
                    pass
        if review_times:
            avg_review_minutes = round(sum(review_times) / len(review_times), 1)

    return {
        "pending": counts.get("pending", 0),
        "approved": counts.get("approved", 0),
        "rejected": counts.get("rejected", 0),
        "edited": counts.get("edited", 0),
        "total_reviewed": counts.get("approved", 0) + counts.get("rejected", 0) + counts.get("edited", 0),
        "avg_review_time_minutes": avg_review_minutes,
    }
