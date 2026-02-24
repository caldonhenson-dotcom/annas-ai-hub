"""
Annas AI Hub — LinkedIn Pydantic Models
==========================================

Request/response schemas for all LinkedIn API endpoints.
Ported from AI Clawdon with prospect_id linkage additions.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ─── Authentication ─────────────────────────────────────────

class LinkedInAuthRequest(BaseModel):
    li_at_cookie: str = Field(..., description="LinkedIn li_at session cookie")
    csrf_token: str = Field(..., description="LinkedIn CSRF token (JSESSIONID value)")


class LinkedInAuthStatus(BaseModel):
    authenticated: bool
    session_valid: bool
    last_validated: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    display_name: Optional[str] = None


# ─── Participants & Contacts ────────────────────────────────

class LinkedInParticipant(BaseModel):
    id: str
    name: str
    profile_url: Optional[str] = None
    photo_url: Optional[str] = None


class LinkedInContactResponse(BaseModel):
    linkedin_id: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    headline: Optional[str] = None
    company: Optional[str] = None
    location: Optional[str] = None
    profile_url: Optional[str] = None
    photo_url: Optional[str] = None
    connection_degree: Optional[int] = None
    prospect_id: Optional[int] = None


class LinkedInContactNoteRequest(BaseModel):
    note: str = Field(..., min_length=1)


class LinkedInContactNoteResponse(BaseModel):
    id: int
    contact_id: str
    note: str
    updated_at: Optional[datetime] = None


# ─── Threads & Messages ────────────────────────────────────

class LinkedInThreadResponse(BaseModel):
    thread_id: str
    participants: List[LinkedInParticipant] = []
    last_message_at: Optional[datetime] = None
    last_message_preview: Optional[str] = None
    unread_count: int = 0
    is_archived: bool = False
    is_muted: bool = False
    is_starred: bool = False
    labels: List[str] = []
    snoozed_until: Optional[datetime] = None


class LinkedInThreadListResponse(BaseModel):
    threads: List[LinkedInThreadResponse]
    total: int
    has_more: bool
    next_cursor: Optional[str] = None


class LinkedInMessageResponse(BaseModel):
    message_id: str
    thread_id: str
    sender_id: Optional[str] = None
    sender_name: Optional[str] = None
    body: Optional[str] = None
    timestamp: Optional[datetime] = None
    is_inbound: bool = True
    attachments: List[Dict[str, Any]] = []


class LinkedInSendMessageRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=8000)


# ─── Labels ─────────────────────────────────────────────────

class LinkedInLabelCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    color: str = Field(default="#6366f1", pattern=r"^#[0-9A-Fa-f]{6}$")
    is_pinned: bool = False


class LinkedInLabelUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    color: Optional[str] = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")
    is_pinned: Optional[bool] = None
    sort_order: Optional[int] = None


class LinkedInLabelResponse(BaseModel):
    id: int
    name: str
    color: str
    sort_order: int = 0
    is_pinned: bool = False
    unread_count: int = 0


class LinkedInLabelAssignRequest(BaseModel):
    label_ids: List[int]


# ─── Snooze ─────────────────────────────────────────────────

class LinkedInSnoozeRequest(BaseModel):
    snooze_until: datetime


class LinkedInSnoozeResponse(BaseModel):
    thread_id: str
    snooze_until: datetime
    created_at: Optional[datetime] = None


# ─── Follow-ups ─────────────────────────────────────────────

class LinkedInFollowUpRequest(BaseModel):
    remind_at: datetime
    note: Optional[str] = None


class LinkedInFollowUpResponse(BaseModel):
    id: int
    thread_id: str
    remind_at: datetime
    note: Optional[str] = None
    is_completed: bool = False


# ─── Snippets ───────────────────────────────────────────────

class LinkedInSnippetCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    trigger: Optional[str] = Field(None, max_length=50)
    body: str = Field(..., min_length=1)
    variables: List[str] = []


class LinkedInSnippetUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    trigger: Optional[str] = Field(None, max_length=50)
    body: Optional[str] = Field(None, min_length=1)


class LinkedInSnippetResponse(BaseModel):
    id: int
    title: str
    trigger: Optional[str] = None
    body: str
    variables: List[str] = []
    use_count: int = 0


# ─── Search ─────────────────────────────────────────────────

class LinkedInSearchResult(BaseModel):
    query: str
    threads: List[LinkedInThreadResponse] = []
    messages: List[LinkedInMessageResponse] = []
    total: int = 0
