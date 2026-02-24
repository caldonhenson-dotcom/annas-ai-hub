"""
Annas AI Hub — Workflow Runner
=================================

Background task that executes outreach sequences automatically.
Queries due enrollments (next_step_at <= NOW), drafts messages via AI,
and manages step progression.

Can run standalone or be integrated into the pipeline orchestrator.

Usage:
    python scripts/outreach/workflow_runner.py              # process due enrollments
    python scripts/outreach/workflow_runner.py --dry-run     # preview without executing
    python scripts/outreach/workflow_runner.py --limit 10    # cap at 10 enrollments
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Path setup for standalone execution
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.lib.logger import setup_logger
from scripts.lib.supabase_client import get_client

logger = setup_logger("workflow_runner")


async def process_due_enrollments(
    limit: int = 50,
    dry_run: bool = False,
) -> dict:
    """
    Process enrollments that have a due next_step_at.

    For each due enrollment:
    1. Load prospect, sequence, and template for the current step
    2. Call message_drafter to create an AI-drafted message
    3. Message enters the approval queue automatically

    Args:
        limit: Max enrollments to process.
        dry_run: If True, log what would happen without drafting.

    Returns:
        Summary dict with processed/drafted/skipped/error counts.
    """
    client = get_client()
    now = datetime.now(timezone.utc).isoformat()

    stats = {
        "processed": 0,
        "drafted": 0,
        "skipped": 0,
        "errors": 0,
    }

    # Find due enrollments
    due_enrollments = (
        client.table("outreach_enrollments")
        .select("*")
        .eq("status", "active")
        .lte("next_step_at", now)
        .order("next_step_at", desc=False)
        .limit(limit)
        .execute()
    )

    if not due_enrollments.data:
        logger.info("No due enrollments to process")
        return stats

    logger.info("Found %d due enrollments", len(due_enrollments.data))

    for enrollment in due_enrollments.data:
        stats["processed"] += 1
        enrollment_id = enrollment["id"]
        prospect_id = enrollment["prospect_id"]
        current_step = enrollment.get("current_step", 1)

        try:
            # Validate prospect still exists and is active
            prospect_result = (
                client.table("outreach_prospects")
                .select("id, status, first_name, last_name")
                .eq("id", prospect_id)
                .limit(1)
                .execute()
            )
            if not prospect_result.data:
                logger.warning("Prospect %d not found, skipping enrollment %d", prospect_id, enrollment_id)
                stats["skipped"] += 1
                _pause_enrollment(client, enrollment_id, "prospect_not_found")
                continue

            prospect = prospect_result.data[0]

            # Skip if prospect opted out or is in a terminal state
            if prospect.get("status") in ("opted_out", "converted", "disqualified"):
                logger.info(
                    "Prospect %d is '%s', cancelling enrollment %d",
                    prospect_id, prospect["status"], enrollment_id,
                )
                stats["skipped"] += 1
                _cancel_enrollment(client, enrollment_id, f"prospect_{prospect['status']}")
                continue

            if dry_run:
                logger.info(
                    "[DRY RUN] Would draft step %d for prospect %d (%s %s) in enrollment %d",
                    current_step, prospect_id,
                    prospect.get("first_name", ""), prospect.get("last_name", ""),
                    enrollment_id,
                )
                stats["drafted"] += 1
                continue

            # Draft the message via AI
            from scripts.outreach.message_drafter import draft_message

            message = await draft_message(
                prospect_id,
                sequence_step=current_step,
                enrollment_id=enrollment_id,
            )

            logger.info(
                "Drafted step %d for prospect %d (%s %s) — message_id=%d, awaiting approval",
                current_step, prospect_id,
                prospect.get("first_name", ""), prospect.get("last_name", ""),
                message["id"],
            )
            stats["drafted"] += 1

        except Exception as e:
            logger.error(
                "Workflow error for enrollment %d (prospect %d, step %d): %s",
                enrollment_id, prospect_id, current_step, e,
            )
            stats["errors"] += 1

            # Increment error count on enrollment
            error_count = enrollment.get("error_count", 0) + 1
            update_data = {
                "error_count": error_count,
                "last_error": str(e)[:500],
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }

            # Auto-pause after 3 consecutive errors
            if error_count >= 3:
                update_data["status"] = "paused"
                logger.warning(
                    "Enrollment %d paused after %d errors", enrollment_id, error_count,
                )

            client.table("outreach_enrollments").update(
                update_data
            ).eq("id", enrollment_id).execute()

    logger.info(
        "Workflow runner complete: %d processed, %d drafted, %d skipped, %d errors",
        stats["processed"], stats["drafted"], stats["skipped"], stats["errors"],
    )
    return stats


async def run_correspondence_monitor(since_minutes: int = 60) -> dict:
    """
    Run the correspondence monitor as part of the workflow.

    Processes inbound messages, classifies intent, updates scores.
    """
    from scripts.outreach.correspondence_monitor import process_new_inbound
    return await process_new_inbound(since_minutes=since_minutes)


async def run_score_recalculation(pillar_id: int | None = None) -> dict:
    """
    Run batch score recalculation as part of the workflow.
    """
    from scripts.outreach.lead_scorer import batch_recalculate
    return batch_recalculate(pillar_id=pillar_id)


def _pause_enrollment(client, enrollment_id: int, reason: str) -> None:
    """Pause an enrollment with a reason."""
    client.table("outreach_enrollments").update({
        "status": "paused",
        "last_error": reason,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", enrollment_id).execute()


def _cancel_enrollment(client, enrollment_id: int, reason: str) -> None:
    """Cancel an enrollment with a reason."""
    client.table("outreach_enrollments").update({
        "status": "cancelled",
        "last_error": reason,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", enrollment_id).execute()


async def run_full_workflow(
    limit: int = 50,
    since_minutes: int = 60,
    dry_run: bool = False,
) -> dict:
    """
    Run the complete outreach workflow cycle:
    1. Process due enrollments (draft messages)
    2. Run correspondence monitor (classify inbound)
    3. Recalculate lead scores

    Returns combined results dict.
    """
    results = {}

    logger.info("=" * 50)
    logger.info("  Outreach Workflow Cycle")
    logger.info("=" * 50)

    # Step 1: Process due enrollments
    logger.info("--- Step 1: Processing due enrollments ---")
    results["enrollments"] = await process_due_enrollments(limit=limit, dry_run=dry_run)

    # Step 2: Correspondence monitor
    if not dry_run:
        logger.info("--- Step 2: Correspondence monitor ---")
        results["correspondence"] = await run_correspondence_monitor(since_minutes=since_minutes)
    else:
        logger.info("[DRY RUN] Skipping correspondence monitor")
        results["correspondence"] = {"skipped": True}

    # Step 3: Score recalculation
    if not dry_run:
        logger.info("--- Step 3: Score recalculation ---")
        results["scoring"] = await run_score_recalculation()
    else:
        logger.info("[DRY RUN] Skipping score recalculation")
        results["scoring"] = {"skipped": True}

    logger.info("=" * 50)
    logger.info("  Workflow cycle complete")
    logger.info("=" * 50)

    return results


def main():
    parser = argparse.ArgumentParser(description="Annas AI Hub — Outreach Workflow Runner")
    parser.add_argument("--limit", type=int, default=50, help="Max enrollments to process")
    parser.add_argument("--since", type=int, default=60, help="Correspondence lookback (minutes)")
    parser.add_argument("--dry-run", action="store_true", help="Preview without executing")
    parser.add_argument(
        "--step",
        choices=["enrollments", "correspondence", "scoring", "all"],
        default="all",
        help="Run a specific step or all",
    )
    args = parser.parse_args()

    async def _run():
        if args.step == "all":
            return await run_full_workflow(
                limit=args.limit,
                since_minutes=args.since,
                dry_run=args.dry_run,
            )
        elif args.step == "enrollments":
            return await process_due_enrollments(limit=args.limit, dry_run=args.dry_run)
        elif args.step == "correspondence":
            return await run_correspondence_monitor(since_minutes=args.since)
        elif args.step == "scoring":
            return await run_score_recalculation()

    results = asyncio.run(_run())
    logger.info("Results: %s", results)


if __name__ == "__main__":
    main()
