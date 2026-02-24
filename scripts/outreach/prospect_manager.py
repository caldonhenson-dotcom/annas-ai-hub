"""
Annas AI Hub — Prospect Manager
=================================

Functions for importing, creating, and managing outreach prospects.
Sources: HubSpot contacts, LinkedIn contacts, CSV upload, manual entry.

Usage:
    from scripts.outreach.prospect_manager import import_from_hubspot, assign_pillar
    results = import_from_hubspot(pillar_id=1)
    assign_pillar(prospect_ids=[1, 2, 3], pillar_id=2)
"""
from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from typing import Optional

from scripts.lib.logger import setup_logger
from scripts.lib.supabase_client import get_client

logger = setup_logger("prospect_manager")


# ─── Import from HubSpot ────────────────────────────────────

def import_from_hubspot(
    pillar_id: int | None = None,
    filters: dict | None = None,
    limit: int = 200,
) -> dict:
    """
    Import prospects from normalised HubSpot contacts table.

    Args:
        pillar_id: Assign all imported prospects to this pillar.
        filters: Optional filters (lifecycle_stage, lead_status, source, owner_id).
        limit: Max contacts to import.

    Returns:
        Summary dict with imported/skipped counts.
    """
    client = get_client()
    filters = filters or {}

    # Query HubSpot contacts
    query = client.table("contacts").select("*")
    if filters.get("lifecycle_stage"):
        query = query.eq("lifecycle_stage", filters["lifecycle_stage"])
    if filters.get("lead_status"):
        query = query.eq("lead_status", filters["lead_status"])
    if filters.get("source"):
        query = query.eq("source", filters["source"])
    if filters.get("owner_id"):
        query = query.eq("owner_id", filters["owner_id"])

    result = query.limit(limit).execute()
    contacts = result.data or []

    imported = 0
    skipped = 0

    for contact in contacts:
        hubspot_id = contact["id"]

        # Check if already imported
        existing = (
            client.table("outreach_prospects")
            .select("id")
            .eq("hubspot_contact_id", hubspot_id)
            .limit(1)
            .execute()
        )
        if existing.data:
            skipped += 1
            continue

        # Build prospect row
        row = {
            "first_name": contact.get("first_name"),
            "last_name": contact.get("last_name"),
            "email": contact.get("email"),
            "phone": contact.get("phone"),
            "company_name": contact.get("company"),
            "job_title": None,
            "industry": None,
            "hubspot_contact_id": hubspot_id,
            "source": "hubspot",
            "status": "new",
        }
        if pillar_id:
            row["pillar_id"] = pillar_id

        # Try to get company details
        _enrich_from_company(client, contact, row)

        client.table("outreach_prospects").insert(row).execute()
        imported += 1

    logger.info(
        "HubSpot import: %d imported, %d skipped (already exist)",
        imported, skipped,
    )
    return {"source": "hubspot", "imported": imported, "skipped": skipped}


def _enrich_from_company(client, contact: dict, row: dict) -> None:
    """Try to enrich prospect with company data from associations."""
    try:
        assoc = (
            client.table("associations")
            .select("to_id")
            .eq("from_type", "contact")
            .eq("from_id", contact["id"])
            .eq("to_type", "company")
            .limit(1)
            .execute()
        )
        if assoc.data:
            company = (
                client.table("companies")
                .select("domain, industry, num_employees")
                .eq("id", assoc.data[0]["to_id"])
                .limit(1)
                .execute()
            )
            if company.data:
                c = company.data[0]
                row["company_domain"] = c.get("domain")
                row["industry"] = c.get("industry")
                emp = c.get("num_employees")
                if emp:
                    row["company_size"] = _employee_range(emp)
    except Exception as e:
        logger.debug("Company enrichment failed for contact %s: %s", contact["id"], e)


def _employee_range(count: int) -> str:
    """Convert employee count to range string."""
    if count < 10:
        return "1-10"
    elif count < 50:
        return "10-50"
    elif count < 200:
        return "50-200"
    elif count < 500:
        return "200-500"
    elif count < 1000:
        return "500-1000"
    else:
        return "1000+"


# ─── Import from LinkedIn ───────────────────────────────────

def import_from_linkedin(
    pillar_id: int | None = None,
    limit: int = 200,
) -> dict:
    """
    Import prospects from cached LinkedIn contacts.

    Args:
        pillar_id: Assign all imported prospects to this pillar.
        limit: Max contacts to import.

    Returns:
        Summary dict with imported/skipped counts.
    """
    client = get_client()

    result = (
        client.table("linkedin_contacts")
        .select("*")
        .is_("prospect_id", "null")
        .limit(limit)
        .execute()
    )
    contacts = result.data or []

    imported = 0
    skipped = 0

    for contact in contacts:
        linkedin_id = contact["id"]

        # Check if already imported by LinkedIn ID
        existing = (
            client.table("outreach_prospects")
            .select("id")
            .eq("linkedin_id", linkedin_id)
            .limit(1)
            .execute()
        )
        if existing.data:
            # Link the existing prospect
            client.table("linkedin_contacts").update(
                {"prospect_id": existing.data[0]["id"]}
            ).eq("id", linkedin_id).execute()
            skipped += 1
            continue

        row = {
            "first_name": contact.get("first_name"),
            "last_name": contact.get("last_name"),
            "linkedin_url": contact.get("profile_url"),
            "linkedin_id": linkedin_id,
            "linkedin_contact_id": linkedin_id,
            "company_name": contact.get("company"),
            "job_title": contact.get("headline"),
            "industry": contact.get("industry"),
            "source": "linkedin",
            "status": "new",
        }
        if pillar_id:
            row["pillar_id"] = pillar_id

        insert_result = client.table("outreach_prospects").insert(row).execute()
        if insert_result.data:
            prospect_id = insert_result.data[0]["id"]
            # Link back to linkedin_contacts
            client.table("linkedin_contacts").update(
                {"prospect_id": prospect_id}
            ).eq("id", linkedin_id).execute()

        imported += 1

    logger.info(
        "LinkedIn import: %d imported, %d skipped",
        imported, skipped,
    )
    return {"source": "linkedin", "imported": imported, "skipped": skipped}


# ─── Import from CSV ────────────────────────────────────────

def import_from_csv(
    csv_content: str,
    pillar_id: int | None = None,
) -> dict:
    """
    Import prospects from CSV string.

    Expected columns (flexible, case-insensitive):
        first_name, last_name, email, linkedin_url, company_name,
        job_title, industry, phone, company_size

    Args:
        csv_content: Raw CSV string.
        pillar_id: Assign all imports to this pillar.

    Returns:
        Summary dict with imported/error counts.
    """
    client = get_client()
    reader = csv.DictReader(io.StringIO(csv_content))

    # Normalise column names
    imported = 0
    errors = 0

    for row_data in reader:
        normalised = {k.lower().strip().replace(" ", "_"): v.strip() for k, v in row_data.items() if v}

        prospect_row = {
            "first_name": normalised.get("first_name"),
            "last_name": normalised.get("last_name"),
            "email": normalised.get("email"),
            "linkedin_url": normalised.get("linkedin_url") or normalised.get("linkedin"),
            "phone": normalised.get("phone"),
            "company_name": normalised.get("company_name") or normalised.get("company"),
            "company_domain": normalised.get("company_domain") or normalised.get("domain"),
            "company_size": normalised.get("company_size"),
            "industry": normalised.get("industry"),
            "job_title": normalised.get("job_title") or normalised.get("title"),
            "source": "csv",
            "status": "new",
        }
        if pillar_id:
            prospect_row["pillar_id"] = pillar_id

        # Deduplicate on email or LinkedIn URL
        if prospect_row.get("email"):
            existing = (
                client.table("outreach_prospects")
                .select("id")
                .eq("email", prospect_row["email"])
                .limit(1)
                .execute()
            )
            if existing.data:
                errors += 1  # duplicate
                continue

        try:
            client.table("outreach_prospects").insert(prospect_row).execute()
            imported += 1
        except Exception as e:
            logger.warning("CSV row import failed: %s", e)
            errors += 1

    logger.info("CSV import: %d imported, %d errors/duplicates", imported, errors)
    return {"source": "csv", "imported": imported, "errors": errors}


# ─── Pillar Assignment ──────────────────────────────────────

def assign_pillar(prospect_ids: list[int], pillar_id: int) -> dict:
    """
    Assign or reassign prospects to a pillar.

    Returns:
        Summary dict with updated count.
    """
    client = get_client()
    now = datetime.now(timezone.utc).isoformat()

    updated = 0
    for pid in prospect_ids:
        try:
            client.table("outreach_prospects").update({
                "pillar_id": pillar_id,
                "updated_at": now,
            }).eq("id", pid).execute()
            updated += 1
        except Exception as e:
            logger.warning("Failed to assign pillar to prospect %d: %s", pid, e)

    logger.info("Pillar assignment: %d prospects -> pillar %d", updated, pillar_id)
    return {"updated": updated, "pillar_id": pillar_id}


# ─── Create Single Prospect ─────────────────────────────────

def create_prospect(data: dict) -> dict:
    """
    Create a single prospect manually.

    Args:
        data: Prospect fields dict.

    Returns:
        The created prospect row.
    """
    client = get_client()
    data.setdefault("source", "manual")
    data.setdefault("status", "new")

    result = client.table("outreach_prospects").insert(data).execute()
    if not result.data:
        raise RuntimeError("Failed to create prospect")
    logger.info("Created prospect: %s %s", data.get("first_name"), data.get("last_name"))
    return result.data[0]
