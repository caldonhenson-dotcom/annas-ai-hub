"""
Annas AI Hub — Message Drafter
=================================

AI-powered message drafting for outreach sequences.
Builds a 6-layer context prompt:
  1. System prompt (persona + constraints)
  2. Pillar context (ICP, messaging angles, objection handlers)
  3. Research brief (AI-generated company/prospect intel)
  4. Template skeleton (structural framework with variables)
  5. Conversation history (last 10 messages for follow-ups)
  6. Intent signals (classified response data for replies)

Creates outreach_messages (status='draft') and outreach_approvals (status='pending').

Usage:
    from scripts.outreach.message_drafter import draft_message, draft_reply
    msg = await draft_message(prospect_id=42, sequence_step=1, enrollment_id=5)
    reply = await draft_reply(prospect_id=42, inbound_message_id=99)
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from scripts.lib.ai_provider import ai_complete, log_ai_error
from scripts.lib.logger import setup_logger
from scripts.lib.supabase_client import get_client

logger = setup_logger("message_drafter")

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


def _parse_jsonb(value) -> dict | list:
    """Parse a JSONB field that may be a string or already parsed."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return {}
    return value or {}


# ─── Draft Outbound Message ─────────────────────────────────

async def draft_message(
    prospect_id: int,
    sequence_step: int,
    enrollment_id: int | None = None,
    *,
    provider: str | None = None,
) -> dict:
    """
    Draft a personalized outbound message for a prospect at a given sequence step.

    Layers:
      1. System prompt from outreach_prompts.json
      2. Pillar context (ICP, angles)
      3. Research brief
      4. Template skeleton
      5. Conversation history

    Args:
        prospect_id: Target prospect.
        sequence_step: Step number in the sequence (1, 2, 3...).
        enrollment_id: Optional enrollment tracking this sequence run.
        provider: Force AI provider.

    Returns:
        The created outreach_messages row.
    """
    client = get_client()
    prompts = _load_prompts()

    # Load prospect
    prospect = _load_prospect(client, prospect_id)
    research_brief = _parse_jsonb(prospect.get("research_brief"))

    # Load pillar
    pillar = None
    if prospect.get("pillar_id"):
        pillar = _load_pillar(client, prospect["pillar_id"])

    # Find the enrollment's sequence and template
    template = None
    sequence = None
    if enrollment_id:
        enrollment = _load_enrollment(client, enrollment_id)
        if enrollment:
            sequence = _load_sequence(client, enrollment["sequence_id"])
            template = _load_template(client, enrollment["sequence_id"], sequence_step)
    elif prospect.get("pillar_id"):
        # Find first active sequence for this pillar
        seq_result = (
            client.table("outreach_sequences")
            .select("*")
            .eq("pillar_id", prospect["pillar_id"])
            .eq("is_active", True)
            .limit(1)
            .execute()
        )
        if seq_result.data:
            sequence = seq_result.data[0]
            template = _load_template(client, sequence["id"], sequence_step)

    # Load conversation history
    conversation_history = _load_conversation_history(client, prospect_id)

    # Build the layered prompt
    system_prompt = prompts["draft_message"]["system_prompt"]
    user_prompt = _build_draft_prompt(
        prospect=prospect,
        research_brief=research_brief,
        pillar=pillar,
        template=template,
        sequence=sequence,
        conversation_history=conversation_history,
        step_number=sequence_step,
    )

    try:
        response = await ai_complete(
            task="draft_message",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            provider=provider,
            prospect_id=prospect_id,
            max_tokens=1000,
            temperature=0.7,
        )

        drafted_body = response.content.strip()

        # Strip any markdown formatting the AI might add
        if drafted_body.startswith('"') and drafted_body.endswith('"'):
            drafted_body = drafted_body[1:-1]

        now = datetime.now(timezone.utc).isoformat()
        channel = template.get("channel", "linkedin") if template else "linkedin"

        # Create message record
        msg_row = {
            "prospect_id": prospect_id,
            "enrollment_id": enrollment_id,
            "channel": channel,
            "direction": "outbound",
            "subject": template.get("subject") if template else None,
            "body": drafted_body,
            "status": "pending_approval",
            "ai_drafted": True,
            "ai_model": f"{response.provider}/{response.model}",
            "template_id": template["id"] if template else None,
            "drafted_at": now,
        }

        msg_result = client.table("outreach_messages").insert(msg_row).execute()
        if not msg_result.data:
            raise RuntimeError("Failed to insert outreach message")

        message = msg_result.data[0]

        # Create approval queue entry
        prospect_snapshot = {
            "id": prospect_id,
            "name": f"{prospect.get('first_name', '')} {prospect.get('last_name', '')}".strip(),
            "company": prospect.get("company_name"),
            "title": prospect.get("job_title"),
            "lead_score": prospect.get("lead_score", 0),
            "pillar_id": prospect.get("pillar_id"),
        }

        approval_row = {
            "message_id": message["id"],
            "prospect_id": prospect_id,
            "prospect_snapshot": json.dumps(prospect_snapshot),
            "pillar_name": pillar["name"] if pillar else None,
            "sequence_name": sequence["name"] if sequence else None,
            "step_number": sequence_step,
            "status": "pending",
        }

        client.table("outreach_approvals").insert(approval_row).execute()

        # Broadcast via WebSocket
        try:
            from dashboard.api.websocket import ws_manager
            import asyncio
            await ws_manager.broadcast({
                "event": "outreach_message_drafted",
                "data": {
                    "message_id": message["id"],
                    "prospect_id": prospect_id,
                    "prospect_name": prospect_snapshot["name"],
                    "channel": channel,
                    "step": sequence_step,
                },
                "timestamp": now,
            })
        except Exception:
            pass  # WebSocket broadcast is best-effort

        logger.info(
            "Message drafted for prospect %d (step %d) — pending approval (msg_id=%d)",
            prospect_id, sequence_step, message["id"],
        )

        return message

    except Exception as e:
        logger.error("Draft failed for prospect %d step %d: %s", prospect_id, sequence_step, e)
        await log_ai_error(
            task="draft_message",
            provider=provider or "groq",
            model="unknown",
            error=e,
            prospect_id=prospect_id,
        )
        raise


# ─── Draft Reply ─────────────────────────────────────────────

async def draft_reply(
    prospect_id: int,
    inbound_message_id: int,
    *,
    provider: str | None = None,
) -> dict:
    """
    Draft a reply to an inbound message from a prospect.

    Uses conversation history + intent classification + pillar objection handlers.

    Args:
        prospect_id: The prospect who responded.
        inbound_message_id: The inbound message to reply to.
        provider: Force AI provider.

    Returns:
        The created outreach_messages row.
    """
    client = get_client()
    prompts = _load_prompts()

    # Load context
    prospect = _load_prospect(client, prospect_id)
    research_brief = _parse_jsonb(prospect.get("research_brief"))

    pillar = None
    if prospect.get("pillar_id"):
        pillar = _load_pillar(client, prospect["pillar_id"])

    # Load the inbound message
    inbound_result = (
        client.table("outreach_messages")
        .select("*")
        .eq("id", inbound_message_id)
        .limit(1)
        .execute()
    )
    if not inbound_result.data:
        raise ValueError(f"Inbound message {inbound_message_id} not found")
    inbound_msg = inbound_result.data[0]

    # Load conversation history
    conversation_history = _load_conversation_history(client, prospect_id, limit=15)

    # Build prompt
    system_prompt = prompts["draft_reply"]["system_prompt"]
    user_prompt = _build_reply_prompt(
        prospect=prospect,
        research_brief=research_brief,
        pillar=pillar,
        inbound_message=inbound_msg,
        conversation_history=conversation_history,
    )

    try:
        response = await ai_complete(
            task="draft_reply",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            provider=provider,
            prospect_id=prospect_id,
            max_tokens=800,
            temperature=0.6,
        )

        reply_body = response.content.strip()
        if reply_body.startswith('"') and reply_body.endswith('"'):
            reply_body = reply_body[1:-1]

        now = datetime.now(timezone.utc).isoformat()

        # Create reply message
        msg_row = {
            "prospect_id": prospect_id,
            "enrollment_id": inbound_msg.get("enrollment_id"),
            "channel": inbound_msg.get("channel", "linkedin"),
            "direction": "outbound",
            "body": reply_body,
            "status": "pending_approval",
            "ai_drafted": True,
            "ai_model": f"{response.provider}/{response.model}",
            "drafted_at": now,
        }

        msg_result = client.table("outreach_messages").insert(msg_row).execute()
        if not msg_result.data:
            raise RuntimeError("Failed to insert reply message")
        message = msg_result.data[0]

        # Create approval entry
        prospect_snapshot = {
            "id": prospect_id,
            "name": f"{prospect.get('first_name', '')} {prospect.get('last_name', '')}".strip(),
            "company": prospect.get("company_name"),
            "title": prospect.get("job_title"),
            "lead_score": prospect.get("lead_score", 0),
            "inbound_intent": inbound_msg.get("intent"),
            "inbound_body_preview": (inbound_msg.get("body") or "")[:200],
        }

        approval_row = {
            "message_id": message["id"],
            "prospect_id": prospect_id,
            "prospect_snapshot": json.dumps(prospect_snapshot),
            "pillar_name": pillar["name"] if pillar else None,
            "status": "pending",
        }

        client.table("outreach_approvals").insert(approval_row).execute()

        logger.info(
            "Reply drafted for prospect %d (replying to msg %d) — pending approval (msg_id=%d)",
            prospect_id, inbound_message_id, message["id"],
        )

        return message

    except Exception as e:
        logger.error("Reply draft failed for prospect %d: %s", prospect_id, e)
        await log_ai_error(
            task="draft_reply",
            provider=provider or "groq",
            model="unknown",
            error=e,
            prospect_id=prospect_id,
        )
        raise


# ─── Intent Classification ──────────────────────────────────

async def classify_intent(
    message_text: str,
    conversation_history: list[dict] | None = None,
    pillar_context: dict | None = None,
    prospect_id: int | None = None,
    *,
    provider: str | None = None,
) -> dict:
    """
    Classify the intent of an inbound message using AI.

    Returns:
        Parsed intent classification dict.
    """
    prompts = _load_prompts()
    system_prompt = prompts["classify_intent"]["system_prompt"]

    sections = [f"## Inbound Message\n{message_text}"]

    if conversation_history:
        sections.append("\n## Conversation History (most recent first)")
        for msg in conversation_history[-10:]:
            direction = "THEM" if msg.get("direction") == "inbound" else "US"
            sections.append(f"[{direction}] {msg.get('body', '')[:300]}")

    if pillar_context:
        sections.append(f"\n## Service Context: {pillar_context.get('name', '')}")
        obj_handlers = pillar_context.get("objection_handlers", {})
        if obj_handlers:
            sections.append("Known objections and our responses:")
            for objection, handler in (obj_handlers.items() if isinstance(obj_handlers, dict) else []):
                sections.append(f"  - {objection}: {handler}")

    schema = prompts["classify_intent"]["output_schema"]
    sections.append(f"\n## Output\nReturn valid JSON matching this schema:\n```json\n{json.dumps(schema, indent=2)}\n```")

    user_prompt = "\n".join(sections)

    try:
        response = await ai_complete(
            task="classify_intent",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            provider=provider,
            prospect_id=prospect_id,
            json_mode=True,
            max_tokens=800,
            temperature=0.3,
        )

        # Parse JSON response
        result = _parse_json_response(response.content)
        logger.info(
            "Intent classified: %s (confidence=%.2f) for prospect %s",
            result.get("intent", "unknown"),
            result.get("confidence", 0),
            prospect_id or "N/A",
        )
        return result

    except Exception as e:
        logger.error("Intent classification failed: %s", e)
        return {
            "intent": "unknown",
            "confidence": 0.0,
            "key_signals": [],
            "sentiment": "neutral",
            "suggested_action": "Manual review required",
            "error": str(e),
        }


# ─── Prompt Builders ────────────────────────────────────────

def _build_draft_prompt(
    prospect: dict,
    research_brief: dict,
    pillar: dict | None,
    template: dict | None,
    sequence: dict | None,
    conversation_history: list[dict],
    step_number: int,
) -> str:
    """Build the layered user prompt for message drafting."""
    sections = []

    # Layer 1: Prospect context
    sections.append("## Prospect")
    sections.append(f"- Name: {prospect.get('first_name', '')} {prospect.get('last_name', '')}")
    sections.append(f"- Title: {prospect.get('job_title', 'Unknown')}")
    sections.append(f"- Company: {prospect.get('company_name', 'Unknown')}")
    if prospect.get("industry"):
        sections.append(f"- Industry: {prospect['industry']}")

    # Layer 2: Pillar context
    if pillar:
        sections.append(f"\n## Service Pillar: {pillar['name']}")
        angles = _parse_jsonb(pillar.get("messaging_angles"))
        if angles:
            sections.append("Key messaging angles:")
            for a in angles:
                sections.append(f"  - {a}")

    # Layer 3: Research brief highlights
    if research_brief and not research_brief.get("parse_error"):
        sections.append("\n## Research Highlights")
        opp = research_brief.get("opportunity_assessment", {})
        if opp:
            sections.append(f"- Fit Rating: {opp.get('fit_rating', 'N/A')}")
            sections.append(f"- Reasoning: {opp.get('reasoning', 'N/A')}")

        starters = research_brief.get("conversation_starters", [])
        if starters:
            sections.append("Conversation starters:")
            for s in starters:
                sections.append(f"  - {s}")

        pain_points = research_brief.get("pain_points", [])
        if pain_points:
            sections.append("Pain points:")
            for pp in pain_points[:3]:
                sections.append(f"  - {pp}")

        digital = research_brief.get("digital_presence", {})
        if digital:
            sections.append(f"- Website quality: {digital.get('website_quality', 'N/A')}")
            sections.append(f"- SEO visibility: {digital.get('seo_visibility', 'N/A')}")

    # Layer 4: Template skeleton
    if template:
        sections.append(f"\n## Template (Step {step_number}: {template.get('name', '')})")
        sections.append(f"Structure to follow:\n{template.get('body_template', '')}")
        if template.get("ai_system_prompt"):
            sections.append(f"\nAdditional instructions: {template['ai_system_prompt']}")
    else:
        sections.append(f"\n## Message Instructions")
        sections.append(f"This is step {step_number} of the outreach sequence.")
        if step_number == 1:
            sections.append("Write a warm initial connection request / introduction.")
        elif step_number == 2:
            sections.append("Write a value-add follow-up (share an insight or piece of content).")
        elif step_number == 3:
            sections.append("Write a social proof message (reference a case study or result).")
        else:
            sections.append("Write a soft-close / gentle final nudge.")

    # Layer 5: Conversation history
    if conversation_history:
        sections.append("\n## Previous Messages")
        for msg in conversation_history[-5:]:
            direction = "US" if msg.get("direction") == "outbound" else "THEM"
            sections.append(f"[{direction}] {msg.get('body', '')[:300]}")
        sections.append("\nContinue the conversation naturally from here.")
    else:
        sections.append("\nThis is the first message to this prospect — no prior conversation.")

    sections.append("\n## Instructions")
    sections.append("Write ONLY the message text. No subject line, no greeting prefix, no signature.")
    sections.append(f"Channel: {'LinkedIn DM (50-120 words)' if (template or {}).get('channel', 'linkedin') == 'linkedin' else 'Email (100-200 words)'}")

    return "\n".join(sections)


def _build_reply_prompt(
    prospect: dict,
    research_brief: dict,
    pillar: dict | None,
    inbound_message: dict,
    conversation_history: list[dict],
) -> str:
    """Build the layered user prompt for reply drafting."""
    sections = []

    # Prospect context
    sections.append("## Prospect")
    sections.append(f"- Name: {prospect.get('first_name', '')} {prospect.get('last_name', '')}")
    sections.append(f"- Company: {prospect.get('company_name', 'Unknown')}")
    sections.append(f"- Title: {prospect.get('job_title', 'Unknown')}")

    # Their message + intent
    sections.append(f"\n## Their Latest Message")
    sections.append(inbound_message.get("body", ""))

    intent = inbound_message.get("intent")
    if intent:
        sections.append(f"\nClassified Intent: {intent}")
        confidence = inbound_message.get("intent_confidence")
        if confidence:
            sections.append(f"Confidence: {confidence}")
        signals = inbound_message.get("intent_signals")
        if signals:
            parsed_signals = _parse_jsonb(signals)
            if parsed_signals:
                sections.append(f"Key signals: {json.dumps(parsed_signals)}")

    # Pillar context + objection handlers
    if pillar:
        sections.append(f"\n## Service Context: {pillar['name']}")
        obj_handlers = _parse_jsonb(pillar.get("objection_handlers"))
        if obj_handlers and intent == "objection":
            obj_type = inbound_message.get("intent_signals", {})
            if isinstance(obj_type, dict):
                obj_type = obj_type.get("objection_type")
            sections.append("Relevant objection handlers:")
            for key, handler in obj_handlers.items():
                sections.append(f"  - {key}: {handler}")

    # Research brief summary
    if research_brief and not research_brief.get("parse_error"):
        opp = research_brief.get("opportunity_assessment", {})
        if opp:
            sections.append(f"\n## Research Context")
            sections.append(f"- Fit: {opp.get('fit_rating', 'N/A')}")
            sections.append(f"- Reasoning: {opp.get('reasoning', 'N/A')}")

    # Full conversation history
    if conversation_history:
        sections.append("\n## Full Conversation History")
        for msg in conversation_history:
            direction = "US" if msg.get("direction") == "outbound" else "THEM"
            ts = msg.get("sent_at") or msg.get("drafted_at") or ""
            sections.append(f"[{direction} - {ts[:16]}] {msg.get('body', '')[:400]}")

    sections.append("\n## Instructions")
    sections.append("Write ONLY the reply text. Keep it natural and directly address what they said.")
    channel = inbound_message.get("channel", "linkedin")
    sections.append(f"Channel: {'LinkedIn DM (40-100 words)' if channel == 'linkedin' else 'Email (80-150 words)'}")

    return "\n".join(sections)


# ─── Data Loaders ────────────────────────────────────────────

def _load_prospect(client, prospect_id: int) -> dict:
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


def _load_pillar(client, pillar_id: int) -> dict | None:
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
    for field in ("icp_criteria", "messaging_angles", "research_prompts", "objection_handlers"):
        if isinstance(pillar.get(field), str):
            try:
                pillar[field] = json.loads(pillar[field])
            except (json.JSONDecodeError, TypeError):
                pass
    return pillar


def _load_enrollment(client, enrollment_id: int) -> dict | None:
    result = (
        client.table("outreach_enrollments")
        .select("*")
        .eq("id", enrollment_id)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def _load_sequence(client, sequence_id: int) -> dict | None:
    result = (
        client.table("outreach_sequences")
        .select("*")
        .eq("id", sequence_id)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def _load_template(client, sequence_id: int, step_number: int) -> dict | None:
    result = (
        client.table("outreach_templates")
        .select("*")
        .eq("sequence_id", sequence_id)
        .eq("step_number", step_number)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def _load_conversation_history(client, prospect_id: int, limit: int = 10) -> list[dict]:
    result = (
        client.table("outreach_messages")
        .select("*")
        .eq("prospect_id", prospect_id)
        .order("drafted_at", desc=True)
        .limit(limit)
        .execute()
    )
    messages = result.data or []
    return list(reversed(messages))  # Chronological order


def _parse_json_response(content: str) -> dict:
    """Parse AI response into dict, handling markdown wrapping."""
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    if "```json" in content:
        start = content.index("```json") + 7
        end = content.index("```", start)
        try:
            return json.loads(content[start:end].strip())
        except json.JSONDecodeError:
            pass

    first = content.find("{")
    last = content.rfind("}")
    if first != -1 and last != -1:
        try:
            return json.loads(content[first:last + 1])
        except json.JSONDecodeError:
            pass

    return {"raw_response": content, "parse_error": True}
