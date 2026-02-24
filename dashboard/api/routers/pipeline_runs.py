"""
Annas AI Hub — Pipeline Runs Router
=====================================
Pipeline execution history and status.

Endpoints:
  GET /api/pipeline-runs         - List recent pipeline runs
  GET /api/pipeline-runs/latest  - Get the latest run
  GET /api/pipeline-runs/{id}    - Get a specific run
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from scripts.lib.logger import setup_logger
from scripts.lib.supabase_client import get_client

logger = setup_logger("pipeline_runs_router")

router = APIRouter(prefix="/api/pipeline-runs", tags=["pipeline"])


@router.get("")
async def list_runs(
    status: str = Query(None, description="Filter by status: running, success, failed"),
    limit: int = Query(20, ge=1, le=100, description="Max results"),
):
    """List recent pipeline runs."""
    try:
        client = get_client()
        query = client.table("pipeline_runs").select("*")
        if status:
            query = query.eq("status", status)
        result = query.order("started_at", desc=True).limit(limit).execute()
        return {"results": result.data or [], "count": len(result.data or [])}
    except Exception as e:
        logger.error("List pipeline runs failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to fetch pipeline runs")


@router.get("/latest")
async def latest_run():
    """Get the most recent pipeline run."""
    try:
        client = get_client()
        result = (
            client.table("pipeline_runs")
            .select("*")
            .order("started_at", desc=True)
            .limit(1)
            .execute()
        )
        if not result.data:
            raise HTTPException(status_code=404, detail="No pipeline runs found")
        return result.data[0]
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Latest pipeline run failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to fetch latest run")


@router.get("/{run_id}")
async def get_run(run_id: int):
    """Get a specific pipeline run by ID."""
    try:
        client = get_client()
        result = (
            client.table("pipeline_runs")
            .select("*")
            .eq("id", run_id)
            .limit(1)
            .execute()
        )
        if not result.data:
            raise HTTPException(status_code=404, detail="Pipeline run not found")
        return result.data[0]
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Get pipeline run failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to fetch pipeline run")
