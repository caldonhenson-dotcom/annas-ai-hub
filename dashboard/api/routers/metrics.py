"""
Annas AI Hub — Metrics Router
===============================
Aggregated metrics endpoints querying materialised views and normalised tables.

Endpoints:
  GET /api/metrics/pipeline    - Pipeline summary from v_pipeline_summary
  GET /api/metrics/activity    - Activity summary from v_activity_by_rep
  GET /api/metrics/leads       - Lead funnel from v_lead_funnel
  GET /api/metrics/kpis        - Weekly KPIs from v_weekly_kpis
  GET /api/metrics/velocity    - Deal velocity from v_deal_velocity
  GET /api/metrics/ma          - M&A pipeline from v_ma_pipeline
  GET /api/metrics/snapshot    - Full snapshot (replaces old JSON endpoint)
  GET /api/metrics/freshness   - Data freshness per source
  GET /api/metrics/diffs       - Recent snapshot diffs
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from scripts.lib.logger import setup_logger
from scripts.lib.supabase_client import get_client, query_table

logger = setup_logger("metrics_router")

router = APIRouter(prefix="/api/metrics", tags=["metrics"])


@router.get("/pipeline")
async def pipeline_summary():
    """Aggregated pipeline metrics by stage."""
    try:
        client = get_client()
        result = client.table("v_pipeline_summary").select("*").order(
            "display_order"
        ).execute()
        stages = result.data or []

        # Compute totals
        total_value = sum(s.get("total_value", 0) or 0 for s in stages)
        weighted_value = sum(s.get("weighted_value", 0) or 0 for s in stages)
        total_deals = sum(s.get("deal_count", 0) or 0 for s in stages)
        won = sum(s.get("won_count", 0) or 0 for s in stages)
        lost = sum(s.get("lost_count", 0) or 0 for s in stages)
        open_count = sum(s.get("open_count", 0) or 0 for s in stages)

        return {
            "stages": stages,
            "totals": {
                "total_pipeline_value": total_value,
                "weighted_pipeline_value": weighted_value,
                "total_deals": total_deals,
                "won": won,
                "lost": lost,
                "open": open_count,
                "win_rate": round(won / max(won + lost, 1), 4),
            },
        }
    except Exception as e:
        logger.error("Pipeline summary query failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to fetch pipeline metrics")


@router.get("/activity")
async def activity_summary():
    """Activity metrics by rep."""
    try:
        client = get_client()
        result = client.table("v_activity_by_rep").select("*").order(
            "total_activities", desc=True
        ).execute()
        reps = result.data or []

        total = sum(r.get("total_activities", 0) or 0 for r in reps)
        return {
            "by_rep": reps,
            "totals": {
                "total_activities": total,
                "total_calls": sum(r.get("calls", 0) or 0 for r in reps),
                "total_emails": sum(r.get("emails", 0) or 0 for r in reps),
                "total_meetings": sum(r.get("meetings", 0) or 0 for r in reps),
                "rep_count": len(reps),
            },
        }
    except Exception as e:
        logger.error("Activity summary query failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to fetch activity metrics")


@router.get("/leads")
async def lead_funnel():
    """Lead lifecycle funnel."""
    try:
        client = get_client()
        result = client.table("v_lead_funnel").select("*").execute()
        return {"funnel": result.data or []}
    except Exception as e:
        logger.error("Lead funnel query failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to fetch lead metrics")


@router.get("/kpis")
async def weekly_kpis():
    """Rolling KPIs (7d, 30d, 90d windows)."""
    try:
        client = get_client()
        result = client.table("v_weekly_kpis").select("*").limit(1).execute()
        if result.data:
            return result.data[0]
        return {}
    except Exception as e:
        logger.error("KPIs query failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to fetch KPIs")


@router.get("/velocity")
async def deal_velocity(
    owner_id: str = Query(None, description="Filter by owner ID"),
    pipeline: str = Query(None, description="Filter by pipeline ID"),
):
    """Deal velocity and conversion metrics."""
    try:
        client = get_client()
        query = client.table("v_deal_velocity").select("*")
        if owner_id:
            query = query.eq("owner_id", owner_id)
        if pipeline:
            query = query.eq("pipeline", pipeline)
        result = query.order("total_won_revenue", desc=True).execute()
        return {"velocity": result.data or []}
    except Exception as e:
        logger.error("Deal velocity query failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to fetch velocity metrics")


@router.get("/ma")
async def ma_pipeline():
    """M&A pipeline summary from Monday.com data."""
    try:
        client = get_client()
        result = client.table("v_ma_pipeline").select("*").order(
            "total_value", desc=True
        ).execute()
        stages = result.data or []

        total_value = sum(s.get("total_value", 0) or 0 for s in stages)
        active_count = sum(s.get("active_count", 0) or 0 for s in stages)

        return {
            "stages": stages,
            "totals": {
                "total_value": total_value,
                "active_projects": active_count,
            },
        }
    except Exception as e:
        logger.error("M&A pipeline query failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to fetch M&A metrics")


@router.get("/snapshot")
async def latest_snapshot(source: str = Query("hubspot_sales", description="Snapshot source")):
    """Full latest snapshot for a source (backwards compatible with old JSON endpoint)."""
    try:
        from scripts.lib.supabase_client import get_latest_snapshot
        data = get_latest_snapshot(source)
        if not data:
            raise HTTPException(status_code=404, detail=f"No snapshot for source: {source}")
        return data
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Snapshot query failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to fetch snapshot")


@router.get("/freshness")
async def data_freshness():
    """Data freshness status per source."""
    try:
        rows = query_table("data_freshness", order_by="updated_at", desc=True)
        return {"sources": rows}
    except Exception as e:
        logger.error("Data freshness query failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to fetch freshness data")


@router.get("/diffs")
async def snapshot_diffs(
    source: str = Query(None, description="Filter by source"),
    limit: int = Query(10, ge=1, le=50, description="Max results"),
):
    """Recent snapshot diffs showing metric changes between pipeline runs."""
    try:
        client = get_client()
        query = client.table("snapshot_diffs").select("*")
        if source:
            query = query.eq("source", source)
        result = query.order("generated_at", desc=True).limit(limit).execute()
        return {"diffs": result.data or []}
    except Exception as e:
        logger.error("Snapshot diffs query failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to fetch diffs")
