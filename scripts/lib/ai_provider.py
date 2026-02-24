"""
Annas AI Hub — Unified AI Provider
====================================

Thin abstraction over Groq and Claude APIs.
Reads AI_PROVIDER env var to choose the default backend.
Every call is logged to the outreach_ai_logs table.

Usage:
    from scripts.lib.ai_provider import ai_complete
    response = await ai_complete(
        task="research",
        system_prompt="You are a B2B research analyst...",
        user_prompt="Research this company...",
        prospect_id=42,
    )
    print(response.content)
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Optional

from scripts.lib.logger import setup_logger

logger = setup_logger("ai_provider")


# ─── Response Model ─────────────────────────────────────────

@dataclass
class AIResponse:
    """Standardised response from any AI provider."""
    content: str
    provider: str          # "groq" | "claude"
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: int


# ─── Provider Config ────────────────────────────────────────

GROQ_MODEL = "llama-3.3-70b-versatile"
CLAUDE_MODEL = "claude-sonnet-4-5-20250929"

DEFAULT_MAX_TOKENS = 2048
DEFAULT_TEMPERATURE = 0.7


# ─── Core Completion ────────────────────────────────────────

async def ai_complete(
    task: str,
    system_prompt: str,
    user_prompt: str,
    *,
    provider: str | None = None,
    model: str | None = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    temperature: float = DEFAULT_TEMPERATURE,
    prospect_id: int | None = None,
    json_mode: bool = False,
) -> AIResponse:
    """
    Run an AI completion and log it.

    Args:
        task: What this call is for (research, draft_message, classify_intent, draft_reply).
        system_prompt: System-level instructions.
        user_prompt: The user-facing prompt content.
        provider: Force a specific provider. Defaults to AI_PROVIDER env var.
        model: Force a specific model. Defaults based on provider.
        max_tokens: Max output tokens.
        temperature: Sampling temperature.
        prospect_id: Optional prospect ID for audit trail.
        json_mode: Request JSON output from the provider.

    Returns:
        AIResponse with content and token usage.
    """
    chosen_provider = (provider or os.getenv("AI_PROVIDER", "groq")).lower()

    if chosen_provider == "claude":
        response = await _call_claude(
            system_prompt, user_prompt,
            model=model or CLAUDE_MODEL,
            max_tokens=max_tokens,
            temperature=temperature,
        )
    else:
        response = await _call_groq(
            system_prompt, user_prompt,
            model=model or GROQ_MODEL,
            max_tokens=max_tokens,
            temperature=temperature,
            json_mode=json_mode,
        )

    # Log to outreach_ai_logs
    await _log_ai_call(
        task=task,
        provider=response.provider,
        model=response.model,
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        latency_ms=response.latency_ms,
        prospect_id=prospect_id,
        success=True,
    )

    logger.info(
        "AI [%s/%s] task=%s tokens=%d+%d latency=%dms",
        response.provider, response.model, task,
        response.input_tokens, response.output_tokens, response.latency_ms,
    )
    return response


# ─── Groq Backend ───────────────────────────────────────────

async def _call_groq(
    system_prompt: str,
    user_prompt: str,
    *,
    model: str,
    max_tokens: int,
    temperature: float,
    json_mode: bool = False,
) -> AIResponse:
    """Call Groq API (Llama 3.3 70B)."""
    from groq import AsyncGroq

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY not set")

    client = AsyncGroq(api_key=api_key)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    kwargs = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    start = time.perf_counter()
    response = await client.chat.completions.create(**kwargs)
    latency_ms = int((time.perf_counter() - start) * 1000)

    choice = response.choices[0]
    usage = response.usage

    return AIResponse(
        content=choice.message.content or "",
        provider="groq",
        model=model,
        input_tokens=usage.prompt_tokens if usage else 0,
        output_tokens=usage.completion_tokens if usage else 0,
        latency_ms=latency_ms,
    )


# ─── Claude Backend ─────────────────────────────────────────

async def _call_claude(
    system_prompt: str,
    user_prompt: str,
    *,
    model: str,
    max_tokens: int,
    temperature: float,
) -> AIResponse:
    """Call Anthropic Claude API."""
    import anthropic

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not set")

    client = anthropic.AsyncAnthropic(api_key=api_key)

    start = time.perf_counter()
    response = await client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    latency_ms = int((time.perf_counter() - start) * 1000)

    content = ""
    for block in response.content:
        if hasattr(block, "text"):
            content += block.text

    return AIResponse(
        content=content,
        provider="claude",
        model=model,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        latency_ms=latency_ms,
    )


# ─── Audit Logging ──────────────────────────────────────────

async def _log_ai_call(
    task: str,
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    latency_ms: int,
    prospect_id: int | None = None,
    success: bool = True,
    error_message: str | None = None,
) -> None:
    """Log AI call to outreach_ai_logs table."""
    try:
        from scripts.lib.supabase_client import get_client
        client = get_client()
        row = {
            "task": task,
            "provider": provider,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "latency_ms": latency_ms,
            "success": success,
        }
        if prospect_id is not None:
            row["prospect_id"] = prospect_id
        if error_message:
            row["error_message"] = error_message
        client.table("outreach_ai_logs").insert(row).execute()
    except Exception as e:
        logger.warning("Failed to log AI call: %s", e)


async def log_ai_error(
    task: str,
    provider: str,
    model: str,
    error: Exception,
    prospect_id: int | None = None,
    latency_ms: int = 0,
) -> None:
    """Log a failed AI call."""
    await _log_ai_call(
        task=task,
        provider=provider,
        model=model,
        input_tokens=0,
        output_tokens=0,
        latency_ms=latency_ms,
        prospect_id=prospect_id,
        success=False,
        error_message=str(error),
    )
