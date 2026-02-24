"""
Annas AI Hub — Deals Router
=============================
Filterable deal endpoints querying normalised Supabase tables.

Endpoints:
  GET /api/deals            - List deals with filters
  GET /api/deals/{id}       - Single deal with associations
  GET /api/deals/forecast   - Forecast by close month
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from typing import Optional

from scripts.lib.logger import setup_logger
from scripts.lib.supabase_client import get_client

logger = setup_logger("deals_router")

router = APIRouter(prefix="/api/deals", tags=["deals"])


@router.get("")
async def list_deals(
    stage: Optional[str] = Query(None, description="Filter by stage ID"),
    owner_id: Optional[str] = Query(None, description="Filter by owner ID"),
    pipeline: Optional[str] = Query(None, description="Filter by pipeline ID"),
    is_closed: Optional[bool] = Query(None, description="Filter by closed status"),
    is_closed_won: Optional[bool] = Query(None, description="Filter by won status"),
    min_amount: Optional[float] = Query(None, description="Minimum deal amount"),
    max_amount: Optional[float] = Query(None, description="Maximum deal amount"),
    sort: str = Query("create_date", description="Sort field"),
    order: str = Query("desc", description="Sort order: asc or desc"),
    limit: int = Query(50, ge=1, le=500, description="Max results"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
):
    """List deals with filtering, sorting, and pagination."""
    try:
        client = get_client()
        query = client.table("deals").select(
            "id, name, stage, stage_label, pipeline, amount, weighted_amount, "
            "probability, owner_id, owner_name, close_date, create_date, "
            "last_modified, is_closed_won, is_closed, source, deal_type, "
            "days_in_stage, forecast_amount"
        )

        if stage:
            query = query.eq("stage", stage)
        if owner_id:
            query = query.eq("owner_id", owner_id)
        if pipeline:
            query = query.eq("pipeline", pipeline)
        if is_closed is not None:
            query = query.eq("is_closed", is_closed)
        if is_closed_won is not None:
            query = query.eq("is_closed_won", is_closed_won)
        if min_amount is not None:
            query = query.gte("amount", min_amount)
        if max_amount is not None:
            query = query.lte("amount", max_amount)

        desc = order.lower() == "desc"
        query = query.order(sort, desc=desc)
        query = query.range(offset, offset + limit - 1)

        result = query.execute()
        deals = result.data or []

        # Get total count (separate query)
        count_query = client.table("deals").select("id", count="exact")
        if stage:
            count_query = count_query.eq("stage", stage)
        if owner_id:
            count_query = count_query.eq("owner_id", owner_id)
        if pipeline:
            count_query = count_query.eq("pipeline", pipeline)
        if is_closed is not None:
            count_query = count_query.eq("is_closed", is_closed)
        if is_closed_won is not None:
            count_query = count_query.eq("is_closed_won", is_closed_won)
        count_result = count_query.execute()

        return {
            "results": deals,
            "count": len(deals),
            "total": count_result.count if hasattr(count_result, "count") else len(deals),
            "offset": offset,
            "limit": limit,
        }
    except Exception as e:
        logger.error("List deals failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to fetch deals")


@router.get("/forecast")
async def deal_forecast():
    """Revenue forecast grouped by expected close month."""
    try:
        client = get_client()
        result = (
            client.table("deals")
            .select("close_date, amount, weighted_amount, name, stage_label, owner_name")
            .eq("is_closed", False)
            .not_.is_("close_date", "null")
            .order("close_date")
            .execute()
        )
        deals = result.data or []

        # Group by month
        by_month: dict = {}
        for d in deals:
            month = d.get("close_date", "")[:7]  # YYYY-MM
            if not month:
                continue
            if month not in by_month:
                by_month[month] = {"month": month, "deal_count": 0, "total_value": 0, "weighted_value": 0}
            by_month[month]["deal_count"] += 1
            by_month[month]["total_value"] += d.get("amount") or 0
            by_month[month]["weighted_value"] += d.get("weighted_amount") or 0

        forecast = sorted(by_month.values(), key=lambda x: x["month"])
        return {"forecast": forecast, "deals": deals}
    except Exception as e:
        logger.error("Deal forecast failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to fetch forecast")


@router.get("/{deal_id}")
async def get_deal(deal_id: str):
    """Get a single deal with its associations."""
    try:
        client = get_client()
        result = client.table("deals").select("*").eq("id", deal_id).limit(1).execute()
        if not result.data:
            raise HTTPException(status_code=404, detail="Deal not found")

        deal = result.data[0]

        # Fetch associated contacts
        assoc_result = (
            client.table("associations")
            .select("from_id")
            .eq("to_type", "deal")
            .eq("to_id", deal_id)
            .eq("from_type", "contact")
            .execute()
        )
        contact_ids = [a["from_id"] for a in (assoc_result.data or [])]

        contacts = []
        if contact_ids:
            contacts_result = (
                client.table("contacts")
                .select("id, email, first_name, last_name, company, lifecycle_stage")
                .in_("id", contact_ids)
                .execute()
            )
            contacts = contacts_result.data or []

        # Fetch associated company
        company_assoc = (
            client.table("associations")
            .select("to_id")
            .eq("from_type", "deal")
            .eq("from_id", deal_id)
            .eq("to_type", "company")
            .limit(1)
            .execute()
        )
        company = None
        if company_assoc.data:
            comp_result = (
                client.table("companies")
                .select("*")
                .eq("id", company_assoc.data[0]["to_id"])
                .limit(1)
                .execute()
            )
            if comp_result.data:
                company = comp_result.data[0]

        return {
            **deal,
            "associated_contacts": contacts,
            "associated_company": company,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Get deal failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to fetch deal")
