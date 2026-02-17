"""
Email Quick Actions
====================

Generates mailto: links and pre-populated email content for the dashboard's
quick action buttons.  Reads templates from config/email_templates.json and
contact data from processed metrics.

Usage:
    python scripts/email_actions.py                   # generate actions JSON
    python scripts/email_actions.py --template london_meeting --to "john@example.com"
"""

from __future__ import annotations

import argparse
import json
import logging
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent.parent
load_dotenv(BASE_DIR / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

CONFIG_PATH = BASE_DIR / "config" / "email_templates.json"
PROCESSED_DIR = BASE_DIR / "data" / "processed"


def load_templates() -> dict:
    """Load email templates from config."""
    if not CONFIG_PATH.exists():
        logger.warning("Email templates not found: %s", CONFIG_PATH)
        return {}
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _fill_template(template: str, variables: Dict[str, str]) -> str:
    """Replace {variable} placeholders in a template string."""
    result = template
    for key, value in variables.items():
        result = result.replace(f"{{{key}}}", str(value))
    return result


def generate_mailto(
    to: str,
    subject: str,
    body: str,
    cc: str = "",
    bcc: str = "",
) -> str:
    """Generate a mailto: URI with pre-populated fields."""
    params = {"subject": subject, "body": body}
    if cc:
        params["cc"] = cc
    if bcc:
        params["bcc"] = bcc
    query = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
    return f"mailto:{urllib.parse.quote(to)}?{query}"


def build_scheduling_action(
    template_key: str,
    to_email: str,
    to_name: str = "",
    variables: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    """Build a scheduling email quick action."""
    config = load_templates()
    scheduling = config.get("scheduling", {})
    templates = scheduling.get("templates", {})
    defaults = config.get("sender_defaults", {})

    template = templates.get(template_key)
    if not template:
        available = list(templates.keys())
        logger.error("Template '%s' not found. Available: %s", template_key, available)
        return {}

    booking_link = scheduling.get("booking_link", "[BOOKING_LINK]")
    first_name = to_name.split()[0] if to_name else to_email.split("@")[0].title()

    vars_merged = {
        "first_name": first_name,
        "booking_link": booking_link,
        "sender_name": defaults.get("sender_name", "[YOUR_NAME]"),
        "meeting_notes": "",
        "next_steps": "",
        "highlights": "",
        **(variables or {}),
    }

    subject = _fill_template(template["subject"], vars_merged)
    body = _fill_template(template["body"], vars_merged)
    mailto = generate_mailto(to_email, subject, body)

    return {
        "template": template_key,
        "template_name": template["name"],
        "to": to_email,
        "to_name": to_name,
        "subject": subject,
        "body": body,
        "mailto": mailto,
    }


def build_quick_response(
    template_key: str,
    to_email: str,
    subject: str = "Re: ",
) -> Dict[str, str]:
    """Build a quick response action."""
    config = load_templates()
    quick = config.get("quick_responses", {}).get("templates", {})
    booking_link = config.get("scheduling", {}).get("booking_link", "[BOOKING_LINK]")

    template = quick.get(template_key)
    if not template:
        return {}

    body = _fill_template(template["body"], {"booking_link": booking_link})
    mailto = generate_mailto(to_email, subject, body)

    return {
        "template": template_key,
        "template_name": template["name"],
        "to": to_email,
        "subject": subject,
        "body": body,
        "mailto": mailto,
    }


def generate_dashboard_actions() -> Dict[str, Any]:
    """Generate all quick action data for the dashboard.

    Reads contacts and deals from processed metrics to produce
    context-aware action suggestions.
    """
    config = load_templates()
    scheduling = config.get("scheduling", {})
    constraints = scheduling.get("constraints", {})

    # Load HubSpot metrics for contact/deal context
    hs_path = PROCESSED_DIR / "hubspot_sales_metrics.json"
    hs_data: dict = {}
    if hs_path.exists():
        try:
            with open(hs_path, "r", encoding="utf-8") as f:
                hs_data = json.load(f)
        except Exception:
            pass

    # Load Monday metrics for M&A context
    monday_path = PROCESSED_DIR / "monday_metrics.json"
    monday_data: dict = {}
    if monday_path.exists():
        try:
            with open(monday_path, "r", encoding="utf-8") as f:
                monday_data = json.load(f)
        except Exception:
            pass

    # Collect deals needing follow-up (close date in next 14 days)
    pipeline = hs_data.get("pipeline", {})
    deals_by_stage = pipeline.get("deals_by_stage", [])

    # Available template list for dashboard buttons
    scheduling_templates = [
        {
            "key": key,
            "name": tmpl["name"],
            "use_when": tmpl.get("use_when", ""),
        }
        for key, tmpl in scheduling.get("templates", {}).items()
    ]

    quick_responses = [
        {"key": key, "name": tmpl["name"]}
        for key, tmpl in config.get("quick_responses", {}).get("templates", {}).items()
    ]

    # M&A projects that might need NDA/scheduling
    ma_projects = monday_data.get("ma_metrics", {}).get("projects", [])
    active_projects = [p for p in ma_projects if p.get("is_active")]

    return {
        "scheduling_constraints": constraints,
        "booking_link": scheduling.get("booking_link", ""),
        "scheduling_templates": scheduling_templates,
        "quick_responses": quick_responses,
        "active_ma_projects": len(active_projects),
        "suggested_actions": _generate_suggestions(hs_data, monday_data),
    }


def _generate_suggestions(hs_data: dict, monday_data: dict) -> List[Dict[str, str]]:
    """Generate AI-recommended actions based on current data."""
    suggestions: List[Dict[str, str]] = []

    # Stale M&A projects needing follow-up
    stale = monday_data.get("ma_metrics", {}).get("stale_projects", [])
    for p in stale[:5]:
        suggestions.append({
            "type": "follow_up",
            "priority": "high" if p.get("days_stale", 0) > 30 else "medium",
            "title": f"Follow up: {p.get('name', 'Unknown')}",
            "detail": f"No update in {p.get('days_stale', 0)} days — stage: {p.get('stage', '')}",
            "action": "schedule_call",
        })

    # IC items without decisions
    ic_items = monday_data.get("ic_metrics", {}).get("items", [])
    undecided = [i for i in ic_items if not i.get("decisions")]
    for item in undecided[:3]:
        suggestions.append({
            "type": "ic_review",
            "priority": "medium",
            "title": f"IC review needed: {item.get('name', '')}",
            "detail": f"Score: {item.get('total_score', 'N/A')} — no IC decision recorded",
            "action": "schedule_meeting",
        })

    return suggestions


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args():
    parser = argparse.ArgumentParser(description="Email Quick Actions")
    parser.add_argument(
        "--template", type=str,
        help="Template key to use (e.g., london_meeting, phone_call)",
    )
    parser.add_argument("--to", type=str, help="Recipient email address")
    parser.add_argument("--name", type=str, default="", help="Recipient name")
    parser.add_argument(
        "--generate-dashboard", action="store_true",
        help="Generate dashboard action data to JSON",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()

    if args.generate_dashboard:
        actions = generate_dashboard_actions()
        out_path = PROCESSED_DIR / "email_actions.json"
        PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(actions, f, indent=2, default=str)
        logger.info("Dashboard actions written to %s", out_path)
        print(f"Templates: {len(actions.get('scheduling_templates', []))} scheduling, "
              f"{len(actions.get('quick_responses', []))} quick responses")
        print(f"Suggested actions: {len(actions.get('suggested_actions', []))}")

    elif args.template and args.to:
        result = build_scheduling_action(args.template, args.to, args.name)
        if result:
            print(f"\nTemplate: {result['template_name']}")
            print(f"To: {result['to']}")
            print(f"Subject: {result['subject']}")
            print(f"\n{result['body']}")
            print(f"\nMailto link:\n{result['mailto']}")
        else:
            print("Failed to generate action. Check template key.")

    else:
        # Default: list available templates
        config = load_templates()
        print("\nAvailable scheduling templates:")
        for key, tmpl in config.get("scheduling", {}).get("templates", {}).items():
            print(f"  {key:20s} — {tmpl['name']}")
        print("\nQuick responses:")
        for key, tmpl in config.get("quick_responses", {}).get("templates", {}).items():
            print(f"  {key:20s} — {tmpl['name']}")
        print("\nUsage: python scripts/email_actions.py --template london_meeting --to user@example.com")
