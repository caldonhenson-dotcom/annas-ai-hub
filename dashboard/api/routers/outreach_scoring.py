"""
Annas AI Hub — Outreach Scoring Router
========================================

Lead scoring endpoints: leaderboard, history, recalculation, HubSpot sync.

Endpoints:
  GET  /api/outreach/scoring/leaderboard       - Top prospects by score
  GET  /api/outreach/scoring/{id}/history       - Score history for a prospect
  POST /api/outreach/scoring/{id}/recalculate   - Recalculate one prospect
  POST /api/outreach/scoring/batch-recalculate  - Recalculate all
  POST /api/outreach/scoring/sync-hubspot       - Push scores to HubSpot
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from scripts.lib.logger import setup_logger

logger = setup_logger("outreach_scoring_router")

router = APIRouter(prefix="/api/outreach/scoring", tags=["outreach-scoring"])


# ─── Request Models ─────────────────────────────────────────

class BatchRecalcRequest(BaseModel):
    pillar_id: Optional[int] = Field(None, description="Filter by pillar")
    limit: int = Field(500, ge=1, le=5000, description="Max prospects")


class SyncHubSpotRequest(BaseModel):
    min_score: int = Field(60, ge=0, le=100, description="Minimum score to sync")
    limit: int = Field(100, ge=1, le=500, description="Max prospects to sync")


# ─── Endpoints ──────────────────────────────────────────────


@router.get("/leaderboard")
async def leaderboard(
    limit: int = Query(50, ge=1, le=200),
    pillar_id: Optional[int] = Query(None, description="Filter by pillar"),
    min_score: int = Query(0, ge=0, le=100, description="Minimum lead score"),
):
    """
    Get top prospects ranked by lead score.

    Returns prospect summary with fit_score, engagement_score, lead_score.
    """
    try:
        from scripts.outreach.lead_scorer import get_leaderboard
        prospects = get_leaderboard(limit=limit, pillar_id=pillar_id, min_score=min_score)
        return {"results": prospects, "count": len(prospects)}
    except Exception as e:
        logger.error("Leaderboard query failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to fetch leaderboard")


@router.get("/{prospect_id}/history")
async def score_history(
    prospect_id: int,
    limit: int = Query(50, ge=1, le=200),
):
    """
    Get score history for a specific prospect.

    Shows how the prospect's fit_score, engagement_score, and lead_score
    have changed over time, with the reason for each change.
    """
    try:
        from scripts.outreach.lead_scorer import get_score_history
        history = get_score_history(prospect_id, limit=limit)
        return {"prospect_id": prospect_id, "history": history, "count": len(history)}
    except Exception as e:
        logger.error("Score history query failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to fetch score history")


@router.post("/{prospect_id}/recalculate")
async def recalculate_prospect(prospect_id: int):
    """
    Recalculate lead score for a single prospect.

    Recomputes fit_score from ICP match and engagement_score from
    message interactions, then updates lead_score and logs to history.
    """
    try:
        from scripts.outreach.lead_scorer import recalculate_total
        result = recalculate_total(prospect_id, reason="manual_recalculation")
        return {"status": "recalculated", **result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Recalculation failed for prospect %d: %s", prospect_id, e)
        raise HTTPException(status_code=500, detail=f"Recalculation failed: {e}")


@router.post("/batch-recalculate")
async def batch_recalculate(body: BatchRecalcRequest = BatchRecalcRequest()):
    """
    Recalculate lead scores for all prospects (or filtered by pillar).

    Useful after importing new prospects, updating pillar ICP criteria,
    or to refresh stale scores.
    """
    try:
        from scripts.outreach.lead_scorer import batch_recalculate as _batch
        result = _batch(pillar_id=body.pillar_id, limit=body.limit)
        return {"status": "complete", **result}
    except Exception as e:
        logger.error("Batch recalculation failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Batch recalculation failed: {e}")


@router.post("/sync-hubspot")
async def sync_hubspot(body: SyncHubSpotRequest = SyncHubSpotRequest()):
    """
    Push lead scores to HubSpot as lifecycle stage updates.

    Maps scores: 80+ → opportunity, 60-79 → SQL, 40-59 → MQL, <40 → lead.
    Only syncs prospects with a linked hubspot_contact_id.
    """
    try:
        from scripts.outreach.lead_scorer import sync_to_hubspot
        result = await sync_to_hubspot(min_score=body.min_score, limit=body.limit)
        return {"status": "complete", **result}
    except Exception as e:
        logger.error("HubSpot sync failed: %s", e)
        raise HTTPException(status_code=500, detail=f"HubSpot sync failed: {e}")
