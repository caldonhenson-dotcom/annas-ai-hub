"""
Annas AI Hub — Pipeline Orchestrator
======================================
Chains all data scripts in the correct order with step tracking, parallel
fetching, retry logic, and run logging to Supabase.

Pipeline phases:
    1. Fetch  (parallel) — hubspot, monday, google sheets
    2. Analyze           — hubspot analyzer, monday analyzer, gsheets analyzer
    3. Automate          — email actions, inbound queue, weekly summary
    4. Generate          — dashboard HTML
    5. Sync              — upload to Supabase
    6. Outreach          — workflow runner (enrollments, correspondence, scoring)

Usage:
    python scripts/pipeline_orchestrator.py                  # full pipeline
    python scripts/pipeline_orchestrator.py --phase fetch     # fetch only
    python scripts/pipeline_orchestrator.py --phase analyze   # analyze only
    python scripts/pipeline_orchestrator.py --skip-fetch      # skip fetching
    python scripts/pipeline_orchestrator.py --dry-run         # log steps without executing
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import runpy
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(PROJECT_ROOT / ".env")

from scripts.lib.logger import setup_logger

logger = setup_logger("pipeline_orchestrator")

# ---------------------------------------------------------------------------
# Try to import Supabase client (optional — pipeline works without it)
# ---------------------------------------------------------------------------
try:
    from scripts.lib.supabase_client import get_client, upsert_row
    SUPABASE_AVAILABLE = True
except Exception:
    SUPABASE_AVAILABLE = False
    logger.warning("Supabase client not available — run tracking disabled")


# ---------------------------------------------------------------------------
# Pipeline step definitions
# ---------------------------------------------------------------------------
FETCH_STEPS = [
    ("Fetch HubSpot", "fetch_hubspot.py"),
    ("Fetch Monday.com", "fetch_monday.py"),
    ("Fetch Google Sheets", "fetch_google_sheets.py"),
]

ANALYZE_STEPS = [
    ("Analyze HubSpot", "hubspot_sales_analyzer.py"),
    ("Analyze Monday.com", "monday_analyzer.py"),
    ("Analyze Google Sheets", "gsheets_analyzer.py"),
]

AUTOMATE_STEPS = [
    ("Email Actions", "email_actions.py"),
    ("Inbound Queue", "inbound_queue.py"),
    ("Weekly Summary", "generate_weekly_summary.py"),
]

GENERATE_STEPS = [
    ("Generate Dashboard", "generate_hubspot_dashboard.py"),
]

SYNC_STEPS = [
    ("Sync to Supabase", "sync_to_supabase.py"),
]

OUTREACH_STEPS = [
    ("Outreach Workflow Runner", "outreach/workflow_runner.py"),
]


# ---------------------------------------------------------------------------
# Step execution
# ---------------------------------------------------------------------------
def run_script(script_name: str) -> Tuple[bool, float, Optional[str]]:
    """
    Execute a pipeline script using runpy.

    Returns:
        Tuple of (success, duration_seconds, error_message).
    """
    script_path = SCRIPT_DIR / script_name

    if not script_path.exists():
        return False, 0.0, f"Script not found: {script_path}"

    start = time.time()
    try:
        runpy.run_path(str(script_path), run_name="__main__")
        duration = time.time() - start
        return True, duration, None
    except SystemExit as e:
        duration = time.time() - start
        if e.code == 0 or e.code is None:
            return True, duration, None
        return False, duration, f"Exited with code {e.code}"
    except Exception as e:
        duration = time.time() - start
        return False, duration, str(e)


async def run_scripts_parallel(steps: List[Tuple[str, str]]) -> List[dict]:
    """
    Run multiple scripts in parallel using subprocesses.

    Args:
        steps: List of (step_name, script_filename) tuples.

    Returns:
        List of step result dicts.
    """
    async def _run_one(step_name: str, script_name: str) -> dict:
        script_path = SCRIPT_DIR / script_name
        if not script_path.exists():
            return {
                "name": step_name,
                "script": script_name,
                "status": "failed",
                "duration_ms": 0,
                "error": f"Script not found: {script_path}",
            }

        start = time.time()
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable, str(script_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(SCRIPT_DIR),
            )
            stdout, stderr = await proc.communicate()
            duration = time.time() - start

            if proc.returncode == 0:
                logger.info(
                    "%s completed in %.1fs", step_name, duration,
                )
                return {
                    "name": step_name,
                    "script": script_name,
                    "status": "success",
                    "duration_ms": round(duration * 1000),
                    "error": None,
                }
            else:
                error_msg = stderr.decode("utf-8", errors="replace")[-500:]
                logger.error(
                    "%s failed (exit %d) in %.1fs: %s",
                    step_name, proc.returncode, duration, error_msg[:200],
                )
                return {
                    "name": step_name,
                    "script": script_name,
                    "status": "failed",
                    "duration_ms": round(duration * 1000),
                    "error": error_msg,
                }
        except Exception as e:
            duration = time.time() - start
            return {
                "name": step_name,
                "script": script_name,
                "status": "failed",
                "duration_ms": round(duration * 1000),
                "error": str(e),
            }

    tasks = [_run_one(name, script) for name, script in steps]
    return await asyncio.gather(*tasks)


def run_steps_sequential(steps: List[Tuple[str, str]], dry_run: bool = False) -> List[dict]:
    """
    Run steps sequentially.

    Args:
        steps: List of (step_name, script_filename) tuples.
        dry_run: If True, log but don't execute.

    Returns:
        List of step result dicts.
    """
    results = []
    for step_name, script_name in steps:
        if dry_run:
            logger.info("[DRY RUN] Would execute: %s (%s)", step_name, script_name)
            results.append({
                "name": step_name,
                "script": script_name,
                "status": "skipped",
                "duration_ms": 0,
                "error": None,
            })
            continue

        logger.info("Running: %s (%s)", step_name, script_name)
        success, duration, error = run_script(script_name)

        status = "success" if success else "failed"
        if not success:
            logger.warning(
                "%s failed in %.1fs: %s — continuing pipeline",
                step_name, duration, error,
            )
        else:
            logger.info("%s completed in %.1fs", step_name, duration)

        results.append({
            "name": step_name,
            "script": script_name,
            "status": status,
            "duration_ms": round(duration * 1000),
            "error": error,
        })

    return results


# ---------------------------------------------------------------------------
# Run tracking (Supabase)
# ---------------------------------------------------------------------------
def create_pipeline_run() -> Optional[int]:
    """Create a new pipeline_run record and return its ID."""
    if not SUPABASE_AVAILABLE:
        return None
    try:
        client = get_client()
        result = client.table("pipeline_runs").insert({
            "started_at": datetime.now(timezone.utc).isoformat(),
            "status": "running",
            "steps": [],
        }).execute()
        if result.data:
            run_id = result.data[0]["id"]
            logger.info("Pipeline run created: #%d", run_id)
            return run_id
        return None
    except Exception as e:
        logger.warning("Failed to create pipeline run record: %s", e)
        return None


def update_pipeline_run(
    run_id: int, status: str, steps: List[dict], error_log: str = None
):
    """Update a pipeline_run record with results."""
    if not SUPABASE_AVAILABLE or run_id is None:
        return
    try:
        client = get_client()
        client.table("pipeline_runs").update({
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "steps": steps,
            "error_log": error_log,
        }).eq("id", run_id).execute()
        logger.info("Pipeline run #%d updated: %s", run_id, status)
    except Exception as e:
        logger.warning("Failed to update pipeline run #%d: %s", run_id, e)


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Annas AI Hub Pipeline Orchestrator")
    parser.add_argument(
        "--phase", choices=["fetch", "analyze", "automate", "generate", "sync", "outreach"],
        help="Run only a specific phase",
    )
    parser.add_argument("--skip-fetch", action="store_true", help="Skip the fetch phase")
    parser.add_argument("--dry-run", action="store_true", help="Log steps without executing")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("  ANNAS AI HUB — Pipeline Orchestrator")
    logger.info("=" * 60)

    if args.dry_run:
        logger.info("  Mode: DRY RUN")

    pipeline_start = time.time()
    all_steps = []

    # Create tracking record
    run_id = None if args.dry_run else create_pipeline_run()

    try:
        # Determine which phases to run
        phases = []
        if args.phase:
            phase_map = {
                "fetch": ("Fetch", FETCH_STEPS, True),
                "analyze": ("Analyze", ANALYZE_STEPS, False),
                "automate": ("Automate", AUTOMATE_STEPS, False),
                "generate": ("Generate", GENERATE_STEPS, False),
                "sync": ("Sync", SYNC_STEPS, False),
                "outreach": ("Outreach", OUTREACH_STEPS, False),
            }
            phase = phase_map[args.phase]
            phases.append(phase)
        else:
            if not args.skip_fetch:
                phases.append(("Fetch", FETCH_STEPS, True))
            phases.append(("Analyze", ANALYZE_STEPS, False))
            phases.append(("Automate", AUTOMATE_STEPS, False))
            phases.append(("Generate", GENERATE_STEPS, False))
            phases.append(("Sync", SYNC_STEPS, False))
            phases.append(("Outreach", OUTREACH_STEPS, False))

        # Execute phases
        for phase_name, steps, parallel in phases:
            logger.info("-" * 40)
            logger.info("Phase: %s%s", phase_name, " (parallel)" if parallel else "")
            logger.info("-" * 40)

            if parallel and not args.dry_run:
                results = asyncio.run(run_scripts_parallel(steps))
            else:
                results = run_steps_sequential(steps, dry_run=args.dry_run)

            all_steps.extend(results)

            # After analysis: refresh materialised views
            if phase_name == "Analyze" and not args.dry_run:
                logger.info("-" * 40)
                logger.info("Post-analysis: Refreshing materialised views")
                logger.info("-" * 40)
                start = time.time()
                try:
                    from scripts.lib.data_sync import refresh_views
                    refresh_views()
                    duration = time.time() - start
                    all_steps.append({
                        "name": "Refresh Views",
                        "script": "data_sync.refresh_views",
                        "status": "success",
                        "duration_ms": round(duration * 1000),
                        "error": None,
                    })
                    logger.info("Views refreshed in %.1fs", duration)
                except Exception as e:
                    duration = time.time() - start
                    logger.warning("View refresh failed (non-fatal): %s", e)
                    all_steps.append({
                        "name": "Refresh Views",
                        "script": "data_sync.refresh_views",
                        "status": "failed",
                        "duration_ms": round(duration * 1000),
                        "error": str(e),
                    })

            # After sync: compute snapshot diffs
            if phase_name == "Sync" and not args.dry_run:
                logger.info("-" * 40)
                logger.info("Post-sync: Computing snapshot diffs")
                logger.info("-" * 40)
                start = time.time()
                try:
                    from scripts.lib.data_sync import compute_snapshot_diff
                    for source in ["hubspot_sales", "monday"]:
                        compute_snapshot_diff(source)
                    duration = time.time() - start
                    all_steps.append({
                        "name": "Snapshot Diffs",
                        "script": "data_sync.compute_snapshot_diff",
                        "status": "success",
                        "duration_ms": round(duration * 1000),
                        "error": None,
                    })
                    logger.info("Snapshot diffs computed in %.1fs", duration)
                except Exception as e:
                    duration = time.time() - start
                    logger.warning("Snapshot diff failed (non-fatal): %s", e)
                    all_steps.append({
                        "name": "Snapshot Diffs",
                        "script": "data_sync.compute_snapshot_diff",
                        "status": "failed",
                        "duration_ms": round(duration * 1000),
                        "error": str(e),
                    })

        # Summary
        elapsed = time.time() - pipeline_start
        successful = sum(1 for s in all_steps if s["status"] == "success")
        failed = sum(1 for s in all_steps if s["status"] == "failed")
        skipped = sum(1 for s in all_steps if s["status"] == "skipped")

        logger.info("=" * 60)
        logger.info("  Pipeline Complete")
        logger.info("  Total steps: %d", len(all_steps))
        logger.info("  Successful:  %d", successful)
        logger.info("  Failed:      %d", failed)
        if skipped:
            logger.info("  Skipped:     %d", skipped)
        logger.info("  Duration:    %.1fs", elapsed)
        logger.info("=" * 60)

        # Log individual step results
        for step in all_steps:
            icon = "OK" if step["status"] == "success" else "FAIL" if step["status"] == "failed" else "SKIP"
            logger.info(
                "  [%4s] %-25s %6dms%s",
                icon, step["name"], step["duration_ms"],
                f"  {step['error'][:80]}" if step["error"] else "",
            )

        # Update tracking
        overall_status = "success" if failed == 0 else "failed"
        error_log = None
        if failed > 0:
            errors = [
                f"{s['name']}: {s['error']}"
                for s in all_steps if s["status"] == "failed"
            ]
            error_log = "\n".join(errors)

        update_pipeline_run(run_id, overall_status, all_steps, error_log)

        if failed > 0:
            sys.exit(1)

    except KeyboardInterrupt:
        logger.warning("Pipeline interrupted by user")
        update_pipeline_run(run_id, "failed", all_steps, "Interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.critical("Pipeline fatal error: %s", e, exc_info=True)
        update_pipeline_run(run_id, "failed", all_steps, str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
