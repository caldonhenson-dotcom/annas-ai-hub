"""
NDA Automation Workflow
=======================
AI-driven workflow for reading, reviewing, and managing incoming NDAs.

Modules:
    NDAParser           - Extract structured data from PDF/DOCX NDA documents
    NDAReviewer         - Check NDA clauses against configurable review parameters
    NDAEmailHandler     - Watch Gmail inbox for NDAs, send templated responses
    NDAWorkflowOrchestrator - Tie everything together with CLI interface

Usage:
    # Continuous inbox polling
    python scripts/nda_workflow.py --watch

    # One-off file review
    python scripts/nda_workflow.py --process-file path/to/nda.pdf

    # Process a specific file and email the result
    python scripts/nda_workflow.py --process-file path/to/nda.pdf --notify user@example.com
"""

from __future__ import annotations

import argparse
import email
import imaplib
import json
import logging
import os
import re
import smtplib
import sys
import tempfile
import time
from datetime import datetime, timezone
from email import policy
from email.message import EmailMessage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent          # Annas Ai Hub/
CONFIG_DIR = BASE_DIR / "config"
DEFAULT_CONFIG_PATH = CONFIG_DIR / "nda_parameters.json"

load_dotenv(BASE_DIR / ".env")

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("nda_workflow")


# ---------------------------------------------------------------------------
# Lazy imports for document parsing (fail gracefully if not installed)
# ---------------------------------------------------------------------------
def _import_pdfplumber():
    """Import pdfplumber with fallback to PyPDF2."""
    try:
        import pdfplumber
        return pdfplumber, "pdfplumber"
    except ImportError:
        pass
    try:
        import PyPDF2
        return PyPDF2, "PyPDF2"
    except ImportError:
        logger.error("Neither pdfplumber nor PyPDF2 is installed. PDF parsing unavailable.")
        return None, None


def _import_docx():
    """Import python-docx."""
    try:
        import docx
        return docx
    except ImportError:
        logger.error("python-docx is not installed. DOCX parsing unavailable.")
        return None


# ---------------------------------------------------------------------------
# Configuration loader
# ---------------------------------------------------------------------------
def load_nda_config(config_path: Optional[Path] = None) -> Dict[str, Any]:
    """Load NDA review parameters from JSON config file.

    Falls back to the default config at config/nda_parameters.json.
    """
    path = config_path or DEFAULT_CONFIG_PATH
    env_override = os.getenv("NDA_REVIEW_CONFIG")
    if env_override:
        override_path = Path(env_override)
        if not override_path.is_absolute():
            override_path = BASE_DIR / override_path
        if override_path.exists():
            path = override_path

    if not path.exists():
        logger.warning("NDA config not found at %s; using built-in defaults", path)
        return _builtin_defaults()

    with open(path, "r", encoding="utf-8") as fh:
        config = json.load(fh)
    logger.info("Loaded NDA config from %s", path)
    return config


def _builtin_defaults() -> Dict[str, Any]:
    """Minimal built-in defaults if the JSON config is missing."""
    return {
        "review_parameters": {
            "term_length": {"max_years": 5, "flag_perpetual": True},
            "non_compete": {"flag_any": True},
            "ip_assignment": {"flag_beyond_confidential": True},
            "jurisdiction": {"accepted": ["England and Wales", "England & Wales"],
                             "flag_if_not_accepted": True},
            "nda_type": {"note_unilateral": True, "preferred": "mutual"},
            "remedies": {"flag_injunctive_without_court": True},
            "definition_scope": {
                "flag_overly_broad": True,
                "broad_indicators": ["all information", "any information",
                                     "any and all", "without limitation"],
            },
            "survival_clause": {"max_years_post_termination": 3},
        },
        "risk_thresholds": {
            "low": {"max_flags": 1},
            "medium": {"max_flags": 3},
            "high": {"min_flags": 4},
            "critical_flags": [
                "ip_assignment_beyond_scope", "perpetual_term",
                "non_compete_present", "injunctive_relief_no_court",
            ],
        },
        "nda_detection": {
            "filename_keywords": ["nda", "non-disclosure", "confidentiality"],
            "content_keywords": ["non-disclosure agreement",
                                 "confidentiality agreement",
                                 "confidential information",
                                 "disclosing party", "receiving party"],
            "min_keyword_matches": 2,
        },
        "email_templates": {
            "clean_subject": "NDA Review Complete - Ready for Signature",
            "flagged_subject": "NDA Review - Issues Flagged for Your Attention",
            "non_nda_subject": "Attachment Received - Not Identified as NDA",
            "sender_name": "Henson AI Assistant",
        },
        "polling": {
            "interval_seconds": 60,
            "inbox_folder": "INBOX",
        },
    }


# ============================================================================
# NDAParser
# ============================================================================

class NDAParser:
    """Extract structured data from NDA documents (PDF and DOCX).

    Returns a dict with all extracted clause fields:
        parties, effective_date, term_duration, confidential_info_definition,
        exclusions, permitted_disclosures, remedies, governing_law,
        jurisdiction, non_compete, non_solicit, ip_assignment,
        survival_clause, nda_type, raw_text
    """

    # Regex patterns for clause extraction
    _PATTERNS = {
        "parties": [
            re.compile(
                r"(?:between|by and between|entered into by)\s+"
                r"(.+?)(?:\s*\(.*?(?:disclosing|receiving|party)\s*\))"
                r"\s*and\s+(.+?)(?:\s*\(.*?(?:disclosing|receiving|party)\s*\))",
                re.IGNORECASE | re.DOTALL,
            ),
            re.compile(
                r"(?:between|by and between)\s+(.+?)\s+and\s+(.+?)(?:\.|,|\s+dated)",
                re.IGNORECASE,
            ),
            re.compile(
                r"parties?\s*:\s*(.+?)\s+and\s+(.+?)(?:\.|$)",
                re.IGNORECASE | re.MULTILINE,
            ),
        ],
        "effective_date": [
            re.compile(
                r"(?:effective\s+(?:as\s+of\s+)?(?:date|the)?\s*[:\-]?\s*)(\d{1,2}[\s/\-\.]\w+[\s/\-\.]\d{2,4})",
                re.IGNORECASE,
            ),
            re.compile(
                r"(?:dated|date)\s*[:\-]?\s*(\d{1,2}[\s/\-\.]\w+[\s/\-\.]\d{2,4})",
                re.IGNORECASE,
            ),
            re.compile(
                r"(?:this|the)\s+(?:\w+\s+)?day\s+of\s+(\w+[\s,]+\d{4})",
                re.IGNORECASE,
            ),
        ],
        "term_duration": [
            re.compile(
                r"(?:term|duration|period)\s*(?:of\s+(?:this\s+)?agreement)?\s*"
                r"[:\-]?\s*(?:shall\s+be\s+)?(\d+)\s*(year|month|day)s?",
                re.IGNORECASE,
            ),
            re.compile(
                r"(?:for\s+a\s+(?:period|term)\s+of\s+)(\d+)\s*(year|month|day)s?",
                re.IGNORECASE,
            ),
            re.compile(
                r"(?:remain\s+in\s+(?:effect|force)\s+for\s+)(\d+)\s*(year|month|day)s?",
                re.IGNORECASE,
            ),
        ],
        "perpetual": [
            re.compile(
                r"(?:perpetual|indefinite|no\s+(?:fixed\s+)?expir(?:y|ation)|"
                r"remain\s+in\s+(?:effect|force)\s+(?:indefinitely|in\s+perpetuity))",
                re.IGNORECASE,
            ),
        ],
        "governing_law": [
            re.compile(
                r"(?:govern(?:ed|ing)\s+(?:by\s+)?(?:the\s+)?law(?:s)?\s+of\s+)"
                r"(.+?)(?:\.|,|\s+and\s|\s+without)",
                re.IGNORECASE,
            ),
            re.compile(
                r"(?:applicable\s+law|choice\s+of\s+law|governing\s+law)\s*"
                r"[:\-]?\s*(.+?)(?:\.|$)",
                re.IGNORECASE | re.MULTILINE,
            ),
        ],
        "jurisdiction": [
            re.compile(
                r"(?:(?:exclusive\s+)?jurisdiction\s+of\s+(?:the\s+)?(?:courts?\s+(?:of|in)\s+)?)"
                r"(.+?)(?:\.|,|$)",
                re.IGNORECASE | re.MULTILINE,
            ),
            re.compile(
                r"(?:submit\s+to\s+(?:the\s+)?(?:exclusive\s+)?jurisdiction\s+of\s+)"
                r"(.+?)(?:\.|,|$)",
                re.IGNORECASE | re.MULTILINE,
            ),
        ],
        "non_compete": [
            re.compile(
                r"(?:non[\s\-]?compet(?:e|ition|ing))\s*(?:clause|covenant|obligation|restriction)?",
                re.IGNORECASE,
            ),
            re.compile(
                r"(?:shall\s+not\s+(?:directly\s+or\s+indirectly\s+)?compet(?:e|ing))",
                re.IGNORECASE,
            ),
            re.compile(
                r"(?:refrain\s+from\s+compet(?:ing|ition))",
                re.IGNORECASE,
            ),
        ],
        "non_solicit": [
            re.compile(
                r"(?:non[\s\-]?solicit(?:ation|ing)?)\s*(?:clause|covenant|obligation|restriction)?",
                re.IGNORECASE,
            ),
            re.compile(
                r"(?:shall\s+not\s+(?:directly\s+or\s+indirectly\s+)?solicit)",
                re.IGNORECASE,
            ),
        ],
        "ip_assignment": [
            re.compile(
                r"(?:assign(?:s|ment)?\s+(?:of\s+)?(?:all\s+)?(?:intellectual\s+property|"
                r"ip|patent|copyright|trademark))",
                re.IGNORECASE,
            ),
            re.compile(
                r"(?:intellectual\s+property\s+(?:rights?\s+)?(?:shall\s+)?(?:vest|belong|be\s+(?:owned|assigned)))",
                re.IGNORECASE,
            ),
            re.compile(
                r"(?:hereby\s+assign(?:s)?\s+.*?(?:right|title|interest))",
                re.IGNORECASE,
            ),
        ],
        "injunctive_relief": [
            re.compile(
                r"(?:injunctive\s+relief|equitable\s+relief|specific\s+performance)",
                re.IGNORECASE,
            ),
            re.compile(
                r"(?:entitled\s+to\s+(?:seek\s+)?(?:injunctive|equitable)\s+relief\s+"
                r"without\s+(?:the\s+necessity\s+of\s+)?(?:posting\s+(?:a\s+)?bond|"
                r"proof\s+of\s+actual\s+damages|court\s+order))",
                re.IGNORECASE,
            ),
        ],
        "survival_clause": [
            re.compile(
                r"(?:surviv(?:e|al)\s+(?:the\s+)?(?:termination|expir(?:y|ation))\s+.*?"
                r"(?:for\s+(?:a\s+period\s+of\s+)?)?(\d+)\s*(year|month)s?)",
                re.IGNORECASE,
            ),
            re.compile(
                r"(?:obligations?\s+(?:shall\s+)?(?:survive|continue)\s+.*?"
                r"(\d+)\s*(year|month)s?\s+(?:after|following|from))",
                re.IGNORECASE,
            ),
        ],
        "confidential_info": [
            re.compile(
                r"(?:\"confidential\s+information\"\s+(?:means|shall\s+mean|includes?|refers?\s+to)\s+)"
                r"(.+?)(?:\.\s+[A-Z]|\.\s*$|\n\n)",
                re.IGNORECASE | re.DOTALL,
            ),
            re.compile(
                r"(?:confidential\s+information\s+(?:is\s+defined\s+as|means)\s+)"
                r"(.+?)(?:\.\s+[A-Z]|\.\s*$|\n\n)",
                re.IGNORECASE | re.DOTALL,
            ),
        ],
        "exclusions": [
            re.compile(
                r"(?:(?:the\s+)?(?:following\s+)?(?:shall\s+)?not\s+(?:be\s+)?(?:considered\s+)?"
                r"confidential\s+information|exclusions?\s+from\s+confidential(?:ity)?)\s*"
                r"[:\-]?\s*(.+?)(?:\n\n|\d+\.\s+[A-Z])",
                re.IGNORECASE | re.DOTALL,
            ),
        ],
        "permitted_disclosures": [
            re.compile(
                r"(?:permitted\s+disclosur(?:e|es)|(?:the\s+)?receiving\s+party\s+may\s+disclose)"
                r"\s*[:\-]?\s*(.+?)(?:\n\n|\d+\.\s+[A-Z])",
                re.IGNORECASE | re.DOTALL,
            ),
        ],
        "nda_type_mutual": [
            re.compile(
                r"(?:mutual\s+(?:non[\s\-]?disclosure|confidentiality)\s+agreement)",
                re.IGNORECASE,
            ),
            re.compile(
                r"(?:each\s+party\s+(?:may\s+)?disclos(?:e|ing).*?(?:to\s+the\s+other|"
                r"the\s+other\s+party))",
                re.IGNORECASE,
            ),
        ],
        "nda_type_unilateral": [
            re.compile(
                r"(?:(?:one[\s\-]?way|unilateral)\s+(?:non[\s\-]?disclosure|confidentiality)\s+agreement)",
                re.IGNORECASE,
            ),
            re.compile(
                r"(?:the\s+disclosing\s+party\s+(?:shall|will)\s+disclose\s+.*?"
                r"(?:the\s+receiving\s+party|recipient))",
                re.IGNORECASE,
            ),
        ],
    }

    def __init__(self):
        self._pdf_lib, self._pdf_lib_name = _import_pdfplumber()
        self._docx_lib = _import_docx()

    def parse(self, file_path: Path) -> Dict[str, Any]:
        """Parse an NDA document and return structured clause data.

        Args:
            file_path: Path to a PDF or DOCX file.

        Returns:
            Dict with extracted NDA fields.
        """
        file_path = Path(file_path)
        if not file_path.exists():
            logger.error("File not found: %s", file_path)
            return self._empty_result(str(file_path), error="File not found")

        suffix = file_path.suffix.lower()
        if suffix == ".pdf":
            raw_text = self._extract_pdf_text(file_path)
        elif suffix in (".docx", ".doc"):
            raw_text = self._extract_docx_text(file_path)
        else:
            logger.warning("Unsupported file format: %s", suffix)
            return self._empty_result(str(file_path), error=f"Unsupported format: {suffix}")

        if not raw_text or len(raw_text.strip()) < 50:
            logger.warning("Extracted text is too short or empty from %s", file_path)
            return self._empty_result(str(file_path), error="Could not extract meaningful text")

        logger.info("Extracted %d characters from %s", len(raw_text), file_path.name)
        return self._extract_clauses(raw_text, str(file_path))

    def _extract_pdf_text(self, file_path: Path) -> str:
        """Extract text from a PDF file."""
        if self._pdf_lib is None:
            return ""

        text_parts: List[str] = []
        try:
            if self._pdf_lib_name == "pdfplumber":
                with self._pdf_lib.open(str(file_path)) as pdf:
                    for page in pdf.pages:
                        page_text = page.extract_text()
                        if page_text:
                            text_parts.append(page_text)
            else:
                # PyPDF2 fallback
                with open(file_path, "rb") as fh:
                    reader = self._pdf_lib.PdfReader(fh)
                    for page in reader.pages:
                        page_text = page.extract_text()
                        if page_text:
                            text_parts.append(page_text)
        except Exception as exc:
            logger.error("PDF extraction failed for %s: %s", file_path.name, exc)
            return ""

        return "\n\n".join(text_parts)

    def _extract_docx_text(self, file_path: Path) -> str:
        """Extract text from a DOCX file."""
        if self._docx_lib is None:
            return ""

        try:
            doc = self._docx_lib.Document(str(file_path))
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            return "\n\n".join(paragraphs)
        except Exception as exc:
            logger.error("DOCX extraction failed for %s: %s", file_path.name, exc)
            return ""

    def _extract_clauses(self, text: str, source: str) -> Dict[str, Any]:
        """Run all regex patterns against the raw text to extract NDA clauses."""
        result: Dict[str, Any] = {
            "source_file": source,
            "parsed_at": datetime.now(timezone.utc).isoformat(),
            "raw_text": text,
            "parties": self._extract_parties(text),
            "effective_date": self._extract_first_match(text, "effective_date"),
            "term_duration": self._extract_term(text),
            "is_perpetual": self._has_match(text, "perpetual"),
            "confidential_info_definition": self._extract_first_group(text, "confidential_info"),
            "exclusions": self._extract_first_group(text, "exclusions"),
            "permitted_disclosures": self._extract_first_group(text, "permitted_disclosures"),
            "remedies": self._extract_remedies(text),
            "governing_law": self._extract_first_group(text, "governing_law"),
            "jurisdiction": self._extract_first_group(text, "jurisdiction"),
            "has_non_compete": self._has_match(text, "non_compete"),
            "has_non_solicit": self._has_match(text, "non_solicit"),
            "has_ip_assignment": self._has_match(text, "ip_assignment"),
            "ip_assignment_details": self._extract_ip_context(text),
            "survival_clause": self._extract_survival(text),
            "nda_type": self._determine_nda_type(text),
        }
        return result

    def _extract_parties(self, text: str) -> List[str]:
        """Extract party names from the NDA."""
        for pattern in self._PATTERNS["parties"]:
            match = pattern.search(text)
            if match:
                parties = [g.strip() for g in match.groups() if g and g.strip()]
                if parties:
                    return parties
        return []

    def _extract_first_match(self, text: str, pattern_key: str) -> Optional[str]:
        """Return the full first match for a pattern key."""
        for pattern in self._PATTERNS.get(pattern_key, []):
            match = pattern.search(text)
            if match:
                return match.group(1).strip() if match.lastindex else match.group(0).strip()
        return None

    def _extract_first_group(self, text: str, pattern_key: str) -> Optional[str]:
        """Return the first capture group for a pattern key."""
        for pattern in self._PATTERNS.get(pattern_key, []):
            match = pattern.search(text)
            if match and match.lastindex:
                value = match.group(1).strip()
                # Truncate overly long extractions to keep summaries manageable
                if len(value) > 1000:
                    value = value[:1000] + "..."
                return value
        return None

    def _has_match(self, text: str, pattern_key: str) -> bool:
        """Check if any pattern matches exist in the text."""
        for pattern in self._PATTERNS.get(pattern_key, []):
            if pattern.search(text):
                return True
        return False

    def _extract_term(self, text: str) -> Optional[Dict[str, Any]]:
        """Extract the term/duration clause."""
        for pattern in self._PATTERNS["term_duration"]:
            match = pattern.search(text)
            if match:
                value = int(match.group(1))
                unit = match.group(2).lower()
                years = value if unit.startswith("year") else (
                    value / 12.0 if unit.startswith("month") else value / 365.0
                )
                return {"value": value, "unit": unit, "years_equivalent": round(years, 2)}
        return None

    def _extract_remedies(self, text: str) -> Dict[str, Any]:
        """Extract remedies information."""
        has_injunctive = self._has_match(text, "injunctive_relief")
        # Check if injunctive relief is available without court order
        injunctive_no_court = False
        if has_injunctive:
            # Check for patterns that bypass court order requirements
            bypass_patterns = [
                re.compile(r"injunctive\s+relief\s+without\s+(?:the\s+necessity|"
                           r"need|requirement|posting)", re.IGNORECASE),
                re.compile(r"without\s+(?:the\s+)?(?:necessity\s+of\s+)?(?:proving|"
                           r"proof\s+of)\s+actual\s+damages", re.IGNORECASE),
                re.compile(r"entitled\s+to\s+(?:immediate\s+)?injunctive\s+relief",
                           re.IGNORECASE),
            ]
            for bp in bypass_patterns:
                if bp.search(text):
                    injunctive_no_court = True
                    break

        return {
            "has_injunctive_relief": has_injunctive,
            "injunctive_without_court_order": injunctive_no_court,
        }

    def _extract_ip_context(self, text: str) -> Optional[str]:
        """Extract context around IP assignment clauses."""
        for pattern in self._PATTERNS["ip_assignment"]:
            match = pattern.search(text)
            if match:
                start = max(0, match.start() - 100)
                end = min(len(text), match.end() + 200)
                return text[start:end].strip()
        return None

    def _extract_survival(self, text: str) -> Optional[Dict[str, Any]]:
        """Extract survival clause duration."""
        for pattern in self._PATTERNS["survival_clause"]:
            match = pattern.search(text)
            if match and match.lastindex and match.lastindex >= 2:
                value = int(match.group(1))
                unit = match.group(2).lower()
                years = value if unit.startswith("year") else value / 12.0
                return {"value": value, "unit": unit, "years_equivalent": round(years, 2)}
        return None

    def _determine_nda_type(self, text: str) -> str:
        """Determine whether the NDA is mutual or unilateral."""
        mutual_score = sum(
            1 for p in self._PATTERNS["nda_type_mutual"] if p.search(text)
        )
        unilateral_score = sum(
            1 for p in self._PATTERNS["nda_type_unilateral"] if p.search(text)
        )
        if mutual_score > unilateral_score:
            return "mutual"
        elif unilateral_score > mutual_score:
            return "unilateral"
        # Heuristic: if both "disclosing party" and "receiving party" appear
        # without mutual indicators, likely unilateral
        if re.search(r"disclosing\s+party", text, re.IGNORECASE) and \
           re.search(r"receiving\s+party", text, re.IGNORECASE):
            if not re.search(r"each\s+party", text, re.IGNORECASE):
                return "unilateral"
            return "mutual"
        return "undetermined"

    @staticmethod
    def _empty_result(source: str, error: str = "") -> Dict[str, Any]:
        """Return an empty result dict with error information."""
        return {
            "source_file": source,
            "parsed_at": datetime.now(timezone.utc).isoformat(),
            "raw_text": "",
            "error": error,
            "parties": [],
            "effective_date": None,
            "term_duration": None,
            "is_perpetual": False,
            "confidential_info_definition": None,
            "exclusions": None,
            "permitted_disclosures": None,
            "remedies": {"has_injunctive_relief": False,
                         "injunctive_without_court_order": False},
            "governing_law": None,
            "jurisdiction": None,
            "has_non_compete": False,
            "has_non_solicit": False,
            "has_ip_assignment": False,
            "ip_assignment_details": None,
            "survival_clause": None,
            "nda_type": "undetermined",
        }


# ============================================================================
# NDAReviewer
# ============================================================================

class NDAReviewer:
    """Check parsed NDA data against configurable review parameters.

    Returns:
        {
            "risk_level": "low" | "medium" | "high",
            "flags": [{"code": str, "severity": str, "message": str, "detail": str}],
            "summary": str,
            "recommended_actions": [str],
            "nda_type_note": str,
            "reviewed_at": str,
        }
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or load_nda_config()
        self._params = self.config.get("review_parameters", {})
        self._thresholds = self.config.get("risk_thresholds", {})

    def review(self, nda_data: Dict[str, Any]) -> Dict[str, Any]:
        """Review parsed NDA data and return risk assessment.

        Args:
            nda_data: Output from NDAParser.parse()

        Returns:
            Review result dict.
        """
        flags: List[Dict[str, str]] = []

        # Check for parse errors first
        if nda_data.get("error"):
            return {
                "risk_level": "high",
                "flags": [{"code": "parse_error", "severity": "critical",
                           "message": "Document could not be parsed",
                           "detail": nda_data["error"]}],
                "summary": f"Unable to review: {nda_data['error']}",
                "recommended_actions": ["Manually review the document",
                                        "Ensure the file is a valid PDF or DOCX"],
                "nda_type_note": "N/A",
                "reviewed_at": datetime.now(timezone.utc).isoformat(),
            }

        # --- Term length ---
        self._check_term_length(nda_data, flags)

        # --- Perpetual term ---
        self._check_perpetual(nda_data, flags)

        # --- Non-compete ---
        self._check_non_compete(nda_data, flags)

        # --- Non-solicitation ---
        self._check_non_solicit(nda_data, flags)

        # --- IP assignment ---
        self._check_ip_assignment(nda_data, flags)

        # --- Jurisdiction ---
        self._check_jurisdiction(nda_data, flags)

        # --- Remedies ---
        self._check_remedies(nda_data, flags)

        # --- Definition scope ---
        self._check_definition_scope(nda_data, flags)

        # --- Survival clause ---
        self._check_survival(nda_data, flags)

        # Determine risk level
        risk_level = self._compute_risk_level(flags)

        # NDA type note
        nda_type = nda_data.get("nda_type", "undetermined")
        nda_type_note = self._nda_type_note(nda_type)

        # Summary
        summary = self._build_summary(nda_data, flags, risk_level, nda_type)

        # Recommended actions
        recommended_actions = self._build_recommendations(flags, risk_level)

        return {
            "risk_level": risk_level,
            "flags": flags,
            "summary": summary,
            "recommended_actions": recommended_actions,
            "nda_type_note": nda_type_note,
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
        }

    def _check_term_length(self, data: Dict, flags: List[Dict]) -> None:
        params = self._params.get("term_length", {})
        max_years = params.get("max_years", 5)
        term = data.get("term_duration")
        if term and term.get("years_equivalent", 0) > max_years:
            flags.append({
                "code": "excessive_term",
                "severity": "medium",
                "message": f"Term length exceeds {max_years} years",
                "detail": (f"NDA term is {term['value']} {term['unit']}(s) "
                           f"({term['years_equivalent']} years equivalent)"),
            })

    def _check_perpetual(self, data: Dict, flags: List[Dict]) -> None:
        params = self._params.get("term_length", {})
        if params.get("flag_perpetual", True) and data.get("is_perpetual"):
            flags.append({
                "code": "perpetual_term",
                "severity": "high",
                "message": "NDA has perpetual / indefinite term",
                "detail": "The agreement has no fixed expiration date. "
                          "Consider requesting a defined term with renewal options.",
            })

    def _check_non_compete(self, data: Dict, flags: List[Dict]) -> None:
        params = self._params.get("non_compete", {})
        if params.get("flag_any", True) and data.get("has_non_compete"):
            flags.append({
                "code": "non_compete_present",
                "severity": "high",
                "message": "Non-compete clause detected",
                "detail": "The NDA contains a non-compete restriction. "
                          "This goes beyond standard confidentiality obligations and "
                          "could restrict business operations.",
            })

    def _check_non_solicit(self, data: Dict, flags: List[Dict]) -> None:
        if data.get("has_non_solicit"):
            flags.append({
                "code": "non_solicit_present",
                "severity": "medium",
                "message": "Non-solicitation clause detected",
                "detail": "The NDA contains non-solicitation restrictions on employees "
                          "or clients. Review scope and duration carefully.",
            })

    def _check_ip_assignment(self, data: Dict, flags: List[Dict]) -> None:
        params = self._params.get("ip_assignment", {})
        if params.get("flag_beyond_confidential", True) and data.get("has_ip_assignment"):
            detail = "IP assignment clause detected."
            if data.get("ip_assignment_details"):
                detail += f" Context: ...{data['ip_assignment_details'][:200]}..."
            flags.append({
                "code": "ip_assignment_beyond_scope",
                "severity": "high",
                "message": "IP assignment clause extends beyond confidential information",
                "detail": detail,
            })

    def _check_jurisdiction(self, data: Dict, flags: List[Dict]) -> None:
        params = self._params.get("jurisdiction", {})
        if not params.get("flag_if_not_accepted", True):
            return
        accepted = [j.lower() for j in params.get("accepted", ["england and wales"])]
        governing_law = (data.get("governing_law") or "").lower().strip()
        jurisdiction = (data.get("jurisdiction") or "").lower().strip()

        # Check both governing law and jurisdiction fields
        law_ok = any(a in governing_law for a in accepted) if governing_law else False
        jur_ok = any(a in jurisdiction for a in accepted) if jurisdiction else False

        if governing_law and not law_ok:
            flags.append({
                "code": "jurisdiction_not_accepted",
                "severity": "medium",
                "message": "Governing law is not England & Wales",
                "detail": f"Governing law stated as: {data.get('governing_law')}. "
                          f"Preferred jurisdiction: England & Wales.",
            })
        elif jurisdiction and not jur_ok and not law_ok:
            flags.append({
                "code": "jurisdiction_not_accepted",
                "severity": "medium",
                "message": "Jurisdiction is not England & Wales",
                "detail": f"Jurisdiction stated as: {data.get('jurisdiction')}. "
                          f"Preferred jurisdiction: England & Wales.",
            })

    def _check_remedies(self, data: Dict, flags: List[Dict]) -> None:
        params = self._params.get("remedies", {})
        remedies = data.get("remedies", {})
        if params.get("flag_injunctive_without_court", True) and \
           remedies.get("injunctive_without_court_order"):
            flags.append({
                "code": "injunctive_relief_no_court",
                "severity": "high",
                "message": "Injunctive relief available without court order",
                "detail": "The NDA grants the right to injunctive relief without "
                          "requiring a court order or proof of actual damages. "
                          "This is an unusually aggressive remedies clause.",
            })

    def _check_definition_scope(self, data: Dict, flags: List[Dict]) -> None:
        params = self._params.get("definition_scope", {})
        if not params.get("flag_overly_broad", True):
            return
        definition = (data.get("confidential_info_definition") or "").lower()
        if not definition:
            return
        indicators = params.get("broad_indicators", [
            "all information", "any information", "any and all", "without limitation",
        ])
        matches = sum(1 for ind in indicators if ind.lower() in definition)
        if matches >= 2:
            flags.append({
                "code": "overly_broad_definition",
                "severity": "medium",
                "message": "Confidential information definition is overly broad",
                "detail": f"The definition uses {matches} broad/catch-all terms. "
                          "Consider requesting a more narrowly scoped definition.",
            })

    def _check_survival(self, data: Dict, flags: List[Dict]) -> None:
        params = self._params.get("survival_clause", {})
        max_years = params.get("max_years_post_termination", 3)
        survival = data.get("survival_clause")
        if survival and survival.get("years_equivalent", 0) > max_years:
            flags.append({
                "code": "excessive_survival",
                "severity": "medium",
                "message": f"Survival clause exceeds {max_years} years post-termination",
                "detail": (f"Confidentiality obligations survive for "
                           f"{survival['value']} {survival['unit']}(s) after termination "
                           f"({survival['years_equivalent']} years). "
                           f"Standard is up to {max_years} years."),
            })

    def _compute_risk_level(self, flags: List[Dict]) -> str:
        """Compute overall risk level from flags."""
        critical_codes = self._thresholds.get("critical_flags", [])
        has_critical = any(f["code"] in critical_codes for f in flags)
        high_severity_count = sum(1 for f in flags if f["severity"] == "high")
        total_flags = len(flags)

        if has_critical or high_severity_count >= 2:
            return "high"

        medium_max = self._thresholds.get("medium", {}).get("max_flags", 3)
        low_max = self._thresholds.get("low", {}).get("max_flags", 1)

        if total_flags > medium_max:
            return "high"
        elif total_flags > low_max:
            return "medium"
        return "low"

    def _nda_type_note(self, nda_type: str) -> str:
        """Generate a note about the NDA type."""
        params = self._params.get("nda_type", {})
        preferred = params.get("preferred", "mutual")
        if nda_type == "mutual":
            return "This is a mutual NDA - both parties have confidentiality obligations."
        elif nda_type == "unilateral":
            note = "This is a unilateral NDA - only one party has confidentiality obligations."
            if preferred == "mutual":
                note += " Consider requesting a mutual agreement for balanced protection."
            return note
        return "NDA type could not be determined. Verify whether obligations are mutual or one-way."

    def _build_summary(self, data: Dict, flags: List[Dict],
                       risk_level: str, nda_type: str) -> str:
        """Build a human-readable summary of the review."""
        parts = []

        # Headline
        risk_label = {"low": "Low Risk", "medium": "Medium Risk", "high": "High Risk"}
        parts.append(f"Risk Assessment: {risk_label.get(risk_level, risk_level.upper())}")
        parts.append(f"NDA Type: {nda_type.title()}")

        # Parties
        parties = data.get("parties", [])
        if parties:
            parts.append(f"Parties: {' and '.join(parties)}")

        # Key terms
        if data.get("effective_date"):
            parts.append(f"Effective Date: {data['effective_date']}")
        if data.get("term_duration"):
            t = data["term_duration"]
            parts.append(f"Term: {t['value']} {t['unit']}(s)")
        elif data.get("is_perpetual"):
            parts.append("Term: Perpetual")

        if data.get("governing_law"):
            parts.append(f"Governing Law: {data['governing_law']}")

        # Flags summary
        if flags:
            parts.append(f"\n{len(flags)} issue(s) flagged:")
            for f in flags:
                parts.append(f"  [{f['severity'].upper()}] {f['message']}")
        else:
            parts.append("\nNo issues flagged. NDA appears standard and acceptable.")

        return "\n".join(parts)

    def _build_recommendations(self, flags: List[Dict],
                               risk_level: str) -> List[str]:
        """Generate recommended actions based on flags."""
        actions: List[str] = []

        if risk_level == "low" and not flags:
            actions.append("NDA is within acceptable parameters - safe to proceed with signing.")
            return actions

        flag_actions = {
            "excessive_term": "Negotiate a shorter term (recommended: 2-3 years with renewal option).",
            "perpetual_term": "Request a defined term. Perpetual NDAs create indefinite obligations.",
            "non_compete_present": "Remove the non-compete clause or negotiate narrow scope and duration.",
            "non_solicit_present": "Review non-solicitation scope. Ensure it is limited and time-bound.",
            "ip_assignment_beyond_scope": "Remove IP assignment clause or limit to pre-existing IP only.",
            "jurisdiction_not_accepted": "Request England & Wales as governing jurisdiction.",
            "injunctive_relief_no_court": "Require that injunctive relief be sought through proper court proceedings.",
            "overly_broad_definition": "Request a more specific definition of confidential information.",
            "excessive_survival": "Negotiate survival period to 2-3 years post-termination.",
        }

        for f in flags:
            action = flag_actions.get(f["code"])
            if action:
                actions.append(action)

        if risk_level == "high":
            actions.append("STRONGLY RECOMMEND: Have a solicitor review this NDA before signing.")
        elif risk_level == "medium":
            actions.append("Consider having a solicitor review the flagged clauses.")

        return actions


# ============================================================================
# NDAEmailHandler
# ============================================================================

class NDAEmailHandler:
    """Handle email-based NDA workflow via Gmail IMAP/SMTP.

    Watches the inbox for incoming emails with PDF/DOCX attachments,
    determines whether they are likely NDAs, and sends templated responses.
    """

    SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".doc"}

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or load_nda_config()
        self.email_address = os.getenv("NDA_EMAIL_ADDRESS", "")
        self.email_password = os.getenv("NDA_EMAIL_PASSWORD", "")
        self.imap_server = os.getenv("NDA_IMAP_SERVER", "imap.gmail.com")
        self.smtp_server = os.getenv("NDA_SMTP_SERVER", "smtp.gmail.com")
        self._detection = self.config.get("nda_detection", {})
        self._templates = self.config.get("email_templates", {})
        self._polling = self.config.get("polling", {})

        if not self.email_address or not self.email_password:
            logger.warning(
                "NDA_EMAIL_ADDRESS or NDA_EMAIL_PASSWORD not set. "
                "Email features will be unavailable."
            )

    def connect_imap(self) -> Optional[imaplib.IMAP4_SSL]:
        """Establish an IMAP connection to Gmail."""
        if not self.email_address or not self.email_password:
            logger.error("Cannot connect IMAP: email credentials not configured")
            return None
        try:
            conn = imaplib.IMAP4_SSL(self.imap_server)
            conn.login(self.email_address, self.email_password)
            logger.info("IMAP connected to %s as %s", self.imap_server, self.email_address)
            return conn
        except imaplib.IMAP4.error as exc:
            logger.error("IMAP login failed: %s", exc)
            return None

    def fetch_unread_emails(self, conn: imaplib.IMAP4_SSL) -> List[Dict[str, Any]]:
        """Fetch unread emails from the inbox.

        Returns a list of dicts with keys: uid, subject, from, date, attachments.
        Each attachment dict has: filename, content_type, data (bytes).
        """
        folder = self._polling.get("inbox_folder", "INBOX")
        conn.select(folder)

        status, data = conn.search(None, "UNSEEN")
        if status != "OK" or not data[0]:
            logger.debug("No unread emails found")
            return []

        email_uids = data[0].split()
        logger.info("Found %d unread email(s)", len(email_uids))

        results: List[Dict[str, Any]] = []
        for uid in email_uids:
            status, msg_data = conn.fetch(uid, "(RFC822)")
            if status != "OK":
                continue

            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email, policy=policy.default)

            email_info: Dict[str, Any] = {
                "uid": uid.decode() if isinstance(uid, bytes) else str(uid),
                "subject": msg.get("Subject", ""),
                "from": msg.get("From", ""),
                "date": msg.get("Date", ""),
                "body": self._extract_body(msg),
                "attachments": [],
            }

            # Extract attachments
            for part in msg.walk():
                content_disposition = part.get_content_disposition()
                if content_disposition != "attachment":
                    continue
                filename = part.get_filename()
                if not filename:
                    continue
                suffix = Path(filename).suffix.lower()
                if suffix in self.SUPPORTED_EXTENSIONS:
                    email_info["attachments"].append({
                        "filename": filename,
                        "content_type": part.get_content_type(),
                        "data": part.get_payload(decode=True),
                    })

            results.append(email_info)

        return results

    def is_likely_nda(self, filename: str, text_content: str = "") -> bool:
        """Determine if an attachment is likely an NDA based on filename and content.

        Args:
            filename: The attachment filename.
            text_content: Extracted text content (if available).

        Returns:
            True if the attachment is likely an NDA.
        """
        filename_lower = filename.lower()
        filename_keywords = self._detection.get("filename_keywords", [])
        content_keywords = self._detection.get("content_keywords", [])
        min_matches = self._detection.get("min_keyword_matches", 2)

        # Filename check
        for kw in filename_keywords:
            if kw.lower() in filename_lower:
                logger.info("NDA detected by filename keyword '%s' in '%s'", kw, filename)
                return True

        # Content check
        if text_content:
            text_lower = text_content.lower()
            matches = sum(1 for kw in content_keywords if kw.lower() in text_lower)
            if matches >= min_matches:
                logger.info(
                    "NDA detected by content keywords (%d/%d matches) in '%s'",
                    matches, min_matches, filename,
                )
                return True

        return False

    def send_response(self, to_address: str, subject: str, html_body: str,
                      attachment_path: Optional[Path] = None) -> bool:
        """Send a response email via SMTP.

        Args:
            to_address: Recipient email address.
            subject: Email subject line.
            html_body: HTML email body.
            attachment_path: Optional file to attach.

        Returns:
            True if sent successfully.
        """
        if not self.email_address or not self.email_password:
            logger.error("Cannot send email: credentials not configured")
            return False

        msg = MIMEMultipart("mixed")
        sender_name = self._templates.get("sender_name", "Henson AI Assistant")
        msg["From"] = f"{sender_name} <{self.email_address}>"
        msg["To"] = to_address
        msg["Subject"] = subject

        # HTML body
        html_part = MIMEText(html_body, "html", "utf-8")
        msg.attach(html_part)

        # Optional attachment
        if attachment_path and attachment_path.exists():
            try:
                with open(attachment_path, "rb") as fh:
                    part = MIMEBase("application", "octet-stream")
                    part.set_payload(fh.read())
                encoders.encode_base64(part)
                part.add_header(
                    "Content-Disposition",
                    f"attachment; filename={attachment_path.name}",
                )
                msg.attach(part)
            except Exception as exc:
                logger.error("Failed to attach file %s: %s", attachment_path, exc)

        try:
            with smtplib.SMTP_SSL(self.smtp_server, 465) as server:
                server.login(self.email_address, self.email_password)
                server.send_message(msg)
            logger.info("Email sent to %s: %s", to_address, subject)
            return True
        except smtplib.SMTPException as exc:
            logger.error("Failed to send email to %s: %s", to_address, exc)
            return False

    def mark_as_read(self, conn: imaplib.IMAP4_SSL, uid: str) -> None:
        """Mark an email as read by setting the Seen flag."""
        try:
            conn.store(uid.encode() if isinstance(uid, str) else uid, "+FLAGS", "\\Seen")
            logger.debug("Marked email %s as read", uid)
        except Exception as exc:
            logger.warning("Failed to mark email %s as read: %s", uid, exc)

    @staticmethod
    def _extract_body(msg) -> str:
        """Extract the plain text body from an email message."""
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    payload = part.get_payload(decode=True)
                    if payload:
                        body = payload.decode("utf-8", errors="replace")
                        break
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                body = payload.decode("utf-8", errors="replace")
        return body


# ============================================================================
# NDAWorkflowOrchestrator
# ============================================================================

class NDAWorkflowOrchestrator:
    """Orchestrate the full NDA review workflow.

    Ties together NDAParser, NDAReviewer, and NDAEmailHandler to provide:
    - process_email(): Process an incoming email with NDA attachment
    - process_file(): One-off review of a local NDA file
    - generate_summary(): Create an HTML summary of the review
    - watch(): Continuous inbox polling mode
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or load_nda_config()
        self.parser = NDAParser()
        self.reviewer = NDAReviewer(self.config)
        self.email_handler = NDAEmailHandler(self.config)
        self._templates = self.config.get("email_templates", {})

    def process_file(self, file_path: Path) -> Dict[str, Any]:
        """Process a single NDA file and return the full result.

        Args:
            file_path: Path to a PDF or DOCX NDA file.

        Returns:
            Dict with keys: nda_data, review_result, summary_html.
        """
        file_path = Path(file_path)
        logger.info("Processing NDA file: %s", file_path)

        nda_data = self.parser.parse(file_path)
        review_result = self.reviewer.review(nda_data)
        summary_html = self.generate_summary(nda_data, review_result)

        result = {
            "file": str(file_path),
            "nda_data": {k: v for k, v in nda_data.items() if k != "raw_text"},
            "review_result": review_result,
            "summary_html": summary_html,
            "processed_at": datetime.now(timezone.utc).isoformat(),
        }

        logger.info(
            "NDA review complete: risk=%s, flags=%d",
            review_result["risk_level"],
            len(review_result["flags"]),
        )
        return result

    def process_email(self, email_info: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Process an incoming email, review any NDA attachments, and return results.

        Args:
            email_info: Dict from NDAEmailHandler.fetch_unread_emails()

        Returns:
            List of result dicts (one per attachment processed).
        """
        sender = email_info.get("from", "unknown")
        subject = email_info.get("subject", "")
        attachments = email_info.get("attachments", [])
        logger.info("Processing email from %s: '%s' (%d attachment(s))",
                     sender, subject, len(attachments))

        if not attachments:
            logger.info("No supported attachments in email from %s", sender)
            return []

        results: List[Dict[str, Any]] = []

        for attachment in attachments:
            filename = attachment["filename"]
            data = attachment["data"]

            # Write attachment to temp file for parsing
            suffix = Path(filename).suffix.lower()
            with tempfile.NamedTemporaryFile(
                suffix=suffix, delete=False, prefix="nda_"
            ) as tmp:
                tmp.write(data)
                tmp_path = Path(tmp.name)

            try:
                # Parse the document to get text for NDA detection
                nda_data = self.parser.parse(tmp_path)
                raw_text = nda_data.get("raw_text", "")

                # Check if it is actually an NDA
                if not self.email_handler.is_likely_nda(filename, raw_text):
                    logger.info("Attachment '%s' is not an NDA - skipping review", filename)
                    results.append({
                        "file": filename,
                        "is_nda": False,
                        "nda_data": None,
                        "review_result": None,
                        "summary_html": self._non_nda_html(filename),
                    })
                    continue

                # Review the NDA
                review_result = self.reviewer.review(nda_data)
                summary_html = self.generate_summary(nda_data, review_result)

                results.append({
                    "file": filename,
                    "is_nda": True,
                    "nda_data": {k: v for k, v in nda_data.items() if k != "raw_text"},
                    "review_result": review_result,
                    "summary_html": summary_html,
                })

                logger.info(
                    "Reviewed '%s': risk=%s, flags=%d",
                    filename, review_result["risk_level"], len(review_result["flags"]),
                )

            finally:
                # Clean up temp file
                try:
                    tmp_path.unlink()
                except OSError:
                    pass

        return results

    def send_review_email(self, to_address: str, results: List[Dict[str, Any]]) -> None:
        """Send review results back to the sender.

        Args:
            to_address: Recipient email address.
            results: List of result dicts from process_email().
        """
        for result in results:
            filename = result.get("file", "attachment")
            is_nda = result.get("is_nda", False)
            summary_html = result.get("summary_html", "")
            review = result.get("review_result")

            if not is_nda:
                subject = self._templates.get(
                    "non_nda_subject",
                    "Attachment Received - Not Identified as NDA",
                )
            elif review and review["risk_level"] == "low":
                subject = self._templates.get(
                    "clean_subject",
                    "NDA Review Complete - Ready for Signature",
                )
            else:
                subject = self._templates.get(
                    "flagged_subject",
                    "NDA Review - Issues Flagged for Your Attention",
                )

            subject = f"{subject} [{filename}]"
            self.email_handler.send_response(to_address, subject, summary_html)

    def watch(self) -> None:
        """Continuously poll the inbox for new NDA emails.

        Runs indefinitely, checking for unread emails at the configured interval.
        """
        interval = self._polling_interval()
        logger.info("Starting NDA inbox watcher (polling every %ds)", interval)

        while True:
            try:
                conn = self.email_handler.connect_imap()
                if conn is None:
                    logger.error("Failed to connect IMAP; retrying in %ds", interval)
                    time.sleep(interval)
                    continue

                try:
                    emails = self.email_handler.fetch_unread_emails(conn)
                    for email_info in emails:
                        sender = email_info.get("from", "")
                        uid = email_info.get("uid", "")

                        results = self.process_email(email_info)

                        # Extract sender email address for reply
                        reply_to = self._extract_email_address(sender)
                        if reply_to and results:
                            self.send_review_email(reply_to, results)

                        # Mark as processed
                        self.email_handler.mark_as_read(conn, uid)

                    if emails:
                        logger.info("Processed %d email(s) this cycle", len(emails))
                    else:
                        logger.debug("No new emails this cycle")

                finally:
                    try:
                        conn.logout()
                    except Exception:
                        pass

            except KeyboardInterrupt:
                logger.info("Watcher stopped by user")
                break
            except Exception as exc:
                logger.error("Watcher cycle error: %s", exc, exc_info=True)

            time.sleep(interval)

    def generate_summary(self, nda_data: Dict[str, Any],
                         review_result: Dict[str, Any]) -> str:
        """Generate an HTML email summary with eComplete branding.

        Uses inline CSS for email-safe rendering.

        Args:
            nda_data: Parsed NDA data from NDAParser.
            review_result: Review result from NDAReviewer.

        Returns:
            HTML string.
        """
        risk_level = review_result.get("risk_level", "unknown")
        flags = review_result.get("flags", [])
        summary_text = review_result.get("summary", "")
        actions = review_result.get("recommended_actions", [])
        nda_type_note = review_result.get("nda_type_note", "")

        # Risk level styling
        risk_colors = {
            "low": {"bg": "#d1fae5", "text": "#065f46", "label": "LOW RISK"},
            "medium": {"bg": "#fef3c7", "text": "#92400e", "label": "MEDIUM RISK"},
            "high": {"bg": "#fee2e2", "text": "#991b1b", "label": "HIGH RISK"},
        }
        risk_style = risk_colors.get(risk_level, risk_colors["high"])

        # Build key terms table rows
        key_terms_rows = self._build_key_terms_rows(nda_data)

        # Build flags HTML
        flags_html = self._build_flags_html(flags)

        # Build recommendations HTML
        actions_html = ""
        if actions:
            action_items = "".join(
                f'<li style="margin-bottom:8px;color:#242833;font-size:14px;">{_esc(a)}</li>'
                for a in actions
            )
            actions_html = f"""
            <div style="background:#f0fdfa;border-left:4px solid #3CB4AD;padding:16px 20px;
                        margin:20px 0;border-radius:0 8px 8px 0;">
                <h3 style="margin:0 0 12px 0;color:#3CB4AD;font-family:Arial,Helvetica,sans-serif;
                           font-size:16px;">Recommended Actions</h3>
                <ol style="margin:0;padding-left:20px;">{action_items}</ol>
            </div>
            """

        # NDA type note
        type_note_html = ""
        if nda_type_note:
            type_note_html = f"""
            <div style="background:#f3f4f6;padding:12px 16px;margin:16px 0;
                        border-radius:6px;font-size:13px;color:#4b5563;">
                {_esc(nda_type_note)}
            </div>
            """

        html = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
<body style="margin:0;padding:0;background-color:#f7f8fa;font-family:Arial,Helvetica,sans-serif;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
       style="background-color:#f7f8fa;">
<tr><td align="center" style="padding:24px 16px;">
<table role="presentation" width="640" cellpadding="0" cellspacing="0" border="0"
       style="max-width:640px;width:100%;">

    <!-- Header -->
    <tr><td style="background:#242833;padding:24px 32px;border-radius:12px 12px 0 0;">
        <table width="100%" cellpadding="0" cellspacing="0" border="0">
        <tr>
            <td style="color:#ffffff;font-size:22px;font-weight:700;
                       font-family:Arial,Helvetica,sans-serif;">
                NDA Review Report
            </td>
            <td align="right" style="color:#3CB4AD;font-size:13px;
                                     font-family:Arial,Helvetica,sans-serif;">
                Henson AI Assistant
            </td>
        </tr>
        </table>
    </td></tr>

    <!-- Risk Badge -->
    <tr><td style="background:#ffffff;padding:24px 32px 0 32px;">
        <table width="100%" cellpadding="0" cellspacing="0" border="0">
        <tr><td>
            <span style="display:inline-block;background:{risk_style['bg']};
                         color:{risk_style['text']};padding:8px 20px;
                         border-radius:20px;font-size:14px;font-weight:700;
                         letter-spacing:0.5px;">
                {risk_style['label']}
            </span>
            <span style="color:#6b7280;font-size:13px;margin-left:12px;">
                {len(flags)} issue(s) flagged
            </span>
        </td></tr>
        </table>
    </td></tr>

    {type_note_html.replace('<div', '<tr><td style="background:#ffffff;padding:0 32px;"><div').replace('</div>', '</div></td></tr>') if type_note_html else ''}

    <!-- Key Terms -->
    <tr><td style="background:#ffffff;padding:20px 32px;">
        <h3 style="margin:0 0 16px 0;color:#242833;font-family:Arial,Helvetica,sans-serif;
                   font-size:16px;border-bottom:2px solid #3CB4AD;padding-bottom:8px;">
            Key Terms
        </h3>
        <table width="100%" cellpadding="0" cellspacing="0" border="0"
               style="font-size:14px;color:#242833;">
            {key_terms_rows}
        </table>
    </td></tr>

    <!-- Flags -->
    {flags_html}

    <!-- Recommendations -->
    <tr><td style="background:#ffffff;padding:0 32px 20px 32px;">
        {actions_html}
    </td></tr>

    <!-- Footer -->
    <tr><td style="background:#242833;padding:20px 32px;border-radius:0 0 12px 12px;
                   text-align:center;">
        <p style="margin:0;color:#9ca3af;font-size:12px;
                  font-family:Arial,Helvetica,sans-serif;">
            Generated by Henson AI Assistant &bull;
            {datetime.now(timezone.utc).strftime('%d %B %Y at %H:%M UTC')}
        </p>
        <p style="margin:8px 0 0 0;color:#6b7280;font-size:11px;
                  font-family:Arial,Helvetica,sans-serif;">
            This is an automated review. It does not constitute legal advice.
            Always consult a qualified solicitor for binding legal decisions.
        </p>
    </td></tr>

</table>
</td></tr>
</table>
</body>
</html>"""

        return html

    def _build_key_terms_rows(self, nda_data: Dict[str, Any]) -> str:
        """Build HTML table rows for key NDA terms."""
        rows = []

        def _row(label: str, value: Any, is_alt: bool = False) -> str:
            bg = "#f9fafb" if is_alt else "#ffffff"
            display = _esc(str(value)) if value else '<span style="color:#9ca3af;">Not found</span>'
            return (
                f'<tr style="background:{bg};">'
                f'<td style="padding:10px 12px;font-weight:600;width:35%;'
                f'vertical-align:top;border-bottom:1px solid #f3f4f6;">{_esc(label)}</td>'
                f'<td style="padding:10px 12px;border-bottom:1px solid #f3f4f6;">{display}</td>'
                f'</tr>'
            )

        parties = nda_data.get("parties", [])
        rows.append(_row("Parties", " and ".join(parties) if parties else None, False))
        rows.append(_row("NDA Type", (nda_data.get("nda_type") or "").title(), True))
        rows.append(_row("Effective Date", nda_data.get("effective_date"), False))

        term = nda_data.get("term_duration")
        if term:
            term_str = f"{term['value']} {term['unit']}(s)"
        elif nda_data.get("is_perpetual"):
            term_str = "Perpetual"
        else:
            term_str = None
        rows.append(_row("Term / Duration", term_str, True))

        rows.append(_row("Governing Law", nda_data.get("governing_law"), False))
        rows.append(_row("Jurisdiction", nda_data.get("jurisdiction"), True))

        # Confidential info definition (truncated)
        ci_def = nda_data.get("confidential_info_definition")
        if ci_def and len(ci_def) > 200:
            ci_def = ci_def[:200] + "..."
        rows.append(_row("Confidential Info Definition", ci_def, False))

        rows.append(_row("Non-Compete Clause",
                         "Yes - PRESENT" if nda_data.get("has_non_compete") else "No",
                         True))
        rows.append(_row("Non-Solicitation Clause",
                         "Yes - PRESENT" if nda_data.get("has_non_solicit") else "No",
                         False))
        rows.append(_row("IP Assignment Clause",
                         "Yes - PRESENT" if nda_data.get("has_ip_assignment") else "No",
                         True))

        survival = nda_data.get("survival_clause")
        if survival:
            surv_str = f"{survival['value']} {survival['unit']}(s) post-termination"
        else:
            surv_str = None
        rows.append(_row("Survival Period", surv_str, False))

        remedies = nda_data.get("remedies", {})
        if remedies.get("injunctive_without_court_order"):
            rem_str = "Injunctive relief (without court order)"
        elif remedies.get("has_injunctive_relief"):
            rem_str = "Injunctive relief available"
        else:
            rem_str = "Standard"
        rows.append(_row("Remedies", rem_str, True))

        return "\n".join(rows)

    def _build_flags_html(self, flags: List[Dict[str, str]]) -> str:
        """Build HTML section for review flags."""
        if not flags:
            return """
            <tr><td style="background:#ffffff;padding:0 32px 20px 32px;">
                <div style="background:#d1fae5;border-left:4px solid #059669;
                            padding:16px 20px;border-radius:0 8px 8px 0;">
                    <p style="margin:0;color:#065f46;font-size:14px;font-weight:600;">
                        No issues detected. This NDA appears standard and within acceptable parameters.
                    </p>
                </div>
            </td></tr>
            """

        severity_styles = {
            "high": {"bg": "#fee2e2", "border": "#dc2626", "text": "#991b1b", "badge": "#dc2626"},
            "critical": {"bg": "#fee2e2", "border": "#dc2626", "text": "#991b1b", "badge": "#dc2626"},
            "medium": {"bg": "#fef3c7", "border": "#d97706", "text": "#92400e", "badge": "#d97706"},
            "low": {"bg": "#f3f4f6", "border": "#6b7280", "text": "#374151", "badge": "#6b7280"},
        }

        flag_items = []
        for f in flags:
            sev = f.get("severity", "medium")
            style = severity_styles.get(sev, severity_styles["medium"])
            flag_items.append(f"""
            <div style="background:{style['bg']};border-left:4px solid {style['border']};
                        padding:14px 18px;margin-bottom:12px;border-radius:0 8px 8px 0;">
                <table width="100%" cellpadding="0" cellspacing="0" border="0">
                <tr>
                    <td style="vertical-align:top;">
                        <span style="display:inline-block;background:{style['badge']};
                                     color:#ffffff;padding:2px 8px;border-radius:4px;
                                     font-size:11px;font-weight:700;text-transform:uppercase;">
                            {_esc(sev)}
                        </span>
                    </td>
                </tr>
                <tr>
                    <td style="padding-top:8px;">
                        <p style="margin:0;color:{style['text']};font-size:14px;font-weight:600;">
                            {_esc(f.get('message', ''))}
                        </p>
                        <p style="margin:6px 0 0 0;color:{style['text']};font-size:13px;opacity:0.85;">
                            {_esc(f.get('detail', ''))}
                        </p>
                    </td>
                </tr>
                </table>
            </div>
            """)

        return f"""
        <tr><td style="background:#ffffff;padding:0 32px 16px 32px;">
            <h3 style="margin:0 0 16px 0;color:#242833;font-family:Arial,Helvetica,sans-serif;
                       font-size:16px;border-bottom:2px solid #ef4444;padding-bottom:8px;">
                Issues Flagged ({len(flags)})
            </h3>
            {''.join(flag_items)}
        </td></tr>
        """

    def _non_nda_html(self, filename: str) -> str:
        """Generate HTML response for a non-NDA attachment."""
        return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background-color:#f7f8fa;font-family:Arial,Helvetica,sans-serif;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
       style="background-color:#f7f8fa;">
<tr><td align="center" style="padding:24px 16px;">
<table role="presentation" width="640" cellpadding="0" cellspacing="0" border="0"
       style="max-width:640px;width:100%;">
    <tr><td style="background:#242833;padding:24px 32px;border-radius:12px 12px 0 0;">
        <p style="margin:0;color:#ffffff;font-size:22px;font-weight:700;
                  font-family:Arial,Helvetica,sans-serif;">Attachment Received</p>
    </td></tr>
    <tr><td style="background:#ffffff;padding:32px;border-radius:0 0 12px 12px;">
        <p style="color:#242833;font-size:14px;">
            The attached file <strong>{_esc(filename)}</strong> was received but
            <strong>could not be identified as an NDA</strong>.
        </p>
        <p style="color:#6b7280;font-size:14px;">
            If this is an NDA, please ensure the filename contains a relevant keyword
            (e.g., "NDA", "Non-Disclosure", "Confidentiality") or forward the document
            with a note confirming it is an NDA for review.
        </p>
        <p style="margin:24px 0 0 0;color:#9ca3af;font-size:12px;">
            Generated by Henson AI Assistant &bull;
            {datetime.now(timezone.utc).strftime('%d %B %Y at %H:%M UTC')}
        </p>
    </td></tr>
</table>
</td></tr>
</table>
</body>
</html>"""

    def _polling_interval(self) -> int:
        """Get the polling interval in seconds."""
        polling = self.config.get("polling", {})
        return polling.get("interval_seconds", 60)

    @staticmethod
    def _extract_email_address(from_header: str) -> Optional[str]:
        """Extract the email address from a From header.

        Handles formats like: 'John Doe <john@example.com>' or 'john@example.com'
        """
        match = re.search(r"<([^>]+)>", from_header)
        if match:
            return match.group(1)
        match = re.search(r"[\w.\-+]+@[\w.\-]+\.\w+", from_header)
        if match:
            return match.group(0)
        return None


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _esc(text: Any) -> str:
    """HTML-escape a value; converts None to empty string."""
    if text is None:
        return ""
    import html as _html
    return _html.escape(str(text))


# ============================================================================
# CLI entry point
# ============================================================================

def main():
    """CLI interface for the NDA Automation Workflow."""
    parser = argparse.ArgumentParser(
        description="NDA Automation Workflow - AI-driven NDA review system",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Continuous inbox polling
  python scripts/nda_workflow.py --watch

  # Review a single NDA file
  python scripts/nda_workflow.py --process-file contracts/nda-acme.pdf

  # Review and email the result
  python scripts/nda_workflow.py --process-file contracts/nda.pdf --notify user@example.com

  # Review with custom config
  python scripts/nda_workflow.py --process-file nda.pdf --config config/custom_params.json
        """,
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Continuously poll inbox for NDA emails",
    )
    parser.add_argument(
        "--process-file",
        type=str,
        metavar="PATH",
        help="Process a single NDA file (PDF or DOCX)",
    )
    parser.add_argument(
        "--notify",
        type=str,
        metavar="EMAIL",
        help="Send review results to this email address (requires --process-file)",
    )
    parser.add_argument(
        "--config",
        type=str,
        metavar="PATH",
        help="Path to custom NDA parameters JSON config",
    )
    parser.add_argument(
        "--output-html",
        type=str,
        metavar="PATH",
        help="Save the HTML summary to a file (with --process-file)",
    )
    parser.add_argument(
        "--output-json",
        type=str,
        metavar="PATH",
        help="Save the full review result as JSON (with --process-file)",
    )

    args = parser.parse_args()

    # Load config
    config_path = Path(args.config) if args.config else None
    config = load_nda_config(config_path)
    orchestrator = NDAWorkflowOrchestrator(config)

    if args.watch and args.process_file:
        logger.error("Cannot use --watch and --process-file together")
        sys.exit(1)

    if not args.watch and not args.process_file:
        parser.print_help()
        sys.exit(0)

    if args.process_file:
        file_path = Path(args.process_file)
        if not file_path.exists():
            logger.error("File not found: %s", file_path)
            sys.exit(1)

        result = orchestrator.process_file(file_path)
        review = result["review_result"]

        # Print summary to console
        print("\n" + "=" * 70)
        print("NDA REVIEW REPORT")
        print("=" * 70)
        print(review["summary"])
        print("\nRecommended Actions:")
        for i, action in enumerate(review["recommended_actions"], 1):
            print(f"  {i}. {action}")
        print("=" * 70)

        # Save HTML output
        if args.output_html:
            html_path = Path(args.output_html)
            html_path.parent.mkdir(parents=True, exist_ok=True)
            with open(html_path, "w", encoding="utf-8") as fh:
                fh.write(result["summary_html"])
            logger.info("HTML summary saved to %s", html_path)

        # Save JSON output
        if args.output_json:
            json_path = Path(args.output_json)
            json_path.parent.mkdir(parents=True, exist_ok=True)
            with open(json_path, "w", encoding="utf-8") as fh:
                json.dump(result, fh, indent=2, default=str)
            logger.info("JSON result saved to %s", json_path)

        # Send email notification
        if args.notify:
            success = orchestrator.email_handler.send_response(
                args.notify,
                f"NDA Review: {file_path.name} [{review['risk_level'].upper()} RISK]",
                result["summary_html"],
            )
            if success:
                print(f"\nReview emailed to {args.notify}")
            else:
                print(f"\nFailed to email review to {args.notify}")

    elif args.watch:
        orchestrator.watch()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        logger.error("NDA workflow failed: %s", exc, exc_info=True)
        sys.exit(1)
