"""
Annas AI Hub — Monday.com Router
==================================
M&A projects and IC scores from normalised Monday.com tables.

Endpoints:
  GET /api/monday/projects     - List M&A projects with filters
  GET /api/monday/projects/{id} - Single project detail
  GET /api/monday/ic-scores    - IC scorecard items
  GET /api/monday/boards       - Board overview
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from typing import Optional

from scripts.lib.logger import setup_logger
from scripts.lib.supabase_client import get_client

logger = setup_logger("monday_router")

router = APIRouter(prefix="/api/monday", tags=["monday"])


@router.get("/projects")
async def list_projects(
    stage: Optional[str] = Query(None, description="Filter by stage"),
    owner: Optional[str] = Query(None, description="Filter by owner name"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    sort: str = Query("value", description="Sort field"),
    order: str = Query("desc", description="Sort order: asc or desc"),
    limit: int = Query(50, ge=1, le=200, description="Max results"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
):
    """List M&A projects with filtering and pagination."""
    try:
        client = get_client()
        query = client.table("monday_projects").select("*")

        if stage:
            query = query.eq("stage", stage)
        if owner:
            query = query.ilike("owner", f"%{owner}%")
        if is_active is not None:
            query = query.eq("is_active", is_active)

        desc = order.lower() == "desc"
        query = query.order(sort, desc=desc)
        query = query.range(offset, offset + limit - 1)

        result = query.execute()
        projects = result.data or []

        return {
            "results": projects,
            "count": len(projects),
            "offset": offset,
            "limit": limit,
        }
    except Exception as e:
        logger.error("List projects failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to fetch projects")


@router.get("/projects/{project_id}")
async def get_project(project_id: str):
    """Get a single M&A project."""
    try:
        client = get_client()
        result = (
            client.table("monday_projects")
            .select("*")
            .eq("id", project_id)
            .limit(1)
            .execute()
        )
        if not result.data:
            raise HTTPException(status_code=404, detail="Project not found")
        return result.data[0]
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Get project failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to fetch project")


@router.get("/ic-scores")
async def list_ic_scores(
    min_score: Optional[float] = Query(None, description="Minimum total score"),
    owner: Optional[str] = Query(None, description="Filter by owner"),
    sort: str = Query("total_score", description="Sort field"),
    order: str = Query("desc", description="Sort order"),
    limit: int = Query(50, ge=1, le=200, description="Max results"),
):
    """List IC scorecard items with filtering."""
    try:
        client = get_client()
        query = client.table("monday_ic_scores").select("*")

        if min_score is not None:
            query = query.gte("total_score", min_score)
        if owner:
            query = query.ilike("owner", f"%{owner}%")

        desc = order.lower() == "desc"
        query = query.order(sort, desc=desc)
        query = query.limit(limit)

        result = query.execute()
        return {
            "results": result.data or [],
            "count": len(result.data or []),
        }
    except Exception as e:
        logger.error("IC scores query failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to fetch IC scores")


@router.get("/boards")
async def list_boards():
    """List all Monday.com boards."""
    try:
        client = get_client()
        result = (
            client.table("monday_boards")
            .select("*")
            .order("workspace_name")
            .execute()
        )
        boards = result.data or []

        # Group by workspace
        workspaces: dict = {}
        for b in boards:
            ws = b.get("workspace_name", "Unknown")
            if ws not in workspaces:
                workspaces[ws] = {"workspace": ws, "boards": [], "total_items": 0}
            workspaces[ws]["boards"].append(b)
            workspaces[ws]["total_items"] += b.get("item_count") or 0

        return {
            "workspaces": list(workspaces.values()),
            "total_boards": len(boards),
        }
    except Exception as e:
        logger.error("Boards query failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to fetch boards")
