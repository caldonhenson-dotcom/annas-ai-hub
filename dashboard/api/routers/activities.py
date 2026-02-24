"""
Annas AI Hub — Activities Router
==================================
Filterable activity endpoints querying normalised Supabase tables.

Endpoints:
  GET /api/activities          - List activities with filters
  GET /api/activities/daily    - Daily activity trend
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from typing import Optional

from scripts.lib.logger import setup_logger
from scripts.lib.supabase_client import get_client

logger = setup_logger("activities_router")

router = APIRouter(prefix="/api/activities", tags=["activities"])


@router.get("")
async def list_activities(
    type: Optional[str] = Query(None, description="Filter by type: call, email, meeting, task, note"),
    owner_id: Optional[str] = Query(None, description="Filter by owner ID"),
    direction: Optional[str] = Query(None, description="Filter by direction: inbound, outbound"),
    sort: str = Query("activity_date", description="Sort field"),
    order: str = Query("desc", description="Sort order: asc or desc"),
    limit: int = Query(50, ge=1, le=500, description="Max results"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
):
    """List activities with filtering, sorting, and pagination."""
    try:
        client = get_client()
        query = client.table("activities").select(
            "id, type, owner_id, owner_name, subject, direction, "
            "status, duration_ms, activity_date, created_at"
        )

        if type:
            query = query.eq("type", type)
        if owner_id:
            query = query.eq("owner_id", owner_id)
        if direction:
            query = query.eq("direction", direction)

        desc = order.lower() == "desc"
        query = query.order(sort, desc=desc)
        query = query.range(offset, offset + limit - 1)

        result = query.execute()
        activities = result.data or []

        return {
            "results": activities,
            "count": len(activities),
            "offset": offset,
            "limit": limit,
        }
    except Exception as e:
        logger.error("List activities failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to fetch activities")


@router.get("/daily")
async def daily_trend(
    owner_id: Optional[str] = Query(None, description="Filter by owner ID"),
    type: Optional[str] = Query(None, description="Filter by activity type"),
    days: int = Query(30, ge=1, le=365, description="Number of days to look back"),
):
    """Daily activity counts for charting."""
    try:
        client = get_client()
        query = (
            client.table("activities")
            .select("activity_date, type")
            .gte("activity_date", f"now() - interval '{days} days'")
            .order("activity_date")
        )
        if owner_id:
            query = query.eq("owner_id", owner_id)
        if type:
            query = query.eq("type", type)

        result = query.execute()
        activities = result.data or []

        # Group by date
        daily: dict = {}
        for a in activities:
            date = (a.get("activity_date") or "")[:10]
            if not date:
                continue
            if date not in daily:
                daily[date] = {"date": date, "total": 0, "calls": 0, "emails": 0, "meetings": 0, "tasks": 0, "notes": 0}
            daily[date]["total"] += 1
            atype = a.get("type", "")
            if atype in daily[date]:
                daily[date][atype] += 1

        trend = sorted(daily.values(), key=lambda x: x["date"])
        return {"trend": trend, "days": days}
    except Exception as e:
        logger.error("Daily trend query failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to fetch daily trend")
