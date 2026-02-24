"""
Annas AI Hub — Outreach Enrollments Router
=============================================

Manage prospect enrollments in outreach sequences.

Endpoints:
  GET    /api/outreach/enrollments              - List enrollments
  POST   /api/outreach/enrollments              - Enroll a prospect
  GET    /api/outreach/enrollments/{id}         - Get enrollment details
  PUT    /api/outreach/enrollments/{id}         - Update enrollment
  POST   /api/outreach/enrollments/{id}/pause   - Pause enrollment
  POST   /api/outreach/enrollments/{id}/resume  - Resume enrollment
  POST   /api/outreach/enrollments/{id}/cancel  - Cancel enrollment
  POST   /api/outreach/enrollments/run-workflow - Trigger workflow runner
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from scripts.lib.logger import setup_logger
from scripts.lib.supabase_client import get_client

logger = setup_logger("outreach_enrollments_router")

router = APIRouter(prefix="/api/outreach/enrollments", tags=["outreach-enrollments"])


# ─── Request Models ─────────────────────────────────────────

class EnrollRequest(BaseModel):
    prospect_id: int = Field(..., description="Prospect to enroll")
    sequence_id: int = Field(..., description="Sequence to enroll in")
    start_step: int = Field(1, ge=1, description="Starting step number")
    delay_hours: int = Field(0, ge=0, description="Hours before first step fires")


class UpdateEnrollmentRequest(BaseModel):
    current_step: Optional[int] = None
    next_step_at: Optional[str] = None
    status: Optional[str] = None


class RunWorkflowRequest(BaseModel):
    limit: int = Field(50, ge=1, le=200, description="Max enrollments to process")
    since_minutes: int = Field(60, ge=1, le=1440, description="Correspondence lookback")
    dry_run: bool = Field(False, description="Preview without executing")


# ─── Endpoints ──────────────────────────────────────────────


@router.get("")
async def list_enrollments(
    status: Optional[str] = Query(None, description="Filter: active, paused, completed, cancelled, replied"),
    prospect_id: Optional[int] = Query(None),
    sequence_id: Optional[int] = Query(None),
    pillar_id: Optional[int] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List enrollments with optional filters."""
    try:
        client = get_client()
        query = client.table("outreach_enrollments").select("*", count="exact")

        if status:
            query = query.eq("status", status)
        if prospect_id is not None:
            query = query.eq("prospect_id", prospect_id)
        if sequence_id is not None:
            query = query.eq("sequence_id", sequence_id)

        query = query.order("created_at", desc=True).range(offset, offset + limit - 1)
        result = query.execute()

        enrollments = result.data or []

        # If filtering by pillar, we need to join through sequences
        if pillar_id is not None:
            seq_result = (
                client.table("outreach_sequences")
                .select("id")
                .eq("pillar_id", pillar_id)
                .execute()
            )
            seq_ids = {s["id"] for s in (seq_result.data or [])}
            enrollments = [e for e in enrollments if e.get("sequence_id") in seq_ids]

        return {
            "results": enrollments,
            "count": len(enrollments),
            "total": result.count or 0,
            "offset": offset,
            "limit": limit,
        }
    except Exception as e:
        logger.error("Failed to list enrollments: %s", e)
        raise HTTPException(status_code=500, detail="Failed to fetch enrollments")


@router.post("")
async def enroll_prospect(body: EnrollRequest):
    """
    Enroll a prospect in an outreach sequence.

    Creates the enrollment, sets the first step, and calculates
    when the first message should be drafted (next_step_at).
    """
    try:
        client = get_client()
        now = datetime.now(timezone.utc)

        # Verify prospect exists
        prospect = (
            client.table("outreach_prospects")
            .select("id, status")
            .eq("id", body.prospect_id)
            .limit(1)
            .execute()
        )
        if not prospect.data:
            raise HTTPException(status_code=404, detail=f"Prospect {body.prospect_id} not found")

        # Verify sequence exists
        sequence = (
            client.table("outreach_sequences")
            .select("id, pillar_id, total_steps")
            .eq("id", body.sequence_id)
            .limit(1)
            .execute()
        )
        if not sequence.data:
            raise HTTPException(status_code=404, detail=f"Sequence {body.sequence_id} not found")

        # Check for existing active enrollment
        existing = (
            client.table("outreach_enrollments")
            .select("id")
            .eq("prospect_id", body.prospect_id)
            .eq("sequence_id", body.sequence_id)
            .eq("status", "active")
            .limit(1)
            .execute()
        )
        if existing.data:
            raise HTTPException(
                status_code=409,
                detail=f"Prospect {body.prospect_id} already enrolled in sequence {body.sequence_id}",
            )

        # Calculate when first step fires
        next_step_at = now + timedelta(hours=body.delay_hours)

        enrollment_data = {
            "prospect_id": body.prospect_id,
            "sequence_id": body.sequence_id,
            "current_step": body.start_step,
            "status": "active",
            "next_step_at": next_step_at.isoformat(),
            "enrolled_at": now.isoformat(),
        }

        result = client.table("outreach_enrollments").insert(enrollment_data).execute()

        # Update prospect status
        client.table("outreach_prospects").update({
            "status": "enrolled",
            "updated_at": now.isoformat(),
        }).eq("id", body.prospect_id).execute()

        logger.info(
            "Prospect %d enrolled in sequence %d (step %d, fires at %s)",
            body.prospect_id, body.sequence_id, body.start_step, next_step_at.isoformat(),
        )

        return {
            "status": "enrolled",
            "enrollment": result.data[0] if result.data else enrollment_data,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Enrollment failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Enrollment failed: {e}")


@router.get("/{enrollment_id}")
async def get_enrollment(enrollment_id: int):
    """Get enrollment details with prospect and sequence context."""
    try:
        client = get_client()

        result = (
            client.table("outreach_enrollments")
            .select("*")
            .eq("id", enrollment_id)
            .limit(1)
            .execute()
        )
        if not result.data:
            raise HTTPException(status_code=404, detail=f"Enrollment {enrollment_id} not found")

        enrollment = result.data[0]

        # Enrich with prospect info
        prospect = (
            client.table("outreach_prospects")
            .select("id, first_name, last_name, company_name, job_title, lead_score, status")
            .eq("id", enrollment["prospect_id"])
            .limit(1)
            .execute()
        )

        # Enrich with sequence info
        sequence = (
            client.table("outreach_sequences")
            .select("id, name, pillar_id, total_steps")
            .eq("id", enrollment["sequence_id"])
            .limit(1)
            .execute()
        )

        # Get messages for this enrollment
        messages = (
            client.table("outreach_messages")
            .select("id, direction, channel, status, intent, created_at, sent_at")
            .eq("enrollment_id", enrollment_id)
            .order("created_at", desc=False)
            .execute()
        )

        return {
            **enrollment,
            "prospect": prospect.data[0] if prospect.data else None,
            "sequence": sequence.data[0] if sequence.data else None,
            "messages": messages.data or [],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get enrollment: %s", e)
        raise HTTPException(status_code=500, detail="Failed to fetch enrollment")


@router.put("/{enrollment_id}")
async def update_enrollment(enrollment_id: int, body: UpdateEnrollmentRequest):
    """Update enrollment fields (step, timing, status)."""
    try:
        client = get_client()

        update_data = {"updated_at": datetime.now(timezone.utc).isoformat()}
        if body.current_step is not None:
            update_data["current_step"] = body.current_step
        if body.next_step_at is not None:
            update_data["next_step_at"] = body.next_step_at
        if body.status is not None:
            update_data["status"] = body.status

        result = (
            client.table("outreach_enrollments")
            .update(update_data)
            .eq("id", enrollment_id)
            .execute()
        )
        if not result.data:
            raise HTTPException(status_code=404, detail=f"Enrollment {enrollment_id} not found")

        return {"status": "updated", "enrollment": result.data[0]}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to update enrollment: %s", e)
        raise HTTPException(status_code=500, detail=f"Update failed: {e}")


@router.post("/{enrollment_id}/pause")
async def pause_enrollment(enrollment_id: int):
    """Pause an active enrollment. No further steps will fire until resumed."""
    return await _set_enrollment_status(enrollment_id, "paused", from_statuses=["active"])


@router.post("/{enrollment_id}/resume")
async def resume_enrollment(enrollment_id: int):
    """Resume a paused enrollment. Recalculates next_step_at from now."""
    try:
        client = get_client()
        now = datetime.now(timezone.utc)

        result = (
            client.table("outreach_enrollments")
            .select("*")
            .eq("id", enrollment_id)
            .limit(1)
            .execute()
        )
        if not result.data:
            raise HTTPException(status_code=404, detail=f"Enrollment {enrollment_id} not found")

        enrollment = result.data[0]
        if enrollment["status"] != "paused":
            raise HTTPException(
                status_code=400,
                detail=f"Enrollment is '{enrollment['status']}', expected 'paused'",
            )

        # Recalculate next_step_at: fire the current step in 1 hour
        next_step_at = now + timedelta(hours=1)

        client.table("outreach_enrollments").update({
            "status": "active",
            "next_step_at": next_step_at.isoformat(),
            "updated_at": now.isoformat(),
        }).eq("id", enrollment_id).execute()

        logger.info("Enrollment %d resumed, next step at %s", enrollment_id, next_step_at.isoformat())
        return {"status": "resumed", "next_step_at": next_step_at.isoformat()}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Resume failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Resume failed: {e}")


@router.post("/{enrollment_id}/cancel")
async def cancel_enrollment(enrollment_id: int):
    """Cancel an enrollment permanently. Cannot be resumed."""
    return await _set_enrollment_status(
        enrollment_id, "cancelled", from_statuses=["active", "paused", "replied"]
    )


async def _set_enrollment_status(
    enrollment_id: int, new_status: str, from_statuses: list[str]
) -> dict:
    """Helper to transition enrollment status."""
    try:
        client = get_client()

        result = (
            client.table("outreach_enrollments")
            .select("status")
            .eq("id", enrollment_id)
            .limit(1)
            .execute()
        )
        if not result.data:
            raise HTTPException(status_code=404, detail=f"Enrollment {enrollment_id} not found")

        current = result.data[0]["status"]
        if current not in from_statuses:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot {new_status} enrollment in '{current}' state",
            )

        client.table("outreach_enrollments").update({
            "status": new_status,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", enrollment_id).execute()

        logger.info("Enrollment %d → %s", enrollment_id, new_status)
        return {"status": new_status, "enrollment_id": enrollment_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Status change failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Status change failed: {e}")


@router.post("/run-workflow")
async def trigger_workflow(body: RunWorkflowRequest = RunWorkflowRequest()):
    """
    Manually trigger the outreach workflow runner.

    Processes due enrollments, runs correspondence monitor,
    and recalculates lead scores.
    """
    try:
        from scripts.outreach.workflow_runner import run_full_workflow
        result = await run_full_workflow(
            limit=body.limit,
            since_minutes=body.since_minutes,
            dry_run=body.dry_run,
        )
        return {"status": "complete", **result}
    except Exception as e:
        logger.error("Workflow trigger failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Workflow failed: {e}")
