"""
Annas AI Hub — Pillar Loader
==============================

Reads configs/outreach_pillars.yaml and upserts into Supabase:
  - outreach_pillars
  - outreach_sequences
  - outreach_templates

Idempotent: safe to run multiple times.

Usage:
    python scripts/outreach/load_pillars.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

from scripts.lib.logger import setup_logger
from scripts.lib.supabase_client import get_client

logger = setup_logger("load_pillars")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = PROJECT_ROOT / "configs" / "outreach_pillars.yaml"


def load_yaml() -> list[dict]:
    """Load pillar definitions from YAML."""
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Pillar config not found: {CONFIG_PATH}")

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    pillars = data.get("pillars", [])
    logger.info("Loaded %d pillars from %s", len(pillars), CONFIG_PATH.name)
    return pillars


def upsert_pillars(pillars: list[dict]) -> dict:
    """
    Upsert pillars, sequences, and templates into Supabase.

    Returns:
        Summary dict with counts.
    """
    client = get_client()
    stats = {"pillars": 0, "sequences": 0, "templates": 0}

    for idx, pillar in enumerate(pillars):
        slug = pillar["slug"]
        logger.info("Processing pillar: %s", slug)

        # Upsert pillar
        pillar_row = {
            "slug": slug,
            "name": pillar["name"],
            "description": pillar.get("description", ""),
            "icp_criteria": json.dumps(pillar.get("icp_criteria", {})),
            "messaging_angles": json.dumps(pillar.get("messaging_angles", [])),
            "research_prompts": json.dumps(pillar.get("research_prompts", [])),
            "objection_handlers": json.dumps(pillar.get("objection_handlers", {})),
            "is_active": True,
            "sort_order": idx,
        }

        result = (
            client.table("outreach_pillars")
            .upsert(pillar_row, on_conflict="slug")
            .execute()
        )
        stats["pillars"] += 1

        # Get the pillar ID back
        pillar_record = (
            client.table("outreach_pillars")
            .select("id")
            .eq("slug", slug)
            .limit(1)
            .execute()
        )
        if not pillar_record.data:
            logger.error("Failed to retrieve pillar ID for slug=%s", slug)
            continue
        pillar_id = pillar_record.data[0]["id"]

        # Upsert sequences
        for seq_def in pillar.get("sequences", []):
            seq_row = {
                "pillar_id": pillar_id,
                "name": seq_def["name"],
                "description": seq_def.get("description"),
                "channel": seq_def.get("channel", "linkedin"),
                "total_steps": seq_def.get("total_steps", 1),
                "delay_days": seq_def.get("delay_days", [3]),
                "is_active": True,
            }

            # Check if sequence exists
            existing = (
                client.table("outreach_sequences")
                .select("id")
                .eq("pillar_id", pillar_id)
                .eq("name", seq_def["name"])
                .limit(1)
                .execute()
            )

            if existing.data:
                seq_id = existing.data[0]["id"]
                client.table("outreach_sequences").update(seq_row).eq("id", seq_id).execute()
            else:
                insert_result = (
                    client.table("outreach_sequences")
                    .insert(seq_row)
                    .execute()
                )
                seq_id = insert_result.data[0]["id"] if insert_result.data else None

            if not seq_id:
                logger.error("Failed to get sequence ID for: %s", seq_def["name"])
                continue

            stats["sequences"] += 1

            # Upsert templates for this sequence
            for tmpl in seq_def.get("templates", []):
                tmpl_row = {
                    "sequence_id": seq_id,
                    "step_number": tmpl["step"],
                    "name": tmpl.get("name"),
                    "channel": seq_def.get("channel", "linkedin"),
                    "subject": tmpl.get("subject"),
                    "body_template": tmpl["body_template"],
                    "ai_system_prompt": tmpl.get("ai_system_prompt"),
                    "variables": json.dumps(tmpl.get("variables", [])),
                }

                # Upsert on (sequence_id, step_number) unique constraint
                client.table("outreach_templates").upsert(
                    tmpl_row,
                    on_conflict="sequence_id,step_number",
                ).execute()
                stats["templates"] += 1

        logger.info("  -> %s: sequences=%d, templates=%d",
                     slug,
                     len(pillar.get("sequences", [])),
                     sum(len(s.get("templates", [])) for s in pillar.get("sequences", [])))

    return stats


def main():
    """Load and upsert all pillars."""
    logger.info("=== Loading Outreach Pillars ===")

    pillars = load_yaml()
    stats = upsert_pillars(pillars)

    logger.info(
        "=== Done: %d pillars, %d sequences, %d templates ===",
        stats["pillars"], stats["sequences"], stats["templates"],
    )
    return stats


if __name__ == "__main__":
    main()
