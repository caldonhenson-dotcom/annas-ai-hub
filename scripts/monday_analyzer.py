"""
Monday.com M&A & IC Score Analyzer
=====================================

Reads raw Monday.com JSON exports from data/raw/ and produces metrics focused
on M&A project progression and IC (Investment Committee) scorecard tracking.

Key design decisions:
  - "Subitems of..." boards are filtered out (child views, not real boards)
  - Boards are grouped by workspace for navigation
  - M&A identification focuses on the "M&A" / "M&A - DD" workspaces plus
    keyword matching on board names
  - IC scoring uses Gate 0-3 Score columns and Latest IC Score columns
    from the M&A Status boards
  - Items without a named owner are kept but flagged; the dashboard
    can filter them

Outputs to data/processed/monday_metrics.json which is consumed by the
dashboard generator.

Usage:
    python scripts/monday_analyzer.py
"""

from __future__ import annotations

import glob
import json
import logging
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
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


def _parse_dt(val: Any) -> Optional[datetime]:
    """Parse a date/datetime string into a timezone-aware datetime."""
    if not val:
        return None
    if isinstance(val, datetime):
        return val if val.tzinfo else val.replace(tzinfo=timezone.utc)
    s = str(val).strip()
    for fmt in (
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            dt = datetime.strptime(s[:26], fmt)
            return dt.replace(tzinfo=timezone.utc) if not dt.tzinfo else dt
        except (ValueError, IndexError):
            continue
    return None


def _date_key_day(dt: Optional[datetime]) -> Optional[str]:
    return dt.strftime("%Y-%m-%d") if dt else None


def _find_status_column(item: dict) -> Optional[str]:
    for cv in item.get("column_values", []):
        if cv.get("type") == "status":
            return cv.get("text") or None
    return None


def _find_numeric_column(item: dict, keywords: List[str]) -> Optional[float]:
    for cv in item.get("column_values", []):
        title = (cv.get("title") or "").lower()
        if any(kw in title for kw in keywords):
            text = cv.get("text", "")
            try:
                cleaned = re.sub(r"[^\d.\-]", "", str(text))
                return float(cleaned) if cleaned else None
            except (ValueError, TypeError):
                return None
    return None


def _find_date_column(item: dict, keywords: List[str]) -> Optional[datetime]:
    for cv in item.get("column_values", []):
        title = (cv.get("title") or "").lower()
        if any(kw in title for kw in keywords):
            return _parse_dt(cv.get("text"))
    return None


def _find_person_column(item: dict) -> Optional[str]:
    for cv in item.get("column_values", []):
        if cv.get("type") in ("people", "person"):
            text = cv.get("text") or None
            if text:
                return text
    return None


def _is_subitem_board(board_name: str) -> bool:
    """Detect child / sub-item boards that are just views of parent data."""
    return board_name.lower().startswith("subitems of ")


def _workspace_name(board: dict) -> str:
    """Extract workspace name from a board dict, defaulting to 'No Workspace'."""
    return (board.get("workspace") or {}).get("name", "") or "No Workspace"


def _workspace_id(board: dict) -> str:
    return str((board.get("workspace") or {}).get("id", ""))


def _filter_real_boards(boards: List[dict]) -> List[dict]:
    """Return only active, non-sub-item boards."""
    return [
        b for b in boards
        if b.get("state") == "active"
        and not _is_subitem_board(b.get("name", ""))
    ]


# ---------------------------------------------------------------------------
# M&A Project Analyzer
# ---------------------------------------------------------------------------

MA_WORKSPACE_KEYWORDS = ["m&a", "merger", "acquisition"]

MA_BOARD_KEYWORDS = [
    "m&a", "merger", "acquisition", "deal flow", "dealflow",
    "due diligence", "pipeline", "target", "investment",
    "status", "deal timetable", "task tracker", "budget",
]

MA_STAGES_ORDERED = [
    "identified", "initial review", "screening", "nda signed",
    "information requested", "due diligence", "loi submitted",
    "loi signed", "dd in progress", "ic review", "ic approved",
    "heads of terms", "negotiation", "contract", "closing",
    "completed", "closed", "passed", "rejected", "on hold",
]


def _is_ma_workspace(board: dict) -> bool:
    ws = _workspace_name(board).lower()
    return any(kw in ws for kw in MA_WORKSPACE_KEYWORDS)


def _is_ma_board(board: dict) -> bool:
    """A board is M&A if it's in an M&A workspace OR its name matches."""
    if _is_ma_workspace(board):
        return True
    name = (board.get("name") or "").lower()
    desc = (board.get("description") or "").lower()
    return any(kw in name or kw in desc for kw in MA_BOARD_KEYWORDS)


def _classify_stage(status_text: str) -> str:
    if not status_text:
        return "unknown"
    s = status_text.lower().strip()
    for stage in MA_STAGES_ORDERED:
        if stage in s or s in stage:
            return stage
    if any(x in s for x in ["pass", "reject", "dead", "lost"]):
        return "passed"
    if any(x in s for x in ["hold", "pause", "wait"]):
        return "on hold"
    if any(x in s for x in ["won", "complete", "close", "done"]):
        return "completed"
    if any(x in s for x in ["review", "assess", "evaluat"]):
        return "ic review"
    if any(x in s for x in ["diligence", "dd"]):
        return "due diligence"
    return s


def _is_active_stage(stage: str) -> bool:
    return stage not in (
        "passed", "rejected", "completed", "closed", "on hold", "unknown",
    )


class MandAAnalyzer:
    """Analyzes M&A deal/project boards for pipeline progression."""

    def analyze(self, boards: List[dict], board_items: dict) -> dict:
        real_boards = _filter_real_boards(boards)
        ma_boards = [b for b in real_boards if _is_ma_board(b)]

        projects: List[dict] = []
        stage_counts: Dict[str, int] = defaultdict(int)
        stage_values: Dict[str, float] = defaultdict(float)
        owner_deals: Dict[str, List[dict]] = defaultdict(list)
        timeline: List[dict] = []
        active_count = 0
        total_value = 0.0

        for board in ma_boards:
            bid = str(board.get("id", ""))
            board_name = board.get("name", "")
            ws = _workspace_name(board)
            board_data = board_items.get(bid, {})
            items = board_data.get("items", []) if isinstance(board_data, dict) else []

            for item in items:
                name = item.get("name", "")
                status = _find_status_column(item) or ""
                stage = _classify_stage(status)
                value = _find_numeric_column(
                    item, ["value", "amount", "revenue", "price",
                           "deal size", "valuation"]
                )
                owner = _find_person_column(item)
                created_dt = _parse_dt(item.get("created_at"))
                updated_dt = _parse_dt(item.get("updated_at"))
                close_date = _find_date_column(
                    item, ["close", "target date", "completion", "deadline"]
                )

                is_active = _is_active_stage(stage)
                if is_active:
                    active_count += 1

                deal_value = value or 0.0
                total_value += deal_value

                project = {
                    "id": item.get("id"),
                    "name": name,
                    "board": board_name,
                    "board_id": bid,
                    "workspace": ws,
                    "status": status,
                    "stage": stage,
                    "value": deal_value,
                    "owner": owner or "Unassigned",
                    "has_owner": owner is not None,
                    "created_at": created_dt.isoformat() if created_dt else None,
                    "updated_at": updated_dt.isoformat() if updated_dt else None,
                    "target_close": close_date.isoformat() if close_date else None,
                    "is_active": is_active,
                    "group": (item.get("group") or {}).get("title", ""),
                    "subitems_count": len(item.get("subitems") or []),
                    "subitems_complete": sum(
                        1 for si in (item.get("subitems") or [])
                        if (_find_status_column(si) or "").lower()
                        in ("done", "complete", "completed")
                    ),
                    "recent_updates": [
                        {
                            "body": u.get("body", "")[:200],
                            "created_at": u.get("created_at"),
                            "creator": (u.get("creator") or {}).get("name", ""),
                        }
                        for u in (item.get("updates") or [])[:3]
                    ],
                }
                projects.append(project)
                stage_counts[stage] += 1
                stage_values[stage] += deal_value

                if owner:
                    owner_deals[owner].append(project)

                if created_dt:
                    timeline.append({
                        "date": _date_key_day(created_dt),
                        "event": "created",
                        "project": name,
                        "stage": stage,
                    })

        # Avg days since last update for active items
        now = _now_utc()
        active_ages = []
        for p in projects:
            if p["is_active"] and p["updated_at"]:
                upd = _parse_dt(p["updated_at"])
                if upd:
                    active_ages.append((now - upd).days)
        avg_age = sum(active_ages) / len(active_ages) if active_ages else 0

        # Stale projects (no update in 14+ days)
        stale_projects = [
            p for p in projects
            if p["is_active"] and p["updated_at"]
            and (now - (_parse_dt(p["updated_at"]) or now)).days > 14
        ]

        # Funnel
        funnel_stages = [
            "identified", "initial review", "screening", "due diligence",
            "ic review", "ic approved", "negotiation", "closing", "completed",
        ]
        funnel = [
            {"stage": fs, "count": stage_counts.get(fs, 0),
             "value": stage_values.get(fs, 0)}
            for fs in funnel_stages
        ]

        # Owner summary (only real owners)
        owner_summary = []
        for owner, deals in sorted(
            owner_deals.items(), key=lambda x: len(x[1]), reverse=True
        ):
            active = sum(1 for d in deals if d["is_active"])
            total_val = sum(d["value"] for d in deals)
            owner_summary.append({
                "owner": owner,
                "total_deals": len(deals),
                "active_deals": active,
                "total_value": total_val,
            })

        return {
            "total_projects": len(projects),
            "active_projects": active_count,
            "total_value": total_value,
            "avg_days_since_update": round(avg_age, 1),
            "stage_distribution": dict(stage_counts),
            "stage_values": {k: round(v, 2) for k, v in stage_values.items()},
            "funnel": funnel,
            "owner_summary": owner_summary,
            "stale_projects": [
                {
                    "name": p["name"],
                    "days_stale": (now - (_parse_dt(p["updated_at"]) or now)).days,
                    "stage": p["stage"],
                }
                for p in stale_projects
            ],
            "projects": sorted(
                projects,
                key=lambda p: p.get("updated_at") or "",
                reverse=True,
            ),
            "timeline": sorted(timeline, key=lambda t: t["date"] or ""),
            "boards_analyzed": [
                {"id": b.get("id"), "name": b.get("name"),
                 "workspace": _workspace_name(b)}
                for b in ma_boards
            ],
        }


# ---------------------------------------------------------------------------
# IC Scorecard Analyzer
# ---------------------------------------------------------------------------

# Columns that specifically hold IC gate scores (from M&A Status boards)
IC_GATE_KEYWORDS = [
    "gate 0", "gate 1", "gate 2", "gate 3",
    "ic score", "latest ic",
]

IC_SCORE_KEYWORDS = [
    "score", "rating", "ic", "assessment", "grade", "rank",
    "evaluation", "total", "weighted", "points", "gate",
]

IC_BOARD_KEYWORDS = [
    "ic", "investment committee", "scorecard", "scoring",
    "assessment", "evaluation", "rating", "review",
    "status",  # The M&A "Status" board has IC columns
]


class ICScoreAnalyzer:
    """Analyzes IC (Investment Committee) scorecard progression.

    Focuses on Gate 0-3 Scores and Latest IC Score columns found
    in M&A Status boards, plus any dedicated IC boards.
    """

    def _is_ic_board(self, board: dict) -> bool:
        """A board is IC-relevant if it's in an M&A workspace or has IC keywords."""
        if _is_ma_workspace(board):
            return True
        name = (board.get("name") or "").lower()
        desc = (board.get("description") or "").lower()
        return any(kw in name or kw in desc for kw in IC_BOARD_KEYWORDS)

    def _board_has_ic_columns(self, board: dict) -> bool:
        """Check if a board has IC-specific columns in its definition."""
        for col in board.get("columns", []):
            title = (col.get("title") or "").lower()
            if any(kw in title for kw in IC_GATE_KEYWORDS):
                return True
        return False

    def _extract_scores(self, item: dict) -> Tuple[Dict[str, float], Dict[str, str]]:
        """Extract IC scores and status decisions from an item."""
        numeric_scores: Dict[str, float] = {}
        status_decisions: Dict[str, str] = {}

        for cv in item.get("column_values", []):
            title = (cv.get("title") or "")
            title_lower = title.lower()
            col_type = cv.get("type", "")
            text = cv.get("text", "")

            # IC Gate scores and score columns
            is_gate_col = any(kw in title_lower for kw in IC_GATE_KEYWORDS)
            is_score_col = any(kw in title_lower for kw in IC_SCORE_KEYWORDS)
            is_numeric = col_type in ("numbers", "rating", "formula")

            if (is_gate_col or is_score_col) and is_numeric:
                try:
                    cleaned = re.sub(r"[^\d.\-]", "", str(text))
                    if cleaned:
                        numeric_scores[title] = float(cleaned)
                except (ValueError, TypeError):
                    pass

            # IC decision status columns
            if col_type == "status" and any(
                kw in title_lower for kw in ["ic", "decision", "approval", "committee", "gate"]
            ):
                if text:
                    status_decisions[title] = text

        return numeric_scores, status_decisions

    def analyze(self, boards: List[dict], board_items: dict) -> dict:
        real_boards = _filter_real_boards(boards)

        # Prioritise boards with IC columns, then IC-keyword boards
        ic_boards = [b for b in real_boards if self._board_has_ic_columns(b)]
        if not ic_boards:
            ic_boards = [b for b in real_boards if self._is_ic_board(b)]

        all_items: List[dict] = []
        for board in ic_boards:
            bid = str(board.get("id", ""))
            board_name = board.get("name", "")
            ws = _workspace_name(board)
            board_data = board_items.get(bid, {})
            items = board_data.get("items", []) if isinstance(board_data, dict) else []

            for item in items:
                numeric_scores, status_decisions = self._extract_scores(item)
                if not numeric_scores and not status_decisions:
                    continue

                status = _find_status_column(item) or ""
                owner = _find_person_column(item)
                created_dt = _parse_dt(item.get("created_at"))
                updated_dt = _parse_dt(item.get("updated_at"))

                total_score = sum(numeric_scores.values()) if numeric_scores else None
                avg_score = (
                    total_score / len(numeric_scores)
                ) if numeric_scores else None

                # Extract all column values as key-value pairs for project context
                all_columns: Dict[str, str] = {}
                for cv in item.get("column_values", []):
                    title = cv.get("title") or cv.get("id", "")
                    text = (cv.get("text") or "").strip()
                    if text and title:
                        all_columns[title] = text

                # Extract updates/notes (body text, creator, date)
                raw_updates = item.get("updates") or []
                updates_list = []
                for u in raw_updates[:5]:
                    body = (u.get("body") or "").strip()
                    if body:
                        updates_list.append({
                            "body": body[:500],
                            "created_at": u.get("created_at"),
                            "creator": (u.get("creator") or {}).get("name", ""),
                        })

                # Extract subitems as task checklist
                raw_subitems = item.get("subitems") or []
                subitems_list = []
                for si in raw_subitems:
                    si_status = _find_status_column(si) or ""
                    si_done = si_status.lower() in ("done", "complete", "completed")
                    subitems_list.append({
                        "name": si.get("name", ""),
                        "status": si_status,
                        "done": si_done,
                    })

                entry = {
                    "id": item.get("id"),
                    "name": item.get("name", ""),
                    "board": board_name,
                    "board_id": bid,
                    "workspace": ws,
                    "status": status,
                    "group": (item.get("group") or {}).get("title", ""),
                    "scores": numeric_scores,
                    "total_score": round(total_score, 2) if total_score is not None else None,
                    "avg_score": round(avg_score, 2) if avg_score is not None else None,
                    "decisions": status_decisions,
                    "created_at": created_dt.isoformat() if created_dt else None,
                    "updated_at": updated_dt.isoformat() if updated_dt else None,
                    "owner": owner or "Unassigned",
                    "has_owner": owner is not None,
                    "columns": all_columns,
                    "updates": updates_list,
                    "subitems": subitems_list,
                    "subitems_count": len(raw_subitems),
                    "subitems_complete": sum(1 for s in subitems_list if s["done"]),
                }
                all_items.append(entry)

        # Score statistics
        all_totals = [e["total_score"] for e in all_items if e["total_score"] is not None]
        score_stats = {}
        if all_totals:
            score_stats = {
                "count": len(all_totals),
                "min": min(all_totals),
                "max": max(all_totals),
                "avg": round(sum(all_totals) / len(all_totals), 2),
                "median": sorted(all_totals)[len(all_totals) // 2],
            }

        # Category breakdown (by column name)
        category_scores: Dict[str, List[float]] = defaultdict(list)
        for entry in all_items:
            for col_name, val in entry["scores"].items():
                category_scores[col_name].append(val)

        category_avg = {}
        for cat, vals in sorted(category_scores.items()):
            category_avg[cat] = {
                "avg": round(sum(vals) / len(vals), 2),
                "min": min(vals),
                "max": max(vals),
                "count": len(vals),
            }

        # Monthly trend
        monthly_scores: Dict[str, List[float]] = defaultdict(list)
        for entry in all_items:
            dt = _parse_dt(entry.get("created_at") or entry.get("updated_at"))
            if dt and entry["total_score"] is not None:
                monthly_scores[dt.strftime("%Y-%m")].append(entry["total_score"])

        score_trend = {
            month: {
                "avg_score": round(sum(vals) / len(vals), 2),
                "count": len(vals),
                "max": max(vals),
                "min": min(vals),
            }
            for month, vals in sorted(monthly_scores.items())
        }

        # Decision summary
        decision_counts: Counter = Counter()
        for entry in all_items:
            for _, decision in entry["decisions"].items():
                if decision:
                    decision_counts[decision] += 1

        # Top scored
        scored = [e for e in all_items if e["total_score"] is not None]
        top_scored = sorted(scored, key=lambda e: e["total_score"] or 0, reverse=True)[:20]

        return {
            "total_scored_items": len(all_items),
            "score_statistics": score_stats,
            "category_scores": category_avg,
            "score_trend": score_trend,
            "decision_distribution": dict(decision_counts),
            "top_scored": [
                {
                    "name": e["name"],
                    "board": e["board"],
                    "workspace": e.get("workspace", ""),
                    "total_score": e["total_score"],
                    "avg_score": e["avg_score"],
                    "scores": e["scores"],
                    "status": e["status"],
                    "owner": e["owner"],
                    "has_owner": e["has_owner"],
                    "updated_at": e.get("updated_at"),
                    "created_at": e.get("created_at"),
                    "columns": e.get("columns", {}),
                    "updates": e.get("updates", []),
                    "subitems": e.get("subitems", []),
                    "subitems_count": e.get("subitems_count", 0),
                    "subitems_complete": e.get("subitems_complete", 0),
                    "group": e.get("group", ""),
                    "decisions": e.get("decisions", {}),
                }
                for e in top_scored
            ],
            "items": all_items,
            "boards_analyzed": [
                {"id": b.get("id"), "name": b.get("name"),
                 "workspace": _workspace_name(b)}
                for b in ic_boards
            ],
        }


# ---------------------------------------------------------------------------
# AI Workspace Analyzer
# ---------------------------------------------------------------------------

AI_WORKSPACE_NAMES = ["ecomplete ai", "e-complete ai", "ai committee"]

AI_BOARD_MAP = {
    "initiatives": ["initiative"],
    "tools": ["tool"],
    "knowledge": ["knowledge"],
    "meetings": ["meeting"],
    "active_projects": ["active ai", "active project"],
    "survey": ["survey", "priorities"],
    "submissions": ["submission", "business need"],
}


class AIWorkspaceAnalyzer:
    """Analyzes boards in the eComplete AI workspace."""

    def _is_ai_workspace(self, board: dict) -> bool:
        ws = _workspace_name(board).lower().strip()
        return any(ws == name or ws.startswith(name) for name in AI_WORKSPACE_NAMES)

    def _classify_board(self, board_name: str) -> str:
        name_lower = board_name.lower()
        for category, keywords in AI_BOARD_MAP.items():
            if any(kw in name_lower for kw in keywords):
                return category
        return "other"

    def analyze(self, boards: List[dict], board_items: dict) -> dict:
        real_boards = _filter_real_boards(boards)
        ai_boards = [b for b in real_boards if self._is_ai_workspace(b)]

        if not ai_boards:
            return {"total_items": 0, "boards": [], "categories": {}}

        categories: Dict[str, List[dict]] = defaultdict(list)
        all_ai_items: List[dict] = []

        for board in ai_boards:
            bid = str(board.get("id", ""))
            board_name = board.get("name", "")
            category = self._classify_board(board_name)
            board_data = board_items.get(bid, {})
            items = board_data.get("items", []) if isinstance(board_data, dict) else []

            board_entry = {
                "id": bid,
                "name": board_name,
                "category": category,
                "item_count": len(items),
                "columns": [c.get("title", "") for c in board.get("columns", [])],
                "groups": [g.get("title", "") for g in board.get("groups", [])],
                "owners": [o.get("name", "") for o in board.get("owners", [])],
                "items": [],
            }

            for item in items:
                status = _find_status_column(item) or ""
                owner = _find_person_column(item)
                created_dt = _parse_dt(item.get("created_at"))
                updated_dt = _parse_dt(item.get("updated_at"))

                # All column values
                cols: Dict[str, str] = {}
                for cv in item.get("column_values", []):
                    title = cv.get("title") or cv.get("id", "")
                    text = (cv.get("text") or "").strip()
                    if text and title:
                        cols[title] = text

                # Updates
                updates = []
                for u in (item.get("updates") or [])[:5]:
                    body = (u.get("body") or "").strip()
                    if body:
                        updates.append({
                            "body": body[:500],
                            "created_at": u.get("created_at"),
                            "creator": (u.get("creator") or {}).get("name", ""),
                        })

                # Subitems
                subitems = []
                for si in item.get("subitems") or []:
                    si_status = _find_status_column(si) or ""
                    subitems.append({
                        "name": si.get("name", ""),
                        "status": si_status,
                        "done": si_status.lower() in ("done", "complete", "completed"),
                    })

                item_entry = {
                    "id": item.get("id"),
                    "name": item.get("name", ""),
                    "board": board_name,
                    "board_id": bid,
                    "category": category,
                    "status": status,
                    "group": (item.get("group") or {}).get("title", ""),
                    "owner": owner or "Unassigned",
                    "has_owner": owner is not None,
                    "created_at": created_dt.isoformat() if created_dt else None,
                    "updated_at": updated_dt.isoformat() if updated_dt else None,
                    "columns": cols,
                    "updates": updates,
                    "subitems": subitems,
                }
                board_entry["items"].append(item_entry)
                all_ai_items.append(item_entry)
                categories[category].append(item_entry)

            board_entry["items"] = board_entry["items"]

        # Status distribution
        status_counts: Counter = Counter()
        for item in all_ai_items:
            status_counts[item.get("status") or "No Status"] += 1

        return {
            "total_items": len(all_ai_items),
            "boards": [
                {
                    "id": b.get("id"),
                    "name": b.get("name"),
                    "category": self._classify_board(b.get("name", "")),
                    "item_count": len(
                        (board_items.get(str(b.get("id", "")), {}) or {}).get("items", [])
                    ),
                    "owners": [o.get("name", "") for o in b.get("owners", [])],
                    "groups": [g.get("title", "") for g in b.get("groups", [])],
                }
                for b in ai_boards
            ],
            "categories": {
                cat: {
                    "count": len(items),
                    "items": items,
                }
                for cat, items in categories.items()
            },
            "status_distribution": dict(status_counts),
            "items": all_ai_items,
        }


# ---------------------------------------------------------------------------
# Board Overview (grouped by workspace)
# ---------------------------------------------------------------------------

class BoardOverviewAnalyzer:
    """Overview of all boards grouped by workspace."""

    def analyze(self, boards: List[dict], board_items: dict, users: List[dict]) -> dict:
        real_boards = _filter_real_boards(boards)
        all_boards_count = len(boards)
        subitem_boards_count = sum(
            1 for b in boards if _is_subitem_board(b.get("name", ""))
        )

        # Group by workspace
        workspace_map: Dict[str, Dict[str, Any]] = {}
        total_items = 0
        total_active = 0

        for board in real_boards:
            bid = str(board.get("id", ""))
            board_name = board.get("name", "")
            ws = _workspace_name(board)
            ws_id = _workspace_id(board)

            if ws not in workspace_map:
                workspace_map[ws] = {
                    "id": ws_id,
                    "name": ws,
                    "board_count": 0,
                    "total_items": 0,
                    "active_items": 0,
                    "boards": [],
                }

            board_data = board_items.get(bid, {})
            items = board_data.get("items", []) if isinstance(board_data, dict) else []

            status_counts: Counter = Counter()
            for item in items:
                status = _find_status_column(item) or "No Status"
                status_counts[status] += 1

            item_count = len(items)
            active = sum(1 for i in items if i.get("state") == "active")
            total_items += item_count
            total_active += active

            workspace_map[ws]["board_count"] += 1
            workspace_map[ws]["total_items"] += item_count
            workspace_map[ws]["active_items"] += active
            workspace_map[ws]["boards"].append({
                "id": bid,
                "name": board_name,
                "item_count": item_count,
                "active_items": active,
                "status_breakdown": dict(status_counts),
                "columns": len(board.get("columns", [])),
                "groups": [g.get("title") for g in board.get("groups", [])],
                "owners": [o.get("name") for o in board.get("owners", [])],
            })

        # Sort workspaces by total items desc; sort boards within each by items desc
        workspaces = sorted(
            workspace_map.values(),
            key=lambda w: w["total_items"],
            reverse=True,
        )
        for ws in workspaces:
            ws["boards"] = sorted(
                ws["boards"], key=lambda b: b["item_count"], reverse=True
            )

        return {
            "total_boards_raw": all_boards_count,
            "subitem_boards_filtered": subitem_boards_count,
            "total_boards": len(real_boards),
            "total_items": total_items,
            "total_active_items": total_active,
            "workspace_count": len(workspaces),
            "workspaces": workspaces,
            "user_count": len(users),
        }


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

def _load_latest_raw(prefix: str) -> Any:
    pattern = str(RAW_DIR / f"{prefix}_*.json")
    files = sorted(glob.glob(pattern), reverse=True)
    if not files:
        logger.warning(f"No raw files found for {prefix}")
        return None
    latest = files[0]
    logger.info(f"Loading {latest}")
    with open(latest, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("results", data)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def run_monday_analysis() -> dict:
    logger.info("=== Monday.com Analysis Starting ===")

    boards = _load_latest_raw("monday_boards") or []
    board_items = _load_latest_raw("monday_items") or {}
    users = _load_latest_raw("monday_users") or []

    real_boards = _filter_real_boards(boards)
    logger.info(
        "Loaded: %d boards (%d real after filtering sub-boards), "
        "%d board item sets, %d users",
        len(boards), len(real_boards),
        len(board_items) if isinstance(board_items, dict) else 0,
        len(users),
    )

    logger.info("Running BoardOverviewAnalyzer...")
    overview = BoardOverviewAnalyzer().analyze(boards, board_items, users)

    logger.info("Running MandAAnalyzer...")
    ma_metrics = MandAAnalyzer().analyze(boards, board_items)

    logger.info("Running ICScoreAnalyzer...")
    ic_metrics = ICScoreAnalyzer().analyze(boards, board_items)

    logger.info("Running AIWorkspaceAnalyzer...")
    ai_metrics = AIWorkspaceAnalyzer().analyze(boards, board_items)

    output = {
        "generated_at": _now_utc().isoformat(),
        "data_source": "monday",
        "board_overview": overview,
        "ma_metrics": ma_metrics,
        "ic_metrics": ic_metrics,
        "ai_metrics": ai_metrics,
    }

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    output_path = PROCESSED_DIR / "monday_metrics.json"
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(output, fh, indent=2, default=str)

    logger.info("Monday.com analysis complete. Output saved to %s", output_path)
    return output


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    results = run_monday_analysis()
    ma = results.get("ma_metrics", {})
    ic = results.get("ic_metrics", {})
    ov = results.get("board_overview", {})
    ai = results.get("ai_metrics", {})
    print(f"\nAnalysis complete.")
    print(f"  Boards: {ov.get('total_boards', 0)} real "
          f"(filtered {ov.get('subitem_boards_filtered', 0)} sub-boards)")
    print(f"  Workspaces: {ov.get('workspace_count', 0)}")
    print(f"  M&A projects: {ma.get('total_projects', 0)} "
          f"({ma.get('active_projects', 0)} active)")
    print(f"  IC scored items: {ic.get('total_scored_items', 0)}")
    print(f"  AI items: {ai.get('total_items', 0)} across {len(ai.get('boards', []))} boards")
    print(f"Output: {PROCESSED_DIR / 'monday_metrics.json'}")
