"""
Annas AI Hub — Prospect Research Engine
==========================================

AI-powered prospect research. Loads prospect + pillar context,
builds a layered research prompt, calls the AI provider, parses
the structured JSON brief, and stores it in outreach_prospects.

Usage:
    from scripts.outreach.research_engine import research_prospect, batch_research
    brief = await research_prospect(prospect_id=42)
    results = await batch_research(prospect_ids=[1, 2, 3])
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from scripts.lib.ai_provider import ai_complete, log_ai_error
from scripts.lib.logger import setup_logger
from scripts.lib.supabase_client import get_client

logger = setup_logger("research_engine")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
PROMPTS_PATH = PROJECT_ROOT / "configs" / "outreach_prompts.json"

_prompts_cache: dict | None = None


def _load_prompts() -> dict:
    """Load and cache the prompt library."""
    global _prompts_cache
    if _prompts_cache is not None:
        return _prompts_cache

    with open(PROMPTS_PATH, "r", encoding="utf-8") as f:
        _prompts_cache = json.load(f)
    return _prompts_cache


def _get_prospect(prospect_id: int) -> dict:
    """Load prospect from Supabase."""
    client = get_client()
    result = (
        client.table("outreach_prospects")
        .select("*")
        .eq("id", prospect_id)
        .limit(1)
        .execute()
    )
    if not result.data:
        raise ValueError(f"Prospect {prospect_id} not found")
    return result.data[0]


def _get_pillar(pillar_id: int) -> dict | None:
    """Load pillar from Supabase."""
    client = get_client()
    result = (
        client.table("outreach_pillars")
        .select("*")
        .eq("id", pillar_id)
        .limit(1)
        .execute()
    )
    if not result.data:
        return None

    pillar = result.data[0]
    # Parse JSONB fields if stored as strings
    for field in ("icp_criteria", "messaging_angles", "research_prompts", "objection_handlers"):
        if isinstance(pillar.get(field), str):
            try:
                pillar[field] = json.loads(pillar[field])
            except (json.JSONDecodeError, TypeError):
                pass
    return pillar


def _build_research_prompt(prospect: dict, pillar: dict | None) -> str:
    """
    Build the user-facing research prompt with all context layers.

    Layer 1: Prospect identity
    Layer 2: Pillar context (ICP + research prompts)
    Layer 3: Output schema instructions
    """
    prompts = _load_prompts()
    schema = prompts["research"]["output_schema"]

    # Layer 1: Prospect identity
    sections = ["## Prospect to Research"]
    sections.append(f"- Name: {prospect.get('first_name', '')} {prospect.get('last_name', '')}")
    if prospect.get("job_title"):
        sections.append(f"- Title: {prospect['job_title']}")
    if prospect.get("company_name"):
        sections.append(f"- Company: {prospect['company_name']}")
    if prospect.get("company_domain"):
        sections.append(f"- Website: {prospect['company_domain']}")
    if prospect.get("industry"):
        sections.append(f"- Industry: {prospect['industry']}")
    if prospect.get("company_size"):
        sections.append(f"- Company Size: {prospect['company_size']}")
    if prospect.get("linkedin_url"):
        sections.append(f"- LinkedIn: {prospect['linkedin_url']}")
    if prospect.get("email"):
        sections.append(f"- Email: {prospect['email']}")

    # Layer 2: Pillar context
    if pillar:
        sections.append(f"\n## eComplete Service Context: {pillar['name']}")
        sections.append(f"Description: {pillar.get('description', '')}")

        icp = pillar.get("icp_criteria", {})
        if icp:
            sections.append("\nIdeal Customer Profile:")
            if icp.get("titles"):
                sections.append(f"  Target titles: {', '.join(icp['titles'])}")
            if icp.get("industries"):
                sections.append(f"  Target industries: {', '.join(icp['industries'])}")
            if icp.get("company_size"):
                sections.append(f"  Company size: {icp['company_size']}")
            if icp.get("revenue_range"):
                sections.append(f"  Revenue range: {icp['revenue_range']}")
            if icp.get("signals"):
                sections.append(f"  Buying signals: {', '.join(icp['signals'])}")

        research_prompts = pillar.get("research_prompts", [])
        if research_prompts:
            sections.append("\nSpecific Research Questions:")
            for i, rp in enumerate(research_prompts, 1):
                sections.append(f"  {i}. {rp}")

        angles = pillar.get("messaging_angles", [])
        if angles:
            sections.append("\nMessaging Angles (for context on what we'd pitch):")
            for angle in angles:
                sections.append(f"  - {angle}")

    # Layer 3: Output instructions
    sections.append("\n## Output Instructions")
    sections.append("Return your research as valid JSON matching this schema:")
    sections.append(f"```json\n{json.dumps(schema, indent=2)}\n```")
    sections.append("\nReplace all 'string' placeholders with actual researched content.")
    sections.append("For arrays, include as many relevant items as you find.")
    sections.append("If information is unavailable, use null or explain in the value.")

    return "\n".join(sections)


async def research_prospect(
    prospect_id: int,
    *,
    provider: str | None = None,
    force: bool = False,
) -> dict:
    """
    Research a prospect using AI.

    Args:
        prospect_id: The prospect to research.
        provider: Force a specific AI provider.
        force: Re-research even if a brief already exists.

    Returns:
        The parsed research brief dict.
    """
    client = get_client()
    prospect = _get_prospect(prospect_id)

    # Skip if already researched (unless forced)
    if not force and prospect.get("research_status") == "complete" and prospect.get("research_brief"):
        logger.info("Prospect %d already researched, skipping (use force=True to re-research)", prospect_id)
        return prospect["research_brief"] if isinstance(prospect["research_brief"], dict) else json.loads(prospect["research_brief"])

    # Mark as in-progress
    client.table("outreach_prospects").update({
        "research_status": "in_progress",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", prospect_id).execute()

    # Load pillar context
    pillar = None
    if prospect.get("pillar_id"):
        pillar = _get_pillar(prospect["pillar_id"])

    # Build prompts
    prompts = _load_prompts()
    system_prompt = prompts["research"]["system_prompt"]
    user_prompt = _build_research_prompt(prospect, pillar)

    try:
        response = await ai_complete(
            task="research",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            provider=provider,
            prospect_id=prospect_id,
            json_mode=True,
            max_tokens=3000,
            temperature=0.4,
        )

        # Parse the JSON response
        brief = _parse_research_response(response.content)

        # Store the research brief
        now = datetime.now(timezone.utc).isoformat()
        client.table("outreach_prospects").update({
            "research_brief": json.dumps(brief),
            "research_status": "complete",
            "researched_at": now,
            "updated_at": now,
        }).eq("id", prospect_id).execute()

        # Update fit score based on research
        _update_fit_score_from_research(client, prospect_id, prospect, brief, pillar)

        logger.info(
            "Research complete for prospect %d (%s %s) — confidence: %s",
            prospect_id,
            prospect.get("first_name", ""),
            prospect.get("last_name", ""),
            brief.get("research_confidence", "unknown"),
        )

        return brief

    except Exception as e:
        logger.error("Research failed for prospect %d: %s", prospect_id, e)

        client.table("outreach_prospects").update({
            "research_status": "failed",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", prospect_id).execute()

        await log_ai_error(
            task="research",
            provider=provider or "groq",
            model="unknown",
            error=e,
            prospect_id=prospect_id,
        )

        raise


def _parse_research_response(content: str) -> dict:
    """Parse AI response into a structured research brief."""
    # Try direct JSON parse
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    # Try extracting JSON from markdown code block
    if "```json" in content:
        start = content.index("```json") + 7
        end = content.index("```", start)
        try:
            return json.loads(content[start:end].strip())
        except json.JSONDecodeError:
            pass

    if "```" in content:
        start = content.index("```") + 3
        end = content.index("```", start)
        try:
            return json.loads(content[start:end].strip())
        except json.JSONDecodeError:
            pass

    # Try finding JSON object boundaries
    first_brace = content.find("{")
    last_brace = content.rfind("}")
    if first_brace != -1 and last_brace != -1:
        try:
            return json.loads(content[first_brace:last_brace + 1])
        except json.JSONDecodeError:
            pass

    # Fallback: store as unstructured
    logger.warning("Could not parse research response as JSON, storing as raw text")
    return {
        "raw_response": content,
        "research_confidence": "low",
        "parse_error": True,
    }


def _update_fit_score_from_research(
    client,
    prospect_id: int,
    prospect: dict,
    brief: dict,
    pillar: dict | None,
) -> None:
    """Calculate and update fit score based on research brief + ICP match."""
    fit_score = 0

    if not pillar:
        return

    icp = pillar.get("icp_criteria", {})

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

    # Revenue range heuristic (+10)
    opp = brief.get("opportunity_assessment", {})
    fit_rating = opp.get("fit_rating", "").lower()
    if fit_rating == "very high":
        fit_score += 10
    elif fit_rating == "high":
        fit_score += 8
    elif fit_rating == "medium":
        fit_score += 5

    # Signal match (+5 per signal, max +15)
    target_signals = [s.lower() for s in icp.get("signals", [])]
    pain_points = [p.lower() for p in brief.get("pain_points", [])]
    signal_matches = sum(
        1 for s in target_signals
        if any(s in pp for pp in pain_points)
    )
    fit_score += min(signal_matches * 5, 15)

    # Cap at 50
    fit_score = min(fit_score, 50)

    engagement_score = prospect.get("engagement_score", 0)
    total = fit_score + engagement_score

    now = datetime.now(timezone.utc).isoformat()
    client.table("outreach_prospects").update({
        "fit_score": fit_score,
        "lead_score": total,
        "updated_at": now,
    }).eq("id", prospect_id).execute()

    # Record score history
    client.table("outreach_score_history").insert({
        "prospect_id": prospect_id,
        "fit_score": fit_score,
        "engagement_score": engagement_score,
        "lead_score": total,
        "reason": "research_complete",
    }).execute()


async def batch_research(
    prospect_ids: list[int],
    *,
    provider: str | None = None,
    force: bool = False,
    max_concurrent: int = 3,
) -> dict:
    """
    Research multiple prospects.

    Args:
        prospect_ids: List of prospect IDs to research.
        provider: Force a specific AI provider.
        force: Re-research even if brief exists.
        max_concurrent: Max concurrent AI calls.

    Returns:
        Summary dict with success/fail counts.
    """
    import asyncio

    semaphore = asyncio.Semaphore(max_concurrent)
    results = {"total": len(prospect_ids), "success": 0, "failed": 0, "skipped": 0}

    async def _research_one(pid: int):
        async with semaphore:
            try:
                prospect = _get_prospect(pid)
                if not force and prospect.get("research_status") == "complete":
                    results["skipped"] += 1
                    return
                await research_prospect(pid, provider=provider, force=force)
                results["success"] += 1
            except Exception as e:
                logger.error("Batch research failed for prospect %d: %s", pid, e)
                results["failed"] += 1

    tasks = [_research_one(pid) for pid in prospect_ids]
    await asyncio.gather(*tasks)

    logger.info(
        "Batch research complete: %d success, %d failed, %d skipped",
        results["success"], results["failed"], results["skipped"],
    )
    return results
