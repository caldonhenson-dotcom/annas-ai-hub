"""
Annas AI Hub — Lead Scorer
=============================

Composite lead scoring model (0-100):
  Fit Score (0-50):   ICP title match, industry, company size, revenue, signals
  Engagement Score (0-50): Response, intent, multi-exchange, negative signals

Functions:
  calculate_fit_score()        - ICP-based scoring from prospect + pillar data
  calculate_engagement_score() - Interaction-based scoring from messages
  recalculate_total()          - Recalculate total score for one prospect
  batch_recalculate()          - Recalculate all prospects
  sync_to_hubspot()            - Push scores to HubSpot lifecycle stages
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from scripts.lib.logger import setup_logger
from scripts.lib.supabase_client import get_client

logger = setup_logger("lead_scorer")


def calculate_fit_score(prospect: dict, pillar: dict | None) -> int:
    """
    Calculate fit score (0-50) based on ICP criteria match.

    Scoring:
      +10  Title match (job title contains target title keyword)
      +10  Industry match
      +5   Company size match
      +10  Revenue range match (from research brief fit_rating)
      +5   Per signal match (max +15)
    """
    if not pillar:
        return 0

    icp = pillar.get("icp_criteria", {})
    if isinstance(icp, str):
        try:
            icp = json.loads(icp)
        except (json.JSONDecodeError, TypeError):
            icp = {}

    fit_score = 0

    # Title match (+10)
    target_titles = [t.lower() for t in icp.get("titles", [])]
    job_title = (prospect.get("job_title") or "").lower()
    if any(t in job_title for t in target_titles):
        fit_score += 10

    # Industry match (+10)
    target_industries = [i.lower() for i in icp.get("industries", [])]
    industry = (prospect.get("industry") or "").lower()
    if any(i in industry for i in target_industries):
        fit_score += 10

    # Company size match (+5)
    target_size = icp.get("company_size", "")
    company_size = prospect.get("company_size", "")
    if target_size and company_size:
        fit_score += 5

    # Revenue / fit rating from research brief (+10)
    research_brief = prospect.get("research_brief")
    if isinstance(research_brief, str):
        try:
            research_brief = json.loads(research_brief)
        except (json.JSONDecodeError, TypeError):
            research_brief = {}

    if research_brief and isinstance(research_brief, dict):
        opp = research_brief.get("opportunity_assessment", {})
        fit_rating = (opp.get("fit_rating") or "").lower()
        if fit_rating == "very high":
            fit_score += 10
        elif fit_rating == "high":
            fit_score += 8
        elif fit_rating == "medium":
            fit_score += 5

        # Signal matches (+5 each, max +15)
        target_signals = [s.lower() for s in icp.get("signals", [])]
        pain_points = [p.lower() for p in research_brief.get("pain_points", [])]
        signal_matches = sum(
            1 for s in target_signals
            if any(s in pp for pp in pain_points)
        )
        fit_score += min(signal_matches * 5, 15)

    return min(fit_score, 50)


def calculate_engagement_score(prospect_id: int) -> int:
    """
    Calculate engagement score (0-50) based on message interactions.

    Scoring:
      +15  Per inbound response (max +30)
      +20  Any 'interested' intent
      +10  Any 'question' intent
      +10  Any 'referral' intent
      +5   Per exchange beyond first (max +15)
      -10  'not_now' intent
      -20  'unsubscribe' intent
    """
    client = get_client()

    messages_result = (
        client.table("outreach_messages")
        .select("direction, intent, intent_confidence")
        .eq("prospect_id", prospect_id)
        .execute()
    )
    messages = messages_result.data or []

    inbound = [m for m in messages if m.get("direction") == "inbound"]
    score = 0

    # Base response score
    score += min(len(inbound) * 15, 30)

    # Intent-based scoring
    intents = [m.get("intent") for m in inbound if m.get("intent")]
    if "interested" in intents:
        score += 20
    if "question" in intents:
        score += 10
    if "referral" in intents:
        score += 10
    if "not_now" in intents:
        score -= 10
    if "unsubscribe" in intents:
        score -= 20

    # Multi-exchange bonus
    if len(inbound) > 1:
        score += min((len(inbound) - 1) * 5, 15)

    return max(0, min(score, 50))


def recalculate_total(
    prospect_id: int,
    reason: str = "manual_recalculation",
) -> dict:
    """
    Recalculate total lead score for a single prospect.

    Loads prospect + pillar, calculates both sub-scores,
    updates the prospect record, and logs to score_history.

    Returns:
        Dict with fit_score, engagement_score, lead_score.
    """
    client = get_client()
    now = datetime.now(timezone.utc).isoformat()

    # Load prospect
    prospect_result = (
        client.table("outreach_prospects")
        .select("*")
        .eq("id", prospect_id)
        .limit(1)
        .execute()
    )
    if not prospect_result.data:
        raise ValueError(f"Prospect {prospect_id} not found")

    prospect = prospect_result.data[0]

    # Load pillar
    pillar = None
    if prospect.get("pillar_id"):
        pillar_result = (
            client.table("outreach_pillars")
            .select("*")
            .eq("id", prospect["pillar_id"])
            .limit(1)
            .execute()
        )
        if pillar_result.data:
            pillar = pillar_result.data[0]
            # Parse JSONB fields
            for field in ("icp_criteria", "messaging_angles", "research_prompts", "objection_handlers"):
                if isinstance(pillar.get(field), str):
                    try:
                        pillar[field] = json.loads(pillar[field])
                    except (json.JSONDecodeError, TypeError):
                        pass

    fit = calculate_fit_score(prospect, pillar)
    engagement = calculate_engagement_score(prospect_id)
    total = fit + engagement

    # Update prospect
    client.table("outreach_prospects").update({
        "fit_score": fit,
        "engagement_score": engagement,
        "lead_score": total,
        "updated_at": now,
    }).eq("id", prospect_id).execute()

    # Log to history
    client.table("outreach_score_history").insert({
        "prospect_id": prospect_id,
        "fit_score": fit,
        "engagement_score": engagement,
        "lead_score": total,
        "reason": reason,
    }).execute()

    logger.info(
        "Prospect %d scored: fit=%d, engagement=%d, total=%d (reason: %s)",
        prospect_id, fit, engagement, total, reason,
    )

    return {
        "prospect_id": prospect_id,
        "fit_score": fit,
        "engagement_score": engagement,
        "lead_score": total,
    }


def batch_recalculate(
    pillar_id: int | None = None,
    limit: int = 500,
) -> dict:
    """
    Recalculate scores for all prospects (or filtered by pillar).

    Args:
        pillar_id: Optional pillar filter.
        limit: Max prospects to process.

    Returns:
        Summary with total/success/failed counts.
    """
    client = get_client()

    query = client.table("outreach_prospects").select("id").limit(limit)
    if pillar_id:
        query = query.eq("pillar_id", pillar_id)

    result = query.execute()
    prospect_ids = [r["id"] for r in (result.data or [])]

    stats = {"total": len(prospect_ids), "success": 0, "failed": 0}

    for pid in prospect_ids:
        try:
            recalculate_total(pid, reason="batch_recalculation")
            stats["success"] += 1
        except Exception as e:
            logger.error("Score recalculation failed for prospect %d: %s", pid, e)
            stats["failed"] += 1

    logger.info(
        "Batch recalculation complete: %d success, %d failed out of %d",
        stats["success"], stats["failed"], stats["total"],
    )
    return stats


def get_leaderboard(
    limit: int = 50,
    pillar_id: int | None = None,
    min_score: int = 0,
) -> list[dict]:
    """
    Get top prospects by lead score.

    Args:
        limit: Max results.
        pillar_id: Optional pillar filter.
        min_score: Minimum lead score threshold.

    Returns:
        List of prospect summaries ordered by lead_score desc.
    """
    client = get_client()

    query = (
        client.table("outreach_prospects")
        .select("id, first_name, last_name, company_name, job_title, "
                "pillar_id, fit_score, engagement_score, lead_score, status")
        .gte("lead_score", min_score)
        .order("lead_score", desc=True)
        .limit(limit)
    )
    if pillar_id:
        query = query.eq("pillar_id", pillar_id)

    result = query.execute()
    return result.data or []


def get_score_history(prospect_id: int, limit: int = 50) -> list[dict]:
    """Get score history for a prospect."""
    client = get_client()

    result = (
        client.table("outreach_score_history")
        .select("*")
        .eq("prospect_id", prospect_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data or []


async def sync_to_hubspot(
    min_score: int = 60,
    limit: int = 100,
) -> dict:
    """
    Sync high-scoring prospects to HubSpot as lifecycle stage updates.

    Maps lead scores to HubSpot lifecycle stages:
      80-100  → opportunity
      60-79   → salesqualifiedlead
      40-59   → marketingqualifiedlead
      0-39    → lead

    Args:
        min_score: Only sync prospects at or above this score.
        limit: Max prospects to sync.

    Returns:
        Summary with synced/failed counts.
    """
    client = get_client()

    prospects = (
        client.table("outreach_prospects")
        .select("id, hubspot_contact_id, lead_score, first_name, last_name")
        .gte("lead_score", min_score)
        .not_.is_("hubspot_contact_id", "null")
        .order("lead_score", desc=True)
        .limit(limit)
        .execute()
    )

    if not prospects.data:
        return {"synced": 0, "failed": 0, "total": 0}

    stats = {"synced": 0, "failed": 0, "total": len(prospects.data)}

    try:
        from integrations.hubspot import HubSpotIntegration
        hs = HubSpotIntegration()
        if not hs.is_configured:
            return {"error": "HubSpot not configured", **stats}
    except Exception as e:
        return {"error": f"HubSpot unavailable: {e}", **stats}

    for prospect in prospects.data:
        score = prospect.get("lead_score", 0)
        hubspot_id = prospect["hubspot_contact_id"]

        if score >= 80:
            stage = "opportunity"
        elif score >= 60:
            stage = "salesqualifiedlead"
        elif score >= 40:
            stage = "marketingqualifiedlead"
        else:
            stage = "lead"

        try:
            await hs.update_contact(hubspot_id, {
                "lifecyclestage": stage,
                "hs_lead_status": "OPEN",
                "anna_lead_score": str(score),
            })
            stats["synced"] += 1
            logger.debug(
                "Synced prospect %d → HubSpot %s (stage: %s, score: %d)",
                prospect["id"], hubspot_id, stage, score,
            )
        except Exception as e:
            logger.error(
                "HubSpot sync failed for prospect %d: %s", prospect["id"], e,
            )
            stats["failed"] += 1

    logger.info(
        "HubSpot sync: %d synced, %d failed out of %d",
        stats["synced"], stats["failed"], stats["total"],
    )
    return stats
