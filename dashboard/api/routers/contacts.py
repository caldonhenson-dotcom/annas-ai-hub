"""
Annas AI Hub — Contacts Router
================================
Filterable contact endpoints querying normalised Supabase tables.

Endpoints:
  GET /api/contacts            - List contacts with filters
  GET /api/contacts/{id}       - Single contact with associations
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from typing import Optional

from scripts.lib.logger import setup_logger
from scripts.lib.supabase_client import get_client

logger = setup_logger("contacts_router")

router = APIRouter(prefix="/api/contacts", tags=["contacts"])


@router.get("")
async def list_contacts(
    lifecycle_stage: Optional[str] = Query(None, description="Filter by lifecycle stage"),
    lead_status: Optional[str] = Query(None, description="Filter by lead status"),
    owner_id: Optional[str] = Query(None, description="Filter by owner ID"),
    source: Optional[str] = Query(None, description="Filter by analytics source"),
    company: Optional[str] = Query(None, description="Filter by company name (partial match)"),
    sort: str = Query("create_date", description="Sort field"),
    order: str = Query("desc", description="Sort order: asc or desc"),
    limit: int = Query(50, ge=1, le=500, description="Max results"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
):
    """List contacts with filtering, sorting, and pagination."""
    try:
        client = get_client()
        query = client.table("contacts").select(
            "id, email, first_name, last_name, company, phone, "
            "lifecycle_stage, lead_status, source, owner_id, owner_name, "
            "create_date, last_modified, page_views, visits, num_deals"
        )

        if lifecycle_stage:
            query = query.eq("lifecycle_stage", lifecycle_stage)
        if lead_status:
            query = query.eq("lead_status", lead_status)
        if owner_id:
            query = query.eq("owner_id", owner_id)
        if source:
            query = query.eq("source", source)
        if company:
            query = query.ilike("company", f"%{company}%")

        desc = order.lower() == "desc"
        query = query.order(sort, desc=desc)
        query = query.range(offset, offset + limit - 1)

        result = query.execute()
        contacts = result.data or []

        return {
            "results": contacts,
            "count": len(contacts),
            "offset": offset,
            "limit": limit,
        }
    except Exception as e:
        logger.error("List contacts failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to fetch contacts")


@router.get("/{contact_id}")
async def get_contact(contact_id: str):
    """Get a single contact with associated deals and company."""
    try:
        client = get_client()
        result = client.table("contacts").select("*").eq("id", contact_id).limit(1).execute()
        if not result.data:
            raise HTTPException(status_code=404, detail="Contact not found")

        contact = result.data[0]

        # Fetch associated deals
        assoc_result = (
            client.table("associations")
            .select("to_id")
            .eq("from_type", "contact")
            .eq("from_id", contact_id)
            .eq("to_type", "deal")
            .execute()
        )
        deal_ids = [a["to_id"] for a in (assoc_result.data or [])]

        deals = []
        if deal_ids:
            deals_result = (
                client.table("deals")
                .select("id, name, stage_label, amount, close_date, is_closed_won, is_closed")
                .in_("id", deal_ids)
                .execute()
            )
            deals = deals_result.data or []

        # Fetch associated company
        company_assoc = (
            client.table("associations")
            .select("to_id")
            .eq("from_type", "contact")
            .eq("from_id", contact_id)
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

        # Fetch recent activities (if contact has associated activities)
        activities = []
        try:
            act_result = (
                client.table("activities")
                .select("id, type, subject, direction, status, activity_date")
                .eq("owner_id", contact.get("owner_id", ""))
                .order("activity_date", desc=True)
                .limit(20)
                .execute()
            )
            activities = act_result.data or []
        except Exception:
            pass

        return {
            **contact,
            "associated_deals": deals,
            "associated_company": company,
            "recent_activities": activities,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Get contact failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to fetch contact")
