"""
Google Sheets Analyzer
========================

Reads raw Google Sheets JSON exports from data/raw/ and produces metrics
based on detected sheet types (CRM, financial, generic).

Sheet type detection:
  - CRM sheets: columns matching name, email, company, phone, etc.
  - Financial sheets: numeric columns with currency/amount/revenue keywords
  - Generic: summary statistics for any tabular data

Extensible design: add new SheetTypeAnalyzer subclasses to handle additional
sheet types (inventory, project tracking, etc.).

Outputs to data/processed/gsheets_metrics.json which is consumed by the
dashboard generator.

Usage:
    python scripts/gsheets_analyzer.py
"""

from __future__ import annotations

import glob
import json
import logging
import re
import sys
from abc import ABC, abstractmethod
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / "data" / "raw"
PROCESSED_DIR = BASE_DIR / "data" / "processed"

load_dotenv(BASE_DIR / ".env")

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _is_numeric(value: str) -> bool:
    """Check if a string value looks numeric (int, float, currency)."""
    if not value or not isinstance(value, str):
        return False
    cleaned = re.sub(r"[$,\s%]", "", value.strip())
    try:
        float(cleaned)
        return True
    except (ValueError, TypeError):
        return False


def _parse_numeric(value: str) -> Optional[float]:
    """Parse a string into a float, stripping currency symbols and commas."""
    if not value or not isinstance(value, str):
        return None
    cleaned = re.sub(r"[$,\s%]", "", value.strip())
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def _column_matches(header: str, keywords: List[str]) -> bool:
    """Check if a column header matches any of the keywords (case-insensitive)."""
    h = header.lower().strip()
    return any(kw in h for kw in keywords)


def _compute_numeric_stats(values: List[float]) -> dict:
    """Compute summary statistics for a list of numeric values."""
    if not values:
        return {}
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    return {
        "count": n,
        "min": round(min(sorted_vals), 2),
        "max": round(max(sorted_vals), 2),
        "sum": round(sum(sorted_vals), 2),
        "avg": round(sum(sorted_vals) / n, 2),
        "median": round(sorted_vals[n // 2], 2),
    }


# ---------------------------------------------------------------------------
# Sheet Type Detection
# ---------------------------------------------------------------------------

CRM_COLUMN_KEYWORDS = [
    "email", "e-mail", "phone", "telephone", "mobile",
    "company", "organisation", "organization", "firm",
    "first name", "last name", "full name", "contact",
    "address", "city", "state", "country", "zip", "postcode",
]

FINANCIAL_COLUMN_KEYWORDS = [
    "amount", "revenue", "cost", "price", "total", "budget",
    "profit", "loss", "margin", "expense", "income", "salary",
    "payment", "invoice", "balance", "fee", "rate", "value",
    "gbp", "usd", "eur", "currency",
]

INVENTORY_COLUMN_KEYWORDS = [
    "sku", "product", "quantity", "stock", "warehouse",
    "inventory", "item", "barcode", "unit",
]


def _detect_sheet_type(headers: List[str]) -> str:
    """Detect sheet type from column headers.

    Returns one of: 'crm', 'financial', 'inventory', 'generic'
    """
    if not headers:
        return "generic"

    headers_lower = [h.lower().strip() for h in headers]

    # CRM detection: needs at least 2 CRM-like columns
    crm_matches = sum(
        1 for h in headers_lower
        if any(kw in h for kw in CRM_COLUMN_KEYWORDS)
    )
    if crm_matches >= 2:
        return "crm"

    # Financial detection: at least 1 financial keyword column
    fin_matches = sum(
        1 for h in headers_lower
        if any(kw in h for kw in FINANCIAL_COLUMN_KEYWORDS)
    )
    if fin_matches >= 1:
        return "financial"

    # Inventory detection
    inv_matches = sum(
        1 for h in headers_lower
        if any(kw in h for kw in INVENTORY_COLUMN_KEYWORDS)
    )
    if inv_matches >= 2:
        return "inventory"

    return "generic"


# ---------------------------------------------------------------------------
# Sheet Type Analyzers (extensible base class)
# ---------------------------------------------------------------------------

class SheetTypeAnalyzer(ABC):
    """Base class for sheet-type-specific analyzers.

    To add a new sheet type:
      1. Subclass SheetTypeAnalyzer
      2. Set `sheet_type` class attribute
      3. Implement `analyze_tab()`
      4. Register it in ANALYZER_REGISTRY
    """
    sheet_type: str = "generic"

    @abstractmethod
    def analyze_tab(self, tab: dict, sheet_name: str) -> dict:
        """Analyze a single tab and return metrics."""
        ...


class CRMAnalyzer(SheetTypeAnalyzer):
    """Analyzes CRM-like sheets: contact extraction, deduplication, metrics."""
    sheet_type = "crm"

    EMAIL_KEYWORDS = ["email", "e-mail"]
    NAME_KEYWORDS = ["name", "contact"]
    COMPANY_KEYWORDS = ["company", "organisation", "organization", "firm"]
    PHONE_KEYWORDS = ["phone", "telephone", "mobile", "tel"]

    def _find_column(self, headers: List[str], keywords: List[str]) -> Optional[str]:
        """Find the first header matching any keyword."""
        for h in headers:
            if _column_matches(h, keywords):
                return h
        return None

    def analyze_tab(self, tab: dict, sheet_name: str) -> dict:
        headers = tab.get("headers", [])
        rows = tab.get("rows", [])

        email_col = self._find_column(headers, self.EMAIL_KEYWORDS)
        name_col = self._find_column(headers, self.NAME_KEYWORDS)
        company_col = self._find_column(headers, self.COMPANY_KEYWORDS)
        phone_col = self._find_column(headers, self.PHONE_KEYWORDS)

        # Extract contacts
        contacts: List[dict] = []
        seen_emails: Dict[str, int] = {}
        duplicate_count = 0

        for row in rows:
            email = (row.get(email_col, "") or "").strip().lower() if email_col else ""
            name = (row.get(name_col, "") or "").strip() if name_col else ""
            company = (row.get(company_col, "") or "").strip() if company_col else ""
            phone = (row.get(phone_col, "") or "").strip() if phone_col else ""

            # Skip completely empty rows
            if not email and not name:
                continue

            # Deduplicate by email
            if email and email in seen_emails:
                duplicate_count += 1
                continue

            if email:
                seen_emails[email] = len(contacts)

            contacts.append({
                "email": email,
                "name": name,
                "company": company,
                "phone": phone,
            })

        # Domain distribution
        domain_counts: Counter = Counter()
        for c in contacts:
            if c["email"] and "@" in c["email"]:
                domain = c["email"].split("@")[1]
                domain_counts[domain] += 1

        # Company distribution
        company_counts: Counter = Counter()
        for c in contacts:
            if c["company"]:
                company_counts[c["company"]] += 1

        # Completeness metrics
        has_email = sum(1 for c in contacts if c["email"])
        has_phone = sum(1 for c in contacts if c["phone"])
        has_company = sum(1 for c in contacts if c["company"])
        total = len(contacts) or 1  # avoid division by zero

        return {
            "type": "crm",
            "tab_name": tab.get("tab_name", ""),
            "sheet_name": sheet_name,
            "total_contacts": len(contacts),
            "duplicates_removed": duplicate_count,
            "completeness": {
                "email": round(has_email / total * 100, 1),
                "phone": round(has_phone / total * 100, 1),
                "company": round(has_company / total * 100, 1),
            },
            "top_domains": dict(domain_counts.most_common(20)),
            "top_companies": dict(company_counts.most_common(20)),
            "contacts": contacts,
            "columns_detected": {
                "email": email_col,
                "name": name_col,
                "company": company_col,
                "phone": phone_col,
            },
        }


class FinancialAnalyzer(SheetTypeAnalyzer):
    """Analyzes financial sheets: detect numeric columns, produce summary stats."""
    sheet_type = "financial"

    def analyze_tab(self, tab: dict, sheet_name: str) -> dict:
        headers = tab.get("headers", [])
        rows = tab.get("rows", [])

        # Identify numeric columns by checking first N rows
        sample_size = min(20, len(rows))
        numeric_columns: List[str] = []
        for h in headers:
            numeric_count = 0
            for row in rows[:sample_size]:
                val = row.get(h, "")
                if _is_numeric(str(val)):
                    numeric_count += 1
            # Column is numeric if >50% of sample values are numeric
            if sample_size > 0 and numeric_count / sample_size > 0.5:
                numeric_columns.append(h)

        # Compute stats per numeric column
        column_stats: Dict[str, dict] = {}
        for col in numeric_columns:
            values = []
            for row in rows:
                parsed = _parse_numeric(str(row.get(col, "")))
                if parsed is not None:
                    values.append(parsed)
            if values:
                column_stats[col] = _compute_numeric_stats(values)

        # Identify category/group columns for breakdown
        non_numeric_cols = [h for h in headers if h not in numeric_columns]
        category_breakdowns: Dict[str, Dict[str, dict]] = {}

        # Use the first non-numeric column as a category for breakdowns
        if non_numeric_cols and numeric_columns:
            cat_col = non_numeric_cols[0]
            for num_col in numeric_columns[:3]:  # limit to first 3 numeric cols
                groups: Dict[str, List[float]] = defaultdict(list)
                for row in rows:
                    cat_val = str(row.get(cat_col, "")).strip()
                    num_val = _parse_numeric(str(row.get(num_col, "")))
                    if cat_val and num_val is not None:
                        groups[cat_val].append(num_val)

                breakdown = {}
                for group_name, vals in sorted(
                    groups.items(), key=lambda x: sum(x[1]), reverse=True
                )[:20]:
                    breakdown[group_name] = _compute_numeric_stats(vals)

                if breakdown:
                    category_breakdowns[f"{cat_col} -> {num_col}"] = breakdown

        # Overall totals
        grand_total = 0.0
        for col, stats in column_stats.items():
            if _column_matches(col, FINANCIAL_COLUMN_KEYWORDS):
                grand_total += stats.get("sum", 0)

        return {
            "type": "financial",
            "tab_name": tab.get("tab_name", ""),
            "sheet_name": sheet_name,
            "row_count": len(rows),
            "numeric_columns": numeric_columns,
            "column_stats": column_stats,
            "category_breakdowns": category_breakdowns,
            "grand_total": round(grand_total, 2),
        }


class GenericAnalyzer(SheetTypeAnalyzer):
    """Fallback analyzer for sheets that don't match CRM or financial patterns."""
    sheet_type = "generic"

    def analyze_tab(self, tab: dict, sheet_name: str) -> dict:
        headers = tab.get("headers", [])
        rows = tab.get("rows", [])

        # Basic stats per column
        column_info: List[dict] = []
        for h in headers:
            values = [str(row.get(h, "")).strip() for row in rows]
            non_empty = [v for v in values if v]
            unique = set(non_empty)
            numeric_vals = [_parse_numeric(v) for v in non_empty]
            numeric_vals = [v for v in numeric_vals if v is not None]

            info: Dict[str, Any] = {
                "column": h,
                "non_empty": len(non_empty),
                "fill_rate": round(len(non_empty) / max(len(rows), 1) * 100, 1),
                "unique_values": len(unique),
            }

            if numeric_vals:
                info["numeric_stats"] = _compute_numeric_stats(numeric_vals)

            # Top values (for non-numeric categorical columns)
            if len(unique) <= 50 and not numeric_vals:
                value_counts = Counter(non_empty)
                info["top_values"] = dict(value_counts.most_common(10))

            column_info.append(info)

        return {
            "type": "generic",
            "tab_name": tab.get("tab_name", ""),
            "sheet_name": sheet_name,
            "row_count": len(rows),
            "column_count": len(headers),
            "columns": column_info,
        }


# Analyzer registry — add new analyzers here
ANALYZER_REGISTRY: Dict[str, SheetTypeAnalyzer] = {
    "crm": CRMAnalyzer(),
    "financial": FinancialAnalyzer(),
    "inventory": GenericAnalyzer(),  # placeholder — extend with InventoryAnalyzer
    "generic": GenericAnalyzer(),
}


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

def _load_raw_gsheets() -> List[dict]:
    """Load all raw gsheets JSON files, returning the most recent per sheet_id."""
    pattern = str(RAW_DIR / "gsheets_*.json")
    files = sorted(glob.glob(pattern), reverse=True)
    if not files:
        logger.warning("No raw gsheets files found in %s", RAW_DIR)
        return []

    # Deduplicate: keep most recent file per sheet_id
    seen_ids: set = set()
    sheets: List[dict] = []
    for fpath in files:
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            sheet_id = data.get("sheet_id", "")
            if sheet_id and sheet_id not in seen_ids:
                seen_ids.add(sheet_id)
                sheets.append(data)
                logger.info(f"Loaded {fpath} (sheet: {data.get('sheet_name', sheet_id)})")
        except Exception as e:
            logger.warning(f"Failed to load {fpath}: {e}")

    logger.info(f"Loaded {len(sheets)} unique sheets from raw files")
    return sheets


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def run_gsheets_analysis() -> dict:
    """Main analysis pipeline: load raw data, detect types, run analyzers."""
    logger.info("=== Google Sheets Analysis Starting ===")

    raw_sheets = _load_raw_gsheets()
    if not raw_sheets:
        logger.warning("No sheets to analyze")
        return {"generated_at": _now_utc().isoformat(), "sheets": []}

    # Aggregate metrics
    all_sheet_results: List[dict] = []
    type_counts: Counter = Counter()
    total_rows = 0
    total_tabs = 0
    all_crm_contacts: List[dict] = []
    all_crm_emails: set = set()

    for sheet_data in raw_sheets:
        sheet_id = sheet_data.get("sheet_id", "")
        sheet_name = sheet_data.get("sheet_name", "")
        tabs = sheet_data.get("tabs", [])

        sheet_result = {
            "sheet_id": sheet_id,
            "sheet_name": sheet_name,
            "captured_at": sheet_data.get("captured_at"),
            "tab_count": len(tabs),
            "tab_results": [],
        }

        for tab in tabs:
            headers = tab.get("headers", [])
            rows = tab.get("rows", [])
            row_count = tab.get("row_count", len(rows))
            total_rows += row_count
            total_tabs += 1

            # Detect sheet type
            sheet_type = _detect_sheet_type(headers)
            type_counts[sheet_type] += 1

            # Run appropriate analyzer
            analyzer = ANALYZER_REGISTRY.get(sheet_type, ANALYZER_REGISTRY["generic"])
            tab_metrics = analyzer.analyze_tab(tab, sheet_name)

            sheet_result["tab_results"].append(tab_metrics)

            # Collect CRM contacts for cross-sheet deduplication
            if sheet_type == "crm":
                for contact in tab_metrics.get("contacts", []):
                    email = contact.get("email", "")
                    if email and email not in all_crm_emails:
                        all_crm_emails.add(email)
                        all_crm_contacts.append(contact)

        all_sheet_results.append(sheet_result)

    # Cross-sheet CRM summary
    crm_summary = {}
    if all_crm_contacts:
        domain_counts: Counter = Counter()
        company_counts: Counter = Counter()
        for c in all_crm_contacts:
            if c.get("email") and "@" in c["email"]:
                domain_counts[c["email"].split("@")[1]] += 1
            if c.get("company"):
                company_counts[c["company"]] += 1

        crm_summary = {
            "total_unique_contacts": len(all_crm_contacts),
            "with_email": sum(1 for c in all_crm_contacts if c.get("email")),
            "with_phone": sum(1 for c in all_crm_contacts if c.get("phone")),
            "with_company": sum(1 for c in all_crm_contacts if c.get("company")),
            "top_domains": dict(domain_counts.most_common(20)),
            "top_companies": dict(company_counts.most_common(20)),
            "contacts": all_crm_contacts,
        }

    output = {
        "generated_at": _now_utc().isoformat(),
        "data_source": "google_sheets",
        "overview": {
            "total_sheets": len(raw_sheets),
            "total_tabs": total_tabs,
            "total_rows": total_rows,
            "type_distribution": dict(type_counts),
        },
        "crm_summary": crm_summary,
        "sheets": all_sheet_results,
    }

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    output_path = PROCESSED_DIR / "gsheets_metrics.json"
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(output, fh, indent=2, default=str)

    logger.info("Google Sheets analysis complete. Output saved to %s", output_path)
    return output


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    results = run_gsheets_analysis()
    ov = results.get("overview", {})
    crm = results.get("crm_summary", {})
    print(f"\nAnalysis complete.")
    print(f"  Sheets: {ov.get('total_sheets', 0)}")
    print(f"  Tabs: {ov.get('total_tabs', 0)}")
    print(f"  Total rows: {ov.get('total_rows', 0)}")
    print(f"  Type distribution: {ov.get('type_distribution', {})}")
    if crm:
        print(f"  CRM contacts (deduplicated): {crm.get('total_unique_contacts', 0)}")
    print(f"Output: {PROCESSED_DIR / 'gsheets_metrics.json'}")
