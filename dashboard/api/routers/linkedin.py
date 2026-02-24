"""
Annas AI Hub — LinkedIn DM Power Inbox Router
================================================

FastAPI router for LinkedIn Voyager integration endpoints.
Handles auth, conversations, labels, snooze, snippets, contacts, and search.

Ported from AI Clawdon, converted from SQLAlchemy to Supabase queries.

Endpoints:
  POST /api/linkedin/auth                           - Store session credentials
  GET  /api/linkedin/auth/status                    - Check auth status
  DELETE /api/linkedin/auth                         - Logout
  GET  /api/linkedin/conversations                  - List conversations
  GET  /api/linkedin/conversations/{id}/messages    - Get thread messages
  POST /api/linkedin/conversations/{id}/messages    - Send message
  POST /api/linkedin/conversations/{id}/read        - Mark as read
  POST /api/linkedin/conversations/{id}/archive     - Archive
  POST /api/linkedin/conversations/{id}/unarchive   - Unarchive
  GET  /api/linkedin/labels                         - List labels
  POST /api/linkedin/labels                         - Create label
  PUT  /api/linkedin/labels/{id}                    - Update label
  DELETE /api/linkedin/labels/{id}                  - Delete label
  POST /api/linkedin/conversations/{id}/labels      - Assign labels
  POST /api/linkedin/conversations/{id}/snooze      - Snooze
  DELETE /api/linkedin/conversations/{id}/snooze    - Unsnooze
  POST /api/linkedin/conversations/{id}/follow-up   - Create follow-up
  POST /api/linkedin/conversations/{id}/follow-up/{fid}/complete - Complete
  GET  /api/linkedin/snippets                       - List snippets
  POST /api/linkedin/snippets                       - Create snippet
  PUT  /api/linkedin/snippets/{id}                  - Update snippet
  DELETE /api/linkedin/snippets/{id}                - Delete snippet
  GET  /api/linkedin/profile/{public_id}            - Fetch profile
  POST /api/linkedin/contacts/{id}/notes            - Upsert note
  GET  /api/linkedin/search                         - Search messages
  POST /api/linkedin/sync                           - Trigger sync
  POST /api/linkedin/heartbeat                      - Browser heartbeat
  GET  /api/linkedin/browser-status                 - Browser status
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from integrations.linkedin_session import LinkedInSessionManager
from integrations.linkedin_voyager import LinkedInVoyagerClient
from models.linkedin_models import (
    LinkedInAuthRequest,
    LinkedInAuthStatus,
    LinkedInContactNoteRequest,
    LinkedInContactNoteResponse,
    LinkedInContactResponse,
    LinkedInFollowUpRequest,
    LinkedInFollowUpResponse,
    LinkedInLabelAssignRequest,
    LinkedInLabelCreate,
    LinkedInLabelResponse,
    LinkedInLabelUpdate,
    LinkedInMessageResponse,
    LinkedInParticipant,
    LinkedInSearchResult,
    LinkedInSendMessageRequest,
    LinkedInSnippetCreate,
    LinkedInSnippetResponse,
    LinkedInSnippetUpdate,
    LinkedInSnoozeRequest,
    LinkedInSnoozeResponse,
    LinkedInThreadListResponse,
    LinkedInThreadResponse,
)
from scripts.lib.errors import VoyagerAuthError
from scripts.lib.logger import setup_logger
from scripts.lib.supabase_client import get_client

logger = setup_logger("linkedin_router")

router = APIRouter(prefix="/api/linkedin", tags=["linkedin"])

session_manager = LinkedInSessionManager()


# ─── Helpers ────────────────────────────────────────────────

def _get_voyager_client() -> LinkedInVoyagerClient:
    """Resolve an authenticated Voyager client from stored session."""
    credentials = session_manager.get_active_session()
    if not credentials:
        raise HTTPException(status_code=401, detail="No active LinkedIn session")
    li_at, csrf = credentials
    return LinkedInVoyagerClient(li_at, csrf)


def _parse_participants(raw) -> list:
    """Parse participants from JSONB (may be string or list)."""
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return []
    return raw or []


# ═════════════════════════════════════════════════════════════
# AUTHENTICATION
# ═════════════════════════════════════════════════════════════


@router.post("/auth")
async def authenticate_linkedin(auth_req: LinkedInAuthRequest):
    """Store LinkedIn session credentials (encrypted)."""
    if not session_manager.validate_session_format(auth_req.li_at_cookie, auth_req.csrf_token):
        raise HTTPException(status_code=400, detail="Invalid credential format")

    # Validate credentials against LinkedIn
    client = LinkedInVoyagerClient(auth_req.li_at_cookie, auth_req.csrf_token)
    if not await client.validate_session():
        raise HTTPException(status_code=401, detail="Invalid LinkedIn credentials")

    session_manager.store_session(auth_req.li_at_cookie, auth_req.csrf_token)

    return LinkedInAuthStatus(
        authenticated=True,
        session_valid=True,
        last_validated=datetime.now(timezone.utc),
        expires_at=session_manager.calculate_expiry(datetime.now(timezone.utc)),
    )


@router.get("/auth/status")
async def get_auth_status():
    """Check LinkedIn authentication status."""
    return session_manager.get_session_status()


@router.delete("/auth")
async def logout_linkedin():
    """Clear LinkedIn session."""
    session_manager.invalidate_session()
    return {"status": "logged_out"}


# ═════════════════════════════════════════════════════════════
# CONVERSATIONS
# ═════════════════════════════════════════════════════════════


@router.get("/conversations")
async def list_conversations(
    limit: int = Query(20, ge=1, le=100),
    archived: bool = Query(False),
    unread_only: bool = Query(False),
    label_id: Optional[int] = Query(None),
):
    """List LinkedIn conversations with optional filters."""
    try:
        client = get_client()
        query = client.table("linkedin_threads").select("*")

        query = query.eq("is_archived", archived)
        if unread_only:
            query = query.gt("unread_count", 0)

        query = query.order("last_message_at", desc=True).limit(limit)
        result = query.execute()
        threads = result.data or []

        # If filtering by label, get thread IDs with that label
        if label_id is not None:
            label_threads = (
                client.table("linkedin_thread_labels")
                .select("thread_id")
                .eq("label_id", label_id)
                .execute()
            )
            label_thread_ids = {lt["thread_id"] for lt in (label_threads.data or [])}
            threads = [t for t in threads if t["id"] in label_thread_ids]

        thread_responses = []
        for t in threads:
            participants = _parse_participants(t.get("participants"))

            # Get labels
            labels_result = (
                client.table("linkedin_thread_labels")
                .select("label_id")
                .eq("thread_id", t["id"])
                .execute()
            )
            label_ids = [lt["label_id"] for lt in (labels_result.data or [])]
            label_names = []
            if label_ids:
                labels_data = (
                    client.table("linkedin_labels")
                    .select("name")
                    .in_("id", label_ids)
                    .execute()
                )
                label_names = [l["name"] for l in (labels_data.data or [])]

            # Get snooze
            snooze_result = (
                client.table("linkedin_snoozes")
                .select("snooze_until")
                .eq("thread_id", t["id"])
                .limit(1)
                .execute()
            )
            snoozed = snooze_result.data[0]["snooze_until"] if snooze_result.data else None

            thread_responses.append(LinkedInThreadResponse(
                thread_id=t["id"],
                participants=[LinkedInParticipant(**p) for p in participants],
                last_message_at=t.get("last_message_at"),
                last_message_preview=t.get("last_message_preview"),
                unread_count=t.get("unread_count", 0),
                is_archived=t.get("is_archived", False),
                is_muted=t.get("is_muted", False),
                is_starred=t.get("is_starred", False),
                labels=label_names,
                snoozed_until=snoozed,
            ))

        return LinkedInThreadListResponse(
            threads=thread_responses,
            total=len(thread_responses),
            has_more=len(threads) == limit,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("List conversations failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to fetch conversations")


@router.get("/conversations/{thread_id}/messages")
async def get_thread_messages(
    thread_id: str,
    limit: int = Query(50, ge=1, le=100),
):
    """Get messages for a specific conversation."""
    try:
        client = get_client()
        result = (
            client.table("linkedin_messages")
            .select("*")
            .eq("thread_id", thread_id)
            .order("sent_at", desc=True)
            .limit(limit)
            .execute()
        )
        messages = result.data or []

        return [
            LinkedInMessageResponse(
                message_id=m["id"],
                thread_id=m["thread_id"],
                sender_id=m.get("sender_id"),
                sender_name=m.get("sender_name"),
                body=m.get("body"),
                timestamp=m.get("sent_at"),
                is_inbound=m.get("is_inbound", True),
                attachments=json.loads(m["attachments"]) if isinstance(m.get("attachments"), str) else (m.get("attachments") or []),
            )
            for m in reversed(messages)
        ]
    except Exception as e:
        logger.error("Get messages failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to fetch messages")


@router.post("/conversations/{thread_id}/messages")
async def send_message(thread_id: str, req: LinkedInSendMessageRequest):
    """Send a message to a conversation via Voyager API."""
    voyager = _get_voyager_client()

    try:
        response = await voyager.send_message(thread_id, req.text)
        msg_data = response.get("value", {})
        message_id = msg_data.get("entityUrn", f"local-{datetime.now().timestamp()}").split(":")[-1]

        now = datetime.now(timezone.utc).isoformat()
        client = get_client()

        # Store sent message
        client.table("linkedin_messages").insert({
            "id": message_id,
            "thread_id": thread_id,
            "sender_id": "self",
            "sender_name": "Me",
            "body": req.text,
            "is_inbound": False,
            "sent_at": now,
            "attachments": "[]",
        }).execute()

        # Update thread
        client.table("linkedin_threads").update({
            "last_message_at": now,
            "last_message_preview": req.text[:500],
            "updated_at": now,
        }).eq("id", thread_id).execute()

        return LinkedInMessageResponse(
            message_id=message_id,
            thread_id=thread_id,
            sender_id="self",
            sender_name="Me",
            body=req.text,
            timestamp=now,
            is_inbound=False,
            attachments=[],
        )

    except VoyagerAuthError:
        raise HTTPException(status_code=401, detail="Session expired")
    except Exception as e:
        logger.error("Failed to send message: %s", e)
        raise HTTPException(status_code=500, detail="Failed to send message")


@router.post("/conversations/{thread_id}/read")
async def mark_conversation_read(thread_id: str):
    """Mark a conversation as read."""
    try:
        voyager = _get_voyager_client()
        await voyager.mark_as_read(thread_id)
    except Exception:
        pass  # Still update locally

    client = get_client()
    client.table("linkedin_threads").update({
        "unread_count": 0,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", thread_id).execute()

    return {"status": "marked_read", "thread_id": thread_id}


@router.post("/conversations/{thread_id}/archive")
async def archive_conversation(thread_id: str):
    """Archive a conversation."""
    client = get_client()
    result = client.table("linkedin_threads").update(
        {"is_archived": True, "updated_at": datetime.now(timezone.utc).isoformat()}
    ).eq("id", thread_id).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Thread not found")
    return {"status": "archived", "thread_id": thread_id}


@router.post("/conversations/{thread_id}/unarchive")
async def unarchive_conversation(thread_id: str):
    """Unarchive a conversation."""
    client = get_client()
    result = client.table("linkedin_threads").update(
        {"is_archived": False, "updated_at": datetime.now(timezone.utc).isoformat()}
    ).eq("id", thread_id).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Thread not found")
    return {"status": "unarchived", "thread_id": thread_id}


# ═════════════════════════════════════════════════════════════
# LABELS
# ═════════════════════════════════════════════════════════════


@router.get("/labels")
async def list_labels():
    """List all custom labels with unread counts."""
    try:
        client = get_client()
        result = (
            client.table("linkedin_labels")
            .select("*")
            .order("sort_order")
            .order("name")
            .execute()
        )
        labels = result.data or []

        responses = []
        for label in labels:
            # Count unread threads with this label
            thread_labels = (
                client.table("linkedin_thread_labels")
                .select("thread_id")
                .eq("label_id", label["id"])
                .execute()
            )
            thread_ids = [tl["thread_id"] for tl in (thread_labels.data or [])]
            unread_count = 0
            if thread_ids:
                unread_threads = (
                    client.table("linkedin_threads")
                    .select("id", count="exact")
                    .in_("id", thread_ids)
                    .gt("unread_count", 0)
                    .eq("is_archived", False)
                    .execute()
                )
                unread_count = unread_threads.count or 0

            responses.append(LinkedInLabelResponse(
                id=label["id"],
                name=label["name"],
                color=label.get("color", "#6366f1"),
                sort_order=label.get("sort_order", 0),
                is_pinned=label.get("is_pinned", False),
                unread_count=unread_count,
            ))

        return responses
    except Exception as e:
        logger.error("List labels failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to fetch labels")


@router.post("/labels")
async def create_label(req: LinkedInLabelCreate):
    """Create a new label."""
    client = get_client()
    result = client.table("linkedin_labels").insert({
        "name": req.name,
        "color": req.color,
        "is_pinned": req.is_pinned,
    }).execute()

    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to create label")

    label = result.data[0]
    return LinkedInLabelResponse(
        id=label["id"],
        name=label["name"],
        color=label.get("color", "#6366f1"),
        sort_order=label.get("sort_order", 0),
        is_pinned=label.get("is_pinned", False),
    )


@router.put("/labels/{label_id}")
async def update_label(label_id: int, req: LinkedInLabelUpdate):
    """Update a label."""
    updates = req.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    client = get_client()
    result = client.table("linkedin_labels").update(updates).eq("id", label_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Label not found")

    label = result.data[0]
    return LinkedInLabelResponse(
        id=label["id"],
        name=label["name"],
        color=label.get("color", "#6366f1"),
        sort_order=label.get("sort_order", 0),
        is_pinned=label.get("is_pinned", False),
    )


@router.delete("/labels/{label_id}")
async def delete_label(label_id: int):
    """Delete a label and remove all assignments."""
    client = get_client()

    # Remove assignments first
    client.table("linkedin_thread_labels").delete().eq("label_id", label_id).execute()
    # Delete label
    result = client.table("linkedin_labels").delete().eq("id", label_id).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Label not found")
    return {"status": "deleted", "label_id": label_id}


@router.post("/conversations/{thread_id}/labels")
async def assign_labels(thread_id: str, req: LinkedInLabelAssignRequest):
    """Replace all labels on a conversation."""
    client = get_client()

    # Remove existing
    client.table("linkedin_thread_labels").delete().eq("thread_id", thread_id).execute()

    # Add new
    for lid in req.label_ids:
        client.table("linkedin_thread_labels").insert({
            "thread_id": thread_id,
            "label_id": lid,
        }).execute()

    return {"status": "labels_assigned", "thread_id": thread_id, "label_ids": req.label_ids}


# ═════════════════════════════════════════════════════════════
# SNOOZE & FOLLOW-UPS
# ═════════════════════════════════════════════════════════════


@router.post("/conversations/{thread_id}/snooze")
async def snooze_conversation(thread_id: str, req: LinkedInSnoozeRequest):
    """Snooze a conversation until a specific time."""
    client = get_client()

    # Remove existing snooze
    client.table("linkedin_snoozes").delete().eq("thread_id", thread_id).execute()

    # Create new
    result = client.table("linkedin_snoozes").insert({
        "thread_id": thread_id,
        "snooze_until": req.snooze_until.isoformat(),
    }).execute()

    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to snooze")

    row = result.data[0]
    return LinkedInSnoozeResponse(
        thread_id=thread_id,
        snooze_until=row["snooze_until"],
        created_at=row.get("created_at"),
    )


@router.delete("/conversations/{thread_id}/snooze")
async def unsnooze_conversation(thread_id: str):
    """Remove snooze from a conversation."""
    client = get_client()
    client.table("linkedin_snoozes").delete().eq("thread_id", thread_id).execute()
    return {"status": "unsnoozed", "thread_id": thread_id}


@router.post("/conversations/{thread_id}/follow-up")
async def create_follow_up(thread_id: str, req: LinkedInFollowUpRequest):
    """Create a follow-up reminder for a conversation."""
    client = get_client()
    result = client.table("linkedin_followups").insert({
        "thread_id": thread_id,
        "remind_at": req.remind_at.isoformat(),
        "note": req.note,
    }).execute()

    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to create follow-up")

    row = result.data[0]
    return LinkedInFollowUpResponse(
        id=row["id"],
        thread_id=thread_id,
        remind_at=row["remind_at"],
        note=row.get("note"),
        is_completed=row.get("is_completed", False),
    )


@router.post("/conversations/{thread_id}/follow-up/{followup_id}/complete")
async def complete_follow_up(thread_id: str, followup_id: int):
    """Mark a follow-up as completed."""
    client = get_client()
    result = (
        client.table("linkedin_followups")
        .update({"is_completed": True})
        .eq("id", followup_id)
        .eq("thread_id", thread_id)
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=404, detail="Follow-up not found")
    return {"status": "completed", "followup_id": followup_id}


# ═════════════════════════════════════════════════════════════
# SNIPPETS
# ═════════════════════════════════════════════════════════════


@router.get("/snippets")
async def list_snippets():
    """List saved message snippets."""
    client = get_client()
    result = (
        client.table("linkedin_snippets")
        .select("*")
        .order("use_count", desc=True)
        .order("title")
        .execute()
    )
    snippets = result.data or []

    return [
        LinkedInSnippetResponse(
            id=s["id"],
            title=s["title"],
            trigger=s.get("trigger"),
            body=s["body"],
            variables=json.loads(s["variables"]) if isinstance(s.get("variables"), str) else (s.get("variables") or []),
            use_count=s.get("use_count", 0),
        )
        for s in snippets
    ]


@router.post("/snippets")
async def create_snippet(req: LinkedInSnippetCreate):
    """Create a new message snippet."""
    client = get_client()
    result = client.table("linkedin_snippets").insert({
        "title": req.title,
        "trigger": req.trigger,
        "body": req.body,
        "variables": json.dumps(req.variables),
    }).execute()

    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to create snippet")

    s = result.data[0]
    return LinkedInSnippetResponse(
        id=s["id"],
        title=s["title"],
        trigger=s.get("trigger"),
        body=s["body"],
        variables=req.variables,
        use_count=0,
    )


@router.put("/snippets/{snippet_id}")
async def update_snippet(snippet_id: int, req: LinkedInSnippetUpdate):
    """Update a snippet."""
    updates = req.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    updates["updated_at"] = datetime.now(timezone.utc).isoformat()

    client = get_client()
    result = client.table("linkedin_snippets").update(updates).eq("id", snippet_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Snippet not found")

    s = result.data[0]
    return LinkedInSnippetResponse(
        id=s["id"],
        title=s["title"],
        trigger=s.get("trigger"),
        body=s["body"],
        variables=json.loads(s["variables"]) if isinstance(s.get("variables"), str) else (s.get("variables") or []),
        use_count=s.get("use_count", 0),
    )


@router.delete("/snippets/{snippet_id}")
async def delete_snippet(snippet_id: int):
    """Delete a snippet."""
    client = get_client()
    result = client.table("linkedin_snippets").delete().eq("id", snippet_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Snippet not found")
    return {"status": "deleted", "snippet_id": snippet_id}


# ═════════════════════════════════════════════════════════════
# CONTACTS
# ═════════════════════════════════════════════════════════════


@router.get("/profile/{public_id}")
async def get_contact_profile(public_id: str):
    """Fetch a LinkedIn contact profile via Voyager API."""
    voyager = _get_voyager_client()

    try:
        profile_data = await voyager.fetch_profile(public_id)
        profile = profile_data.get("profile", {})
        linkedin_id = profile.get("entityUrn", "").split(":")[-1]

        now = datetime.now(timezone.utc).isoformat()
        client = get_client()

        contact_row = {
            "id": linkedin_id,
            "first_name": profile.get("firstName", ""),
            "last_name": profile.get("lastName", ""),
            "headline": profile.get("headline", ""),
            "location": profile.get("locationName", ""),
            "profile_url": f"https://linkedin.com/in/{public_id}",
            "updated_at": now,
        }

        client.table("linkedin_contacts").upsert(
            contact_row, on_conflict="id"
        ).execute()

        return LinkedInContactResponse(
            linkedin_id=linkedin_id,
            first_name=contact_row["first_name"],
            last_name=contact_row["last_name"],
            headline=contact_row["headline"],
            location=contact_row["location"],
            profile_url=contact_row["profile_url"],
        )

    except Exception as e:
        logger.error("Failed to fetch profile: %s", e)
        raise HTTPException(status_code=500, detail="Failed to fetch profile")


@router.post("/contacts/{contact_id}/notes")
async def upsert_contact_note(contact_id: str, req: LinkedInContactNoteRequest):
    """Add or update a note for a contact."""
    client = get_client()
    now = datetime.now(timezone.utc).isoformat()

    # Check existing
    existing = (
        client.table("linkedin_contact_notes")
        .select("id")
        .eq("contact_id", contact_id)
        .limit(1)
        .execute()
    )

    if existing.data:
        result = (
            client.table("linkedin_contact_notes")
            .update({"note": req.note, "updated_at": now})
            .eq("id", existing.data[0]["id"])
            .execute()
        )
    else:
        result = client.table("linkedin_contact_notes").insert({
            "contact_id": contact_id,
            "note": req.note,
        }).execute()

    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to save note")

    row = result.data[0]
    return LinkedInContactNoteResponse(
        id=row["id"],
        contact_id=contact_id,
        note=row["note"],
        updated_at=row.get("updated_at"),
    )


# ═════════════════════════════════════════════════════════════
# SEARCH
# ═════════════════════════════════════════════════════════════


@router.get("/search")
async def search_messages(
    q: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=100),
):
    """Search messages and threads locally."""
    client = get_client()

    # Search threads by participant name or preview
    thread_results = (
        client.table("linkedin_threads")
        .select("*")
        .or_(
            f"last_message_preview.ilike.%{q}%,"
            f"participants.ilike.%{q}%"
        )
        .order("last_message_at", desc=True)
        .limit(limit)
        .execute()
    )

    threads = []
    for t in (thread_results.data or []):
        participants = _parse_participants(t.get("participants"))
        threads.append(LinkedInThreadResponse(
            thread_id=t["id"],
            participants=[LinkedInParticipant(**p) for p in participants],
            last_message_at=t.get("last_message_at"),
            last_message_preview=t.get("last_message_preview"),
            unread_count=t.get("unread_count", 0),
            is_archived=t.get("is_archived", False),
        ))

    # Search messages by body
    msg_results = (
        client.table("linkedin_messages")
        .select("*")
        .ilike("body", f"%{q}%")
        .order("sent_at", desc=True)
        .limit(limit)
        .execute()
    )

    messages = [
        LinkedInMessageResponse(
            message_id=m["id"],
            thread_id=m["thread_id"],
            sender_id=m.get("sender_id"),
            sender_name=m.get("sender_name"),
            body=m.get("body"),
            timestamp=m.get("sent_at"),
            is_inbound=m.get("is_inbound", True),
            attachments=json.loads(m["attachments"]) if isinstance(m.get("attachments"), str) else (m.get("attachments") or []),
        )
        for m in (msg_results.data or [])
    ]

    return LinkedInSearchResult(
        query=q,
        threads=threads,
        messages=messages,
        total=len(threads) + len(messages),
    )


# ═════════════════════════════════════════════════════════════
# SYNC & HEARTBEAT
# ═════════════════════════════════════════════════════════════


@router.post("/sync")
async def trigger_sync(full: bool = Query(False)):
    """Manually trigger LinkedIn message sync."""
    from scripts.outreach.linkedin_sync import linkedin_sync_engine
    result = await linkedin_sync_engine.sync_conversations(full_sync=full)
    return {"status": "sync_complete", "full_sync": full, "stats": result}


@router.post("/heartbeat")
async def receive_heartbeat():
    """Called by the session refresh script to signal browser is open."""
    from scripts.outreach.linkedin_sync import linkedin_sync_engine
    linkedin_sync_engine.update_heartbeat()
    return {"status": "ok", "message": "Heartbeat received", "sync_enabled": True}


@router.get("/browser-status")
async def get_browser_status():
    """Check whether the browser is active and sync is enabled."""
    from scripts.outreach.linkedin_sync import linkedin_sync_engine
    return linkedin_sync_engine.get_browser_status()
