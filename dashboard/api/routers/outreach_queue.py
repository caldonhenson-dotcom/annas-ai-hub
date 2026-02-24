"""
Annas AI Hub — Outreach Approval Queue Router
================================================

Human-in-the-loop approval queue API for AI-drafted messages.

Endpoints:
  GET  /api/outreach/queue              - List pending approvals
  GET  /api/outreach/queue/stats        - Queue statistics
  POST /api/outreach/queue/{id}/approve - Approve (optionally edit) a message
  POST /api/outreach/queue/{id}/reject  - Reject a message
  POST /api/outreach/queue/{id}/send    - Send an approved message
  POST /api/outreach/queue/send-batch   - Send all approved messages
  GET  /api/outreach/queue/{id}/history - Message history for an approval
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from scripts.lib.logger import setup_logger

logger = setup_logger("outreach_queue_router")

router = APIRouter(prefix="/api/outreach/queue", tags=["outreach-queue"])


# ─── Request Models ─────────────────────────────────────────

class ApproveRequest(BaseModel):
    reviewer_notes: Optional[str] = Field(None, description="Notes from the reviewer")
    edited_body: Optional[str] = Field(None, description="Edited message body (replaces AI draft)")


class RejectRequest(BaseModel):
    reviewer_notes: Optional[str] = Field(None, description="Reason for rejection")


class SendBatchRequest(BaseModel):
    limit: int = Field(20, ge=1, le=100, description="Max messages to send")


# ─── Queue Endpoints ────────────────────────────────────────


@router.get("")
async def list_pending_approvals(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    pillar_name: Optional[str] = Query(None, description="Filter by pillar name"),
):
    """
    List pending approval items with full message and prospect context.

    Returns enriched approval records with message body, channel, AI model,
    and the prospect snapshot captured at draft time.
    """
    try:
        from scripts.outreach.approval_queue import get_pending_approvals
        return get_pending_approvals(limit=limit, offset=offset, pillar_name=pillar_name)
    except Exception as e:
        logger.error("Failed to list approvals: %s", e)
        raise HTTPException(status_code=500, detail="Failed to fetch approval queue")


@router.get("/stats")
async def approval_stats():
    """
    Queue statistics: counts by status, average review time.

    Returns pending, approved, rejected, edited counts and
    average review time in minutes (from the last 100 reviews).
    """
    try:
        from scripts.outreach.approval_queue import get_approval_stats
        return get_approval_stats()
    except Exception as e:
        logger.error("Failed to get approval stats: %s", e)
        raise HTTPException(status_code=500, detail="Failed to fetch stats")


@router.post("/{approval_id}/approve")
async def approve_message(approval_id: int, body: ApproveRequest = ApproveRequest()):
    """
    Approve a pending message. Optionally edit the body before approval.

    If edited_body is provided, the original AI draft is replaced and the
    approval status is set to 'edited' (vs 'approved'). Both the approval
    record and the outreach_messages record are updated.
    """
    try:
        from scripts.outreach.approval_queue import approve_message as _approve
        result = _approve(
            approval_id,
            reviewer_notes=body.reviewer_notes,
            edited_body=body.edited_body,
        )
        return {"status": "approved", "approval": result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Approval failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Approval failed: {e}")


@router.post("/{approval_id}/reject")
async def reject_message(approval_id: int, body: RejectRequest = RejectRequest()):
    """
    Reject a pending message with optional notes.

    Sets approval status to 'rejected' and message status to 'failed'.
    The message will not be sent.
    """
    try:
        from scripts.outreach.approval_queue import reject_message as _reject
        result = _reject(
            approval_id,
            reviewer_notes=body.reviewer_notes,
        )
        return {"status": "rejected", "approval": result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Rejection failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Rejection failed: {e}")


@router.post("/{approval_id}/send")
async def send_approved_message(approval_id: int):
    """
    Send an approved message via its channel (LinkedIn or email).

    Loads the approval to find the message, then routes to LinkedIn
    Voyager API or Resend email. Updates message status to 'sent',
    advances enrollment step, and calculates next_step_at.
    """
    try:
        from scripts.lib.supabase_client import get_client
        client = get_client()

        # Get the approval to find the message ID
        approval_result = (
            client.table("outreach_approvals")
            .select("message_id, status")
            .eq("id", approval_id)
            .limit(1)
            .execute()
        )
        if not approval_result.data:
            raise HTTPException(status_code=404, detail=f"Approval {approval_id} not found")

        approval = approval_result.data[0]
        if approval["status"] not in ("approved", "edited"):
            raise HTTPException(
                status_code=400,
                detail=f"Approval {approval_id} is '{approval['status']}' — must be approved first",
            )

        from scripts.outreach.message_sender import send_message
        result = await send_message(approval["message_id"])
        return result

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error("Send failed for approval %d: %s", approval_id, e)
        raise HTTPException(status_code=500, detail=f"Send failed: {e}")


@router.post("/send-batch")
async def send_batch(body: SendBatchRequest = SendBatchRequest()):
    """
    Send all approved messages that are ready.

    Returns summary with sent/failed counts. Messages are sent
    sequentially to respect LinkedIn rate limits.
    """
    try:
        from scripts.outreach.message_sender import send_batch as _batch
        return await _batch(limit=body.limit)
    except Exception as e:
        logger.error("Batch send failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Batch send failed: {e}")


@router.get("/{approval_id}/history")
async def approval_message_history(approval_id: int):
    """
    Get the full message thread for an approval item.

    Returns the prospect's complete outreach message history
    (both sent and received) for context when reviewing the draft.
    """
    try:
        from scripts.lib.supabase_client import get_client
        client = get_client()

        # Get the approval
        approval_result = (
            client.table("outreach_approvals")
            .select("prospect_id, message_id")
            .eq("id", approval_id)
            .limit(1)
            .execute()
        )
        if not approval_result.data:
            raise HTTPException(status_code=404, detail=f"Approval {approval_id} not found")

        prospect_id = approval_result.data[0].get("prospect_id")
        if not prospect_id:
            # Get prospect_id from the message
            msg_result = (
                client.table("outreach_messages")
                .select("prospect_id")
                .eq("id", approval_result.data[0]["message_id"])
                .limit(1)
                .execute()
            )
            prospect_id = msg_result.data[0]["prospect_id"] if msg_result.data else None

        if not prospect_id:
            return {"messages": [], "count": 0}

        # Get all messages for this prospect
        messages_result = (
            client.table("outreach_messages")
            .select("*")
            .eq("prospect_id", prospect_id)
            .order("created_at", desc=False)
            .execute()
        )

        return {
            "prospect_id": prospect_id,
            "messages": messages_result.data or [],
            "count": len(messages_result.data or []),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get message history: %s", e)
        raise HTTPException(status_code=500, detail="Failed to fetch message history")


@router.get("/monitor/run")
async def run_correspondence_monitor(
    since_minutes: int = Query(60, ge=1, le=1440, description="Process messages from last N minutes"),
):
    """
    Trigger the correspondence monitor manually.

    Processes new inbound LinkedIn messages: matches to prospects,
    classifies intent via AI, updates enrollment status, and
    recalculates lead scores.
    """
    try:
        from scripts.outreach.correspondence_monitor import process_new_inbound
        result = await process_new_inbound(since_minutes=since_minutes)
        return {"status": "complete", **result}
    except Exception as e:
        logger.error("Correspondence monitor failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Monitor failed: {e}")
