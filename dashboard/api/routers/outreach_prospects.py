"""
Annas AI Hub — Outreach Prospects Router
==========================================

Prospect management: list, create, update, import, assign.

Endpoints:
  GET  /api/outreach/prospects               - List prospects with filters
  POST /api/outreach/prospects               - Create a single prospect
  GET  /api/outreach/prospects/{id}          - Get a prospect with full context
  PUT  /api/outreach/prospects/{id}          - Update a prospect
  POST /api/outreach/prospects/import        - Bulk import from HubSpot/LinkedIn/CSV
  POST /api/outreach/prospects/assign-pillar - Assign prospects to a pillar
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, UploadFile, File
from typing import Optional

from models.outreach_models import (
    ProspectCreate,
    ProspectUpdate,
    BulkImportRequest,
    PillarAssignRequest,
)
from scripts.lib.logger import setup_logger
from scripts.lib.supabase_client import get_client

logger = setup_logger("outreach_prospects_router")

router = APIRouter(prefix="/api/outreach/prospects", tags=["outreach-prospects"])


@router.get("")
async def list_prospects(
    pillar_id: Optional[int] = Query(None, description="Filter by pillar"),
    status: Optional[str] = Query(None, description="Filter by status"),
    source: Optional[str] = Query(None, description="Filter by source"),
    min_score: Optional[int] = Query(None, description="Minimum lead score"),
    research_status: Optional[str] = Query(None, description="Filter by research status"),
    search: Optional[str] = Query(None, description="Search name/company/email"),
    sort: str = Query("lead_score", description="Sort field"),
    order: str = Query("desc", description="Sort order: asc or desc"),
    limit: int = Query(50, ge=1, le=200, description="Max results"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
):
    """List prospects with filtering and pagination."""
    try:
        client = get_client()
        query = client.table("outreach_prospects").select("*", count="exact")

        if pillar_id is not None:
            query = query.eq("pillar_id", pillar_id)
        if status:
            query = query.eq("status", status)
        if source:
            query = query.eq("source", source)
        if min_score is not None:
            query = query.gte("lead_score", min_score)
        if research_status:
            query = query.eq("research_status", research_status)
        if search:
            query = query.or_(
                f"first_name.ilike.%{search}%,"
                f"last_name.ilike.%{search}%,"
                f"company_name.ilike.%{search}%,"
                f"email.ilike.%{search}%"
            )

        desc = order.lower() == "desc"
        query = query.order(sort, desc=desc)
        query = query.range(offset, offset + limit - 1)

        result = query.execute()
        prospects = result.data or []

        return {
            "results": prospects,
            "count": len(prospects),
            "total": result.count or len(prospects),
            "offset": offset,
            "limit": limit,
        }
    except Exception as e:
        logger.error("List prospects failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to fetch prospects")


@router.post("")
async def create_prospect(body: ProspectCreate):
    """Create a single prospect manually."""
    try:
        from scripts.outreach.prospect_manager import create_prospect
        result = create_prospect(body.model_dump(exclude_none=True))
        return result
    except Exception as e:
        logger.error("Create prospect failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to create prospect")


@router.get("/{prospect_id}")
async def get_prospect(prospect_id: int):
    """Get a single prospect with full context (pillar, messages, enrollment)."""
    try:
        client = get_client()

        # Get prospect
        result = (
            client.table("outreach_prospects")
            .select("*")
            .eq("id", prospect_id)
            .limit(1)
            .execute()
        )
        if not result.data:
            raise HTTPException(status_code=404, detail="Prospect not found")

        prospect = result.data[0]

        # Get pillar info
        if prospect.get("pillar_id"):
            pillar_result = (
                client.table("outreach_pillars")
                .select("id, name, slug")
                .eq("id", prospect["pillar_id"])
                .limit(1)
                .execute()
            )
            prospect["pillar"] = pillar_result.data[0] if pillar_result.data else None
        else:
            prospect["pillar"] = None

        # Get enrollments
        enrollment_result = (
            client.table("outreach_enrollments")
            .select("*")
            .eq("prospect_id", prospect_id)
            .order("enrolled_at", desc=True)
            .execute()
        )
        prospect["enrollments"] = enrollment_result.data or []

        # Get recent messages
        msg_result = (
            client.table("outreach_messages")
            .select("*")
            .eq("prospect_id", prospect_id)
            .order("drafted_at", desc=True)
            .limit(20)
            .execute()
        )
        prospect["messages"] = msg_result.data or []

        # Get score history
        score_result = (
            client.table("outreach_score_history")
            .select("*")
            .eq("prospect_id", prospect_id)
            .order("scored_at", desc=True)
            .limit(10)
            .execute()
        )
        prospect["score_history"] = score_result.data or []

        return prospect
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Get prospect failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to fetch prospect")


@router.put("/{prospect_id}")
async def update_prospect(prospect_id: int, body: ProspectUpdate):
    """Update a prospect's fields."""
    try:
        client = get_client()
        updates = body.model_dump(exclude_none=True)

        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")

        result = (
            client.table("outreach_prospects")
            .update(updates)
            .eq("id", prospect_id)
            .execute()
        )

        if not result.data:
            raise HTTPException(status_code=404, detail="Prospect not found")

        return result.data[0]
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Update prospect failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to update prospect")


@router.post("/import")
async def import_prospects(body: BulkImportRequest):
    """Bulk import prospects from HubSpot or LinkedIn."""
    try:
        if body.source == "hubspot":
            from scripts.outreach.prospect_manager import import_from_hubspot
            result = import_from_hubspot(
                pillar_id=body.pillar_id,
                filters=body.filters,
            )
        elif body.source == "linkedin":
            from scripts.outreach.prospect_manager import import_from_linkedin
            result = import_from_linkedin(pillar_id=body.pillar_id)
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported import source: {body.source}. Use 'hubspot' or 'linkedin'.",
            )

        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Import prospects failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to import prospects")


@router.post("/import-csv")
async def import_csv(
    file: UploadFile = File(...),
    pillar_id: Optional[int] = Query(None, description="Assign to pillar"),
):
    """Import prospects from uploaded CSV file."""
    try:
        content = await file.read()
        csv_text = content.decode("utf-8")

        from scripts.outreach.prospect_manager import import_from_csv
        result = import_from_csv(csv_text, pillar_id=pillar_id)
        return result
    except Exception as e:
        logger.error("CSV import failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to import CSV")


@router.post("/assign-pillar")
async def assign_pillar_to_prospects(body: PillarAssignRequest):
    """Assign or reassign prospects to a pillar."""
    try:
        from scripts.outreach.prospect_manager import assign_pillar
        result = assign_pillar(body.prospect_ids, body.pillar_id)
        return result
    except Exception as e:
        logger.error("Pillar assignment failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to assign pillar")
