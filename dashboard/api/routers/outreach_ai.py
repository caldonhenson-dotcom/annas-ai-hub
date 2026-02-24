"""
Annas AI Hub — Outreach AI Router
====================================

AI-powered research, message drafting, intent classification, and logging.

Endpoints:
  POST /api/outreach/ai/research/{prospect_id}        - Research a prospect
  POST /api/outreach/ai/research/batch                 - Batch research
  POST /api/outreach/ai/draft/{prospect_id}            - Draft a message
  POST /api/outreach/ai/reply/{prospect_id}            - Draft a reply
  POST /api/outreach/ai/classify                       - Classify intent
  GET  /api/outreach/ai/logs                           - View AI call logs
  GET  /api/outreach/ai/logs/stats                     - AI usage statistics
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from scripts.lib.logger import setup_logger
from scripts.lib.supabase_client import get_client

logger = setup_logger("outreach_ai_router")

router = APIRouter(prefix="/api/outreach/ai", tags=["outreach-ai"])


# ─── Request Models ─────────────────────────────────────────

class ResearchRequest(BaseModel):
    provider: Optional[str] = Field(None, description="Force AI provider: groq | claude")
    force: bool = Field(False, description="Re-research even if brief exists")


class BatchResearchRequest(BaseModel):
    prospect_ids: list[int] = Field(..., description="List of prospect IDs")
    provider: Optional[str] = None
    force: bool = False
    max_concurrent: int = Field(3, ge=1, le=10)


class DraftRequest(BaseModel):
    sequence_step: int = Field(1, ge=1, le=10, description="Step number in sequence")
    enrollment_id: Optional[int] = Field(None, description="Enrollment ID if enrolled")
    provider: Optional[str] = None


class ReplyRequest(BaseModel):
    inbound_message_id: int = Field(..., description="ID of the inbound message to reply to")
    provider: Optional[str] = None


class ClassifyRequest(BaseModel):
    message_text: str = Field(..., min_length=1, description="Inbound message text")
    prospect_id: Optional[int] = Field(None, description="Prospect ID for context")
    conversation_history: Optional[list[dict]] = Field(None, description="Previous messages for context")
    provider: Optional[str] = None


# ─── Research Endpoints ─────────────────────────────────────


@router.post("/research/{prospect_id}")
async def research_prospect(prospect_id: int, body: ResearchRequest = ResearchRequest()):
    """
    AI-research a prospect.

    Loads prospect + pillar context, calls AI, parses structured brief,
    stores in outreach_prospects.research_brief, updates fit score.
    """
    try:
        from scripts.outreach.research_engine import research_prospect as _research
        brief = await _research(
            prospect_id,
            provider=body.provider,
            force=body.force,
        )
        return {
            "status": "complete",
            "prospect_id": prospect_id,
            "research_brief": brief,
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Research endpoint failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Research failed: {e}")


@router.post("/research/batch")
async def batch_research(body: BatchResearchRequest):
    """
    Research multiple prospects concurrently.

    Returns summary with success/fail/skipped counts.
    """
    try:
        from scripts.outreach.research_engine import batch_research as _batch
        results = await _batch(
            body.prospect_ids,
            provider=body.provider,
            force=body.force,
            max_concurrent=body.max_concurrent,
        )
        return {"status": "complete", "results": results}
    except Exception as e:
        logger.error("Batch research failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Batch research failed: {e}")


# ─── Drafting Endpoints ─────────────────────────────────────


@router.post("/draft/{prospect_id}")
async def draft_message(prospect_id: int, body: DraftRequest):
    """
    Draft an AI-personalized outbound message for a prospect.

    Uses 6-layer context: system prompt + pillar + research + template + history + intent.
    Creates message (status='pending_approval') and approval queue entry.
    """
    try:
        from scripts.outreach.message_drafter import draft_message as _draft
        message = await _draft(
            prospect_id,
            sequence_step=body.sequence_step,
            enrollment_id=body.enrollment_id,
            provider=body.provider,
        )
        return {
            "status": "drafted",
            "message_id": message["id"],
            "body_preview": message["body"][:200],
            "channel": message.get("channel", "linkedin"),
            "ai_model": message.get("ai_model"),
            "approval_required": True,
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Draft endpoint failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Drafting failed: {e}")


@router.post("/reply/{prospect_id}")
async def draft_reply(prospect_id: int, body: ReplyRequest):
    """
    Draft an AI reply to a prospect's inbound message.

    Loads full conversation + intent + pillar objection handlers.
    Creates reply (status='pending_approval') and approval queue entry.
    """
    try:
        from scripts.outreach.message_drafter import draft_reply as _reply
        message = await _reply(
            prospect_id,
            inbound_message_id=body.inbound_message_id,
            provider=body.provider,
        )
        return {
            "status": "drafted",
            "message_id": message["id"],
            "body_preview": message["body"][:200],
            "channel": message.get("channel", "linkedin"),
            "ai_model": message.get("ai_model"),
            "approval_required": True,
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Reply draft endpoint failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Reply drafting failed: {e}")


# ─── Intent Classification ──────────────────────────────────


@router.post("/classify")
async def classify_intent(body: ClassifyRequest):
    """
    Classify the intent of an inbound message using AI.

    Returns: intent, confidence, key_signals, sentiment, suggested_action.
    """
    try:
        from scripts.outreach.message_drafter import classify_intent as _classify

        # Load pillar context if prospect provided
        pillar_context = None
        if body.prospect_id:
            client = get_client()
            prospect_result = (
                client.table("outreach_prospects")
                .select("pillar_id")
                .eq("id", body.prospect_id)
                .limit(1)
                .execute()
            )
            if prospect_result.data and prospect_result.data[0].get("pillar_id"):
                pillar_result = (
                    client.table("outreach_pillars")
                    .select("*")
                    .eq("id", prospect_result.data[0]["pillar_id"])
                    .limit(1)
                    .execute()
                )
                if pillar_result.data:
                    pillar_context = pillar_result.data[0]

        result = await _classify(
            message_text=body.message_text,
            conversation_history=body.conversation_history,
            pillar_context=pillar_context,
            prospect_id=body.prospect_id,
            provider=body.provider,
        )
        return result
    except Exception as e:
        logger.error("Classification failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Classification failed: {e}")


# ─── AI Logs ────────────────────────────────────────────────


@router.get("/logs")
async def list_ai_logs(
    task: Optional[str] = Query(None, description="Filter by task type"),
    provider: Optional[str] = Query(None, description="Filter by provider"),
    prospect_id: Optional[int] = Query(None, description="Filter by prospect"),
    success: Optional[bool] = Query(None, description="Filter by success status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """View AI call audit logs with optional filters."""
    try:
        client = get_client()
        query = client.table("outreach_ai_logs").select("*", count="exact")

        if task:
            query = query.eq("task", task)
        if provider:
            query = query.eq("provider", provider)
        if prospect_id is not None:
            query = query.eq("prospect_id", prospect_id)
        if success is not None:
            query = query.eq("success", success)

        query = query.order("created_at", desc=True).range(offset, offset + limit - 1)
        result = query.execute()

        return {
            "results": result.data or [],
            "count": len(result.data or []),
            "total": result.count or 0,
            "offset": offset,
            "limit": limit,
        }
    except Exception as e:
        logger.error("AI logs query failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to fetch AI logs")


@router.get("/logs/stats")
async def ai_usage_stats():
    """
    AI usage statistics: total calls, tokens, latency, by provider/task.
    """
    try:
        client = get_client()

        # Total counts
        all_logs = client.table("outreach_ai_logs").select("*").execute()
        logs = all_logs.data or []

        if not logs:
            return {
                "total_calls": 0,
                "total_input_tokens": 0,
                "total_output_tokens": 0,
                "avg_latency_ms": 0,
                "success_rate": 0,
                "by_task": {},
                "by_provider": {},
            }

        total_calls = len(logs)
        successful = sum(1 for l in logs if l.get("success", True))
        total_input = sum(l.get("input_tokens", 0) or 0 for l in logs)
        total_output = sum(l.get("output_tokens", 0) or 0 for l in logs)
        latencies = [l.get("latency_ms", 0) or 0 for l in logs if l.get("latency_ms")]
        avg_latency = sum(latencies) / len(latencies) if latencies else 0

        # Group by task
        by_task: dict = {}
        for l in logs:
            task = l.get("task", "unknown")
            if task not in by_task:
                by_task[task] = {"calls": 0, "tokens": 0, "errors": 0}
            by_task[task]["calls"] += 1
            by_task[task]["tokens"] += (l.get("input_tokens", 0) or 0) + (l.get("output_tokens", 0) or 0)
            if not l.get("success", True):
                by_task[task]["errors"] += 1

        # Group by provider
        by_provider: dict = {}
        for l in logs:
            prov = l.get("provider", "unknown")
            if prov not in by_provider:
                by_provider[prov] = {"calls": 0, "tokens": 0, "avg_latency_ms": 0, "_latencies": []}
            by_provider[prov]["calls"] += 1
            by_provider[prov]["tokens"] += (l.get("input_tokens", 0) or 0) + (l.get("output_tokens", 0) or 0)
            if l.get("latency_ms"):
                by_provider[prov]["_latencies"].append(l["latency_ms"])

        for prov in by_provider.values():
            lats = prov.pop("_latencies")
            prov["avg_latency_ms"] = int(sum(lats) / len(lats)) if lats else 0

        return {
            "total_calls": total_calls,
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_tokens": total_input + total_output,
            "avg_latency_ms": int(avg_latency),
            "success_rate": round(successful / total_calls, 3) if total_calls else 0,
            "by_task": by_task,
            "by_provider": by_provider,
        }
    except Exception as e:
        logger.error("AI stats query failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to compute AI stats")
