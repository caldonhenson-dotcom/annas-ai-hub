"""
Annas AI Hub — Outreach Analytics Router
==========================================

Outreach-specific analytics powered by materialised views.

Endpoints:
  GET /api/outreach/analytics/summary     - Per-pillar outreach metrics
  GET /api/outreach/analytics/by-pillar   - Detailed pillar breakdown
  GET /api/outreach/analytics/funnel      - Conversion funnel
  GET /api/outreach/analytics/ai-usage    - AI provider usage stats
  GET /api/outreach/analytics/approval    - Approval queue health
  POST /api/outreach/analytics/refresh    - Refresh materialised views
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from scripts.lib.logger import setup_logger
from scripts.lib.supabase_client import get_client

logger = setup_logger("outreach_analytics_router")

router = APIRouter(prefix="/api/outreach/analytics", tags=["outreach-analytics"])


@router.get("/summary")
async def outreach_summary():
    """
    Per-pillar outreach metrics from mv_outreach_summary.

    Returns: prospects, enrollments, messages sent/received,
    reply rate, conversion rate, avg scores — per pillar.
    """
    try:
        client = get_client()
        result = client.table("mv_outreach_summary").select("*").execute()
        pillars = result.data or []

        # Compute totals
        totals = {
            "total_prospects": sum(p.get("total_prospects", 0) for p in pillars),
            "researched_prospects": sum(p.get("researched_prospects", 0) for p in pillars),
            "total_enrollments": sum(p.get("total_enrollments", 0) for p in pillars),
            "active_enrollments": sum(p.get("active_enrollments", 0) for p in pillars),
            "messages_sent": sum(p.get("messages_sent", 0) for p in pillars),
            "messages_received": sum(p.get("messages_received", 0) for p in pillars),
            "interested_count": sum(p.get("interested_count", 0) for p in pillars),
        }
        total_sent = totals["messages_sent"]
        totals["reply_rate"] = round(
            totals["messages_received"] / total_sent, 3
        ) if total_sent > 0 else 0

        return {
            "pillars": pillars,
            "totals": totals,
            "pillar_count": len(pillars),
        }
    except Exception as e:
        logger.error("Analytics summary failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to fetch analytics summary")


@router.get("/by-pillar")
async def analytics_by_pillar(
    pillar_id: Optional[int] = Query(None, description="Specific pillar ID"),
):
    """
    Detailed breakdown for a single pillar or all pillars.

    Includes prospect status distribution, message channel split,
    and intent classification breakdown.
    """
    try:
        client = get_client()

        # Prospect status distribution
        prospect_query = client.table("outreach_prospects").select("pillar_id, status")
        if pillar_id:
            prospect_query = prospect_query.eq("pillar_id", pillar_id)
        prospects = prospect_query.execute()

        status_counts: dict = {}
        for p in (prospects.data or []):
            st = p.get("status", "unknown")
            status_counts[st] = status_counts.get(st, 0) + 1

        # Message channel and direction breakdown
        msg_query = client.table("outreach_messages").select(
            "channel, direction, intent, prospect_id"
        )
        if pillar_id:
            # Filter by prospects in this pillar
            pid_result = (
                client.table("outreach_prospects")
                .select("id")
                .eq("pillar_id", pillar_id)
                .execute()
            )
            prospect_ids = {r["id"] for r in (pid_result.data or [])}
        else:
            prospect_ids = None

        messages = msg_query.execute()
        msg_data = messages.data or []

        if prospect_ids is not None:
            msg_data = [m for m in msg_data if m.get("prospect_id") in prospect_ids]

        channel_counts: dict = {}
        direction_counts: dict = {"inbound": 0, "outbound": 0}
        intent_counts: dict = {}

        for m in msg_data:
            ch = m.get("channel", "unknown")
            channel_counts[ch] = channel_counts.get(ch, 0) + 1

            d = m.get("direction", "unknown")
            if d in direction_counts:
                direction_counts[d] += 1

            intent = m.get("intent")
            if intent:
                intent_counts[intent] = intent_counts.get(intent, 0) + 1

        return {
            "pillar_id": pillar_id,
            "prospect_status_distribution": status_counts,
            "message_channels": channel_counts,
            "message_directions": direction_counts,
            "intent_distribution": intent_counts,
            "total_prospects": len(prospects.data or []),
            "total_messages": len(msg_data),
        }

    except Exception as e:
        logger.error("Analytics by-pillar failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to fetch pillar analytics")


@router.get("/funnel")
async def outreach_funnel():
    """
    Conversion funnel from mv_outreach_funnel.

    Stages: prospects → researched → enrolled → contacted → replied → interested → converted.
    """
    try:
        client = get_client()
        result = client.table("mv_outreach_funnel").select("*").execute()
        pillars = result.data or []

        # Aggregate funnel
        totals = {
            "total_prospects": sum(p.get("total_prospects", 0) for p in pillars),
            "researched": sum(p.get("researched", 0) for p in pillars),
            "enrolled": sum(p.get("enrolled", 0) for p in pillars),
            "contacted": sum(p.get("contacted", 0) for p in pillars),
            "replied": sum(p.get("replied", 0) for p in pillars),
            "interested": sum(p.get("interested", 0) for p in pillars),
            "converted": sum(p.get("converted", 0) for p in pillars),
        }

        # Calculate stage conversion rates
        stages = ["total_prospects", "researched", "enrolled", "contacted", "replied", "interested", "converted"]
        conversions = {}
        for i in range(1, len(stages)):
            prev = totals[stages[i - 1]]
            curr = totals[stages[i]]
            rate = round(curr / prev, 3) if prev > 0 else 0
            conversions[f"{stages[i-1]}_to_{stages[i]}"] = rate

        return {
            "by_pillar": pillars,
            "totals": totals,
            "stage_conversions": conversions,
        }

    except Exception as e:
        logger.error("Funnel analytics failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to fetch funnel analytics")


@router.get("/ai-usage")
async def ai_usage():
    """
    AI provider usage statistics from mv_ai_usage_summary.

    Returns call counts, token usage, latency, and success rates
    broken down by provider and task.
    """
    try:
        client = get_client()
        result = client.table("mv_ai_usage_summary").select("*").execute()
        rows = result.data or []

        # Aggregate totals
        totals = {
            "total_calls": sum(r.get("total_calls", 0) for r in rows),
            "successful_calls": sum(r.get("successful_calls", 0) for r in rows),
            "failed_calls": sum(r.get("failed_calls", 0) for r in rows),
            "total_input_tokens": sum(r.get("total_input_tokens", 0) for r in rows),
            "total_output_tokens": sum(r.get("total_output_tokens", 0) for r in rows),
            "total_tokens": sum(r.get("total_tokens", 0) for r in rows),
        }
        tc = totals["total_calls"]
        totals["success_rate"] = round(totals["successful_calls"] / tc, 3) if tc > 0 else 0

        # Group by provider
        by_provider: dict = {}
        for r in rows:
            prov = r.get("provider", "unknown")
            if prov not in by_provider:
                by_provider[prov] = {"calls": 0, "tokens": 0, "tasks": []}
            by_provider[prov]["calls"] += r.get("total_calls", 0)
            by_provider[prov]["tokens"] += r.get("total_tokens", 0)
            by_provider[prov]["tasks"].append({
                "task": r.get("task"),
                "calls": r.get("total_calls", 0),
                "tokens": r.get("total_tokens", 0),
                "avg_latency_ms": r.get("avg_latency_ms", 0),
                "p95_latency_ms": r.get("p95_latency_ms", 0),
                "success_rate": r.get("success_rate", 0),
            })

        return {
            "breakdown": rows,
            "totals": totals,
            "by_provider": by_provider,
        }

    except Exception as e:
        logger.error("AI usage analytics failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to fetch AI usage analytics")


@router.get("/approval")
async def approval_metrics():
    """
    Approval queue health from mv_approval_metrics.

    Returns pending/reviewed counts, approval rate, average review time,
    and daily/weekly throughput.
    """
    try:
        client = get_client()
        result = client.table("mv_approval_metrics").select("*").execute()

        if not result.data:
            return {
                "pending_count": 0,
                "approved_count": 0,
                "rejected_count": 0,
                "edited_count": 0,
                "total_reviewed": 0,
                "avg_review_minutes": 0,
                "approval_rate": 0,
                "submitted_today": 0,
                "reviewed_today": 0,
                "submitted_7d": 0,
                "reviewed_7d": 0,
            }

        return result.data[0]

    except Exception as e:
        logger.error("Approval metrics failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to fetch approval metrics")


@router.post("/refresh")
async def refresh_views():
    """
    Refresh all outreach materialised views.

    Calls the refresh_outreach_views() PostgreSQL function.
    This is automatically run after pipeline sync, but can be
    triggered manually for up-to-date analytics.
    """
    try:
        client = get_client()
        client.rpc("refresh_outreach_views").execute()
        return {"status": "refreshed", "views": [
            "mv_outreach_summary",
            "mv_approval_metrics",
            "mv_outreach_funnel",
            "mv_ai_usage_summary",
        ]}
    except Exception as e:
        logger.error("View refresh failed: %s", e)
        raise HTTPException(status_code=500, detail=f"View refresh failed: {e}")
