"""
Annas AI Hub — Outreach Engine Pydantic Models
================================================

Request/response models for outreach pillars, prospects,
enrollments, messages, and approvals.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ─── Pillar Models ──────────────────────────────────────────

class PillarResponse(BaseModel):
    """Outreach pillar as returned by API."""
    id: int
    slug: str
    name: str
    description: Optional[str] = None
    icp_criteria: dict = Field(default_factory=dict)
    messaging_angles: list = Field(default_factory=list)
    research_prompts: list = Field(default_factory=list)
    objection_handlers: dict = Field(default_factory=dict)
    is_active: bool = True
    sort_order: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class PillarUpdate(BaseModel):
    """Fields that can be updated on a pillar."""
    name: Optional[str] = None
    description: Optional[str] = None
    icp_criteria: Optional[dict] = None
    messaging_angles: Optional[list] = None
    research_prompts: Optional[list] = None
    objection_handlers: Optional[dict] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


# ─── Prospect Models ────────────────────────────────────────

class ProspectCreate(BaseModel):
    """Create a new prospect."""
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    linkedin_url: Optional[str] = None
    linkedin_id: Optional[str] = None
    phone: Optional[str] = None
    company_name: Optional[str] = None
    company_domain: Optional[str] = None
    company_size: Optional[str] = None
    industry: Optional[str] = None
    job_title: Optional[str] = None
    pillar_id: Optional[int] = None
    source: str = "manual"


class ProspectUpdate(BaseModel):
    """Update prospect fields."""
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    linkedin_url: Optional[str] = None
    linkedin_id: Optional[str] = None
    phone: Optional[str] = None
    company_name: Optional[str] = None
    company_domain: Optional[str] = None
    company_size: Optional[str] = None
    industry: Optional[str] = None
    job_title: Optional[str] = None
    pillar_id: Optional[int] = None
    status: Optional[str] = None


class ProspectResponse(BaseModel):
    """Prospect as returned by API."""
    id: int
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    linkedin_url: Optional[str] = None
    linkedin_id: Optional[str] = None
    phone: Optional[str] = None
    company_name: Optional[str] = None
    company_domain: Optional[str] = None
    company_size: Optional[str] = None
    industry: Optional[str] = None
    job_title: Optional[str] = None
    hubspot_contact_id: Optional[str] = None
    linkedin_contact_id: Optional[str] = None
    source: str = "manual"
    pillar_id: Optional[int] = None
    research_brief: Optional[dict] = None
    research_status: str = "pending"
    researched_at: Optional[datetime] = None
    fit_score: int = 0
    engagement_score: int = 0
    lead_score: int = 0
    status: str = "new"
    last_contacted: Optional[datetime] = None
    last_replied: Optional[datetime] = None
    total_messages_sent: int = 0
    total_messages_received: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class BulkImportRequest(BaseModel):
    """Bulk import prospects from a source."""
    source: str = Field(description="Import source: hubspot | linkedin | csv")
    pillar_id: Optional[int] = Field(None, description="Assign all imports to this pillar")
    filters: Optional[dict] = Field(None, description="Source-specific filters")


class PillarAssignRequest(BaseModel):
    """Assign prospects to a pillar."""
    prospect_ids: list[int]
    pillar_id: int


# ─── Sequence / Enrollment Models ───────────────────────────

class SequenceResponse(BaseModel):
    """Outreach sequence as returned by API."""
    id: int
    pillar_id: int
    name: str
    description: Optional[str] = None
    channel: str = "linkedin"
    total_steps: int = 1
    delay_days: list[int] = Field(default_factory=list)
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class TemplateResponse(BaseModel):
    """Message template as returned by API."""
    id: int
    sequence_id: int
    step_number: int
    name: Optional[str] = None
    channel: str = "linkedin"
    subject: Optional[str] = None
    body_template: str
    ai_system_prompt: Optional[str] = None
    variables: list = Field(default_factory=list)
    created_at: Optional[datetime] = None


# ─── Message / Approval Models ──────────────────────────────

class MessageResponse(BaseModel):
    """Outreach message as returned by API."""
    id: int
    prospect_id: int
    enrollment_id: Optional[int] = None
    channel: str = "linkedin"
    direction: str
    subject: Optional[str] = None
    body: str
    status: str = "draft"
    ai_drafted: bool = False
    ai_model: Optional[str] = None
    intent: Optional[str] = None
    intent_confidence: Optional[float] = None
    intent_signals: Optional[dict] = None
    drafted_at: Optional[datetime] = None
    approved_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None
    received_at: Optional[datetime] = None


class ApprovalResponse(BaseModel):
    """Approval queue item as returned by API."""
    id: int
    message_id: int
    prospect_id: int
    prospect_snapshot: dict
    pillar_name: Optional[str] = None
    sequence_name: Optional[str] = None
    step_number: Optional[int] = None
    status: str = "pending"
    reviewer_notes: Optional[str] = None
    edited_body: Optional[str] = None
    submitted_at: Optional[datetime] = None
    reviewed_at: Optional[datetime] = None


class ApprovalAction(BaseModel):
    """Approve or reject a message."""
    action: str = Field(description="approve | reject | edit")
    reviewer_notes: Optional[str] = None
    edited_body: Optional[str] = None


# ─── AI Models ──────────────────────────────────────────────

class AILogResponse(BaseModel):
    """AI call log entry."""
    id: int
    task: str
    provider: str
    model: str
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    latency_ms: Optional[int] = None
    prospect_id: Optional[int] = None
    success: bool = True
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None
