"""
Annas AI Hub — Outreach Pillars Router
========================================

Service pillar management: list, update, reload from YAML.

Endpoints:
  GET  /api/outreach/pillars           - List all pillars
  GET  /api/outreach/pillars/{id}      - Get a single pillar with sequences
  PUT  /api/outreach/pillars/{id}      - Update pillar fields
  POST /api/outreach/pillars/reload    - Reload all pillars from YAML
  GET  /api/outreach/sequences/{id}    - Get sequence with templates
"""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Query

from models.outreach_models import PillarUpdate
from scripts.lib.logger import setup_logger
from scripts.lib.supabase_client import get_client

logger = setup_logger("outreach_pillars_router")

router = APIRouter(prefix="/api/outreach", tags=["outreach-pillars"])


@router.get("/pillars")
async def list_pillars(
    active_only: bool = Query(True, description="Only return active pillars"),
):
    """List all service pillars."""
    try:
        client = get_client()
        query = client.table("outreach_pillars").select("*")
        if active_only:
            query = query.eq("is_active", True)
        result = query.order("sort_order").execute()

        pillars = result.data or []

        # Parse JSONB fields
        for p in pillars:
            for field in ("icp_criteria", "messaging_angles", "research_prompts", "objection_handlers"):
                if isinstance(p.get(field), str):
                    try:
                        p[field] = json.loads(p[field])
                    except (json.JSONDecodeError, TypeError):
                        pass

        return {"results": pillars, "count": len(pillars)}
    except Exception as e:
        logger.error("List pillars failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to fetch pillars")


@router.get("/pillars/{pillar_id}")
async def get_pillar(pillar_id: int):
    """Get a single pillar with its sequences and templates."""
    try:
        client = get_client()

        # Get pillar
        result = (
            client.table("outreach_pillars")
            .select("*")
            .eq("id", pillar_id)
            .limit(1)
            .execute()
        )
        if not result.data:
            raise HTTPException(status_code=404, detail="Pillar not found")

        pillar = result.data[0]

        # Parse JSONB fields
        for field in ("icp_criteria", "messaging_angles", "research_prompts", "objection_handlers"):
            if isinstance(pillar.get(field), str):
                try:
                    pillar[field] = json.loads(pillar[field])
                except (json.JSONDecodeError, TypeError):
                    pass

        # Get sequences
        seq_result = (
            client.table("outreach_sequences")
            .select("*")
            .eq("pillar_id", pillar_id)
            .order("id")
            .execute()
        )
        sequences = seq_result.data or []

        # Get templates for each sequence
        for seq in sequences:
            tmpl_result = (
                client.table("outreach_templates")
                .select("*")
                .eq("sequence_id", seq["id"])
                .order("step_number")
                .execute()
            )
            seq["templates"] = tmpl_result.data or []

        pillar["sequences"] = sequences

        # Get prospect count for this pillar
        count_result = (
            client.table("outreach_prospects")
            .select("id", count="exact")
            .eq("pillar_id", pillar_id)
            .execute()
        )
        pillar["prospect_count"] = count_result.count or 0

        return pillar
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Get pillar failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to fetch pillar")


@router.put("/pillars/{pillar_id}")
async def update_pillar(pillar_id: int, body: PillarUpdate):
    """Update a pillar's fields."""
    try:
        client = get_client()

        # Build update dict (only non-None fields)
        updates = {}
        for field, value in body.model_dump(exclude_none=True).items():
            if isinstance(value, (dict, list)):
                updates[field] = json.dumps(value)
            else:
                updates[field] = value

        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")

        result = (
            client.table("outreach_pillars")
            .update(updates)
            .eq("id", pillar_id)
            .execute()
        )

        if not result.data:
            raise HTTPException(status_code=404, detail="Pillar not found")

        return result.data[0]
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Update pillar failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to update pillar")


@router.post("/pillars/reload")
async def reload_pillars():
    """Reload all pillars from configs/outreach_pillars.yaml."""
    try:
        from scripts.outreach.load_pillars import load_yaml, upsert_pillars

        pillars = load_yaml()
        stats = upsert_pillars(pillars)
        return {
            "status": "reloaded",
            "pillars": stats["pillars"],
            "sequences": stats["sequences"],
            "templates": stats["templates"],
        }
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Reload pillars failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to reload pillars")


@router.get("/sequences/{sequence_id}")
async def get_sequence(sequence_id: int):
    """Get a sequence with its templates."""
    try:
        client = get_client()

        # Get sequence
        result = (
            client.table("outreach_sequences")
            .select("*")
            .eq("id", sequence_id)
            .limit(1)
            .execute()
        )
        if not result.data:
            raise HTTPException(status_code=404, detail="Sequence not found")

        sequence = result.data[0]

        # Get templates
        tmpl_result = (
            client.table("outreach_templates")
            .select("*")
            .eq("sequence_id", sequence_id)
            .order("step_number")
            .execute()
        )
        sequence["templates"] = tmpl_result.data or []

        # Get pillar name
        pillar_result = (
            client.table("outreach_pillars")
            .select("name, slug")
            .eq("id", sequence["pillar_id"])
            .limit(1)
            .execute()
        )
        if pillar_result.data:
            sequence["pillar_name"] = pillar_result.data[0]["name"]
            sequence["pillar_slug"] = pillar_result.data[0]["slug"]

        return sequence
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Get sequence failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to fetch sequence")
