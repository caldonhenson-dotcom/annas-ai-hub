"""
HubSpot Sales Dashboard Generator
===================================
Reads data/processed/hubspot_sales_metrics.json and generates a spectacular
self-contained HTML dashboard at dashboard/frontend/dashboard-v2.html.

No external CDN dependencies -- all CSS, JS, and SVG charts are inline so the
dashboard works offline and on Vercel static hosting.

Usage:
    python scripts/generate_hubspot_dashboard.py
"""

from __future__ import annotations

import html
import json
import logging
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent          # Annas Ai Hub/
DATA_FILE = BASE_DIR / "data" / "processed" / "hubspot_sales_metrics.json"
OUTPUT_DIR = BASE_DIR / "dashboard" / "frontend"
OUTPUT_FILE = OUTPUT_DIR / "dashboard-v2.html"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("generate_hubspot_dashboard")

# ---------------------------------------------------------------------------
# Colour palette
# ---------------------------------------------------------------------------
COLORS = {
    "bg":           "#f7f8fa",       # eComplete light background
    "card":         "#ffffff",       # White cards
    "card_border":  "#e2e5ea",       # Light grey border
    "text":         "#121212",       # eComplete near-black
    "text_muted":   "#6b7280",       # Medium grey
    "accent":       "#3CB4AD",       # eComplete teal
    "accent2":      "#334FB4",       # eComplete royal blue
    "accent3":      "#a78bfa",       # violet-400
    "accent4":      "#34d399",       # emerald-400
    "accent5":      "#f472b6",       # pink-400
    "accent6":      "#f59e0b",       # amber
    "success":      "#22c55e",
    "danger":       "#ef4444",
    "warning":      "#f59e0b",
    "info":         "#3b82f6",
    "surface":      "#ffffff",       # White
    "surface2":     "#f3f4f6",       # Light grey
}

CHART_PALETTE = [
    "#3CB4AD", "#334FB4", "#a78bfa", "#34d399", "#f472b6",
    "#f59e0b", "#60a5fa", "#ef4444", "#2dd4bf", "#c084fc",
    "#4ade80", "#fbbf24", "#e879f9", "#22d3ee", "#fb7185",
]

# ---------------------------------------------------------------------------
# Module Registry — single source of truth for pages, sidebar, builders
# ---------------------------------------------------------------------------
# Each module: id, label (sidebar), group, group_icon, builder function name (resolved later)

MODULES = [
    {"id": "anna",              "label": "eComplete AI",          "group": "Assistant",     "icon": "&#9889;"},
    {"id": "executive",         "label": "Executive Summary",    "group": "Overview",      "icon": "&#9679;"},
    {"id": "leads",             "label": "Leads & Conversion",   "group": "Sales",         "icon": "&#9733;"},
    {"id": "pipeline",          "label": "Pipeline View",        "group": "Sales",         "icon": "&#9733;"},
    {"id": "targets",           "label": "Targets & Rev Eng",    "group": "Sales",         "icon": "&#9733;"},
    {"id": "activities",        "label": "Activity & Contacts",  "group": "Performance",   "icon": "&#9993;"},
    {"id": "insights",          "label": "Insights & Forecast",  "group": "Performance",   "icon": "&#10024;"},
    {"id": "monday-pipeline",   "label": "M&A Pipeline",         "group": "M&A",           "icon": "&#128188;"},
    {"id": "monday-ic",         "label": "IC Scorecards",        "group": "M&A",           "icon": "&#128188;"},
    {"id": "ai-roadmap",        "label": "AI Roadmap",           "group": "Operations",    "icon": "&#129302;"},
    {"id": "inbound-queue",     "label": "Inbound Queue",        "group": "Operations",    "icon": "&#9889;"},
]

# Builder function map — populated after function definitions (see bottom of section builders)
_MODULE_BUILDERS: Dict[str, Any] = {}


def _register_builders() -> None:
    """Map module IDs to their builder functions. Called once at generation time."""
    _MODULE_BUILDERS.update({
        "anna":              _build_anna_page,
        "executive":         _build_executive_summary,
        "leads":             _build_leads_and_funnel,
        "targets":           _build_target_section,
        "pipeline":          _build_pipeline_section,
        "activities":        _build_activities_and_contacts,
        "insights":          _build_insights_section,
        "monday-pipeline":   _build_monday_pipeline_and_workspaces,
        "monday-ic":         _build_monday_ic,
        "ai-roadmap":        _build_ai_section,
        "inbound-queue":     _build_inbound_and_actions,
    })


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def _esc(text: Any) -> str:
    """HTML-escape a value; converts None to empty string."""
    if text is None:
        return ""
    return html.escape(str(text))


def _fmt_currency(value: Any, symbol: str = "\u00a3") -> str:
    """Format a number as GBP currency (£)."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return f"{symbol}0"
    if abs(v) >= 1_000_000:
        return f"{symbol}{v / 1_000_000:,.1f}M"
    if abs(v) >= 1_000:
        return f"{symbol}{v / 1_000:,.1f}K"
    return f"{symbol}{v:,.0f}"


def _fmt_number(value: Any) -> str:
    """Format a number with commas."""
    try:
        v = float(value)
        if v == int(v):
            return f"{int(v):,}"
        return f"{v:,.1f}"
    except (TypeError, ValueError):
        return "0"


def _fmt_pct(value: Any) -> str:
    """Format a value as a percentage string."""
    try:
        v = float(value)
        return f"{v:.1f}%"
    except (TypeError, ValueError):
        return "0%"


def _safe_get(data: dict, *keys, default=None):
    """Safely traverse nested dicts."""
    current = data
    for k in keys:
        if isinstance(current, dict):
            current = current.get(k, default)
        else:
            return default
    return current if current is not None else default


def _normalize_metrics(data: dict) -> dict:
    """Normalize analyzer output: convert dict-keyed fields to list-of-dict format
    expected by dashboard builder.  Mutates *data* in-place and returns it."""

    # -- lead_metrics --
    lm = data.get("lead_metrics", {})
    # leads_over_time: {month: count} -> [{month, count}]
    if isinstance(lm.get("leads_over_time"), dict):
        lm["leads_over_time"] = [{"month": k, "count": v} for k, v in lm["leads_over_time"].items()]
    # source_effectiveness: {source: {mql: ..}} -> [{source, ...}]
    if isinstance(lm.get("source_effectiveness"), dict):
        lm["source_effectiveness"] = [
            {"source": k, **(v if isinstance(v, dict) else {"lead_count": v, "mql_count": 0, "conversion_rate": 0})}
            for k, v in lm["source_effectiveness"].items()
        ]
    # leads_by_source already dict {source:count} - keep as-is, charts handle dicts
    # lead_status_distribution already dict - keep as-is

    # -- pipeline_metrics --
    pm = data.get("pipeline_metrics", {})
    # deals_by_stage: {label: {count, value, ...}} -> [{stage, label, count, value, ...}]
    if isinstance(pm.get("deals_by_stage"), dict):
        pm["deals_by_stage"] = [
            {"stage": k, "label": k, **(v if isinstance(v, dict) else {"count": v, "value": 0, "weighted_value": 0, "probability": 0, "avg_days_in_stage": 0})}
            for k, v in pm["deals_by_stage"].items()
        ]
    # pipeline_by_owner: {id: {name, deals, ...}} -> [{owner_id, owner_name, ...}]
    if isinstance(pm.get("pipeline_by_owner"), dict):
        pm["pipeline_by_owner"] = [
            {"owner_id": k, **(v if isinstance(v, dict) else {"owner_name": str(k), "deal_count": 0, "total_value": 0})}
            for k, v in pm["pipeline_by_owner"].items()
        ]
    # close_date_distribution: keep as dict {month: count} - generator uses .items()

    # -- activity_metrics --
    am = data.get("activity_metrics", {})
    # by_rep: {name: {calls, emails, ...}} -> [{owner_name, calls, ...}]
    if isinstance(am.get("by_rep"), dict):
        am["by_rep"] = [
            {"owner_name": k, **(v if isinstance(v, dict) else {"total": v})}
            for k, v in am["by_rep"].items()
        ]
    # daily_trend: {date: count} -> [{date, count}]
    if isinstance(am.get("daily_trend"), dict):
        am["daily_trend"] = [{"date": k, "count": v} for k, v in am["daily_trend"].items()]

    # -- contact_metrics --
    cm = data.get("contact_metrics", {})
    # by_lifecycle: {stage: count} - keep as dict for charts
    # companies_summary might be dict not list
    if isinstance(cm.get("companies_summary"), dict) and "total" in cm["companies_summary"]:
        # It's a summary object, wrap it
        pass  # handled inline

    # -- insights --
    ins = data.get("insights", {})
    # sales_cycle_trend: {month: avg_days} -> [{month, avg_days}]
    if isinstance(ins.get("sales_cycle_trend"), dict):
        ins["sales_cycle_trend"] = [{"month": k, "avg_days": v} for k, v in ins["sales_cycle_trend"].items()]
    # deal_size_distribution: {range: count} -> [{range, count}]
    if isinstance(ins.get("deal_size_distribution"), dict):
        ins["deal_size_distribution"] = [{"range": k, "count": v} for k, v in ins["deal_size_distribution"].items()]
    # rep_performance: {id: {...}} -> [{owner_id, ...}]
    if isinstance(ins.get("rep_performance"), dict):
        ins["rep_performance"] = [
            {"owner_id": k, **(v if isinstance(v, dict) else {"name": str(k)})}
            for k, v in ins["rep_performance"].items()
        ]
    # cohort_analysis: {month: {...}} -> [{cohort_month, ...}]
    if isinstance(ins.get("cohort_analysis"), dict):
        ins["cohort_analysis"] = [
            {"cohort_month": k, **(v if isinstance(v, dict) else {"total_leads": v})}
            for k, v in ins["cohort_analysis"].items()
        ]

    return data


def _color_at(idx: int) -> str:
    """Return a palette colour by index (wrapping)."""
    return CHART_PALETTE[idx % len(CHART_PALETTE)]


# ---------------------------------------------------------------------------
# SVG chart generators
# ---------------------------------------------------------------------------

def _svg_bar_chart(
    data: List[Tuple[str, float]],
    width: int = 500,
    height: int = 180,
    color: str = "#3CB4AD",
    show_values: bool = True,
) -> str:
    """Horizontal bar chart.  data = [(label, value), ...]."""
    if not data:
        return _no_data_svg(width, height)
    bar_height = 22
    gap = 4
    label_width = 140
    value_width = 80
    chart_width = width - label_width - value_width - 20
    max_val = max(v for _, v in data) or 1
    total_height = max(height, len(data) * (bar_height + gap) + 20)

    bars = []
    for i, (label, val) in enumerate(data):
        y = i * (bar_height + gap) + 10
        bar_w = max(2, (val / max_val) * chart_width)
        label_text = label[:18] + ".." if len(str(label)) > 20 else str(label)
        c = _color_at(i)
        bars.append(f'''
        <text x="{label_width - 8}" y="{y + bar_height / 2 + 5}"
              text-anchor="end" fill="{COLORS['text_muted']}"
              font-size="12" font-family="system-ui, sans-serif">{_esc(label_text)}</text>
        <rect x="{label_width}" y="{y}" width="0" height="{bar_height}"
              rx="6" fill="{c}" opacity="0.85">
            <animate attributeName="width" from="0" to="{bar_w}"
                     dur="0.8s" begin="{i * 0.05}s" fill="freeze"
                     calcMode="spline" keySplines="0.25 0.1 0.25 1"/>
        </rect>''')
        if show_values:
            display_val = _fmt_currency(val) if val > 100 else _fmt_number(val)
            bars.append(f'''
        <text x="{label_width + bar_w + 8}" y="{y + bar_height / 2 + 5}"
              fill="{COLORS['text']}" font-size="12" font-weight="600"
              font-family="system-ui, sans-serif" opacity="0">
            {_esc(display_val)}
            <animate attributeName="opacity" from="0" to="1"
                     dur="0.3s" begin="{0.5 + i * 0.05}s" fill="freeze"/>
        </text>''')

    return f'''<svg width="100%" viewBox="0 0 {width} {total_height}"
         xmlns="http://www.w3.org/2000/svg" role="img"
         aria-label="Bar chart">{''.join(bars)}
    </svg>'''


def _svg_donut(
    segments: List[Tuple[str, float]],
    size: int = 150,
    inner_ratio: float = 0.6,
) -> str:
    """Donut / pie chart with animated segments and legend."""
    if not segments or all(v == 0 for _, v in segments):
        return _no_data_svg(size, size)
    total = sum(v for _, v in segments) or 1
    cx, cy = size / 2, size / 2
    r = (size / 2) - 20
    ir = r * inner_ratio

    paths = []
    legend_items = []
    angle = -90  # start at top

    for i, (label, val) in enumerate(segments):
        pct = val / total
        sweep = pct * 360
        if sweep < 0.5:
            continue
        large = 1 if sweep > 180 else 0
        start_rad = math.radians(angle)
        end_rad = math.radians(angle + sweep)

        # Outer arc
        x1 = cx + r * math.cos(start_rad)
        y1 = cy + r * math.sin(start_rad)
        x2 = cx + r * math.cos(end_rad)
        y2 = cy + r * math.sin(end_rad)
        # Inner arc (reverse)
        ix1 = cx + ir * math.cos(end_rad)
        iy1 = cy + ir * math.sin(end_rad)
        ix2 = cx + ir * math.cos(start_rad)
        iy2 = cy + ir * math.sin(start_rad)

        c = _color_at(i)
        d = (f"M {x1:.1f} {y1:.1f} "
             f"A {r:.1f} {r:.1f} 0 {large} 1 {x2:.1f} {y2:.1f} "
             f"L {ix1:.1f} {iy1:.1f} "
             f"A {ir:.1f} {ir:.1f} 0 {large} 0 {ix2:.1f} {iy2:.1f} Z")

        paths.append(f'''
        <path d="{d}" fill="{c}" opacity="0" stroke="{COLORS['bg']}" stroke-width="2">
            <animate attributeName="opacity" from="0" to="0.9"
                     dur="0.6s" begin="{i * 0.08}s" fill="freeze"/>
        </path>''')

        short_label = label[:16] + ".." if len(str(label)) > 18 else str(label)
        legend_items.append(f'''
        <div style="display:flex;align-items:center;gap:6px;font-size:11px;color:{COLORS['text_muted']}">
            <span style="width:10px;height:10px;border-radius:50%;background:{c};flex-shrink:0"></span>
            {_esc(short_label)}: {_fmt_pct(pct * 100)}
        </div>''')
        angle += sweep

    # Centre label
    centre = f'''
        <text x="{cx}" y="{cy - 6}" text-anchor="middle"
              fill="{COLORS['text']}" font-size="22" font-weight="700"
              font-family="system-ui, sans-serif">{_fmt_number(total)}</text>
        <text x="{cx}" y="{cy + 14}" text-anchor="middle"
              fill="{COLORS['text_muted']}" font-size="11"
              font-family="system-ui, sans-serif">Total</text>'''

    svg = f'''<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}"
         xmlns="http://www.w3.org/2000/svg" role="img"
         aria-label="Donut chart">{''.join(paths)}{centre}
    </svg>'''

    legend = f'''<div style="display:flex;flex-wrap:wrap;gap:6px 16px;
                 margin-top:8px;">{''.join(legend_items)}</div>'''
    return f'<div style="text-align:center">{svg}{legend}</div>'


def _svg_sparkline(
    values: List[float],
    width: int = 160,
    height: int = 40,
    color: str = "#3CB4AD",
    fill: bool = True,
) -> str:
    """Tiny trend sparkline."""
    if not values or len(values) < 2:
        return f'<svg width="{width}" height="{height}"></svg>'
    mn = min(values)
    mx = max(values)
    rng = mx - mn or 1
    pad = 2
    w = width - pad * 2
    h = height - pad * 2

    points = []
    for i, v in enumerate(values):
        x = pad + (i / (len(values) - 1)) * w
        y = pad + h - ((v - mn) / rng) * h
        points.append(f"{x:.1f},{y:.1f}")

    polyline = ' '.join(points)
    fill_path = ""
    if fill:
        first_x = pad
        last_x = pad + w
        fill_points = f"{first_x},{pad + h} {polyline} {last_x},{pad + h}"
        fill_path = f'''<polygon points="{fill_points}"
            fill="url(#sparkGrad_{id(values)})" opacity="0.3"/>'''

    return f'''<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}"
         xmlns="http://www.w3.org/2000/svg">
        <defs>
            <linearGradient id="sparkGrad_{id(values)}" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stop-color="{color}" stop-opacity="0.4"/>
                <stop offset="100%" stop-color="{color}" stop-opacity="0"/>
            </linearGradient>
        </defs>
        {fill_path}
        <polyline points="{polyline}" fill="none"
                  stroke="{color}" stroke-width="2" stroke-linecap="round"
                  stroke-linejoin="round"/>
        <circle cx="{points[-1].split(',')[0]}" cy="{points[-1].split(',')[1]}"
                r="3" fill="{color}"/>
    </svg>'''


def _svg_funnel(
    stages: List[Tuple[str, float, str]],
    width: int = 500,
    height: int = 220,
) -> str:
    """Conversion funnel.  stages = [(label, value, conversion_text), ...]."""
    if not stages:
        return _no_data_svg(width, height)
    n = len(stages)
    stage_h = height / n
    max_val = stages[0][1] or 1
    min_width_pct = 0.25
    pad = 40

    shapes = []
    for i, (label, val, conv_text) in enumerate(stages):
        pct = max(val / max_val, min_width_pct)
        next_pct = max(stages[i + 1][1] / max_val, min_width_pct) if i < n - 1 else pct * 0.8

        top_w = pct * (width - 2 * pad)
        bot_w = next_pct * (width - 2 * pad)
        cx_val = width / 2
        y_top = i * stage_h
        y_bot = y_top + stage_h

        tl = cx_val - top_w / 2
        tr = cx_val + top_w / 2
        bl = cx_val - bot_w / 2
        br = cx_val + bot_w / 2

        c = _color_at(i)
        shapes.append(f'''
        <polygon points="{tl:.0f},{y_top:.0f} {tr:.0f},{y_top:.0f}
                         {br:.0f},{y_bot:.0f} {bl:.0f},{y_bot:.0f}"
                 fill="{c}" opacity="0" stroke="{COLORS['bg']}" stroke-width="2">
            <animate attributeName="opacity" from="0" to="0.85"
                     dur="0.5s" begin="{i * 0.12}s" fill="freeze"/>
        </polygon>
        <text x="{cx_val}" y="{y_top + stage_h * 0.38}" text-anchor="middle"
              fill="white" font-size="14" font-weight="700"
              font-family="system-ui, sans-serif" opacity="0">
            {_esc(label)}: {_fmt_number(val)}
            <animate attributeName="opacity" from="0" to="1"
                     dur="0.3s" begin="{0.3 + i * 0.12}s" fill="freeze"/>
        </text>
        <text x="{cx_val}" y="{y_top + stage_h * 0.68}" text-anchor="middle"
              fill="rgba(255,255,255,0.7)" font-size="11"
              font-family="system-ui, sans-serif" opacity="0">
            {_esc(conv_text)}
            <animate attributeName="opacity" from="0" to="1"
                     dur="0.3s" begin="{0.4 + i * 0.12}s" fill="freeze"/>
        </text>''')

    return f'''<svg width="100%" viewBox="0 0 {width} {height}"
         xmlns="http://www.w3.org/2000/svg" role="img"
         aria-label="Conversion funnel">{''.join(shapes)}
    </svg>'''


def _svg_horizontal_bar(
    label: str,
    value: float,
    max_val: float,
    color: str = "#3CB4AD",
    show_pct: bool = True,
) -> str:
    """Single horizontal progress bar with label."""
    value = value or 0
    max_val = max_val or 1
    pct = min(value / max_val, 1.0) * 100 if max_val else 0
    return f'''<div style="margin-bottom:10px">
        <div style="display:flex;justify-content:space-between;margin-bottom:4px;
                    font-size:13px;color:{COLORS['text_muted']}">
            <span>{_esc(str(label))}</span>
            <span style="font-weight:600;color:{COLORS['text']}">{_fmt_number(value)}
                {f' ({pct:.0f}%)' if show_pct else ''}</span>
        </div>
        <div style="height:8px;background:{COLORS['card_border']};border-radius:4px;overflow:hidden">
            <div style="height:100%;width:{pct:.1f}%;background:linear-gradient(90deg,{color},{color}dd);
                        border-radius:4px;transition:width 1.2s cubic-bezier(.25,.1,.25,1)"></div>
        </div>
    </div>'''


def _svg_line_chart(
    data_points: List[Tuple[str, float]],
    width: int = 500,
    height: int = 150,
    color: str = "#38bdf8",
    show_dots: bool = True,
    show_labels: bool = True,
) -> str:
    """Line chart with area fill.  data_points = [(label, value), ...]."""
    if not data_points or len(data_points) < 2:
        return _no_data_svg(width, height)
    values = [v for _, v in data_points]
    labels = [l for l, _ in data_points]
    mn = min(values)
    mx = max(values)
    rng = mx - mn or 1
    pad_x, pad_y = 50, 30
    chart_w = width - pad_x * 2
    chart_h = height - pad_y * 2

    points = []
    for i, v in enumerate(values):
        x = pad_x + (i / (len(values) - 1)) * chart_w
        y = pad_y + chart_h - ((v - mn) / rng) * chart_h
        points.append((x, y))

    polyline = ' '.join(f"{x:.1f},{y:.1f}" for x, y in points)
    fill_pts = (f"{points[0][0]:.1f},{pad_y + chart_h} {polyline} "
                f"{points[-1][0]:.1f},{pad_y + chart_h}")

    uid = abs(hash(str(data_points))) % 100000

    dots = ""
    if show_dots:
        for i, (x, y) in enumerate(points):
            dots += f'''<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{color}"
                stroke="{COLORS['bg']}" stroke-width="2" opacity="0">
                <animate attributeName="opacity" from="0" to="1"
                         dur="0.2s" begin="{0.5 + i * 0.03}s" fill="freeze"/>
            </circle>\n'''

    x_labels = ""
    if show_labels and len(labels) <= 20:
        step = max(1, len(labels) // 8)
        for i in range(0, len(labels), step):
            x = pad_x + (i / (len(labels) - 1)) * chart_w
            raw = str(labels[i])
            # Format YYYY-MM dates as "Mon YY"
            try:
                from datetime import datetime as _dt
                dt = _dt.strptime(raw[:7], "%Y-%m")
                short = dt.strftime("%b %y")
            except Exception:
                # Format YYYY-MM-DD dates as "DD Mon"
                try:
                    dt = _dt.strptime(raw[:10], "%Y-%m-%d")
                    short = dt.strftime("%d %b")
                except Exception:
                    short = raw[-5:]
            x_labels += f'''<text x="{x:.1f}" y="{pad_y + chart_h + 18}"
                text-anchor="middle" fill="{COLORS['text_muted']}" font-size="10"
                font-family="system-ui, sans-serif">{_esc(short)}</text>\n'''

    # Y-axis labels
    y_labels = ""
    for i in range(5):
        val = mn + (rng * i / 4)
        y = pad_y + chart_h - (chart_h * i / 4)
        y_labels += f'''<text x="{pad_x - 8}" y="{y + 4}" text-anchor="end"
            fill="{COLORS['text_muted']}" font-size="10"
            font-family="system-ui, sans-serif">{_fmt_number(val)}</text>
        <line x1="{pad_x}" y1="{y}" x2="{pad_x + chart_w}" y2="{y}"
              stroke="{COLORS['card_border']}" stroke-width="0.5" stroke-dasharray="4"/>\n'''

    return f'''<svg width="100%" viewBox="0 0 {width} {height}"
         xmlns="http://www.w3.org/2000/svg" role="img"
         aria-label="Line chart">
        <defs>
            <linearGradient id="lineGrad_{uid}" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stop-color="{color}" stop-opacity="0.3"/>
                <stop offset="100%" stop-color="{color}" stop-opacity="0.02"/>
            </linearGradient>
        </defs>
        {y_labels}
        <polygon points="{fill_pts}" fill="url(#lineGrad_{uid})"/>
        <polyline points="{polyline}" fill="none" stroke="{color}"
                  stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
        {dots}
        {x_labels}
    </svg>'''


def _no_data_svg(width: int = 400, height: int = 100) -> str:
    """Placeholder SVG when no data is available."""
    return f'''<svg width="100%" viewBox="0 0 {width} {height}"
         xmlns="http://www.w3.org/2000/svg">
        <rect width="{width}" height="{height}" fill="{COLORS['surface2']}"
              rx="12" opacity="0.5"/>
        <text x="{width / 2}" y="{height / 2 + 5}" text-anchor="middle"
              fill="{COLORS['text_muted']}" font-size="14"
              font-family="system-ui, sans-serif">No data available</text>
    </svg>'''


# ---------------------------------------------------------------------------
# HTML component helpers
# ---------------------------------------------------------------------------

def _stat_card(
    title: str,
    value: str,
    subtitle: str = "",
    icon: str = "",
    color: str = "#3CB4AD",
    sparkline_values: Optional[List[float]] = None,
    nav_page: str = "",
    metric_key: str = "",
) -> str:
    """Metric KPI card with optional sparkline and clickable navigation (#40)."""
    spark_html = ""
    if sparkline_values and len(sparkline_values) >= 2:
        spark_html = f'''<div style="margin-top:6px">
            {_svg_sparkline(sparkline_values, 130, 28, color)}
        </div>'''

    icon_html = ""
    if icon:
        icon_html = f'''<div style="width:22px;height:22px;border-radius:5px;
            background:linear-gradient(135deg,{color}22,{color}11);
            display:flex;align-items:center;justify-content:center;
            font-size:11px;flex-shrink:0;margin-bottom:2px;
            border:1px solid {color}33">{icon}</div>'''

    nav_attr = f' data-nav-page="{nav_page}"' if nav_page else ""
    nav_hint = f' title="Click to view {title}"' if nav_page else ""
    metric_attr = f' data-metric="{metric_key}"' if metric_key else ""

    return f'''<div class="stat-card" style="--accent:{color}"{nav_attr}{nav_hint}{metric_attr}>
        {icon_html}
        <div style="font-size:10px;color:{COLORS['text_muted']};text-transform:uppercase;
                    letter-spacing:0.05em;margin-bottom:1px">{_esc(title)}</div>
        <div data-role="stat-value" style="font-size:17px;font-weight:800;color:{COLORS['text']};
                    line-height:1.1;margin-bottom:1px">{_esc(value)}</div>
        <div data-role="stat-subtitle" style="font-size:11px;color:{COLORS['text_muted']}">{_esc(subtitle)}</div>
        {spark_html}
    </div>'''


def _data_table(
    headers: List[str],
    rows: List[List[str]],
    table_id: str = "",
    max_rows: int = 50,
) -> str:
    """Sortable data table component."""
    if not rows:
        return f'''<div style="text-align:center;padding:32px;color:{COLORS['text_muted']};
                    font-size:14px">No data available</div>'''

    display_rows = rows[:max_rows]
    tid = table_id or f"tbl_{abs(hash(str(headers))) % 100000}"

    header_cells = ''.join(
        f'<th onclick="sortTable(\'{tid}\', {i})" '
        f'style="cursor:pointer;user-select:none">{_esc(h)} '
        f'<span style="opacity:0.4;font-size:10px">&#x25B2;&#x25BC;</span></th>'
        for i, h in enumerate(headers)
    )

    body_rows = ""
    for row in display_rows:
        cells = ''.join(f'<td>{cell}</td>' for cell in row)
        body_rows += f'<tr>{cells}</tr>\n'

    truncated = ""
    if len(rows) > max_rows:
        truncated = f'''<div style="text-align:center;padding:8px;font-size:12px;
            color:{COLORS['text_muted']}">Showing {max_rows} of {len(rows)} rows</div>'''

    return f'''<div class="table-wrapper">
        <table id="{tid}" class="data-table">
            <thead><tr>{header_cells}</tr></thead>
            <tbody>{body_rows}</tbody>
        </table>
        {truncated}
    </div>'''


def _progress_bar(
    value: float,
    max_val: float,
    color: str = "#3CB4AD",
    label: str = "",
    show_values: bool = True,
) -> str:
    """CSS progress bar."""
    pct = min((value / max_val) * 100, 100) if max_val else 0
    value_text = ""
    if show_values:
        value_text = f'''<span style="font-weight:600;color:{COLORS['text']}">
            {_fmt_number(value)} / {_fmt_number(max_val)}</span>'''

    return f'''<div style="margin-bottom:8px">
        <div style="display:flex;justify-content:space-between;margin-bottom:4px;font-size:13px">
            <span style="color:{COLORS['text_muted']}">{_esc(label)}</span>
            {value_text}
        </div>
        <div style="height:10px;background:{COLORS['card_border']};border-radius:5px;overflow:hidden">
            <div class="progress-fill" style="height:100%;width:{pct:.1f}%;
                background:linear-gradient(90deg,{color},{color}cc);border-radius:5px"></div>
        </div>
    </div>'''


def _section_header(section_id: str, title: str, subtitle: str = "", icon: str = "") -> str:
    """Section heading with anchor."""
    return f'''<section id="{section_id}" class="dashboard-section">
        <div class="section-header">
            <div>
                <h2 class="section-title">{icon} {_esc(title)}</h2>
                <p class="section-subtitle">{_esc(subtitle)}</p>
            </div>
        </div>'''


# ---------------------------------------------------------------------------
# Dashboard sections
# ---------------------------------------------------------------------------

def _build_anna_page(data: dict) -> str:
    """Full-page Anna AI assistant — conversation sidebar, embedded chat, inline reports."""
    # No section header — the Anna page uses its own layout
    return f'''<section class="dashboard-section anna-section">
    <div class="anna-layout">
        <!-- Conversation sidebar -->
        <div class="anna-sidebar" id="anna-sidebar">
            <button class="anna-new-chat" onclick="window.AnnaPage.newChat()">
                &#43; New Chat
            </button>
            <div class="anna-conv-list" id="anna-conv-list"></div>
            <div class="anna-sidebar-divider"></div>
            <div class="anna-sidebar-label">&#128196; Reports</div>
            <button class="anna-report-btn" onclick="window.AnnaPage.runReport('monthly-deal-flow')">
                <span>&#9733;</span> Monthly Deal Flow</button>
            <button class="anna-report-btn" onclick="window.AnnaPage.runReport('pipeline-health')">
                <span>&#9881;</span> Pipeline Health</button>
            <button class="anna-report-btn" onclick="window.AnnaPage.runReport('lead-source')">
                <span>&#10024;</span> Lead Source Analysis</button>
            <button class="anna-report-btn" onclick="window.AnnaPage.runReport('weekly-activity')">
                <span>&#9993;</span> Weekly Activity</button>
            <button class="anna-report-btn" onclick="window.AnnaPage.runReport('ma-pipeline')">
                <span>&#128188;</span> M&amp;A Pipeline</button>
            <button class="anna-report-btn" onclick="window.AnnaPage.runReport('rep-scorecard')">
                <span>&#9879;</span> Rep Scorecard</button>
        </div>

        <!-- Main chat area -->
        <div class="anna-chat-area">
            <div class="anna-chat-header">
                <div class="anna-avatar">e</div>
                <div class="anna-header-info">
                    <div class="anna-header-name">eComplete AI</div>
                    <div class="anna-header-status">Sales &amp; M&amp;A Intelligence Assistant</div>
                </div>
                <div class="anna-header-actions">
                    <button class="anna-header-btn" onclick="window.AnnaPage.clearChat()" title="Clear chat">&#128465;</button>
                </div>
            </div>
            <div class="anna-messages" id="anna-page-msgs">
                <div class="anna-welcome" id="anna-welcome">
                    <div class="anna-welcome-avatar">e</div>
                    <div class="anna-welcome-title">eComplete AI</div>
                    <div class="anna-welcome-sub">Your sales &amp; M&amp;A intelligence assistant. Ask me anything about your dashboard data.</div>
                    <div class="anna-suggestions" id="anna-suggestions">
                        <button class="anna-suggest-btn" onclick="window.AnnaPage.ask(this.textContent)">Summarise deal flow this month</button>
                        <button class="anna-suggest-btn" onclick="window.AnnaPage.ask(this.textContent)">Which deals are stale or at risk?</button>
                        <button class="anna-suggest-btn" onclick="window.AnnaPage.ask(this.textContent)">Pipeline health &amp; coverage</button>
                        <button class="anna-suggest-btn" onclick="window.AnnaPage.ask(this.textContent)">Lead source effectiveness</button>
                        <button class="anna-suggest-btn" onclick="window.AnnaPage.ask(this.textContent)">Top performing rep this month</button>
                        <button class="anna-suggest-btn" onclick="window.AnnaPage.ask(this.textContent)">M&amp;A pipeline status</button>
                        <button class="anna-suggest-btn" onclick="window.AnnaPage.ask(this.textContent)">Revenue forecast next 90 days</button>
                        <button class="anna-suggest-btn" onclick="window.AnnaPage.ask(this.textContent)">Weekly summary</button>
                    </div>
                </div>
            </div>
            <div class="anna-input-area">
                <input class="anna-input" id="anna-page-input" type="text"
                    placeholder="Ask eComplete AI about your data..."
                    onkeydown="if(event.key==='Enter'&&!event.shiftKey){{event.preventDefault();window.AnnaPage.send()}}" />
                <button class="anna-send-btn" onclick="window.AnnaPage.send()">&#10148;</button>
            </div>
        </div>
    </div>
    </section>'''


def _build_executive_summary(data: dict) -> str:
    """Dashboard Overview — compact KPI strip + 4-pillar AI-driven snapshots."""
    pipeline = _safe_get(data, "pipeline_metrics", default={})
    activity = _safe_get(data, "activity_metrics", default={})
    leads = _safe_get(data, "lead_metrics", default={})
    contacts = _safe_get(data, "contact_metrics", default={})
    counts = _safe_get(data, "record_counts", default={})
    rev_eng = _safe_get(data, "reverse_engineering", default={})
    insights = _safe_get(data, "insights", default={})
    forecast = _safe_get(insights, "revenue_forecast", default={})
    monday = data.get("monday", {})
    ma_data = monday.get("ma_metrics", {}) if monday else {}

    html = _section_header("executive", "Dashboard",
                           "Live business intelligence overview",
                           "\U0001F4CA")

    # ── Compact KPI strip (all 8 in one row) ──
    kpis = [
        ("Pipeline", _fmt_currency(pipeline.get("total_pipeline_value", 0)), COLORS['accent']),
        ("Weighted", _fmt_currency(pipeline.get("weighted_pipeline_value", 0)), COLORS['accent2']),
        ("Win Rate", _fmt_pct(pipeline.get("win_rate", 0)), COLORS['accent4']),
        ("Open Deals", _fmt_number(pipeline.get("open_deals_count", 0)), COLORS['accent3']),
        ("Avg Size", _fmt_currency(pipeline.get("avg_deal_size", 0)), COLORS['accent6']),
        ("Leads", _fmt_number(leads.get("total_leads", 0)), COLORS['info']),
        ("Activities", _fmt_number(activity.get("total_activities", 0)), COLORS['accent5']),
        ("30d Forecast", _fmt_currency(forecast.get("days_30", 0)), COLORS['warning']),
    ]
    kpi_html = ""
    for label, val, color in kpis:
        kpi_html += f'''<div class="exec-kpi">
            <div class="exec-kpi-val" style="color:{color}">{val}</div>
            <div class="exec-kpi-label">{label}</div>
        </div>'''
    html += f'<div class="exec-kpi-strip">{kpi_html}</div>'

    # ── 4-Pillar Snapshots ──
    # Each pillar: icon, title, 3-4 bullet-point insights
    won = pipeline.get("won_deals_count", 0)
    lost = pipeline.get("lost_deals_count", 0)
    stale_deals = pipeline.get("stale_deals", [])
    cycle_days = pipeline.get("avg_sales_cycle_days", 0)
    top_rep = ""
    by_rep = pipeline.get("pipeline_by_rep", [])
    if by_rep and isinstance(by_rep, list) and len(by_rep) > 0:
        top_rep = by_rep[0].get("owner", by_rep[0].get("rep", ""))

    # Build sales pillar points
    sales_points = []
    sales_points.append(f'<strong>{_fmt_currency(pipeline.get("total_pipeline_value", 0))}</strong> total pipeline ({_fmt_number(pipeline.get("open_deals_count", 0))} open deals)')
    if won or lost:
        sales_points.append(f'<strong>{won}</strong> deals won vs <strong>{lost}</strong> lost &mdash; {_fmt_pct(pipeline.get("win_rate", 0))} win rate')
    if cycle_days:
        sales_points.append(f'Average sales cycle: <strong>{_fmt_number(cycle_days)} days</strong>')
    if stale_deals:
        sales_points.append(f'<span style="color:{COLORS["warning"]}">&#9888; {len(stale_deals)} stale deals</span> sitting in stage &gt;30 days')
    if top_rep:
        sales_points.append(f'Top pipeline holder: <strong>{_esc(top_rep)}</strong>')

    # Build leads pillar points
    leads_points = []
    new_30 = leads.get("new_leads_30d", 0)
    mql = leads.get("mql_count", 0)
    sql = leads.get("sql_count", 0)
    leads_points.append(f'<strong>{_fmt_number(leads.get("total_leads", 0))}</strong> total leads ({_fmt_number(new_30)} new in last 30d)')
    if mql:
        leads_points.append(f'<strong>{_fmt_number(mql)}</strong> MQLs &mdash; {_fmt_pct(leads.get("lead_to_mql_rate", 0))} conversion rate')
    top_source = ""
    sources = leads.get("leads_by_source", {})
    if sources and isinstance(sources, dict):
        top_source = max(sources, key=sources.get, default="")
        if top_source:
            leads_points.append(f'Top source: <strong>{_esc(top_source)}</strong> ({_fmt_number(sources[top_source])} leads)')
    leads_points.append(f'<strong>{_fmt_number(counts.get("contacts", 0))}</strong> contacts, <strong>{_fmt_number(counts.get("companies", 0))}</strong> companies in CRM')

    # Build M&A pillar points
    ma_points = []
    active_ma = ma_data.get("active_projects", 0)
    total_ma = ma_data.get("total_projects", 0)
    stale_ma = ma_data.get("stale_projects", [])
    stage_dist = ma_data.get("stage_distribution", {})
    ma_points.append(f'<strong>{active_ma}</strong> active projects out of {total_ma} total')
    if stage_dist:
        top_stages = sorted(stage_dist.items(), key=lambda x: x[1], reverse=True)[:3]
        stage_str = ", ".join(f'{s}: {c}' for s, c in top_stages)
        ma_points.append(f'Top stages: {stage_str}')
    if stale_ma:
        ma_points.append(f'<span style="color:{COLORS["warning"]}">&#9888; {len(stale_ma)} stale projects</span> need follow-up')
    ic_data = monday.get("ic_metrics", {}) if monday else {}
    ic_pending = len([i for i in ic_data.get("items", []) if not i.get("decisions")])
    if ic_pending:
        ma_points.append(f'<strong>{ic_pending}</strong> IC items awaiting decision')

    # Build ops pillar points
    ops_points = []
    ai_data = monday.get("ai_metrics", {}) if monday else {}
    ai_total = ai_data.get("total_items", 0)
    by_type = activity.get("by_type", {})
    calls = by_type.get("calls", by_type.get("CALL", 0))
    emails = by_type.get("emails", by_type.get("EMAIL", 0))
    meetings = by_type.get("meetings", by_type.get("MEETING", 0))
    if calls or emails or meetings:
        ops_points.append(f'Activity mix: <strong>{_fmt_number(calls)}</strong> calls, <strong>{_fmt_number(emails)}</strong> emails, <strong>{_fmt_number(meetings)}</strong> meetings')
    tpw = activity.get("touches_per_won_deal", 0)
    if tpw:
        ops_points.append(f'<strong>{_fmt_number(tpw)}</strong> touches per won deal')
    if ai_total:
        ops_points.append(f'<strong>{ai_total}</strong> items on AI roadmap')
    # Queue
    queue_file_path = BASE_DIR / "data" / "processed" / "inbound_queue.json"
    critical_count = 0
    if queue_file_path.exists():
        try:
            with open(queue_file_path, "r", encoding="utf-8") as qf:
                q_data = json.load(qf)
            critical_count = q_data.get("priority_breakdown", q_data.get("summary", {})).get("critical", 0)
        except Exception:
            pass
    if critical_count:
        ops_points.append(f'<span style="color:{COLORS["danger"]}">&#9888; {critical_count} critical</span> items in inbound queue')

    pillars = [
        ("Sales & Pipeline", COLORS['accent'], "&#9733;", sales_points, "pipeline"),
        ("Leads & Conversion", COLORS['accent2'], "&#10024;", leads_points, "leads"),
        ("M&A", COLORS['accent3'], "&#128188;", ma_points, "monday-pipeline"),
        ("Activity & Operations", COLORS['accent5'], "&#9889;", ops_points, "activities"),
    ]

    html += '<div class="exec-pillars">'
    for title, color, icon, points, nav in pillars:
        pts = "".join(f'<li>{p}</li>' for p in points[:5])
        html += f'''<div class="exec-pillar" onclick="showPage('{nav}')" style="cursor:pointer">
            <div class="exec-pillar-header">
                <span class="exec-pillar-icon" style="background:{color}15;color:{color}">{icon}</span>
                <span class="exec-pillar-title">{title}</span>
                <span class="exec-pillar-arrow" style="color:{color}">&#8594;</span>
            </div>
            <ul class="exec-pillar-points">{pts}</ul>
        </div>'''
    html += '</div>'

    # ── Compact trend charts ──
    html += f'''<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-top:8px">
        <div class="glass-card" style="padding:10px 12px">
            <div class="card-title" style="font-size:10px;margin-bottom:4px">Leads (6mo)</div>
            <div id="dynamic-leads-barchart"></div>
        </div>
        <div class="glass-card" style="padding:10px 12px">
            <div class="card-title" style="font-size:10px;margin-bottom:4px">Revenue (6mo)</div>
            <div id="dynamic-revenue-barchart"></div>
        </div>
        <div class="glass-card" style="padding:10px 12px">
            <div class="card-title" style="font-size:10px;margin-bottom:4px">Deals Created (6mo)</div>
            <div id="dynamic-deals-barchart"></div>
        </div>
        <div class="glass-card" style="padding:10px 12px">
            <div class="card-title" style="font-size:10px;margin-bottom:4px">Activity (6mo)</div>
            <div id="dynamic-activity-barchart"></div>
        </div>
    </div>'''

    # ── Revenue target (compact) ──
    rev_target = _safe_get(rev_eng, "revenue_target", default={})
    monthly_target = rev_target.get("monthly", 100000)
    weighted = pipeline.get("weighted_pipeline_value", 0)
    html += f'''<div class="glass-card" style="margin-top:8px;padding:10px 14px">
        <div style="font-size:10px;color:{COLORS['text_muted']};text-transform:uppercase;
            letter-spacing:0.04em;margin-bottom:4px">Revenue Target Progress</div>
        {_progress_bar(weighted, monthly_target, COLORS['accent4'],
                       f"Weighted Pipeline vs Monthly Target ({_fmt_currency(monthly_target)})")}
    </div>'''

    html += '</section>'
    return html


def _build_leads_section(data: dict) -> str:
    """Section 2: Leads & Conversion — department grouping, source analysis, marketing funnel."""
    leads = _safe_get(data, "lead_metrics", default={})
    pipeline = _safe_get(data, "pipeline_metrics", default={})
    html = _section_header("leads", "Leads & Conversion",
                           "Lead sources, department breakdown, and marketing funnel",
                           "\U0001F4E5")

    DEPT_MAP = {
        "james carberry": "Supply Chain", "rose galbally": "Supply Chain",
        "jake heath": "Delivery",
        "josh elliott": "CDD", "carell": "CDD",
        "caldon henson": "Management", "anna younger": "Operations",
        "kirill kopica": "Operations", "skye whitton": "Operations",
    }

    # ── KPI strip (5 in one row) ──
    total_leads = leads.get("total_leads", 0)
    new_30 = leads.get("new_leads_30d", 0)
    mql = leads.get("mql_count", 0)
    sql = leads.get("sql_count", 0)
    response_h = leads.get("avg_lead_response_hours", 0)
    html += '<div class="kpi-grid" style="grid-template-columns:repeat(5,1fr)">'
    html += _stat_card("Total Leads", _fmt_number(total_leads),
                       f"New 30d: {_fmt_number(new_30)}", "\U0001F4CA", COLORS['accent'])
    html += _stat_card("MQLs", _fmt_number(mql),
                       f"{_fmt_pct(leads.get('lead_to_mql_rate', 0))} conv.",
                       "\U0001F31F", COLORS['accent2'])
    html += _stat_card("SQLs", _fmt_number(sql), "", "\U0001F525", COLORS['accent4'])
    html += _stat_card("Open Deals", _fmt_number(pipeline.get("open_deals_count", 0)),
                       "", "\U0001F4BC", COLORS['accent3'])
    html += _stat_card("Avg Response", f"{int(round(response_h))}h" if response_h else "N/A",
                       "", "\u23F1\uFE0F", COLORS['accent5'])
    html += '</div>'

    # ── Source breakdown + leads trend (2-col) ──
    sources = leads.get("leads_by_source", {})
    leads_over_time = leads.get("leads_over_time", {})
    html += '<div class="grid-2" style="margin-top:8px">'
    if sources:
        source_data = sorted(sources.items(), key=lambda x: x[1], reverse=True)[:8]
        html += f'''<div class="glass-card">
            <h3 class="card-title">Leads by Source</h3>
            {_svg_bar_chart(source_data, 450, max(120, len(source_data) * 26))}
        </div>'''
    else:
        html += '<div></div>'
    if leads_over_time:
        if isinstance(leads_over_time, dict):
            trend_data = [(m, c) for m, c in sorted(leads_over_time.items())]
        elif isinstance(leads_over_time, list):
            trend_data = [(item.get("month", ""), item.get("count", 0)) for item in leads_over_time]
        else:
            trend_data = []
        if trend_data:
            html += f'''<div class="glass-card">
                <h3 class="card-title">Lead Trend (Monthly)</h3>
                {_svg_line_chart(trend_data[-18:], 450, 140, COLORS['accent'])}
            </div>'''
        else:
            html += '<div></div>'
    else:
        html += '<div></div>'
    html += '</div>'

    # ── Lead status + source effectiveness (2-col) ──
    status_dist = leads.get("lead_status_distribution", {})
    effectiveness = leads.get("source_effectiveness", {})
    has_status = bool(status_dist)
    has_eff = bool(effectiveness)
    if has_status or has_eff:
        html += '<div class="grid-2" style="margin-top:8px">'
        if has_status:
            named_status = {k: v for k, v in status_dist.items() if not k.strip().isdigit()}
            if named_status:
                html += f'''<div class="glass-card">
                    <h3 class="card-title">Lead Status</h3>'''
                max_s = max(named_status.values()) if named_status else 1
                for status, count in sorted(named_status.items(), key=lambda x: x[1], reverse=True)[:6]:
                    html += _svg_horizontal_bar(status, count, max_s, COLORS['accent2'])
                html += '</div>'
            else:
                html += '<div></div>'
        else:
            html += '<div></div>'
        if has_eff:
            eff_rows = []
            if isinstance(effectiveness, dict):
                for src, info in sorted(effectiveness.items(), key=lambda x: x[1].get("total", 0) if isinstance(x[1], dict) else 0, reverse=True):
                    if isinstance(info, dict):
                        eff_rows.append([_esc(src), _fmt_number(info.get("total", 0)),
                                         _fmt_number(info.get("mqls", 0)), _fmt_pct(info.get("conversion_rate", 0))])
            elif isinstance(effectiveness, list):
                for item in effectiveness:
                    eff_rows.append([_esc(item.get("source", "")), _fmt_number(item.get("lead_count", item.get("total", 0))),
                                     _fmt_number(item.get("mql_count", item.get("mqls", 0))), _fmt_pct(item.get("conversion_rate", 0))])
            if eff_rows:
                html += f'''<div class="glass-card">
                    <h3 class="card-title">Source Effectiveness</h3>
                    {_data_table(["Source", "Leads", "MQLs", "Conv."], eff_rows, "source_eff")}
                </div>'''
            else:
                html += '<div></div>'
        else:
            html += '<div></div>'
        html += '</div>'

    # ── Department Pipeline Summary ──
    by_owner = pipeline.get("pipeline_by_owner", {})
    if isinstance(by_owner, dict) and by_owner:
        dept_data = {}
        for oid, info in by_owner.items():
            if not isinstance(info, dict):
                continue
            name = info.get("name", "")
            if not name or name.strip().isdigit():
                continue
            dept = DEPT_MAP.get(name.lower().strip(), "Other")
            if dept not in dept_data:
                dept_data[dept] = {"deals": 0, "value": 0, "reps": []}
            dept_data[dept]["deals"] += info.get("deal_count", 0)
            dept_data[dept]["value"] += info.get("total_value", 0)
            dept_data[dept]["reps"].append(name.split()[0])
        if dept_data:
            dept_colors = {"Supply Chain": COLORS['accent'], "Delivery": COLORS['accent2'],
                           "CDD": COLORS['accent3'], "Management": COLORS['accent5'],
                           "Operations": COLORS['accent4'], "Other": COLORS['info']}
            html += f'''<div class="glass-card" style="margin-top:8px">
                <h3 class="card-title">Pipeline by Department</h3>
                <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:8px">'''
            for dept, dinfo in sorted(dept_data.items(), key=lambda x: x[1]["value"], reverse=True):
                dc = dept_colors.get(dept, COLORS['info'])
                reps_str = ", ".join(dinfo["reps"])
                html += f'''<div style="background:{dc}11;border:1px solid {dc}33;border-radius:8px;padding:10px 12px">
                    <div style="font-size:10px;text-transform:uppercase;letter-spacing:0.04em;color:{dc};font-weight:700;margin-bottom:4px">{_esc(dept)}</div>
                    <div style="font-size:18px;font-weight:800;color:{COLORS['text']}">{_fmt_currency(dinfo["value"])}</div>
                    <div style="font-size:11px;color:{COLORS['text_muted']}">{dinfo["deals"]} deals &middot; {_esc(reps_str)}</div>
                </div>'''
            html += '</div></div>'

    html += '</section>'
    return html


def _build_funnel_section(data: dict) -> str:
    """Section 3: Deal Stage Flow — funnel based on actual deal stages."""
    leads = _safe_get(data, "lead_metrics", default={})
    pipeline = _safe_get(data, "pipeline_metrics", default={})

    # No separate section header — merged into leads page
    html = ''

    # ── Deal stage funnel (from real data) ──
    deals_by_stage = pipeline.get("deals_by_stage", {})
    funnel_flow = [
        ("Inbound Leads", ["Inbound Lead"], COLORS['accent']),
        ("First Meetings", ["First Meeting Booked"], COLORS['accent2']),
        ("Second Meetings", ["Second Meeting Booked"], COLORS['accent3']),
        ("Engaged", ["Engaged"], COLORS['info']),
        ("Proposals", ["Proposal Shared"], COLORS['accent5']),
        ("Decision Maker", ["Decision Maker Bought-In"], COLORS['warning']),
        ("Contracts", ["Contract Sent"], COLORS['accent4']),
        ("Won", ["Closed Won"], COLORS['success']),
    ]

    if isinstance(deals_by_stage, dict) and deals_by_stage:
        active_stages = []
        for label, stage_keys, color in funnel_flow:
            count = sum(deals_by_stage.get(s, {}).get("count", 0) if isinstance(deals_by_stage.get(s), dict) else 0 for s in stage_keys)
            value = sum(deals_by_stage.get(s, {}).get("total_value", 0) if isinstance(deals_by_stage.get(s), dict) else 0 for s in stage_keys)
            if count > 0:
                active_stages.append((label, count, value, color))
        if active_stages:
            max_count = max(s[1] for s in active_stages) or 1
            html += f'''<div class="glass-card" style="margin-top:8px">
                <h3 class="card-title">Deal Stage Flow</h3>
                <div style="max-width:700px;margin:0 auto">'''
            for label, count, value, color in active_stages:
                pct_w = max(15, (count / max_count) * 100)
                html += f'''<div style="display:flex;align-items:center;gap:10px;margin-bottom:6px">
                    <div style="width:120px;text-align:right;font-size:12px;color:{COLORS['text_muted']};flex-shrink:0">{_esc(label)}</div>
                    <div style="flex:1;height:28px;background:{COLORS['card_border']};border-radius:6px;overflow:hidden;position:relative">
                        <div style="height:100%;width:{pct_w:.0f}%;background:linear-gradient(90deg,{color},{color}88);border-radius:6px"></div>
                        <span style="position:absolute;right:8px;top:50%;transform:translateY(-50%);font-size:11px;font-weight:600;color:{COLORS['text']}">{count} deals &middot; {_fmt_currency(value)}</span>
                    </div>
                </div>'''
            html += '</div></div>'

    # ── Conversion rates + time in stage (2-col) ──
    conversion_rates = leads.get("conversion_rates", {})
    time_in_stage = leads.get("time_in_stage", {})
    if conversion_rates or time_in_stage:
        html += '<div class="grid-2" style="margin-top:8px">'
        if conversion_rates:
            html += f'''<div class="glass-card">
                <h3 class="card-title">Stage Conversion Rates</h3>'''
            rate_items = [
                ("lead_to_mql", "Lead \u2192 MQL", COLORS['accent']),
                ("mql_to_sql", "MQL \u2192 SQL", COLORS['accent2']),
                ("sql_to_opp", "SQL \u2192 Opp", COLORS['accent3']),
                ("opp_to_won", "Opp \u2192 Won", COLORS['accent4']),
                ("lead_to_customer", "Lead \u2192 Customer", COLORS['accent5']),
            ]
            for key, label, color in rate_items:
                val = conversion_rates.get(key)
                if val is not None:
                    html += f'''<div style="display:flex;justify-content:space-between;padding:5px 0;border-bottom:1px solid {COLORS['card_border']}22;font-size:13px">
                        <span style="color:{COLORS['text_muted']}">{label}</span>
                        <span style="color:{color};font-weight:700">{_fmt_pct(val)}</span>
                    </div>'''
            html += '</div>'
        else:
            html += '<div></div>'
        if time_in_stage:
            safe_vals = [v for v in time_in_stage.values() if v is not None and v > 0]
            if safe_vals:
                max_days = max(safe_vals)
                html += f'''<div class="glass-card">
                    <h3 class="card-title">Avg Time in Stage (days)</h3>'''
                for stage, days in sorted(time_in_stage.items(), key=lambda x: (x[1] or 0), reverse=True):
                    if days is not None and days > 0:
                        html += _svg_horizontal_bar(stage, int(round(days)), int(round(max_days)), COLORS['accent3'], show_pct=False)
                html += '</div>'
            else:
                html += '<div></div>'
        else:
            html += '<div></div>'
        html += '</div>'

    html += '</section>'
    return html


def _build_target_section(data: dict) -> str:
    """Section 4: Targets & Reverse Engineering — volume funnel, gap analysis, requirements."""
    rev_eng = _safe_get(data, "reverse_engineering", default={})
    pipeline = _safe_get(data, "pipeline_metrics", default={})
    leads = _safe_get(data, "lead_metrics", default={})

    if not rev_eng:
        html = _section_header("targets", "Targets & Reverse Engineering",
                               "Revenue targets and required volumes", "\U0001F4C8")
        html += f'''<div class="glass-card"><p style="color:{COLORS['text_muted']};
            text-align:center;padding:32px">No reverse engineering data available</p></div>'''
        html += '</section>'
        return html

    html = _section_header("targets", "Targets & Reverse Engineering",
                           "Revenue targets, required volumes, and gap analysis",
                           "\U0001F4C8")

    # ── Revenue targets + current actuals (5 in one row) ──
    rev_target = rev_eng.get("revenue_target", {})
    won_value = 0
    deals_by_stage = pipeline.get("deals_by_stage", {})
    if isinstance(deals_by_stage, dict):
        cw = deals_by_stage.get("Closed Won", {})
        won_value = cw.get("total_value", 0) if isinstance(cw, dict) else 0
    html += '<div class="kpi-grid" style="grid-template-columns:repeat(5,1fr)">'
    html += _stat_card("Monthly Target", _fmt_currency(rev_target.get("monthly", 0)),
                       "", "\U0001F4B7", COLORS['accent'])
    html += _stat_card("Quarterly Target", _fmt_currency(rev_target.get("quarterly", 0)),
                       "", "\U0001F4C5", COLORS['accent2'])
    html += _stat_card("Annual Target", _fmt_currency(rev_target.get("annual", 0)),
                       "", "\U0001F3C6", COLORS['accent4'])
    html += _stat_card("Won to Date", _fmt_currency(won_value),
                       f"{pipeline.get('won_deals_count', 0)} deals", "\u2705", COLORS['success'])
    html += _stat_card("Pipeline", _fmt_currency(pipeline.get("total_pipeline_value", 0)),
                       f"{pipeline.get('open_deals_count', 0)} open", "\U0001F4CA", COLORS['accent3'])
    html += '</div>'

    # ── Required Volume Funnel (visual flow) ──
    chain_items = [
        ("Leads", rev_eng.get("required_leads", 0), leads.get("total_leads", 0), COLORS['accent']),
        ("MQLs", rev_eng.get("required_mqls", 0), leads.get("mql_count", 0), COLORS['accent2']),
        ("SQLs", rev_eng.get("required_sqls", 0), leads.get("sql_count", 0), COLORS['accent3']),
        ("Opps", rev_eng.get("required_opps", 0), pipeline.get("open_deals_count", 0) + pipeline.get("won_deals_count", 0) + pipeline.get("lost_deals_count", 0), COLORS['accent5']),
        ("Deals", rev_eng.get("required_deals", 0), pipeline.get("won_deals_count", 0), COLORS['accent4']),
    ]
    html += f'''<div class="glass-card" style="margin-top:8px">
        <h3 class="card-title">Required vs Actual (Monthly)</h3>
        <div style="display:grid;grid-template-columns:repeat(5,1fr);gap:8px">'''
    for label, required, actual, color in chain_items:
        req_int = int(round(required)) if required else 0
        act_int = int(round(actual)) if actual else 0
        gap_val = act_int - req_int
        gap_color = COLORS['success'] if gap_val >= 0 else COLORS['danger']
        gap_prefix = "+" if gap_val > 0 else ""
        html += f'''<div style="text-align:center;padding:8px">
            <div style="font-size:10px;text-transform:uppercase;letter-spacing:0.04em;color:{COLORS['text_muted']};margin-bottom:4px">{_esc(label)}</div>
            <div style="font-size:20px;font-weight:800;color:{color}">{_fmt_number(req_int)}</div>
            <div style="font-size:11px;color:{COLORS['text_muted']}">required</div>
            <div style="font-size:14px;font-weight:700;color:{COLORS['text']};margin-top:4px">{_fmt_number(act_int)}</div>
            <div style="font-size:11px;color:{gap_color};font-weight:600">{gap_prefix}{_fmt_number(gap_val)} gap</div>
        </div>'''
    html += '</div></div>'

    # ── Gap analysis + Requirements + What-if (3-col) ──
    gap = rev_eng.get("gap_analysis", {})
    daily = rev_eng.get("daily_requirements", {})
    weekly = rev_eng.get("weekly_requirements", {})
    scenarios = rev_eng.get("what_if_scenarios", [])

    if gap or daily or weekly or scenarios:
        html += '<div class="grid-3" style="margin-top:8px">'
        if gap:
            html += f'''<div class="glass-card">
                <h3 class="card-title">Gap Analysis</h3>'''
            for key, val in gap.items():
                label = key.replace("_", " ").title()
                if isinstance(val, (int, float)):
                    gcolor = COLORS['success'] if val >= 0 else COLORS['danger']
                    display = _fmt_number(int(round(val))) if abs(val) < 1000 else _fmt_currency(val)
                    prefix = "+" if val > 0 else ""
                    html += f'''<div style="display:flex;justify-content:space-between;
                        padding:4px 0;border-bottom:1px solid {COLORS['card_border']}22;font-size:12px">
                        <span style="color:{COLORS['text_muted']}">{_esc(label)}</span>
                        <span style="color:{gcolor};font-weight:600">{prefix}{display}</span>
                    </div>'''
            html += '</div>'
        else:
            html += '<div></div>'
        if daily or weekly:
            html += f'''<div class="glass-card">
                <h3 class="card-title">Daily / Weekly Requirements</h3>'''
            if daily:
                for key, val in list(daily.items())[:4]:
                    label = key.replace("_", " ").title()
                    html += f'''<div style="display:flex;justify-content:space-between;padding:3px 0;font-size:12px;border-bottom:1px solid {COLORS['card_border']}22">
                        <span style="color:{COLORS['text_muted']}">Daily {_esc(label)}</span>
                        <span style="color:{COLORS['text']};font-weight:600">{_fmt_number(val)}</span>
                    </div>'''
            if weekly:
                for key, val in list(weekly.items())[:4]:
                    label = key.replace("_", " ").title()
                    html += f'''<div style="display:flex;justify-content:space-between;padding:3px 0;font-size:12px;border-bottom:1px solid {COLORS['card_border']}22">
                        <span style="color:{COLORS['text_muted']}">Weekly {_esc(label)}</span>
                        <span style="color:{COLORS['text']};font-weight:600">{_fmt_number(val)}</span>
                    </div>'''
            html += '</div>'
        else:
            html += '<div></div>'
        if scenarios:
            rows = []
            for s in scenarios:
                imp = s.get("improvement_pct", 0)
                improved_rates = s.get("improved_rates", {})
                new_rate = improved_rates.get("lead_to_mql", s.get("new_lead_to_mql", 0))
                req_leads = s.get("required_leads_monthly", s.get("required_leads", 0))
                saved = s.get("lead_reduction_vs_baseline", s.get("leads_saved", 0))
                rows.append([
                    f"+{_fmt_number(imp)}%",
                    _fmt_pct(new_rate),
                    _fmt_number(int(round(req_leads))) if req_leads else "0",
                    _fmt_number(int(round(saved))) if saved else "0",
                ])
            html += f'''<div class="glass-card">
                <h3 class="card-title">What-If Scenarios</h3>
                <p style="font-size:11px;color:{COLORS['text_muted']};margin-bottom:6px">
                    Lead-to-MQL improvements</p>
                {_data_table(["Imp.", "New Rate", "Leads", "Saved"], rows, "whatif")}
            </div>'''
        else:
            html += '<div></div>'
        html += '</div>'

    html += '</section>'
    return html


def _build_pipeline_section(data: dict) -> str:
    """Section 5: Pipeline View."""
    pipeline = _safe_get(data, "pipeline_metrics", default={})
    html = _section_header("pipeline", "Pipeline View",
                           "Deal stages, rep performance, and velocity",
                           "\U0001F4B0")

    # --- KPIs (5 cards: Total Pipeline, Coverage, Avg Sales Cycle, Win Rate, Velocity) ---
    velocity_raw = pipeline.get("pipeline_velocity", 0)
    velocity_val = float(velocity_raw) if isinstance(velocity_raw, (int, float)) else 0

    avg_cycle_raw = pipeline.get("avg_sales_cycle_days", 0)
    try:
        avg_cycle_int = int(float(avg_cycle_raw))
    except (ValueError, TypeError):
        avg_cycle_int = 0

    html += f'<div style="display:grid;grid-template-columns:repeat(5,1fr);gap:16px;margin-bottom:16px">'
    html += _stat_card("Total Pipeline", _fmt_currency(pipeline.get("total_pipeline_value", 0)),
                       f"Weighted: {_fmt_currency(pipeline.get('weighted_pipeline_value', 0))}",
                       "\U0001F4B0", COLORS['accent'])
    html += _stat_card("Pipeline Coverage", f"{_fmt_number(pipeline.get('pipeline_coverage', 0))}x",
                       "vs revenue target", "\U0001F6E1", COLORS['accent2'])
    html += _stat_card("Avg Sales Cycle", f"{avg_cycle_int}d",
                       f"Avg deal: {_fmt_currency(pipeline.get('avg_deal_size', 0))}",
                       "\u23F1", COLORS['accent3'])
    html += _stat_card("Win Rate", _fmt_pct(pipeline.get("win_rate", 0)),
                       f"Won {pipeline.get('won_deals_count', 0)} | Lost {pipeline.get('lost_deals_count', 0)}",
                       "\U0001F3AF", COLORS['accent4'])
    html += _stat_card("Pipeline Velocity", _fmt_currency(velocity_val),
                       "value per day", "\U0001F680", COLORS['accent5'])
    html += '</div>'

    # --- Deals by Stage (2-col: table left, bars right) ---
    deals_by_stage = pipeline.get("deals_by_stage", {})
    if isinstance(deals_by_stage, dict) and deals_by_stage:
        stage_rows = []
        for stage_name, info in sorted(deals_by_stage.items(),
                                        key=lambda x: x[1].get("total_value", 0) if isinstance(x[1], dict) else 0,
                                        reverse=True):
            if isinstance(info, dict):
                count = info.get("count", 0)
                value = info.get("total_value", 0)
                prob = info.get("probability", 0)
                weighted = value * prob
                stage_rows.append([stage_name, count, value, weighted, prob])
        # Only show stages with count > 0
        stage_rows = [r for r in stage_rows if r[1] > 0]

        if stage_rows:
            # Table rows formatted for display
            table_rows = []
            for r in stage_rows:
                table_rows.append([
                    _esc(r[0]),
                    _fmt_number(r[1]),
                    _fmt_currency(r[2]),
                    _fmt_currency(r[3]),
                    _fmt_pct(r[4]),
                ])

            # Bar data
            max_stage_val = max((r[2] for r in stage_rows), default=1) or 1
            bars_html = ""
            for i, r in enumerate(stage_rows):
                bars_html += _svg_horizontal_bar(
                    r[0], r[2], max_stage_val, _color_at(i), show_pct=False,
                )

            html += f'''<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px">
                <div class="glass-card">
                    <h3 class="card-title">Deals by Stage</h3>
                    {_data_table(["Stage", "Deals", "Value", "Weighted", "Probability"],
                                 table_rows, "pipeline_stages")}
                </div>
                <div class="glass-card">
                    <h3 class="card-title">Stage Value Distribution</h3>
                    {bars_html}
                </div>
            </div>'''

    # --- Pipeline by Rep (grouped by department) ---
    _dept_map = {
        "james carberry": "Supply Chain",
        "rose galbally": "Supply Chain",
        "jake heath": "Delivery",
        "josh elliott": "CDD",
        "carell": "CDD",
        "caldon henson": "Management",
        "anna younger": "Operations",
        "kirill kopica": "Operations",
    }

    by_owner = pipeline.get("pipeline_by_owner", {})
    if isinstance(by_owner, dict) and by_owner:
        owner_rows = []
        for oid, info in by_owner.items():
            if isinstance(info, dict):
                name = info.get("name", "")
                if not name or name.strip().isdigit():
                    continue
                dept = _dept_map.get(name.lower().strip(), "Other")
                owner_rows.append({
                    "name": name,
                    "deals": info.get("deal_count", 0),
                    "value": info.get("total_value", 0),
                    "weighted": info.get("weighted_value", 0),
                    "dept": dept,
                })
        owner_rows.sort(key=lambda x: x["value"], reverse=True)

        if owner_rows:
            # Group by department
            dept_groups = {}
            for row in owner_rows:
                dept = row["dept"]
                if dept not in dept_groups:
                    dept_groups[dept] = []
                dept_groups[dept].append(row)

            html += '<div class="glass-card" style="margin-bottom:16px">'
            html += '<h3 class="card-title">Pipeline by Rep</h3>'

            for dept_name, members in sorted(dept_groups.items()):
                html += f'''<div style="margin-bottom:12px">
                    <div style="font-size:12px;font-weight:700;color:{COLORS['accent2']};
                        text-transform:uppercase;letter-spacing:0.05em;
                        margin-bottom:6px;padding-bottom:4px;
                        border-bottom:1px solid {COLORS['card_border']}">{_esc(dept_name)}</div>'''

                dept_table_rows = []
                for m in members:
                    dept_table_rows.append([
                        _esc(m["name"]),
                        _fmt_number(m["deals"]),
                        _fmt_currency(m["value"]),
                        _fmt_currency(m["weighted"]),
                    ])
                html += _data_table(["Name", "Deals", "Total Value", "Weighted"],
                                    dept_table_rows, f"rep_{dept_name.lower().replace(' ', '_')}")
                html += '</div>'
            html += '</div>'

    # --- Bottom row: Stale Deals + Close Date Distribution (2-col) ---
    stale = pipeline.get("stale_deals", [])
    close_dist = pipeline.get("close_date_distribution", {})
    has_stale = isinstance(stale, list) and len(stale) > 0
    has_close = isinstance(close_dist, dict) and len(close_dist) > 0

    if has_stale or has_close:
        html += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px">'

        # Stale deals
        if has_stale:
            html += f'''<div class="glass-card alert-card" style="border-color:{COLORS['warning']}44">
                <h3 class="card-title" style="color:{COLORS['warning']}">
                    \u26A0 Stale Deals ({len(stale)})</h3>
                <p style="font-size:12px;color:{COLORS['text_muted']};margin-bottom:8px">
                    Deals with no activity beyond threshold</p>'''
            stale_rows = []
            for d in stale[:20]:
                days_val = d.get("days_since_update", 0)
                try:
                    days_display = str(int(float(days_val)))
                except (ValueError, TypeError):
                    days_display = "0"
                stale_rows.append([
                    _esc(d.get("dealname", "Unknown")),
                    _fmt_currency(d.get("amount", 0)),
                    _esc(d.get("stage", "")),
                    days_display,
                    _esc(d.get("owner", "")),
                ])
            html += _data_table(["Deal", "Value", "Stage", "Days Stale", "Owner"],
                                stale_rows, "stale_deals")
            html += '</div>'
        else:
            html += '<div></div>'

        # Close date distribution
        if has_close:
            dist_data = []
            for month_str, count in sorted(close_dist.items()):
                try:
                    dt = datetime.strptime(month_str, "%Y-%m")
                    label = dt.strftime("%b %y")
                except (ValueError, TypeError):
                    label = month_str
                dist_data.append((label, count))

            html += f'''<div class="glass-card">
                <h3 class="card-title">Expected Close Date Distribution</h3>
                {_svg_bar_chart(dist_data, 500, 180)}
            </div>'''
        else:
            html += '<div></div>'

        html += '</div>'

    html += '</section>'
    return html


def _build_activity_section(data: dict) -> str:
    """Section 6: Activity Tracking."""
    activity = _safe_get(data, "activity_metrics", default={})
    html = _section_header("activities", "Activity Tracking",
                           "Sales activities, rep engagement, and trends",
                           "\u26A1")

    # Activity type KPIs -- all on ONE row (6 columns: Total + up to 5 types)
    by_type = activity.get("by_type", {})
    icon_map = {
        "calls": "\U0001F4DE",
        "emails": "\u2709\uFE0F",
        "meetings": "\U0001F91D",
        "tasks": "\u2705",
        "notes": "\U0001F4DD",
    }
    color_map = {
        "calls": COLORS['accent'],
        "emails": COLORS['accent2'],
        "meetings": COLORS['accent3'],
        "tasks": COLORS['accent4'],
        "notes": COLORS['accent5'],
    }

    sorted_types = sorted(by_type.items(), key=lambda x: x[1], reverse=True)[:5]
    num_cols = 1 + len(sorted_types)  # Total card + one per type
    html += f'<div class="kpi-grid" style="grid-template-columns:repeat({num_cols}, 1fr)">'
    html += _stat_card("Total Activities", _fmt_number(activity.get("total_activities", 0)),
                       f"{len(by_type)} types", "\u26A1", COLORS['accent6'])
    for act_type, count in sorted_types:
        icon = icon_map.get(act_type.lower(), "\U0001F4CB")
        color = color_map.get(act_type.lower(), COLORS['info'])
        html += _stat_card(act_type.title(), _fmt_number(count), "", icon, color)
    html += '</div>'

    # Activity Breakdown + Distribution donut + Trend -- 3-column row
    daily_trend = activity.get("daily_trend", [])
    by_rep = activity.get("by_rep", [])

    html += '<div style="display:grid;grid-template-columns:1fr auto 1fr;gap:16px;margin-top:8px">'
    html += f'''<div class="glass-card">
        <h3 class="card-title">Activity Breakdown <span style="font-size:11px;font-weight:400;color:{COLORS['text_muted']}">(filtered by period)</span></h3>
        <div id="dynamic-activity-breakdown"></div>
    </div>'''
    if by_type:
        type_segments = [(k.title(), v) for k, v in sorted(by_type.items(), key=lambda x: x[1], reverse=True)]
        html += f'''<div class="glass-card" style="min-width:180px">
            <h3 class="card-title">Distribution</h3>
            {_svg_donut(type_segments, 130)}
        </div>'''
    else:
        html += '<div></div>'
    if daily_trend:
        trend_data = [(item.get("date", ""), item.get("count", 0)) for item in daily_trend]
        html += f'''<div class="glass-card">
            <h3 class="card-title">Daily Trend <span style="font-size:11px;font-weight:400;color:{COLORS['text_muted']}">(30d)</span></h3>
            {_svg_line_chart(trend_data[-30:], 400, 140, COLORS['accent2'])}
        </div>'''
    else:
        html += f'''<div class="glass-card">
            <h3 class="card-title">Daily Trend</h3>
            <div style="text-align:center;padding:32px;color:{COLORS['text_muted']};font-size:14px">No trend data</div>
        </div>'''
    html += '</div>'

    # Activity by Rep -- full-width
    # Filter: only keep reps with actual names (not numeric IDs), exclude unassigned
    named_reps = [r for r in by_rep if r.get("owner_name", "").strip()
                  and not r.get("owner_name", "").strip().replace("-", "").isdigit()
                  and r.get("owner_name", "").strip().lower() != "unassigned"]
    REP_LIMIT = 10
    if named_reps:
        rep_rows_html = ""
        for i, rep in enumerate(named_reps):
            hidden_style = ' style="display:none"' if i >= REP_LIMIT else ''
            extra_cls = ' activity-rep-extra' if i >= REP_LIMIT else ''
            rep_rows_html += (
                f'<tr class="{extra_cls.strip()}"{hidden_style}>'
                f'<td>{_esc(rep.get("owner_name", "Unknown"))}</td>'
                f'<td>{_fmt_number(rep.get("calls", 0))}</td>'
                f'<td>{_fmt_number(rep.get("emails", 0))}</td>'
                f'<td>{_fmt_number(rep.get("meetings", 0))}</td>'
                f'<td>{_fmt_number(rep.get("tasks", 0))}</td>'
                f'<td>{_fmt_number(rep.get("notes", 0))}</td>'
                f'<td><strong>{_fmt_number(rep.get("total", 0))}</strong></td>'
                f'</tr>\n'
            )
        rep_show_more = ""
        if len(named_reps) > REP_LIMIT:
            remaining = len(named_reps) - REP_LIMIT
            rep_show_more = (
                f'<div style="text-align:center;padding:10px;border-top:1px solid {COLORS["card_border"]}">'
                f'<button id="act-rep-show-more" onclick="toggleExpandList(\'activity-rep-extra\',\'act-rep-show-more\',{len(named_reps)},{REP_LIMIT})"'
                f' style="background:none;border:1px solid {COLORS["card_border"]};border-radius:8px;'
                f'padding:6px 20px;color:{COLORS["accent2"]};font-size:12px;font-weight:600;'
                f'cursor:pointer">Show all {len(named_reps)} ({remaining} more)</button>'
                f'</div>'
            )
        header_cells = ''.join(
            f'<th style="cursor:pointer;user-select:none">{h}</th>'
            for h in ["Rep", "Calls", "Emails", "Meetings", "Tasks", "Notes", "Total"]
        )
        html += f'''<div class="glass-card" style="padding-bottom:0;margin-top:8px">
            <h3 class="card-title">Activity by Rep</h3>
            <div class="table-wrapper">
                <table id="activity_reps" class="data-table">
                    <thead><tr>{header_cells}</tr></thead>
                    <tbody>{rep_rows_html}</tbody>
                </table>
            </div>
            {rep_show_more}
        </div>'''
    else:
        html += f'''<div class="glass-card" style="margin-top:8px">
            <h3 class="card-title">Activity by Rep</h3>
            <div style="text-align:center;padding:32px;color:{COLORS['text_muted']};font-size:14px">No named reps found</div>
        </div>'''

    html += '</section>'
    return html


def _build_contacts_section(data: dict) -> str:
    """Section 7: Contacts & Companies."""
    contacts = _safe_get(data, "contact_metrics", default={})
    counts = _safe_get(data, "record_counts", default={})
    html = _section_header("contacts", "Contacts & Companies",
                           "Lifecycle stages, engagement, and company overview",
                           "\U0001F465")

    # KPIs (3-column row -- kept as-is)
    html += '<div class="kpi-grid kpi-grid-3">'
    html += _stat_card("Total Contacts", _fmt_number(counts.get("contacts", 0)),
                       f"New 30d: {_fmt_number(contacts.get('new_contacts_30d', 0))}",
                       "\U0001F465", COLORS['accent'])
    html += _stat_card("Companies", _fmt_number(counts.get("companies", 0)),
                       "", "\U0001F3E2", COLORS['accent2'])
    html += _stat_card("Owners/Reps", _fmt_number(counts.get("owners", 0)),
                       "", "\U0001F464", COLORS['accent3'])
    html += '</div>'

    # Lifecycle distribution -- filter out numeric-only keys, merged donut + bars
    lifecycle = contacts.get("by_lifecycle", {})
    named_lifecycle = {k: v for k, v in lifecycle.items() if not k.strip().isdigit()}
    if named_lifecycle:
        lc_segments = sorted(named_lifecycle.items(), key=lambda x: x[1], reverse=True)
        max_lc = max(named_lifecycle.values()) if named_lifecycle else 1
        bars_html = ""
        for stage, count in lc_segments:
            bars_html += _svg_horizontal_bar(stage, count, max_lc, COLORS['accent2'], show_pct=False)
        html += f'''<div class="glass-card" style="margin-top:8px">
            <h3 class="card-title">Lifecycle Distribution</h3>
            <div style="display:flex;gap:24px;align-items:flex-start">
                <div style="flex-shrink:0">{_svg_donut(lc_segments, 120)}</div>
                <div style="flex:1;min-width:0">{bars_html}</div>
            </div>
        </div>'''
    else:
        html += f'''<div class="glass-card" style="margin-top:8px">
            <h3 class="card-title">Lifecycle Distribution</h3>
            <div style="text-align:center;padding:32px;color:{COLORS['text_muted']};font-size:14px">
                No lifecycle data with named stages</div>
        </div>'''

    # Top engaged contacts -- first 5 visible, rest collapsible
    engaged = contacts.get("top_engaged", [])
    if engaged:
        CONTACT_LIMIT = 5
        contact_rows_html = ""
        for i, c in enumerate(engaged):
            hidden_style = ' style="display:none"' if i >= CONTACT_LIMIT else ''
            extra_cls = ' contacts-extra-row' if i >= CONTACT_LIMIT else ''
            contact_rows_html += (
                f'<tr class="{extra_cls.strip()}"{hidden_style}>'
                f'<td>{_esc(c.get("name", ""))}</td>'
                f'<td>{_esc(c.get("email", ""))}</td>'
                f'<td>{_fmt_number(c.get("page_views", 0))}</td>'
                f'<td>{_fmt_number(c.get("visits", 0))}</td>'
                f'<td>{_fmt_number(c.get("events", 0))}</td>'
                f'</tr>\n'
            )
        contact_show_more = ""
        if len(engaged) > CONTACT_LIMIT:
            remaining = len(engaged) - CONTACT_LIMIT
            contact_show_more = (
                f'<div style="text-align:center;padding:10px;border-top:1px solid {COLORS["card_border"]}">'
                f'<button id="engaged-show-more" onclick="toggleExpandList(\'contacts-extra-row\',\'engaged-show-more\',{len(engaged)},{CONTACT_LIMIT})"'
                f' style="background:none;border:1px solid {COLORS["card_border"]};border-radius:8px;'
                f'padding:6px 20px;color:{COLORS["accent2"]};font-size:12px;font-weight:600;'
                f'cursor:pointer">Show all {len(engaged)} ({remaining} more)</button>'
                f'</div>'
            )
        header_cells = ''.join(
            f'<th style="cursor:pointer;user-select:none">{h}</th>'
            for h in ["Name", "Email", "Page Views", "Visits", "Events"]
        )
        html += f'''<div class="glass-card" style="margin-top:8px;padding-bottom:0">
            <h3 class="card-title">Top Engaged Contacts</h3>
            <div class="table-wrapper">
                <table id="top_engaged" class="data-table">
                    <thead><tr>{header_cells}</tr></thead>
                    <tbody>{contact_rows_html}</tbody>
                </table>
            </div>
            {contact_show_more}
        </div>'''

    # Companies summary (compact)
    companies = contacts.get("companies_summary", {})
    if companies:
        if isinstance(companies, dict):
            # Summary object format: {total, with_deals, by_industry, by_size}
            html += f'''<div class="glass-card" style="margin-top:8px;padding:10px 14px">
                <h3 class="card-title" style="margin-bottom:6px">Companies Overview</h3>
                <div class="kpi-grid kpi-grid-3" style="gap:8px">'''
            html += _stat_card("Total", _fmt_number(companies.get("total", 0)), "", "", COLORS['accent2'])
            html += _stat_card("With Deals", _fmt_number(companies.get("with_deals", 0)), "", "", COLORS['accent3'])
            by_industry = companies.get("by_industry", {})
            if isinstance(by_industry, dict):
                top_industry = max(by_industry, key=by_industry.get, default="N/A") if by_industry else "N/A"
                html += _stat_card("Top Industry", _esc(str(top_industry)), "", "", COLORS['accent4'])
            html += '</div></div>'
        elif isinstance(companies, list):
            rows = []
            for co in companies[:15]:
                rows.append([
                    _esc(co.get("name", "")),
                    _esc(co.get("domain", "")),
                    _fmt_number(co.get("contacts", 0)),
                    _fmt_number(co.get("deals", 0)),
                    _fmt_currency(co.get("revenue", 0)),
                ])
            html += f'''<div class="glass-card" style="margin-top:8px;padding:10px 14px">
                <h3 class="card-title" style="margin-bottom:6px">Companies Summary</h3>
                {_data_table(["Company", "Domain", "Contacts", "Deals", "Revenue"],
                             rows, "companies")}
            </div>'''

    html += '</section>'
    return html


def _build_insights_section(data: dict) -> str:
    """Section 8: Insights & Forecast."""
    insights = _safe_get(data, "insights", default={})
    html = _section_header("insights", "Insights & Forecast",
                           "Win/loss analysis, forecasts, and performance",
                           "\U0001F52E")

    # Revenue forecast
    forecast = insights.get("revenue_forecast", {})
    if forecast:
        html += '<div class="kpi-grid kpi-grid-3">'
        html += _stat_card("30-Day Forecast", _fmt_currency(forecast.get("days_30", 0)),
                           "", "\U0001F4C5", COLORS['accent'])
        html += _stat_card("60-Day Forecast", _fmt_currency(forecast.get("days_60", 0)),
                           "", "\U0001F4C6", COLORS['accent2'])
        html += _stat_card("90-Day Forecast", _fmt_currency(forecast.get("days_90", 0)),
                           "", "\U0001F4C8", COLORS['accent4'])
        html += '</div>'

    # Win/Loss + Cycle Trend + Deal Size — 3-column row
    wl = insights.get("win_loss_analysis", {})
    cycle_trend = insights.get("sales_cycle_trend", {})
    if isinstance(cycle_trend, dict):
        trend_data = [(month, int(round(days))) for month, days in sorted(cycle_trend.items())]
    elif isinstance(cycle_trend, list):
        trend_data = [(item.get("month", ""), int(round(item.get("avg_days", 0)))) for item in cycle_trend]
    else:
        trend_data = []
    deal_sizes = insights.get("deal_size_distribution", {})
    if isinstance(deal_sizes, dict):
        size_data = [(range_str, count) for range_str, count in deal_sizes.items()]
    elif isinstance(deal_sizes, list):
        size_data = [(item.get("range", ""), item.get("count", 0)) for item in deal_sizes]
    else:
        size_data = []

    if wl or trend_data or size_data:
        html += '<div class="grid-3" style="margin-top:8px">'
        # Win/Loss (donut + reasons merged)
        if wl:
            reasons_html = ""
            won_reasons = wl.get("won_reasons", {})
            lost_reasons = wl.get("lost_reasons", {})
            if won_reasons:
                reasons_html += f'<h4 style="font-size:11px;color:{COLORS["accent4"]};margin:6px 0 2px;text-transform:uppercase">Won</h4>'
                if isinstance(won_reasons, dict):
                    for reason, count in sorted(won_reasons.items(), key=lambda x: x[1], reverse=True)[:3]:
                        reasons_html += f'<div style="font-size:12px;padding:2px 0;color:{COLORS["text_muted"]}">{_esc(reason)}: <strong style="color:{COLORS["text"]}">{_fmt_number(count)}</strong></div>'
                elif isinstance(won_reasons, list):
                    for item in won_reasons[:3]:
                        reasons_html += f'<div style="font-size:12px;padding:2px 0;color:{COLORS["text_muted"]}">{_esc(str(item))}</div>'
            if lost_reasons:
                reasons_html += f'<h4 style="font-size:11px;color:{COLORS["danger"]};margin:6px 0 2px;text-transform:uppercase">Lost</h4>'
                if isinstance(lost_reasons, dict):
                    for reason, count in sorted(lost_reasons.items(), key=lambda x: x[1], reverse=True)[:3]:
                        reasons_html += f'<div style="font-size:12px;padding:2px 0;color:{COLORS["text_muted"]}">{_esc(reason)}: <strong style="color:{COLORS["text"]}">{_fmt_number(count)}</strong></div>'
                elif isinstance(lost_reasons, list):
                    for item in lost_reasons[:3]:
                        reasons_html += f'<div style="font-size:12px;padding:2px 0;color:{COLORS["text_muted"]}">{_esc(str(item))}</div>'
            html += f'''<div class="glass-card">
                <h3 class="card-title">Win/Loss Analysis</h3>
                <div style="display:flex;gap:16px;align-items:flex-start">
                    <div style="flex-shrink:0">
                        {_svg_donut([("Won", wl.get("won_count", 0)), ("Lost", wl.get("lost_count", 0))], 100)}
                        <div style="text-align:center;margin-top:4px;font-size:13px;color:{COLORS['text']}">
                            Win Rate: <strong style="color:{COLORS['accent4']}">{_fmt_pct(wl.get("win_rate", 0))}</strong>
                        </div>
                    </div>
                    <div style="flex:1;min-width:0">{reasons_html}</div>
                </div>
            </div>'''
        else:
            html += '<div></div>'
        # Sales Cycle Trend
        if trend_data:
            html += f'''<div class="glass-card">
                <h3 class="card-title">Sales Cycle Trend (Days)</h3>
                {_svg_line_chart(trend_data, 400, 140, COLORS['accent3'])}
            </div>'''
        else:
            html += '<div></div>'
        # Deal Size Distribution
        if size_data:
            html += f'''<div class="glass-card">
                <h3 class="card-title">Deal Size Distribution</h3>
                {_svg_bar_chart(size_data, 400, max(130, len(size_data) * 26))}
            </div>'''
        else:
            html += '<div></div>'
        html += '</div>'

    # Rep performance leaderboard
    rep_perf = insights.get("rep_performance", [])
    if rep_perf:
        # Filter out reps whose name is numeric (e.g. owner IDs without names)
        named_reps = [r for r in rep_perf if r.get("name", "").strip() and not r.get("name", "").strip().replace("-", "").isdigit()]
        if named_reps:
            rows = []
            for i, rep in enumerate(sorted(named_reps, key=lambda x: x.get("total_won_value", 0), reverse=True)):
                medal = ["\U0001F947", "\U0001F948", "\U0001F949"][i] if i < 3 else f"#{i+1}"
                raw_cycle = rep.get("avg_cycle_days")
                if raw_cycle is not None and raw_cycle != "":
                    try:
                        cycle_str = str(int(round(float(raw_cycle))))
                    except (ValueError, TypeError):
                        cycle_str = "N/A"
                else:
                    cycle_str = "N/A"
                rows.append([
                    f"{medal} {_esc(rep.get('name', 'Unknown'))}",
                    _fmt_number(rep.get("deals_won", 0)),
                    _fmt_number(rep.get("deals_lost", 0)),
                    _fmt_currency(rep.get("total_won_value", 0)),
                    _fmt_currency(rep.get("total_pipeline_value", 0)),
                    _fmt_pct(rep.get("win_rate", 0)),
                    cycle_str,
                ])
            html += f'''<div class="glass-card" style="margin-top:8px">
                <h3 class="card-title">Rep Performance Leaderboard</h3>
                {_data_table(["Rep", "Won", "Lost", "Revenue", "Pipeline", "Win Rate", "Avg Cycle (Days)"],
                             rows, "rep_perf")}
            </div>'''

    # Cohort analysis
    cohorts = insights.get("cohort_analysis", [])
    if cohorts:
        rows = []
        for c in cohorts:
            rows.append([
                _esc(c.get("cohort_month", "")),
                _fmt_number(c.get("total_leads", 0)),
                _fmt_number(c.get("became_mql", 0)),
                _fmt_number(c.get("became_sql", 0)),
                _fmt_number(c.get("became_customer", 0)),
                _fmt_pct(c.get("conversion_rate", 0)),
            ])
        html += f'''<div class="glass-card" style="margin-top:8px">
            <h3 class="card-title">Cohort Analysis</h3>
            {_data_table(["Cohort", "Leads", "MQL", "SQL", "Customer", "Conv. Rate"],
                         rows, "cohorts")}
        </div>'''

    html += '</section>'
    return html


# ---------------------------------------------------------------------------
# Section 9: Monday.com — M&A Projects & IC Scores
# ---------------------------------------------------------------------------

MONDAY_PURPLE = "#6C6CFF"
MONDAY_RED = "#F44336"
MONDAY_YELLOW = "#FFCB00"
MONDAY_GREEN = "#00CA72"

# Dormancy cutoff: items not updated in this many months are considered dormant
DORMANCY_MONTHS = 5


def _is_dormant(updated_at_str: str, months: int = DORMANCY_MONTHS) -> bool:
    """Check if an item hasn't been updated in the last N months."""
    if not updated_at_str:
        return True  # no date = treat as dormant
    try:
        from datetime import datetime, timezone, timedelta
        # Parse ISO date string
        dt_str = updated_at_str[:19].replace("T", " ")
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(dt_str, fmt).replace(tzinfo=timezone.utc)
                cutoff = datetime.now(timezone.utc) - timedelta(days=months * 30)
                return dt < cutoff
            except ValueError:
                continue
        return True
    except Exception:
        return True


def _monday_stage_badge(stage: str) -> str:
    """Return an HTML stage badge with color coding."""
    s = stage.lower()
    if "ic" in s:
        bg, fg = f"{MONDAY_PURPLE}33", MONDAY_PURPLE
    elif any(x in s for x in ["diligence", "negotiation", "closing", "approved"]):
        bg, fg = f"{MONDAY_GREEN}33", MONDAY_GREEN
    elif any(x in s for x in ["hold", "stuck", "passed", "rejected"]):
        bg, fg = f"{MONDAY_RED}33", MONDAY_RED
    elif any(x in s for x in ["completed", "closed"]):
        bg, fg = f"{MONDAY_GREEN}55", MONDAY_GREEN
    else:
        bg, fg = f"{MONDAY_YELLOW}33", MONDAY_YELLOW
    label = _esc(stage.replace("_", " ").title())
    return (f'<span style="display:inline-block;padding:2px 8px;border-radius:10px;'
            f'font-size:11px;background:{bg};color:{fg}">{label}</span>')


def _classify_ic_stage(status_text: str) -> str:
    """Classify a raw status string into a deal flow stage key for IC filtering."""
    if not status_text:
        return "unknown"
    s = status_text.lower().strip()
    stage_map = [
        ("identified", ["identified", "new", "prospect"]),
        ("screening", ["screen", "initial review", "gate 0", "im received", "pending info",
                        "pending nda", "disqualified im"]),
        ("due diligence", ["diligence", "dd", "pending scorecard"]),
        ("ic review", ["ic review", "ic pending", "scorecard", "assess", "evaluat", "gate 1",
                        "gate 2", "gate 3"]),
        ("ic approved", ["ic approved", "approved"]),
        ("negotiation", ["negotiat", "heads of terms", "hots", "loi", "offer", "contract"]),
        ("closing", ["closing", "close"]),
        ("completed", ["completed", "done", "won"]),
        ("on hold", ["hold", "pause", "wait", "stuck"]),
        ("passed", ["pass", "reject", "dead", "lost", "declined", "failed", "unsuccessful",
                     "retract", "disqualif"]),
    ]
    for stage_key, keywords in stage_map:
        if any(kw in s for kw in keywords):
            return stage_key
    return "screening"  # default to screening for unclassified M&A items


def _build_monday_pipeline(data: dict) -> str:
    """M&A Pipeline page — KPIs, deal funnel, board-style project table, stale warnings, owner summary."""
    monday = data.get("monday", {})
    if not monday:
        return '<section class="dashboard-section"><div class="glass-card" style="padding:40px;text-align:center;color:#6b7280"><p>No Monday.com data available. Run fetch_monday.py and monday_analyzer.py first.</p></div></section>'

    ma = monday.get("ma_metrics", {})
    overview = monday.get("board_overview", {})

    html = _section_header(
        "monday-pipeline", "M&A Pipeline",
        "Monday.com project tracking — active deals, pipeline stages, and owner workloads (dormant items hidden)",
        "\U0001F4BC",
    )

    # ── Deal Flow Navigation ──
    deal_flow_stages = [
        ("Identified", "#3CB4AD"),
        ("Initial Review", "#3CB4AD"),
        ("Screening", "#334FB4"),
        ("NDA Signed", "#334FB4"),
        ("Info Requested", "#a78bfa"),
        ("Due Diligence", "#a78bfa"),
        ("LOI", "#f59e0b"),
        ("IC Review", "#6C6CFF"),
        ("IC Approved", "#22c55e"),
        ("Negotiation", "#f59e0b"),
        ("Contract", "#ef4444"),
        ("Closing", "#34d399"),
        ("Completed", "#22c55e"),
    ]
    flow_html = '<div class="glass-card" style="margin-bottom:10px;padding:10px 14px">'
    flow_html += f'<div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.06em;color:{COLORS["text_muted"]};margin-bottom:10px">Deal Flow — Order of Events</div>'
    flow_html += '<div class="deal-flow-nav">'
    for i, (stage_name, stage_color) in enumerate(deal_flow_stages):
        flow_html += f'''<div class="deal-flow-step">
            <span class="step-dot" style="background:{stage_color}">{i + 1}</span>
            <span class="step-label">{stage_name}</span>'''
        if i < len(deal_flow_stages) - 1:
            flow_html += '<span class="step-arrow">&#8594;</span>'
        flow_html += '</div>'
    flow_html += '</div></div>'
    html += flow_html

    # ── Filter out dormant projects and sort by recency ──
    MA_OWNERS = {"josh elliott", "josie greenwood"}
    projects = ma.get("projects", [])
    # Remove dormant (5+ months no update)
    fresh_projects = [p for p in projects if not _is_dormant(p.get("updated_at", ""))]
    # Sort by most recently updated
    fresh_projects.sort(key=lambda p: p.get("updated_at") or "", reverse=True)
    # Filter active list to relevant M&A owners only
    active_list = [p for p in fresh_projects if p.get("is_active")
                   and p.get("owner", "").lower().strip() in MA_OWNERS]
    dormant_count = len(projects) - len(fresh_projects)

    # ── KPI row ──
    total_projects = len(fresh_projects)
    active_projects = len(active_list)
    total_value = sum(p.get("value", 0) for p in active_list)
    avg_stale = ma.get("avg_days_since_update", 0)

    html += '<div class="kpi-grid kpi-grid-3">'
    html += _stat_card("Active Projects", _fmt_number(active_projects),
                       f"{total_projects} total ({dormant_count} dormant hidden)", "\U0001F4C1", MONDAY_PURPLE)
    html += _stat_card("Pipeline Value", _fmt_currency(total_value),
                       f"Across {active_projects} active deals", "\U0001F4B0", MONDAY_GREEN)
    html += _stat_card("Avg Days Since Update", _fmt_number(avg_stale),
                       "Active projects",
                       "\u23F1\uFE0F",
                       MONDAY_YELLOW if avg_stale < 7 else MONDAY_RED)
    html += '</div>'

    # ── Search & Filter Bar ──
    html += f'''<div class="glass-card" style="margin-top:8px;padding:12px 16px">
        <div style="display:flex;flex-wrap:wrap;gap:10px;align-items:center">
            <input type="text" id="monday-search" placeholder="Search projects, owners, boards..."
                style="flex:1;min-width:200px;padding:8px 12px;border:1px solid {COLORS['card_border']};
                border-radius:8px;background:{COLORS['bg']};color:{COLORS['text']};font-size:13px;
                outline:none" oninput="filterMonday()">
            <select id="monday-filter-owner" onchange="filterMonday()"
                style="padding:8px 12px;border:1px solid {COLORS['card_border']};border-radius:8px;
                background:{COLORS['bg']};color:{COLORS['text']};font-size:13px">
                <option value="">All Owners</option>
            </select>
            <select id="monday-filter-stage" onchange="filterMonday()"
                style="padding:8px 12px;border:1px solid {COLORS['card_border']};border-radius:8px;
                background:{COLORS['bg']};color:{COLORS['text']};font-size:13px">
                <option value="">All Stages</option>
            </select>
            <label style="display:flex;align-items:center;gap:4px;font-size:12px;color:{COLORS['text_muted']};cursor:pointer">
                <input type="checkbox" id="monday-hide-unassigned" onchange="filterMonday()"> Hide unassigned
            </label>
        </div>
    </div>'''

    # ── M&A Pipeline Funnel ──
    funnel = ma.get("funnel", [])
    if funnel:
        active_funnel = [s for s in funnel if s.get("count", 0) > 0]
        if active_funnel:
            max_count = max(s.get("count", 0) for s in active_funnel) or 1
            funnel_html = ""
            stage_colors = [MONDAY_PURPLE, "#7B61FF", "#9B8AFF", COLORS['accent2'],
                            COLORS['info'], MONDAY_GREEN, COLORS['accent4'],
                            COLORS['accent'], MONDAY_YELLOW]
            for i, stage in enumerate(active_funnel):
                name = stage.get("stage", "").replace("_", " ").title()
                count = stage.get("count", 0)
                value = stage.get("value", 0)
                pct = (count / max_count) * 100
                color = stage_colors[i % len(stage_colors)]
                funnel_html += f'''<div style="margin-bottom:10px">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
                        <span style="font-size:13px;color:{COLORS['text_muted']};text-transform:capitalize">{_esc(name)}</span>
                        <span style="font-size:13px;font-weight:600;color:{COLORS['text']}">{_fmt_number(count)} deals &middot; {_fmt_currency(value)}</span>
                    </div>
                    <div style="height:24px;background:{COLORS['card_border']};border-radius:6px;overflow:hidden">
                        <div class="progress-fill" style="height:100%;width:{pct:.1f}%;
                            background:linear-gradient(90deg,{color},{color}88);border-radius:6px"></div>
                    </div>
                </div>'''

            html += f'''<div class="glass-card" style="margin-top:8px">
                <h3 class="card-title" style="display:flex;align-items:center;gap:8px">
                    <span style="color:{MONDAY_PURPLE}">\U0001F3E2</span> Deal Pipeline by Stage
                </h3>
                {funnel_html}
            </div>'''

    # ── Board-style Active Projects (sorted by recency, show 10) ──
    if active_list:
        # Stage color mapping
        stage_color_map = {
            "ic_review": MONDAY_PURPLE,
            "due_diligence": COLORS['accent2'],
            "negotiation": COLORS['info'],
            "approved": MONDAY_GREEN,
            "closing": MONDAY_GREEN,
            "completed": "#22c55e",
            "on_hold": MONDAY_YELLOW,
            "passed": MONDAY_RED,
            "rejected": MONDAY_RED,
        }
        avatar_colors = ["#6C3CE1", "#0073EA", "#00CA72", "#FDAB3D",
                         "#E2445C", "#A25DDC", "#579BFC", "#CAB641"]

        SHOW_LIMIT = 10
        board_html = '<div class="board-container">'
        board_html += '''<div class="board-header-row">
            <div>Project</div>
            <div>Stage</div>
            <div>Value</div>
            <div>Owner</div>
            <div>Workspace</div>
            <div>Tasks</div>
            <div>Updated</div>
        </div>'''

        for idx, p in enumerate(active_list):
            name = _esc(p.get("name", "Unknown"))
            stage = p.get("stage", "")
            value = _fmt_currency(p.get("value", 0))
            owner = _esc(p.get("owner", "Unassigned"))
            ws = _esc(p.get("workspace", ""))
            updated = p.get("updated_at", "")[:10] if p.get("updated_at") else "N/A"
            si_count = p.get("subitems_count", 0)
            si_done = p.get("subitems_complete", 0)
            has_owner = "1" if p.get("has_owner") else "0"
            group_color = stage_color_map.get(stage, COLORS['accent'])

            initials = "".join(w[0] for w in owner.split()[:2]).upper() if owner != "Unassigned" else "?"
            av_color = avatar_colors[hash(owner) % len(avatar_colors)]

            if si_count > 0:
                pct = min(100, (si_done / si_count) * 100)
                prog_color = MONDAY_GREEN if pct >= 75 else (MONDAY_YELLOW if pct >= 40 else COLORS['text_muted'])
                progress_html = f'''<div class="progress-mini">
                    <div class="bar"><div class="bar-fill" style="width:{pct:.0f}%;background:{prog_color}"></div></div>
                    <span class="pct">{si_done}/{si_count}</span>
                </div>'''
            else:
                progress_html = f'<span style="color:{COLORS["text_muted"]};font-size:11px">-</span>'

            # Hide items beyond the first 10
            hidden = ' style="display:none"' if idx >= SHOW_LIMIT else ''
            extra_class = ' pipeline-extra-row' if idx >= SHOW_LIMIT else ''

            board_html += (
                f'<div class="board-row monday-row{extra_class}" data-owner="{owner}" data-stage="{_esc(stage)}" '
                f'data-name="{name}" data-ws="{ws}" data-has-owner="{has_owner}"{hidden}>'
                f'<div style="display:flex;align-items:center;gap:8px">'
                f'<div style="width:4px;height:24px;border-radius:2px;background:{group_color};flex-shrink:0"></div>'
                f'<span style="font-weight:500;color:{COLORS["text"]}">{name}</span></div>'
                f'<div>{_monday_stage_badge(stage)}</div>'
                f'<div style="font-weight:600">{value}</div>'
                f'<div class="person-avatar">'
                f'<span class="avatar-circle" style="background:{av_color}">{initials}</span>'
                f'<span>{owner}</span></div>'
                f'<div style="font-size:12px;color:{COLORS["text_muted"]}">{ws}</div>'
                f'<div>{progress_html}</div>'
                f'<div style="font-size:12px;color:{COLORS["text_muted"]}">{updated}</div>'
                f'</div>'
            )

        board_html += '</div>'

        # Show more button
        show_more_btn = ""
        if len(active_list) > SHOW_LIMIT:
            remaining = len(active_list) - SHOW_LIMIT
            show_more_btn = f'''<div style="text-align:center;padding:12px;border-top:1px solid {COLORS['card_border']}">
                <button id="pipeline-show-more" onclick="toggleExpandList('pipeline-extra-row','pipeline-show-more',{len(active_list)},{SHOW_LIMIT})"
                    style="background:none;border:1px solid {COLORS['card_border']};border-radius:8px;
                    padding:8px 24px;color:{COLORS['accent2']};font-size:13px;font-weight:600;
                    cursor:pointer;transition:all 0.2s ease">
                    Show all {len(active_list)} projects ({remaining} more)
                </button>
            </div>'''

        html += f'''<div class="glass-card" style="margin-top:8px;padding:0;overflow:hidden">
            <div style="padding:10px 14px;border-bottom:1px solid {COLORS['card_border']}">
                <h3 class="card-title" style="margin-bottom:0">\U0001F3AF Active M&A Projects
                    <span id="monday-count" style="font-size:13px;font-weight:400;color:{COLORS['text_muted']}">
                        ({len(active_list)} — showing {min(SHOW_LIMIT, len(active_list))})
                    </span>
                </h3>
                <p style="font-size:11px;color:{COLORS['text_muted']};margin-top:4px">Sorted by most recently updated &middot; {dormant_count} dormant items hidden</p>
            </div>
            {board_html}
            {show_more_btn}
        </div>'''

    # ── Previous Projects (closed/completed/unsuccessful) ──
    stale = ma.get("stale_projects", [])
    stale.sort(key=lambda sp: sp.get("days_stale", 0), reverse=True)
    stale = [sp for sp in stale if sp.get("days_stale", 0) < DORMANCY_MONTHS * 30]
    if stale:
        STALE_LIMIT = 5
        stale_html = ""
        for i, sp in enumerate(stale):
            days = sp.get("days_stale", 0)
            urgency_color = MONDAY_RED if days > 21 else MONDAY_YELLOW
            hidden = ' style="display:none"' if i >= STALE_LIMIT else ''
            extra_cls = ' stale-extra-row' if i >= STALE_LIMIT else ''
            stale_html += f'''<div class="stale-item{extra_cls}" {hidden if i >= STALE_LIMIT else ''}>
                <div style="display:flex;justify-content:space-between;align-items:center;
                    padding:8px 12px;border-bottom:1px solid {COLORS['card_border']}">
                    <div>
                        <span style="font-size:12px;color:{COLORS['text']};font-weight:500">{_esc(sp.get("name", ""))}</span>
                        <span style="font-size:10px;color:{COLORS['text_muted']};margin-left:8px">{_esc(sp.get("stage", "").title())}</span>
                    </div>
                    <span style="font-size:11px;font-weight:600;color:{urgency_color}">{days}d</span>
                </div>
            </div>'''
        stale_more = ""
        if len(stale) > STALE_LIMIT:
            remaining = len(stale) - STALE_LIMIT
            stale_more = f'''<div style="text-align:center;padding:8px">
                <button id="stale-show-more" onclick="toggleExpandList('stale-extra-row','stale-show-more',{len(stale)},{STALE_LIMIT})"
                    style="background:none;border:1px solid {COLORS['card_border']};border-radius:8px;
                    padding:5px 16px;color:{COLORS['text_muted']};font-size:11px;font-weight:600;
                    cursor:pointer">Show all {len(stale)} ({remaining} more)</button>
            </div>'''
        html += f'''<div class="glass-card" style="margin-top:8px">
            <h3 class="card-title">Previous Projects ({len(stale)})</h3>
            <p style="font-size:11px;color:{COLORS['text_muted']};margin-bottom:6px">Closed, completed, or inactive — no updates in 14+ days</p>
            {stale_html}
            {stale_more}
        </div>'''

    # ── Filter and board toggle JavaScript ──
    html += '''<script>
    (function(){
        var rows = document.querySelectorAll('.monday-row');
        var owners = new Set(), stages = new Set();
        rows.forEach(function(r){
            var o = r.getAttribute('data-owner');
            var s = r.getAttribute('data-stage');
            if(o && o !== 'Unassigned') owners.add(o);
            if(s) stages.add(s);
        });
        var ownerSel = document.getElementById('monday-filter-owner');
        var stageSel = document.getElementById('monday-filter-stage');
        if(ownerSel){
            Array.from(owners).sort().forEach(function(o){
                var opt = document.createElement('option');
                opt.value = o; opt.textContent = o;
                ownerSel.appendChild(opt);
            });
        }
        if(stageSel){
            Array.from(stages).sort().forEach(function(s){
                var opt = document.createElement('option');
                opt.value = s;
                opt.textContent = s.replace(/_/g,' ').replace(/\\b\\w/g,function(l){return l.toUpperCase()});
                stageSel.appendChild(opt);
            });
        }
    })();
    function filterMonday(){
        var q = (document.getElementById('monday-search').value || '').toLowerCase();
        var owner = document.getElementById('monday-filter-owner').value;
        var stage = document.getElementById('monday-filter-stage').value;
        var hideUnassigned = document.getElementById('monday-hide-unassigned').checked;
        var rows = document.querySelectorAll('.monday-row');
        var visible = 0;
        rows.forEach(function(r){
            var show = true;
            if(q){
                var text = (r.getAttribute('data-name')||'') + ' ' +
                           (r.getAttribute('data-owner')||'') + ' ' +
                           (r.getAttribute('data-ws')||'') + ' ' +
                           (r.getAttribute('data-stage')||'');
                if(text.toLowerCase().indexOf(q) === -1) show = false;
            }
            if(owner && r.getAttribute('data-owner') !== owner) show = false;
            if(stage && r.getAttribute('data-stage') !== stage) show = false;
            if(hideUnassigned && r.getAttribute('data-has-owner') === '0') show = false;
            r.style.display = show ? '' : 'none';
            if(show) visible++;
        });
        var countEl = document.getElementById('monday-count');
        if(countEl) countEl.textContent = '(' + visible + ')';
    }
    window.toggleBoardGroup = function(id){
        var el = document.getElementById(id);
        var arrow = document.getElementById(id + '_arrow');
        if(!el) return;
        if(el.style.display === 'none'){
            el.style.display = 'block';
            if(arrow) arrow.classList.add('expanded');
        } else {
            el.style.display = 'none';
            if(arrow) arrow.classList.remove('expanded');
        }
    };
    window.toggleExpandList = function(extraClass, btnId, total, limit) {
        var extras = document.querySelectorAll('.' + extraClass);
        var btn = document.getElementById(btnId);
        if (!btn) return;
        var isExpanded = btn.getAttribute('data-expanded') === '1';
        extras.forEach(function(el) {
            el.style.display = isExpanded ? 'none' : '';
        });
        if (isExpanded) {
            btn.textContent = 'Show all ' + total + ' (' + (total - limit) + ' more)';
            btn.setAttribute('data-expanded', '0');
        } else {
            btn.textContent = 'Show less (collapse to ' + limit + ')';
            btn.setAttribute('data-expanded', '1');
        }
    };
    </script>'''

    html += '</section>'
    return html


def _build_monday_ic(data: dict) -> str:
    """IC Scorecards page — Gate score breakdowns, category scores, trend, decision distribution."""
    monday = data.get("monday", {})
    if not monday:
        return '<section class="dashboard-section"><div class="glass-card" style="padding:40px;text-align:center;color:#6b7280"><p>No Monday.com data available.</p></div></section>'

    ic = monday.get("ic_metrics", {})

    html = _section_header(
        "monday-ic", "IC Scorecards",
        "Investment Committee scoring — gate scores, trends, and decision tracking (dormant items hidden)",
        "\U0001F4CB",
    )

    # ── IC Deal Flow Filter Buttons ──
    ic_flow_stages = [
        ("all", "All", "#6b7280"),
        ("identified", "Identified", "#3CB4AD"),
        ("screening", "Screening", "#334FB4"),
        ("due diligence", "Due Diligence", "#a78bfa"),
        ("ic review", "IC Review", "#6C6CFF"),
        ("ic approved", "IC Approved", "#22c55e"),
        ("negotiation", "Negotiation", "#f59e0b"),
        ("closing", "Closing", "#34d399"),
        ("completed", "Completed", "#22c55e"),
        ("on hold", "On Hold", "#f59e0b"),
        ("passed", "Passed", "#ef4444"),
    ]
    ic_flow_html = f'<div class="glass-card" style="margin-bottom:10px;padding:10px 14px">'
    ic_flow_html += f'<div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:12px">'
    ic_flow_html += '<div style="flex:1;min-width:300px">'
    ic_flow_html += f'<div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.06em;color:{COLORS["text_muted"]};margin-bottom:10px">IC Gate Progression — Click to Filter</div>'
    ic_flow_html += '<div style="display:flex;flex-wrap:wrap;gap:6px;align-items:center">'
    for i, (stage_key, stage_label, stage_color) in enumerate(ic_flow_stages):
        is_all = stage_key == "all"
        active_cls = ' ic-stage-active' if is_all else ''
        ic_flow_html += (
            f'<button class="ic-stage-btn{active_cls}" data-ic-filter="{stage_key}" '
            f'onclick="filterICStage(\'{stage_key}\')" '
            f'style="display:inline-flex;align-items:center;gap:5px;padding:6px 14px;'
            f'border-radius:20px;font-size:12px;font-weight:600;cursor:pointer;'
            f'transition:all 0.2s ease;font-family:inherit;white-space:nowrap;'
            f'border:1px solid {COLORS["card_border"]};background:{COLORS["card"]};color:{COLORS["text_muted"]}">'
        )
        if not is_all:
            ic_flow_html += (
                f'<span style="width:8px;height:8px;border-radius:50%;background:{stage_color};'
                f'flex-shrink:0;display:inline-block"></span>'
            )
        ic_flow_html += f'{stage_label}'
        ic_flow_html += f'<span class="ic-stage-count" data-stage-count="{stage_key}" '
        ic_flow_html += f'style="font-size:10px;opacity:0.7"></span>'
        ic_flow_html += '</button>'
        # Add arrow separator between non-"all" stages (except last)
        if not is_all and i < len(ic_flow_stages) - 1 and ic_flow_stages[i + 1][0] != "on hold":
            ic_flow_html += f'<span style="color:#d1d5db;font-size:12px">&#8594;</span>'
        elif stage_key == "ic approved":
            ic_flow_html += f'<span style="color:#d1d5db;font-size:12px;margin:0 2px">|</span>'
    ic_flow_html += '</div></div>'
    # IC Scorecard data source info
    ic_flow_html += f'''<div style="text-align:right;font-size:11px;color:{COLORS["text_muted"]};flex-shrink:0">
        <div style="font-weight:600;margin-bottom:2px">IC Scorecard Data</div>
        <div>Source: Monday.com M&amp;A Boards</div>
        <div>Metrics: <a href="javascript:void(0)" onclick="window.open('data/processed/monday_metrics.json','_blank')"
            style="color:{COLORS["accent"]};text-decoration:none">monday_metrics.json</a></div>
        <div id="ic-filter-status" style="margin-top:6px;font-weight:600;color:{COLORS["accent"]}"></div>
    </div>'''
    ic_flow_html += '</div></div>'
    html += ic_flow_html

    # ── Filter & sort IC items ──
    top_scored = ic.get("top_scored", [])
    # Filter out dormant IC items
    top_scored = [s for s in top_scored if not _is_dormant(s.get("updated_at") or s.get("created_at") or "")]
    # Sort by most recently updated
    top_scored.sort(key=lambda s: s.get("updated_at") or s.get("created_at") or "", reverse=True)

    dormant_ic = ic.get("total_scored_items", 0) - len(top_scored)

    # ── IC KPI row ──
    ic_stats = ic.get("score_statistics", {})
    ic_avg = ic_stats.get("avg", 0)
    ic_max = ic_stats.get("max", 0)
    ic_min = ic_stats.get("min", 0)
    decisions = ic.get("decision_distribution", {})
    total_decisions = sum(decisions.values()) if decisions else 0

    html += '<div class="kpi-grid kpi-grid-3">'
    html += _stat_card("IC Scored Items", _fmt_number(len(top_scored)),
                       f"Avg: {ic_avg:.1f} | {dormant_ic} dormant hidden", "\U0001F4CB", MONDAY_PURPLE)
    html += _stat_card("Average IC Score", f"{ic_avg:.1f}",
                       f"Range: {ic_min:.1f} — {ic_max:.1f}", "\U0001F4CA", COLORS['accent2'])
    html += _stat_card("IC Decisions", _fmt_number(total_decisions),
                       f"{len(decisions)} outcome types", "\U0001F3DB\uFE0F", COLORS['accent4'])
    html += '</div>'

    # ── IC Scorecard with Gate Breakdown + Expandable Project Detail ──
    if top_scored:
        max_score = max(s.get("total_score", 0) for s in top_scored) or 1
        IC_LIMIT = 10

        board_html = '<div class="board-container">'
        board_html += f'''<div class="board-header-row" style="grid-template-columns:2fr 70px 110px 1fr 90px 70px 20px">
            <div>Project</div>
            <div>Score</div>
            <div>Status</div>
            <div>Gate Scores</div>
            <div>Owner</div>
            <div>Updated</div>
            <div></div>
        </div>'''

        # Count items per stage for the filter button badges
        ic_stage_counts: Dict[str, int] = {}
        for item in top_scored:
            stage = _classify_ic_stage(item.get("status", ""))
            ic_stage_counts[stage] = ic_stage_counts.get(stage, 0) + 1

        for idx, item in enumerate(top_scored):
            name = _esc(item.get("name", "Unknown"))
            total = item.get("total_score", 0)
            avg = item.get("avg_score", 0)
            status = _esc(item.get("status", ""))
            owner = _esc(item.get("owner", "Unassigned"))
            pct = (total / max_score) * 100
            score_color = MONDAY_GREEN if pct >= 70 else (MONDAY_YELLOW if pct >= 40 else MONDAY_RED)
            ic_stage = _classify_ic_stage(item.get("status", ""))
            detail_id = f"ic_detail_{idx}"
            updated_short = (item.get("updated_at") or "")[:10]

            scores = item.get("scores", {})
            gate_html = ""
            for gate_name, gate_val in sorted(scores.items()):
                g_pct = min(100, gate_val * 10)
                g_color = MONDAY_GREEN if g_pct >= 70 else (MONDAY_YELLOW if g_pct >= 40 else MONDAY_RED)
                gate_html += (
                    f'<span class="status-pill" style="background:{g_color}22;color:{g_color};'
                    f'min-width:auto;padding:2px 6px;margin:1px 2px;font-size:10px">'
                    f'{_esc(gate_name[:10])}: {gate_val:.1f}</span>'
                )

            bar_html = f'''<div style="display:flex;align-items:center;gap:4px">
                <span style="font-weight:700;color:{score_color};font-size:13px">{total:.1f}</span>
                <div style="flex:1;height:4px;background:{COLORS['card_border']};border-radius:2px;overflow:hidden;max-width:36px">
                    <div style="height:100%;width:{pct:.0f}%;background:{score_color};border-radius:2px"></div>
                </div>
            </div>'''

            extra_cls = ' ic-extra-row' if idx >= IC_LIMIT else ''

            board_html += (
                f'<div class="board-row ic-row{extra_cls}" data-ic-stage="{ic_stage}" '
                f'onclick="toggleICDetail(\'{detail_id}\')" '
                f'style="grid-template-columns:2fr 70px 110px 1fr 90px 70px 20px'
                f'{";display:none" if idx >= IC_LIMIT else ""}">'
                f'<div style="font-weight:500;color:{COLORS["text"]}">'
                f'{name}<span style="font-size:10px;color:{COLORS["text_muted"]};margin-left:6px">(avg {avg:.1f})</span></div>'
                f'<div>{bar_html}</div>'
                f'<div>{_monday_stage_badge(status) if status else "<span style=\'color:#64748b\'>—</span>"}</div>'
                f'<div style="display:flex;flex-wrap:wrap;gap:2px">{gate_html}</div>'
                f'<div style="font-size:11px;color:{COLORS["text_muted"]}">{owner}</div>'
                f'<div style="font-size:10px;color:{COLORS["text_muted"]}">{updated_short}</div>'
                f'<div class="ic-expand-arrow" id="{detail_id}_arrow">&#9654;</div>'
                f'</div>'
            )

            # ── Expandable Project Detail Panel ──
            columns = item.get("columns", {})
            updates = item.get("updates", [])
            subitems = item.get("subitems", [])
            decisions = item.get("decisions", {})
            group = item.get("group", "")
            created = (item.get("created_at") or "")[:10]
            updated = (item.get("updated_at") or "")[:10]

            # Column values (non-score, meaningful)
            skip_cols = set(scores.keys()) | {""}
            col_rows = ""
            for col_title, col_val in columns.items():
                if col_title in skip_cols or len(col_val) > 200:
                    continue
                col_rows += f'''<div class="ic-detail-row">
                    <span class="label">{_esc(col_title)}</span>
                    <span class="value">{_esc(col_val[:80])}</span>
                </div>'''
            if group:
                col_rows = f'''<div class="ic-detail-row">
                    <span class="label">Group</span>
                    <span class="value">{_esc(group)}</span>
                </div>''' + col_rows
            col_rows += f'''<div class="ic-detail-row">
                <span class="label">Board</span>
                <span class="value">{_esc(item.get("board", ""))}</span>
            </div>'''
            if created:
                col_rows += f'''<div class="ic-detail-row">
                    <span class="label">Created</span><span class="value">{created}</span>
                </div>'''
            if updated:
                col_rows += f'''<div class="ic-detail-row">
                    <span class="label">Last Updated</span><span class="value">{updated}</span>
                </div>'''
            for dec_title, dec_val in decisions.items():
                col_rows += f'''<div class="ic-detail-row">
                    <span class="label">{_esc(dec_title)}</span>
                    <span class="value" style="color:{MONDAY_PURPLE};font-weight:600">{_esc(dec_val)}</span>
                </div>'''

            # Updates / Notes
            notes_html = ""
            if updates:
                for u in updates[:3]:
                    body = u.get("body", "")[:300]
                    creator = u.get("creator", "")
                    udate = (u.get("created_at") or "")[:10]
                    notes_html += f'''<div style="padding:4px 0;border-bottom:1px solid {COLORS['card_border']}">
                        <div style="font-size:10px;color:{COLORS['text_muted']}">{_esc(creator)} &middot; {udate}</div>
                        <div style="font-size:12px;color:{COLORS['text']};margin-top:2px">{_esc(body)}</div>
                    </div>'''
            else:
                notes_html = f'<div style="font-size:11px;color:{COLORS["text_muted"]};font-style:italic">No notes or updates recorded</div>'

            # Subitems / Tasks
            tasks_html = ""
            if subitems:
                for si in subitems:
                    done = si.get("done", False)
                    check_cls = "check done" if done else "check"
                    check_icon = "&#10003;" if done else ""
                    tasks_html += f'''<div class="ic-task-item">
                        <span class="{check_cls}">{check_icon}</span>
                        <span style="color:{COLORS['text'] if not done else COLORS['text_muted']};{'text-decoration:line-through' if done else ''}">{_esc(si.get("name", ""))}</span>
                        {f'<span style="font-size:10px;color:{COLORS["text_muted"]};margin-left:auto">{_esc(si.get("status", ""))}</span>' if si.get("status") else ""}
                    </div>'''
            else:
                tasks_html = f'<div style="font-size:11px;color:{COLORS["text_muted"]};font-style:italic">No sub-tasks defined</div>'

            # Gap Flags — flag missing information
            gaps = []
            if not updates:
                gaps.append("No notes/updates")
            if not subitems:
                gaps.append("No sub-tasks")
            if not item.get("has_owner"):
                gaps.append("No owner assigned")
            if not created:
                gaps.append("No creation date")
            has_value = any("value" in k.lower() or "revenue" in k.lower() or "amount" in k.lower() for k in columns.keys())
            if not has_value and not any("value" in k.lower() for k in scores.keys()):
                gaps.append("No deal value")
            if not decisions:
                gaps.append("No IC decision recorded")
            score_cols_with_data = sum(1 for v in scores.values() if v > 0)
            if score_cols_with_data < len(scores) and len(scores) > 0:
                gaps.append(f"Only {score_cols_with_data}/{len(scores)} gate scores filled")

            gaps_html = ""
            if gaps:
                for g in gaps:
                    gaps_html += f'<span class="ic-gap-flag">&#9888; {_esc(g)}</span>'
            else:
                gaps_html = f'<span style="font-size:11px;color:{COLORS["success"]};font-weight:600">&#10003; No gaps detected</span>'

            # Recommended Next Steps — based on stage + gaps
            next_steps = []
            stage_lower = ic_stage.lower()
            if stage_lower in ("screening", "identified"):
                next_steps.append("Complete initial information gathering and IM review")
                if not subitems:
                    next_steps.append("Define due diligence checklist tasks")
            elif stage_lower == "due diligence":
                next_steps.append("Complete outstanding DD tasks and prepare for IC review")
                if subitems:
                    incomplete = sum(1 for s in subitems if not s.get("done"))
                    if incomplete:
                        next_steps.append(f"Complete {incomplete} remaining sub-task(s)")
            elif stage_lower == "ic review":
                next_steps.append("Prepare scorecard presentation for IC committee")
                if not decisions:
                    next_steps.append("Record IC decision outcome")
            elif stage_lower == "negotiation":
                next_steps.append("Progress commercial terms and heads of terms")
                if not updates:
                    next_steps.append("Add negotiation status update")
            elif stage_lower == "completed":
                next_steps.append("Archive and record lessons learned")
            elif stage_lower == "passed":
                next_steps.append("Record reason for passing and archive")
            else:
                next_steps.append("Update project status and add latest progress notes")
            if not updates:
                next_steps.append("Add a project update note with current status")
            if not item.get("has_owner"):
                next_steps.append("Assign a project owner")

            next_steps_html = ""
            for ns in next_steps[:4]:
                next_steps_html += f'<div class="ic-next-step"><span class="bullet">&#8226;</span> {_esc(ns)}</div>'

            # Assemble detail panel
            board_html += f'''<div class="ic-detail" id="{detail_id}">
                <div style="margin-bottom:8px">{gaps_html}</div>
                <div class="ic-detail-grid">
                    <div>
                        <div class="ic-detail-section">
                            <h4>Project Details</h4>
                            {col_rows}
                        </div>
                        <div class="ic-detail-section" style="margin-top:8px">
                            <h4>Recommended Next Steps</h4>
                            {next_steps_html}
                        </div>
                    </div>
                    <div>
                        <div class="ic-detail-section">
                            <h4>Notes &amp; Updates ({len(updates)})</h4>
                            {notes_html}
                        </div>
                        <div class="ic-detail-section" style="margin-top:8px">
                            <h4>Sub-Tasks ({len(subitems)})</h4>
                            {tasks_html}
                        </div>
                    </div>
                </div>
            </div>'''

        board_html += '</div>'

        ic_more = ""
        if len(top_scored) > IC_LIMIT:
            remaining = len(top_scored) - IC_LIMIT
            ic_more = f'''<div style="text-align:center;padding:10px;border-top:1px solid {COLORS['card_border']}">
                <button id="ic-show-more" onclick="toggleExpandList('ic-extra-row','ic-show-more',{len(top_scored)},{IC_LIMIT})"
                    style="background:none;border:1px solid {COLORS['card_border']};border-radius:8px;
                    padding:6px 20px;color:{COLORS['accent2']};font-size:12px;font-weight:600;
                    cursor:pointer;transition:all 0.2s ease">
                    Show all {len(top_scored)} items ({remaining} more)
                </button>
            </div>'''

        html += f'''<div class="glass-card" style="margin-top:8px;padding:0;overflow:hidden;border-top:3px solid {MONDAY_PURPLE}">
            <div style="padding:10px 16px;border-bottom:1px solid {COLORS['card_border']}">
                <h3 class="card-title" style="margin-bottom:0;display:flex;align-items:center;gap:6px;font-size:13px">
                    <span style="color:{MONDAY_PURPLE}">\U0001F4CB</span> IC Scorecard — Click a project to expand details
                </h3>
                <p style="font-size:10px;color:{COLORS['text_muted']};margin-top:2px">Sorted by most recently updated &middot; {len(top_scored)} projects &middot; click row for context, notes, next steps &amp; gaps</p>
            </div>
            {board_html}
            {ic_more}
        </div>'''

    # ── IC Category Scores ──
    cat_scores = ic.get("category_scores", {})
    if cat_scores:
        cat_data = [(name, stats.get("avg", 0))
                    for name, stats in sorted(cat_scores.items(),
                                              key=lambda x: x[1].get("avg", 0), reverse=True)]
        if cat_data:
            html += f'''<div class="glass-card" style="margin-top:8px">
                <h3 class="card-title">\U0001F4CA IC Score by Category (Averages)</h3>
                {_svg_bar_chart(cat_data, 650, max(140, len(cat_data) * 28), MONDAY_PURPLE)}
            </div>'''

    # ── Charts row: Trend + Decision Distribution ──
    score_trend = ic.get("score_trend", {})
    if score_trend or decisions:
        html += '<div class="grid-2" style="margin-top:8px">'
        if score_trend:
            trend_data = [(month, stats.get("avg_score", 0))
                          for month, stats in sorted(score_trend.items())]
            if trend_data:
                html += f'''<div class="glass-card">
                    <h3 class="card-title">\U0001F4C8 IC Score Trend (Monthly Avg)</h3>
                    {_svg_line_chart(trend_data, 500, 150, MONDAY_PURPLE)}
                </div>'''
        if decisions:
            decision_data = [(k, v) for k, v in sorted(decisions.items(),
                                                        key=lambda x: x[1], reverse=True)]
            html += f'''<div class="glass-card">
                <h3 class="card-title">\U0001F3DB\uFE0F IC Decision Distribution</h3>
                {_svg_donut(decision_data, 150)}
            </div>'''
        html += '</div>'

    # ── IC Detail Toggle + Stage Filter JavaScript ──
    ic_stage_counts_json = json.dumps(ic_stage_counts if top_scored else {})
    html += f'''<script>
    // Toggle IC project detail panel
    window.toggleICDetail = function(id) {{
        var el = document.getElementById(id);
        var arrow = document.getElementById(id + '_arrow');
        if (!el) return;
        var isOpen = el.classList.contains('open');
        // Close all other open details
        document.querySelectorAll('.ic-detail.open').forEach(function(d) {{
            if (d.id !== id) {{
                d.classList.remove('open');
                var otherArrow = document.getElementById(d.id + '_arrow');
                if (otherArrow) otherArrow.classList.remove('open');
            }}
        }});
        el.classList.toggle('open');
        if (arrow) arrow.classList.toggle('open');
    }};

    (function() {{
        var icStageCounts = {ic_stage_counts_json};
        icStageCounts['all'] = {len(top_scored) if top_scored else 0};
        // Populate stage count badges
        document.querySelectorAll('[data-stage-count]').forEach(function(el) {{
            var stage = el.getAttribute('data-stage-count');
            var count = icStageCounts[stage] || 0;
            if (stage === 'all') count = icStageCounts['all'];
            el.textContent = count > 0 ? '(' + count + ')' : '';
        }});

        var currentICFilter = 'all';

        window.filterICStage = function(stage) {{
            currentICFilter = stage;
            var rows = document.querySelectorAll('.ic-row');
            var visibleCount = 0;

            // When filtering, first expand all rows (override show-10 limit)
            if (stage !== 'all') {{
                rows.forEach(function(row) {{
                    if (row.classList.contains('ic-extra-row')) {{
                        // Remove the hidden state from expand logic
                        row.style.display = '';
                    }}
                }});
            }}

            rows.forEach(function(row) {{
                var rowStage = row.getAttribute('data-ic-stage');
                var match = (stage === 'all' || rowStage === stage);
                if (match) {{
                    row.style.display = '';
                    visibleCount++;
                }} else {{
                    row.style.display = 'none';
                }}
            }});

            // If "all" is selected, re-apply the show-10 limit
            if (stage === 'all') {{
                var idx = 0;
                rows.forEach(function(row) {{
                    if (row.classList.contains('ic-extra-row')) {{
                        var expandBtn = document.getElementById('ic-show-more');
                        var isExpanded = expandBtn && expandBtn.getAttribute('data-expanded') === '1';
                        if (!isExpanded) {{
                            row.style.display = 'none';
                        }}
                    }}
                    idx++;
                }});
            }}

            // Hide show-more button when filtering
            var moreBtn = document.getElementById('ic-show-more');
            if (moreBtn) {{
                moreBtn.parentElement.style.display = (stage === 'all') ? '' : 'none';
            }}

            // Update active button styling
            document.querySelectorAll('.ic-stage-btn').forEach(function(btn) {{
                var btnStage = btn.getAttribute('data-ic-filter');
                if (btnStage === stage) {{
                    btn.classList.add('ic-stage-active');
                    btn.style.background = '{COLORS["accent"]}';
                    btn.style.color = '#fff';
                    btn.style.borderColor = '{COLORS["accent"]}';
                    btn.style.boxShadow = '0 2px 8px rgba(60,180,173,0.25)';
                }} else {{
                    btn.classList.remove('ic-stage-active');
                    btn.style.background = '{COLORS["card"]}';
                    btn.style.color = '{COLORS["text_muted"]}';
                    btn.style.borderColor = '{COLORS["card_border"]}';
                    btn.style.boxShadow = 'none';
                }}
            }});

            // Update filter status text
            var statusEl = document.getElementById('ic-filter-status');
            if (statusEl) {{
                if (stage === 'all') {{
                    statusEl.textContent = '';
                }} else {{
                    var label = stage.charAt(0).toUpperCase() + stage.slice(1);
                    statusEl.textContent = 'Showing: ' + label + ' (' + visibleCount + ')';
                }}
            }}
        }};

        // Initial: set "All" as active on page load
        var allBtn = document.querySelector('.ic-stage-btn.ic-stage-active');
        if (allBtn) {{
            allBtn.style.background = '{COLORS["accent"]}';
            allBtn.style.color = '#fff';
            allBtn.style.borderColor = '{COLORS["accent"]}';
            allBtn.style.boxShadow = '0 2px 8px rgba(60,180,173,0.25)';
        }}
    }})();
    </script>'''

    html += '</section>'
    return html


def _build_monday_workspaces(data: dict) -> str:
    """Workspaces page — board overview by workspace with collapsible groups, dormant filtered."""
    monday = data.get("monday", {})
    if not monday:
        return '<section class="dashboard-section"><div class="glass-card" style="padding:40px;text-align:center;color:#6b7280"><p>No Monday.com data available.</p></div></section>'

    overview = monday.get("board_overview", {})

    html = _section_header(
        "monday-workspaces", "Workspaces",
        "Monday.com workspace and board overview — sorted by activity, dormant workspaces hidden",
        "\U0001F3E2",
    )

    # ── Filter dormant workspaces (all items inactive for 5+ months) ──
    workspaces_raw = overview.get("workspaces", [])
    # Keep workspaces that have active items (rough activity proxy)
    active_workspaces = [ws for ws in workspaces_raw if ws.get("active_items", 0) > 0]
    dormant_ws = len(workspaces_raw) - len(active_workspaces)

    # ── KPI row ──
    ws_count = len(active_workspaces)
    board_count = sum(ws.get("board_count", 0) for ws in active_workspaces)
    filtered_out = overview.get("subitem_boards_filtered", 0)
    total_items = sum(ws.get("total_items", 0) for ws in active_workspaces)
    total_active = sum(ws.get("active_items", 0) for ws in active_workspaces)

    html += '<div class="kpi-grid kpi-grid-3">'
    html += _stat_card("Active Workspaces", _fmt_number(ws_count),
                       f"{dormant_ws} dormant hidden", "\U0001F3E2", COLORS['accent2'])
    html += _stat_card("Total Items", _fmt_number(total_items),
                       f"{_fmt_number(total_active)} active", "\U0001F4CA", COLORS['accent'])
    html += _stat_card("Filtered Out", _fmt_number(filtered_out),
                       "Sub-item boards removed", "\U0001F50D", COLORS['text_muted'])
    html += '</div>'

    # ── Workspace board-style listing (show 10 with expand) ──
    if active_workspaces:
        # Sort workspaces by active items desc (most active first)
        active_workspaces.sort(key=lambda ws: ws.get("active_items", 0), reverse=True)

        ws_colors = [MONDAY_PURPLE, COLORS['accent2'], MONDAY_GREEN, COLORS['accent'],
                     MONDAY_YELLOW, COLORS['accent3'], COLORS['info'], COLORS['accent4'],
                     "#E2445C", "#FF642E", "#579BFC", "#CAB641"]

        WS_LIMIT = 10
        board_html = '<div class="board-container">'
        for i, ws in enumerate(active_workspaces):
            ws_name = _esc(ws.get("name", "Unknown"))
            ws_boards = ws.get("board_count", 0)
            ws_items = ws.get("total_items", 0)
            ws_active = ws.get("active_items", 0)
            boards = ws.get("boards", [])
            ws_id = f"ws_grp_{i}"
            ws_color = ws_colors[i % len(ws_colors)]

            # Hide workspaces beyond the first 10
            hidden_style = 'display:none;' if i >= WS_LIMIT else ''
            extra_cls = ' ws-extra-group' if i >= WS_LIMIT else ''

            board_html += f'''<div class="board-group{extra_cls}" style="{hidden_style}">
                <div class="board-group-header" onclick="toggleBoardGroup('{ws_id}')">
                    <div class="group-color" style="background:{ws_color}"></div>
                    <div class="group-title">{ws_name}</div>
                    <div class="group-count">{ws_boards} boards &middot; {_fmt_number(ws_items)} items &middot; {_fmt_number(ws_active)} active</div>
                    <div class="group-arrow" id="{ws_id}_arrow">&#9654;</div>
                </div>
                <div class="board-rows" id="{ws_id}" style="display:none">'''

            if boards:
                # Sort boards by active items desc
                boards_sorted = sorted(boards, key=lambda b: b.get("active_items", 0), reverse=True)
                # Filter out boards with 0 items
                boards_sorted = [b for b in boards_sorted if b.get("item_count", 0) > 0]

                board_html += f'''<div class="board-header-row" style="grid-template-columns:2fr 100px 100px">
                    <div>Board Name</div>
                    <div>Items</div>
                    <div>Active</div>
                </div>'''

                for b in boards_sorted[:20]:
                    b_name = _esc(b.get("name", ""))
                    b_items = b.get("item_count", 0)
                    b_active = b.get("active_items", 0)
                    active_pct = (b_active / b_items * 100) if b_items > 0 else 0
                    bar_color = MONDAY_GREEN if active_pct >= 50 else (MONDAY_YELLOW if active_pct >= 20 else COLORS['text_muted'])

                    board_html += f'''<div class="board-row" style="grid-template-columns:2fr 100px 100px">
                        <div style="font-weight:500;color:{COLORS['text']}">{b_name}</div>
                        <div style="font-size:12px">{_fmt_number(b_items)}</div>
                        <div>
                            <div class="progress-mini">
                                <div class="bar"><div class="bar-fill" style="width:{active_pct:.0f}%;background:{bar_color}"></div></div>
                                <span class="pct">{_fmt_number(b_active)}</span>
                            </div>
                        </div>
                    </div>'''

            board_html += '</div></div>'

        board_html += '</div>'

        ws_more = ""
        if len(active_workspaces) > WS_LIMIT:
            remaining = len(active_workspaces) - WS_LIMIT
            ws_more = f'''<div style="text-align:center;padding:12px;border-top:1px solid {COLORS['card_border']}">
                <button id="ws-show-more" onclick="toggleExpandList('ws-extra-group','ws-show-more',{len(active_workspaces)},{WS_LIMIT})"
                    style="background:none;border:1px solid {COLORS['card_border']};border-radius:8px;
                    padding:8px 24px;color:{COLORS['accent2']};font-size:13px;font-weight:600;
                    cursor:pointer;transition:all 0.2s ease">
                    Show all {len(active_workspaces)} workspaces ({remaining} more)
                </button>
            </div>'''

        html += f'''<div class="glass-card" style="margin-top:8px;padding:0;overflow:hidden">
            <div style="padding:10px 14px;border-bottom:1px solid {COLORS['card_border']}">
                <h3 class="card-title" style="margin-bottom:0">\U0001F3E2 Active Workspaces
                    <span style="font-size:13px;font-weight:400;color:{COLORS['text_muted']}">
                        ({len(active_workspaces)} active, {dormant_ws} dormant hidden)
                    </span>
                </h3>
                <p style="font-size:11px;color:{COLORS['text_muted']};margin-top:4px">
                    Sorted by most active &middot; Click to expand &middot; Showing {min(WS_LIMIT, len(active_workspaces))} of {len(active_workspaces)}
                </p>
            </div>
            {board_html}
            {ws_more}
        </div>'''

    # ── toggleBoardGroup JS (shared) ──
    html += '''<script>
    if(!window.toggleBoardGroup) {
        window.toggleBoardGroup = function(id){
            var el = document.getElementById(id);
            var arrow = document.getElementById(id + '_arrow');
            if(!el) return;
            if(el.style.display === 'none'){
                el.style.display = 'block';
                if(arrow) arrow.classList.add('expanded');
            } else {
                el.style.display = 'none';
                if(arrow) arrow.classList.remove('expanded');
            }
        };
    }
    if(!window.toggleExpandList) {
        window.toggleExpandList = function(extraClass, btnId, total, limit) {
            var extras = document.querySelectorAll('.' + extraClass);
            var btn = document.getElementById(btnId);
            if (!btn) return;
            var isExpanded = btn.getAttribute('data-expanded') === '1';
            extras.forEach(function(el) {
                el.style.display = isExpanded ? 'none' : '';
            });
            if (isExpanded) {
                btn.textContent = 'Show all ' + total + ' (' + (total - limit) + ' more)';
                btn.setAttribute('data-expanded', '0');
            } else {
                btn.textContent = 'Show less (collapse to ' + limit + ')';
                btn.setAttribute('data-expanded', '1');
            }
        };
    }
    </script>'''

    html += '</section>'
    return html


# ---------------------------------------------------------------------------
# Section: AI Roadmap & Tasks
# ---------------------------------------------------------------------------

AI_TEAL = "#3CB4AD"
AI_BLUE = "#334FB4"

AI_CATEGORY_LABELS = {
    "initiatives": ("Initiatives", AI_TEAL, "\U0001F680"),
    "tools": ("AI Tools", AI_BLUE, "\U0001F6E0\uFE0F"),
    "knowledge": ("Knowledge Base", "#a78bfa", "\U0001F4DA"),
    "meetings": ("Meetings", "#f59e0b", "\U0001F4C5"),
    "active_projects": ("Active Projects", "#22c55e", "\u2699\uFE0F"),
    "survey": ("Surveys", "#f472b6", "\U0001F4CA"),
    "submissions": ("Business Needs", "#60a5fa", "\U0001F4DD"),
    "other": ("Other", "#6b7280", "\U0001F4C1"),
}


def _build_ai_section(data: dict) -> str:
    """AI Roadmap & Tasks page — eComplete AI workspace boards."""
    monday = data.get("monday", {})
    ai = monday.get("ai_metrics", {})
    if not ai or not ai.get("total_items"):
        return '''<section class="dashboard-section"><div class="glass-card" style="padding:30px;text-align:center;color:#6b7280"><p>No AI workspace data available. Ensure the eComplete AI workspace exists in Monday.com.</p></div></section>'''

    html = _section_header(
        "ai-roadmap", "AI Roadmap & Tasks",
        "eComplete AI Committee — initiatives, tools, knowledge, meetings, and project tracking",
        "\U0001F916",
    )

    total_items = ai.get("total_items", 0)
    boards = ai.get("boards", [])
    categories = ai.get("categories", {})
    status_dist = ai.get("status_distribution", {})

    # ── KPI row ──
    html += '<div class="kpi-grid">'
    html += _stat_card("AI Items", _fmt_number(total_items),
                       f"Across {len(boards)} boards", "\U0001F916", AI_TEAL)
    html += _stat_card("Initiatives", _fmt_number(len(categories.get("initiatives", {}).get("items", []))),
                       "", "\U0001F680", AI_BLUE)
    html += _stat_card("Tools Tracked", _fmt_number(len(categories.get("tools", {}).get("items", []))),
                       "", "\U0001F6E0\uFE0F", "#a78bfa")
    html += _stat_card("Active Projects", _fmt_number(len(categories.get("active_projects", {}).get("items", []))),
                       "", "\u2699\uFE0F", "#22c55e")
    html += '</div>'

    # ── Status distribution ──
    if status_dist:
        status_items = sorted(status_dist.items(), key=lambda x: x[1], reverse=True)
        max_status = max(status_dist.values()) if status_dist else 1
        html += f'''<div class="glass-card" style="margin-top:10px">
            <h3 class="card-title">Status Distribution</h3>'''
        for s_name, s_count in status_items[:10]:
            html += _svg_horizontal_bar(s_name, s_count, max_status, AI_TEAL, show_pct=False)
        html += '</div>'

    # ── Category boards with expandable items ──
    ai_detail_idx = 0
    for cat_key, cat_data in sorted(categories.items(), key=lambda x: len(x[1].get("items", [])), reverse=True):
        cat_label, cat_color, cat_icon = AI_CATEGORY_LABELS.get(cat_key, ("Other", "#6b7280", "\U0001F4C1"))
        cat_items = cat_data.get("items", [])
        if not cat_items:
            continue

        items_html = ""
        for item in cat_items:
            ai_detail_idx += 1
            detail_id = f"ai_det_{ai_detail_idx}"
            i_name = _esc(item.get("name", ""))
            i_status = _esc(item.get("status", ""))
            i_owner = _esc(item.get("owner", "Unassigned"))
            i_updated = (item.get("updated_at") or "")[:10]

            status_bg = f"{cat_color}22"
            items_html += (
                f'<div class="ai-item-row" onclick="toggleAIDetail(\'{detail_id}\')">'
                f'<div style="font-weight:500;color:{COLORS["text"]}">{i_name}</div>'
                f'<div><span class="status-pill" style="background:{status_bg};color:{cat_color};padding:2px 8px;min-width:auto;font-size:10px">{i_status or "—"}</span></div>'
                f'<div style="font-size:11px;color:{COLORS["text_muted"]}">{i_owner}</div>'
                f'<div style="font-size:11px;color:{COLORS["text_muted"]}">{i_updated}</div>'
                f'</div>'
            )

            # Detail panel
            cols = item.get("columns", {})
            updates = item.get("updates", [])
            subitems = item.get("subitems", [])

            det_cols = ""
            for ck, cv in cols.items():
                if len(cv) > 300:
                    continue
                det_cols += f'''<div class="ic-detail-row">
                    <span class="label">{_esc(ck)}</span>
                    <span class="value">{_esc(cv[:100])}</span>
                </div>'''

            det_notes = ""
            if updates:
                for u in updates[:3]:
                    det_notes += f'''<div style="padding:3px 0;border-bottom:1px solid {COLORS['card_border']}">
                        <div style="font-size:10px;color:{COLORS['text_muted']}">{_esc(u.get("creator",""))} &middot; {(u.get("created_at","") or "")[:10]}</div>
                        <div style="font-size:12px;color:{COLORS['text']};margin-top:1px">{_esc(u.get("body","")[:200])}</div>
                    </div>'''
            else:
                det_notes = f'<span style="font-size:11px;color:{COLORS["text_muted"]};font-style:italic">No updates</span>'

            det_tasks = ""
            if subitems:
                for si in subitems:
                    done = si.get("done", False)
                    check_cls = "check done" if done else "check"
                    det_tasks += f'''<div class="ic-task-item">
                        <span class="{check_cls}">{"&#10003;" if done else ""}</span>
                        <span>{_esc(si.get("name",""))}</span>
                    </div>'''
            else:
                det_tasks = f'<span style="font-size:11px;color:{COLORS["text_muted"]};font-style:italic">No sub-tasks</span>'

            items_html += f'''<div class="ai-item-detail" id="{detail_id}">
                <div class="ic-detail-grid">
                    <div class="ic-detail-section">
                        <h4>Details</h4>{det_cols if det_cols else f'<span style="font-size:11px;color:{COLORS["text_muted"]}">No additional data</span>'}
                    </div>
                    <div>
                        <div class="ic-detail-section">
                            <h4>Notes ({len(updates)})</h4>{det_notes}
                        </div>
                        {f'<div class="ic-detail-section" style="margin-top:6px"><h4>Tasks ({len(subitems)})</h4>{det_tasks}</div>' if subitems else ''}
                    </div>
                </div>
            </div>'''

        html += f'''<div class="glass-card" style="margin-top:10px;padding:0;overflow:hidden;border-left:3px solid {cat_color}">
            <div style="padding:10px 14px;border-bottom:1px solid {COLORS['card_border']};display:flex;justify-content:space-between;align-items:center">
                <h3 class="card-title" style="margin-bottom:0;font-size:13px">{cat_icon} {cat_label}
                    <span style="font-size:11px;font-weight:400;color:{COLORS['text_muted']}">({len(cat_items)} items)</span>
                </h3>
            </div>
            <div class="board-container" style="border:none;border-radius:0">
                <div style="display:grid;grid-template-columns:2fr 120px 100px 120px;padding:4px 12px;font-size:10px;font-weight:600;color:{COLORS['text_muted']};text-transform:uppercase;letter-spacing:0.04em;background:{COLORS['surface2']};border-bottom:1px solid {COLORS['card_border']}">
                    <div>Item</div><div>Status</div><div>Owner</div><div>Updated</div>
                </div>
                {items_html}
            </div>
        </div>'''

    # ── Board overview list ──
    if boards:
        board_rows = ""
        for b in boards:
            b_name = _esc(b.get("name", ""))
            b_cat = b.get("category", "other")
            b_label, b_color, _ = AI_CATEGORY_LABELS.get(b_cat, ("Other", "#6b7280", ""))
            b_count = b.get("item_count", 0)
            b_owners = ", ".join(b.get("owners", [])[:3]) or "—"
            board_rows += f'''<div style="display:flex;justify-content:space-between;align-items:center;padding:6px 0;border-bottom:1px solid {COLORS['card_border']}">
                <div>
                    <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:{b_color};margin-right:6px"></span>
                    <span style="font-size:12px;font-weight:500;color:{COLORS['text']}">{b_name}</span>
                    <span style="font-size:10px;color:{COLORS['text_muted']};margin-left:6px">{b_label}</span>
                </div>
                <div style="text-align:right">
                    <span style="font-size:12px;font-weight:600;color:{COLORS['text']}">{b_count}</span>
                    <span style="font-size:10px;color:{COLORS['text_muted']};margin-left:8px">{_esc(b_owners)}</span>
                </div>
            </div>'''

        html += f'''<div class="glass-card" style="margin-top:10px">
            <h3 class="card-title">AI Boards Overview</h3>
            {board_rows}
        </div>'''

    # ── AI Detail toggle JS ──
    html += '''<script>
    window.toggleAIDetail = function(id) {
        var el = document.getElementById(id);
        if (!el) return;
        var isOpen = el.classList.contains('open');
        document.querySelectorAll('.ai-item-detail.open').forEach(function(d) {
            if (d.id !== id) d.classList.remove('open');
        });
        el.classList.toggle('open');
    };
    </script>'''

    html += '</section>'
    return html


# ---------------------------------------------------------------------------
# CSS stylesheet
# ---------------------------------------------------------------------------

def _build_css() -> str:
    """Build the complete CSS for the dashboard — eComplete light theme."""
    return f'''
    <style>
        /* ============================================================
           CSS Custom Properties — eComplete Brand
           ============================================================ */
        :root {{
            --bg:          {COLORS['bg']};
            --card:        {COLORS['card']};
            --card-border: {COLORS['card_border']};
            --text:        {COLORS['text']};
            --text-muted:  {COLORS['text_muted']};
            --accent:      {COLORS['accent']};
            --accent2:     {COLORS['accent2']};
            --accent3:     {COLORS['accent3']};
            --accent4:     {COLORS['accent4']};
            --accent5:     {COLORS['accent5']};
            --accent6:     {COLORS['accent6']};
            --success:     {COLORS['success']};
            --danger:      {COLORS['danger']};
            --warning:     {COLORS['warning']};
            --info:        {COLORS['info']};
            --surface:     {COLORS['surface']};
            --surface2:    {COLORS['surface2']};
            --radius:      10px;
            --radius-sm:   6px;
            --shadow:      0 1px 3px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04);
            --shadow-lg:   0 4px 16px rgba(0,0,0,0.08), 0 1px 4px rgba(0,0,0,0.04);
            --transition:  all 0.3s cubic-bezier(.25,.1,.25,1);
        }}

        /* ============================================================
           Reset & Base
           ============================================================ */
        *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
        html {{ scroll-behavior: smooth; scroll-padding-top: 24px; }}
        body {{
            background: var(--bg);
            color: var(--text);
            font-family: 'Assistant', 'Inter', 'Segoe UI', system-ui, -apple-system, sans-serif;
            line-height: 1.6;
            min-height: 100vh;
            -webkit-font-smoothing: antialiased;
            overflow-x: hidden;
            display: flex;
        }}

        /* Scrollbar styling */
        ::-webkit-scrollbar {{ width: 8px; height: 8px; }}
        ::-webkit-scrollbar-track {{ background: var(--bg); }}
        ::-webkit-scrollbar-thumb {{ background: #d1d5db; border-radius: 4px; }}
        ::-webkit-scrollbar-thumb:hover {{ background: #9ca3af; }}

        /* ============================================================
           Left Sidebar Navigation — eComplete Dark
           ============================================================ */
        .sidebar {{
            position: fixed;
            top: 0;
            left: 0;
            bottom: 0;
            width: 220px;
            background: linear-gradient(180deg, #242833 0%, #1e2230 100%);
            border-right: 1px solid rgba(255, 255, 255, 0.06);
            z-index: 200;
            display: flex;
            flex-direction: column;
            overflow-y: auto;
            scrollbar-width: thin;
            scrollbar-color: rgba(255,255,255,0.1) transparent;
            transition: transform 0.3s cubic-bezier(.25,.1,.25,1);
        }}
        .sidebar::-webkit-scrollbar {{ width: 4px; }}
        .sidebar::-webkit-scrollbar-track {{ background: transparent; }}
        .sidebar::-webkit-scrollbar-thumb {{ background: rgba(255,255,255,0.1); border-radius: 4px; }}

        .sidebar-brand {{
            padding: 20px 18px 16px;
            display: flex;
            align-items: center;
            gap: 10px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.06);
        }}
        .sidebar-brand .brand-dot {{
            width: 28px;
            height: 28px;
            border-radius: 50%;
            background: var(--accent);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 14px;
            font-weight: 800;
            color: #fff;
            flex-shrink: 0;
        }}
        .sidebar-brand-text {{
            font-weight: 800;
            font-size: 16px;
            color: #ffffff;
            letter-spacing: -0.01em;
        }}

        .sidebar-nav {{
            flex: 1;
            padding: 12px 0;
        }}
        .sidebar-group {{
            margin-bottom: 4px;
        }}
        .sidebar-group-label {{
            padding: 8px 18px 4px;
            font-size: 10px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            color: rgba(255, 255, 255, 0.35);
        }}
        .sidebar-link {{
            display: block;
            padding: 7px 18px 7px 28px;
            font-size: 13px;
            font-weight: 500;
            color: rgba(255, 255, 255, 0.55);
            text-decoration: none;
            border-left: 3px solid transparent;
            transition: all 0.2s ease;
            position: relative;
        }}
        .sidebar-link:hover {{
            color: rgba(255, 255, 255, 0.9);
            background: rgba(255,255,255,0.04);
            border-left-color: rgba(255, 255, 255, 0.15);
        }}
        .sidebar-link.active {{
            color: var(--accent);
            background: rgba(60, 180, 173, 0.1);
            border-left-color: var(--accent);
            font-weight: 600;
        }}

        /* Sidebar favourite star */
        .sidebar-link {{ position: relative; }}
        .sidebar-fav {{
            position: absolute;
            right: 8px;
            top: 50%;
            transform: translateY(-50%);
            background: none;
            border: none;
            cursor: pointer;
            font-size: 12px;
            color: rgba(255,255,255,0.15);
            padding: 2px;
            line-height: 1;
            opacity: 0;
            transition: opacity 0.2s, color 0.2s;
        }}
        .sidebar-link:hover .sidebar-fav {{ opacity: 1; }}
        .sidebar-fav:hover {{ color: {COLORS['accent6']}; }}
        .sidebar-fav.is-fav {{
            opacity: 1;
            color: {COLORS['accent6']};
        }}

        /* Favourites group */
        .sidebar-favs-group {{
            border-bottom: 1px solid rgba(255,255,255,0.06);
            display: none;
        }}
        .sidebar-favs-group.has-favs {{
            display: block;
        }}
        .sidebar-favs-group .sidebar-group-label {{
            color: {COLORS['accent6']};
            opacity: 0.7;
        }}

        /* AI assistant link */
        .sidebar-ai-link {{
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 10px 18px;
            margin: 4px 10px;
            border-radius: var(--radius-sm);
            font-size: 13px;
            font-weight: 600;
            color: #fff;
            text-decoration: none;
            cursor: pointer;
            background: linear-gradient(135deg, {COLORS['accent']}, {COLORS['accent2']});
            border: none;
            transition: opacity 0.2s, transform 0.2s;
        }}
        .sidebar-ai-link:hover {{
            opacity: 0.9;
            transform: translateY(-1px);
        }}
        .sidebar-ai-link-dot {{
            font-size: 14px;
        }}
        .sidebar-ai-badge {{
            margin-left: auto;
            background: rgba(255,255,255,0.2);
            padding: 1px 6px;
            border-radius: 8px;
            font-size: 9px;
            font-weight: 700;
            letter-spacing: 0.04em;
        }}

        .sidebar-footer {{
            padding: 14px 18px;
            font-size: 10px;
            color: rgba(255, 255, 255, 0.25);
            text-transform: uppercase;
            letter-spacing: 0.06em;
            border-top: 1px solid rgba(255, 255, 255, 0.06);
        }}

        /* Layout wrapper to the right of sidebar */
        .layout-main {{
            margin-left: 220px;
            flex: 1;
            min-width: 0;
        }}

        /* Sidebar hamburger toggle (hidden on desktop) */
        .sidebar-toggle {{
            display: none;
            position: fixed;
            top: 14px;
            left: 14px;
            z-index: 250;
            background: rgba(36, 40, 51, 0.95);
            backdrop-filter: blur(12px);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 8px;
            padding: 10px 11px;
            cursor: pointer;
            flex-direction: column;
            gap: 4px;
        }}
        .sidebar-toggle span {{
            display: block;
            width: 20px;
            height: 2px;
            background: #ffffff;
            border-radius: 2px;
            transition: all 0.3s ease;
        }}
        .sidebar-toggle.open span:nth-child(1) {{
            transform: rotate(45deg) translate(4px, 4px);
        }}
        .sidebar-toggle.open span:nth-child(2) {{
            opacity: 0;
        }}
        .sidebar-toggle.open span:nth-child(3) {{
            transform: rotate(-45deg) translate(4px, -4px);
        }}

        /* Mobile overlay */
        .sidebar-overlay {{
            display: none;
            position: fixed;
            inset: 0;
            background: rgba(0,0,0,0.3);
            z-index: 190;
        }}
        .sidebar-overlay.visible {{
            display: block;
        }}

        /* ============================================================
           Layout
           ============================================================ */
        .main-content {{
            max-width: 1400px;
            margin: 0 auto;
            padding: 10px 16px;
        }}

        /* ============================================================
           Sections
           ============================================================ */
        .dashboard-section {{
            margin-bottom: 10px;
        }}

        @keyframes fade-in-up {{
            to {{ opacity: 1; transform: translateY(0); }}
        }}

        .section-header {{
            margin-bottom: 8px;
            padding-bottom: 6px;
            border-bottom: 1px solid var(--card-border);
        }}
        .section-title {{
            font-size: 14px;
            font-weight: 800;
            color: var(--text);
            letter-spacing: -0.02em;
        }}
        .section-subtitle {{
            font-size: 11px;
            color: var(--text-muted);
            margin-top: 1px;
        }}

        /* ============================================================
           Cards — eComplete clean style
           ============================================================ */
        .glass-card {{
            background: var(--card);
            border: 1px solid var(--card-border);
            border-radius: var(--radius);
            padding: 8px 12px;
            box-shadow: var(--shadow);
            transition: var(--transition);
        }}
        .glass-card:hover {{
            border-color: rgba(60, 180, 173, 0.25);
            box-shadow: var(--shadow-lg);
        }}
        .card-title {{
            font-size: 12px;
            font-weight: 700;
            color: var(--text);
            margin-bottom: 6px;
            text-transform: uppercase;
            letter-spacing: 0.04em;
        }}
        .alert-card {{
            border-left: 3px solid var(--warning);
        }}

        /* ============================================================
           Stat Cards (KPI) — eComplete
           ============================================================ */
        .kpi-grid {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 8px;
            margin-bottom: 8px;
        }}
        .kpi-grid-3 {{
            grid-template-columns: repeat(3, 1fr);
        }}
        .stat-card {{
            background: var(--card);
            border: 1px solid var(--card-border);
            border-radius: var(--radius-sm);
            padding: 8px 10px;
            transition: var(--transition);
            position: relative;
            overflow: hidden;
        }}
        .stat-card::before {{
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 3px;
            background: linear-gradient(90deg, var(--accent), transparent);
            opacity: 0;
            transition: opacity 0.3s ease;
        }}
        .stat-card:hover {{
            border-color: rgba(60, 180, 173, 0.3);
            box-shadow: 0 4px 12px rgba(0,0,0,0.06);
        }}
        .stat-card:hover::before {{
            opacity: 1;
        }}

        /* ============================================================
           Grid layouts
           ============================================================ */
        .grid-2 {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 8px;
        }}
        .grid-3 {{
            display: grid;
            grid-template-columns: 1fr 1fr 1fr;
            gap: 8px;
        }}

        /* ============================================================
           Volume Chain (Reverse Engineering)
           ============================================================ */
        .volume-chain {{
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 0;
            flex-wrap: wrap;
            padding: 8px 0;
        }}
        .chain-item {{
            text-align: center;
            padding: 10px 14px;
            border: 2px solid var(--card-border);
            border-radius: var(--radius);
            background: var(--surface2);
            min-width: 80px;
            transition: var(--transition);
        }}
        .chain-item:hover {{
            transform: scale(1.05);
            box-shadow: 0 4px 16px rgba(60, 180, 173, 0.12);
        }}
        .chain-value {{
            font-size: 18px;
            font-weight: 800;
            line-height: 1.2;
        }}
        .chain-label {{
            font-size: 11px;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-top: 4px;
        }}
        .chain-arrow {{
            font-size: 20px;
            color: var(--text-muted);
            padding: 0 8px;
        }}

        /* ============================================================
           Data Tables
           ============================================================ */
        .table-wrapper {{
            overflow-x: auto;
            border-radius: var(--radius-sm);
        }}
        .data-table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
        }}
        .data-table th {{
            background: var(--surface2);
            color: var(--text-muted);
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.04em;
            font-size: 10px;
            padding: 8px 10px;
            text-align: left;
            border-bottom: 2px solid var(--card-border);
            white-space: nowrap;
        }}
        .data-table td {{
            padding: 6px 10px;
            border-bottom: 1px solid var(--card-border);
            color: var(--text);
            font-size: 12px;
        }}
        .data-table tbody tr {{
            transition: background 0.15s ease;
        }}
        .data-table tbody tr:hover {{
            background: rgba(60, 180, 173, 0.04);
        }}
        .data-table tbody tr:last-child td {{
            border-bottom: none;
        }}

        /* ============================================================
           Progress bars
           ============================================================ */
        .progress-fill {{
            transition: width 1.2s cubic-bezier(.25,.1,.25,1);
        }}

        /* ============================================================
           Footer
           ============================================================ */
        .dashboard-footer {{
            text-align: center;
            padding: 10px 16px;
            color: var(--text-muted);
            font-size: 11px;
            border-top: 1px solid var(--card-border);
            margin-top: 12px;
        }}
        .dashboard-footer .brand {{
            color: var(--accent);
            font-weight: 700;
        }}

        /* ============================================================
           Responsive
           ============================================================ */
        @media (max-width: 1024px) {{
            .sidebar {{ transform: translateX(-100%); }}
            .sidebar.open {{ transform: translateX(0); }}
            .layout-main {{ margin-left: 0; }}
            .sidebar-toggle {{ display: flex; }}
            .kpi-grid {{ grid-template-columns: repeat(2, 1fr); }}
            .kpi-grid-3 {{ grid-template-columns: repeat(2, 1fr); }}
            .grid-2 {{ grid-template-columns: 1fr; }}
            .grid-3 {{ grid-template-columns: 1fr; }}
            .volume-chain {{ gap: 8px; }}
            .chain-item {{ min-width: 80px; padding: 12px; }}
            .chain-value {{ font-size: 18px; }}
            .main-content {{ padding: 16px 20px; }}
        }}
        @media (max-width: 640px) {{
            .kpi-grid {{ grid-template-columns: 1fr; }}
            .kpi-grid-3 {{ grid-template-columns: 1fr; }}
            .main-content {{ padding: 12px 14px; }}
            .glass-card {{ padding: 16px; }}
            .stat-card {{ padding: 14px; }}
            .section-title {{ font-size: 18px; }}
            .volume-chain {{ flex-direction: column; }}
            .chain-arrow {{ transform: rotate(90deg); }}
        }}

        /* ============================================================
           Filter Bar — eComplete
           ============================================================ */
        .filter-bar {{
            position: sticky;
            top: 0;
            z-index: 99;
            background: rgba(247, 248, 250, 0.92);
            backdrop-filter: blur(20px) saturate(180%);
            -webkit-backdrop-filter: blur(20px) saturate(180%);
            border-bottom: 1px solid var(--card-border);
            padding: 10px 24px;
        }}
        .filter-inner {{
            max-width: 1400px;
            margin: 0 auto;
            display: flex;
            align-items: center;
            gap: 8px;
            flex-wrap: wrap;
        }}
        .filter-label {{
            font-size: 11px;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.06em;
            font-weight: 600;
            margin-right: 4px;
            white-space: nowrap;
        }}
        .filter-btn {{
            padding: 6px 16px;
            font-size: 12px;
            font-weight: 600;
            color: var(--text-muted);
            background: var(--card);
            border: 1px solid var(--card-border);
            border-radius: 20px;
            cursor: pointer;
            transition: all 0.25s cubic-bezier(.25,.1,.25,1);
            white-space: nowrap;
            font-family: inherit;
        }}
        .filter-btn:hover {{
            color: var(--text);
            background: var(--surface2);
            border-color: #d1d5db;
        }}
        .filter-btn.active {{
            color: #fff;
            background: var(--accent);
            border-color: var(--accent);
            box-shadow: 0 2px 12px rgba(60, 180, 173, 0.25);
        }}
        .filter-period-label {{
            margin-left: auto;
            font-size: 11px;
            color: var(--text-muted);
            opacity: 0.7;
        }}
        /* Data freshness bar (#45) */
        .freshness-bar {{
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 4px 24px;
            background: var(--surface2);
            border-bottom: 1px solid var(--card-border);
            font-size: 10px;
        }}
        .freshness-pill {{
            display: inline-flex;
            align-items: center;
            gap: 4px;
            padding: 2px 8px;
            border-radius: 10px;
            background: rgba(60, 180, 173, 0.08);
            color: var(--text-muted);
            font-weight: 500;
            white-space: nowrap;
        }}
        .live-dot {{
            width: 6px; height: 6px; border-radius: 50%;
            background: #22c55e;
            animation: livePulse 2s infinite;
            display: inline-block;
        }}
        @keyframes livePulse {{
            0%, 100% {{ opacity: 1; }}
            50% {{ opacity: 0.3; }}
        }}
        .supabase-status {{
            margin-left: auto;
            display: inline-flex;
            align-items: center;
            gap: 4px;
            padding: 2px 8px;
            border-radius: 10px;
            font-size: 10px;
            font-weight: 600;
            white-space: nowrap;
        }}
        .supabase-status.live {{
            background: rgba(34, 197, 94, 0.1);
            color: #16a34a;
        }}
        .supabase-status.offline {{
            background: rgba(107, 114, 128, 0.1);
            color: var(--text-muted);
        }}
        .supabase-status.error {{
            background: rgba(239, 68, 68, 0.1);
            color: #dc2626;
        }}
        .kpi-updated {{
            animation: kpiFlash 0.6s ease;
        }}
        @keyframes kpiFlash {{
            0% {{ background: rgba(60, 180, 173, 0.15); }}
            100% {{ background: transparent; }}
        }}

        /* Clickable KPI cards (#40) */
        .stat-card[data-nav-page] {{
            cursor: pointer;
        }}
        .stat-card[data-nav-page]:hover {{
            border-color: var(--accent);
            box-shadow: 0 4px 16px rgba(60, 180, 173, 0.12);
        }}
        .stat-card[data-nav-page]:hover::before {{
            opacity: 1;
        }}

        .yoy-badge {{
            display: inline-flex;
            align-items: center;
            gap: 3px;
            font-size: 11px;
            font-weight: 600;
            padding: 2px 8px;
            border-radius: 12px;
            margin-left: 6px;
            vertical-align: middle;
        }}
        .yoy-badge.up {{
            color: #16a34a;
            background: rgba(34, 197, 94, 0.1);
        }}
        .yoy-badge.down {{
            color: #dc2626;
            background: rgba(239, 68, 68, 0.1);
        }}
        .yoy-badge.neutral {{
            color: var(--text-muted);
            background: rgba(107, 114, 128, 0.1);
        }}
        @media (max-width: 640px) {{
            .filter-bar {{ padding: 8px 16px; top: 0; }}
            .filter-btn {{ padding: 5px 12px; font-size: 11px; }}
            .filter-period-label {{ display: none; }}
        }}

        /* ============================================================
           Login Overlay
           ============================================================ */
        .login-overlay {{
            position: fixed;
            inset: 0;
            z-index: 99999;
            background: #242833;
            display: flex;
            align-items: center;
            justify-content: center;
        }}
        .login-overlay.hidden {{
            display: none;
        }}
        .login-card {{
            background: #fff;
            border-radius: 16px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            padding: 48px 40px;
            max-width: 380px;
            width: 90%;
            text-align: center;
        }}
        .login-brand {{
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
            margin-bottom: 24px;
        }}
        .login-brand .brand-dot {{
            width: 32px;
            height: 32px;
            background: {COLORS["accent"]};
            border-radius: 8px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            color: #fff;
            font-weight: 800;
            font-size: 18px;
        }}
        .login-brand span:last-child {{
            font-size: 22px;
            font-weight: 700;
            color: {COLORS["text"]};
        }}
        .login-title {{
            font-size: 28px;
            font-weight: 800;
            color: {COLORS["text"]};
            margin-bottom: 6px;
        }}
        .login-subtitle {{
            color: {COLORS["text_muted"]};
            font-size: 14px;
            margin: 0 0 24px 0;
        }}
        .login-input {{
            width: 100%;
            padding: 12px 16px;
            border: 2px solid {COLORS["card_border"]};
            border-radius: 10px;
            font-size: 16px;
            font-family: 'Assistant', sans-serif;
            outline: none;
            transition: border-color 0.2s;
            box-sizing: border-box;
        }}
        .login-input:focus {{
            border-color: {COLORS["accent"]};
        }}
        .login-btn {{
            width: 100%;
            margin-top: 16px;
            padding: 12px;
            background: linear-gradient(135deg, {COLORS["accent"]}, {COLORS["accent2"]});
            color: #fff;
            border: none;
            border-radius: 10px;
            font-size: 16px;
            font-weight: 700;
            font-family: 'Assistant', sans-serif;
            cursor: pointer;
            transition: opacity 0.2s;
        }}
        .login-btn:hover {{
            opacity: 0.9;
        }}

        /* Sidebar user display */
        .sidebar-user {{
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 10px 20px;
            border-top: 1px solid rgba(255,255,255,0.08);
            border-bottom: 1px solid rgba(255,255,255,0.08);
            color: rgba(255,255,255,0.65);
            font-size: 13px;
        }}
        .sidebar-user-icon {{
            font-size: 16px;
        }}
        .sidebar-user-name {{
            font-weight: 600;
            color: rgba(255,255,255,0.9);
        }}

        /* ============================================================
           Print
           ============================================================ */
        @media print {{
            body {{ background: white; color: #1a1a1a; display: block; }}
            .sidebar {{ display: none; }}
            .sidebar-toggle {{ display: none; }}
            .filter-bar {{ display: none; }}
            .freshness-bar {{ display: none; }}
            .layout-main {{ margin-left: 0; }}
            .glass-card, .stat-card {{
                background: white;
                border: 1px solid #ddd;
                box-shadow: none;
                break-inside: avoid;
            }}
            .dashboard-section {{ opacity: 1; transform: none; animation: none; }}
            .data-table th {{ background: #f5f5f5; color: #333; }}
            .data-table td {{ color: #333; }}
            .section-title {{ color: #1a1a1a; }}
            .section-subtitle, .card-title {{ color: #666; }}
        }}

        /* ============================================================
           Page-based SPA
           ============================================================ */
        .dash-page {{
            display: none;
        }}
        .dash-page.active {{
            display: block;
            animation: page-fade-in 0.4s ease-out;
        }}
        @keyframes page-fade-in {{
            from {{ opacity: 0; transform: translateY(12px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}

        /* ============================================================
           Deal Flow Navigation
           ============================================================ */
        .deal-flow-nav {{
            display: flex;
            align-items: center;
            gap: 0;
            overflow-x: auto;
            padding: 8px 0;
            margin-bottom: 8px;
            scrollbar-width: thin;
        }}
        .deal-flow-step {{
            display: flex;
            align-items: center;
            gap: 0;
            white-space: nowrap;
        }}
        .deal-flow-step .step-dot {{
            width: 22px;
            height: 22px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 10px;
            font-weight: 700;
            color: #fff;
            flex-shrink: 0;
            transition: all 0.2s ease;
        }}
        .deal-flow-step .step-label {{
            font-size: 11px;
            font-weight: 600;
            color: var(--text-muted);
            margin-left: 6px;
            letter-spacing: 0.01em;
        }}
        .deal-flow-step .step-arrow {{
            font-size: 14px;
            color: #d1d5db;
            margin: 0 8px;
        }}

        /* ============================================================
           Monday.com Board Styles — eComplete Light
           ============================================================ */
        .board-container {{
            border-radius: var(--radius);
            overflow: hidden;
            border: 1px solid var(--card-border);
        }}
        .board-group {{
            border-bottom: 1px solid var(--card-border);
        }}
        .board-group:last-child {{
            border-bottom: none;
        }}
        .board-group-header {{
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 8px 14px;
            cursor: pointer;
            transition: background 0.15s ease;
            user-select: none;
            background: var(--surface2);
        }}
        .board-group-header:hover {{
            background: #eef0f3;
        }}
        .board-group-header .group-color {{
            width: 5px;
            height: 24px;
            border-radius: 3px;
            flex-shrink: 0;
        }}
        .board-group-header .group-title {{
            font-size: 13px;
            font-weight: 700;
            color: var(--text);
            flex: 1;
        }}
        .board-group-header .group-count {{
            font-size: 12px;
            color: var(--text-muted);
            font-weight: 500;
        }}
        .board-group-header .group-arrow {{
            font-size: 10px;
            color: var(--text-muted);
            transition: transform 0.2s ease;
        }}
        .board-group-header .group-arrow.expanded {{
            transform: rotate(90deg);
        }}

        .board-rows {{
            background: var(--card);
        }}
        .board-row {{
            display: grid;
            grid-template-columns: 2fr 120px 100px 120px 100px 90px 90px;
            align-items: center;
            padding: 6px 14px 6px 28px;
            border-bottom: 1px solid var(--card-border);
            font-size: 12px;
            transition: background 0.12s ease;
        }}
        .board-row:hover {{
            background: rgba(60, 180, 173, 0.04);
        }}
        .board-row:last-child {{
            border-bottom: none;
        }}
        .board-header-row {{
            display: grid;
            grid-template-columns: 2fr 120px 100px 120px 100px 90px 90px;
            padding: 5px 14px 5px 28px;
            font-size: 11px;
            font-weight: 600;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.04em;
            background: var(--surface2);
            border-bottom: 1px solid var(--card-border);
        }}

        .status-pill {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: 600;
            white-space: nowrap;
            min-width: 80px;
            text-align: center;
        }}

        .person-avatar {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            font-size: 12px;
        }}
        .person-avatar .avatar-circle {{
            width: 26px;
            height: 26px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 10px;
            font-weight: 700;
            color: #fff;
            flex-shrink: 0;
        }}

        .progress-mini {{
            display: flex;
            align-items: center;
            gap: 6px;
        }}
        .progress-mini .bar {{
            flex: 1;
            height: 6px;
            background: #e5e7eb;
            border-radius: 3px;
            overflow: hidden;
            min-width: 40px;
        }}
        .progress-mini .bar-fill {{
            height: 100%;
            border-radius: 3px;
            transition: width 0.6s ease;
        }}
        .progress-mini .pct {{
            font-size: 11px;
            color: var(--text-muted);
            min-width: 30px;
            text-align: right;
        }}

        @media (max-width: 1024px) {{
            .board-row, .board-header-row {{
                grid-template-columns: 1.5fr 100px 80px 100px;
            }}
            .board-row > :nth-child(n+5),
            .board-header-row > :nth-child(n+5) {{
                display: none;
            }}
            .deal-flow-nav {{
                padding: 12px 0;
            }}
            .deal-flow-step .step-label {{
                font-size: 10px;
            }}
        }}
        @media (max-width: 640px) {{
            .board-row, .board-header-row {{
                grid-template-columns: 1fr 90px;
            }}
            .board-row > :nth-child(n+3),
            .board-header-row > :nth-child(n+3) {{
                display: none;
            }}
            .deal-flow-step .step-label {{
                display: none;
            }}
            .deal-flow-step .step-dot {{
                width: 22px;
                height: 22px;
                font-size: 9px;
            }}
        }}

        /* ============================================================
           IC Project Detail Panels (expandable)
           ============================================================ */
        .ic-detail {{
            display: none;
            background: var(--surface2);
            border-top: 1px solid var(--card-border);
            padding: 12px 16px 12px 36px;
            animation: detail-slide-in 0.25s ease;
        }}
        .ic-detail.open {{
            display: block;
        }}
        @keyframes detail-slide-in {{
            from {{ opacity: 0; max-height: 0; }}
            to {{ opacity: 1; max-height: 600px; }}
        }}
        .ic-detail-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
        }}
        .ic-detail-section {{
            background: var(--card);
            border: 1px solid var(--card-border);
            border-radius: var(--radius-sm);
            padding: 10px 12px;
        }}
        .ic-detail-section h4 {{
            font-size: 11px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: var(--text-muted);
            margin-bottom: 6px;
        }}
        .ic-detail-row {{
            display: flex;
            justify-content: space-between;
            padding: 3px 0;
            font-size: 12px;
            border-bottom: 1px solid var(--card-border);
        }}
        .ic-detail-row:last-child {{ border-bottom: none; }}
        .ic-detail-row .label {{ color: var(--text-muted); }}
        .ic-detail-row .value {{ color: var(--text); font-weight: 500; max-width: 60%; text-align: right; }}
        .ic-next-step {{
            display: flex;
            align-items: flex-start;
            gap: 6px;
            padding: 4px 0;
            font-size: 12px;
            color: var(--text);
        }}
        .ic-next-step .bullet {{
            color: var(--accent);
            font-weight: 700;
            flex-shrink: 0;
        }}
        .ic-gap-flag {{
            display: inline-flex;
            align-items: center;
            gap: 4px;
            padding: 2px 8px;
            border-radius: 10px;
            font-size: 10px;
            font-weight: 600;
            background: rgba(239, 68, 68, 0.1);
            color: #dc2626;
            margin: 2px;
        }}
        .ic-task-item {{
            display: flex;
            align-items: center;
            gap: 5px;
            font-size: 12px;
            padding: 2px 0;
        }}
        .ic-task-item .check {{
            width: 14px;
            height: 14px;
            border-radius: 3px;
            border: 1.5px solid var(--card-border);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 9px;
            flex-shrink: 0;
        }}
        .ic-task-item .check.done {{
            background: var(--success);
            border-color: var(--success);
            color: #fff;
        }}
        .board-row.ic-row {{ cursor: pointer; }}
        .board-row.ic-row:hover {{ background: rgba(60, 180, 173, 0.06); }}
        .ic-expand-arrow {{
            font-size: 10px;
            color: var(--text-muted);
            transition: transform 0.2s ease;
            margin-left: auto;
        }}
        .ic-expand-arrow.open {{ transform: rotate(90deg); }}

        /* ============================================================
           AI Section
           ============================================================ */
        .ai-board-card {{
            background: var(--card);
            border: 1px solid var(--card-border);
            border-radius: var(--radius-sm);
            padding: 12px 14px;
            transition: var(--transition);
        }}
        .ai-board-card:hover {{
            border-color: rgba(60, 180, 173, 0.25);
        }}
        .ai-item-row {{
            display: grid;
            grid-template-columns: 2fr 120px 100px 120px;
            align-items: center;
            padding: 6px 12px;
            font-size: 12px;
            border-bottom: 1px solid var(--card-border);
            cursor: pointer;
            transition: background 0.12s ease;
        }}
        .ai-item-row:hover {{ background: rgba(60, 180, 173, 0.04); }}
        .ai-item-row:last-child {{ border-bottom: none; }}
        .ai-item-detail {{
            display: none;
            background: var(--surface2);
            border-top: 1px solid var(--card-border);
            padding: 10px 14px;
            font-size: 12px;
            animation: detail-slide-in 0.25s ease;
        }}
        .ai-item-detail.open {{ display: block; }}
        @media (max-width: 1024px) {{
            .ic-detail-grid {{ grid-template-columns: 1fr; }}
            .ai-item-row {{ grid-template-columns: 1fr 100px; }}
            .ai-item-row > :nth-child(n+3) {{ display: none; }}
        }}

        /* ============================================================
           AI Chat Assistant (eComplete AI)
           ============================================================ */
        .chat-fab {{
            position: fixed;
            bottom: 24px;
            right: 24px;
            width: 52px;
            height: 52px;
            border-radius: 50%;
            background: linear-gradient(135deg, {COLORS['accent']}, {COLORS['accent2']});
            color: #fff;
            border: none;
            cursor: pointer;
            box-shadow: 0 4px 16px rgba(60,180,173,0.35);
            z-index: 9999;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 22px;
            transition: transform 0.2s, box-shadow 0.2s;
        }}
        .chat-fab:hover {{
            transform: scale(1.08);
            box-shadow: 0 6px 24px rgba(60,180,173,0.45);
        }}
        .chat-fab.has-panel {{ display: none; }}

        .chat-panel {{
            position: fixed;
            bottom: 24px;
            right: 24px;
            width: 400px;
            max-width: calc(100vw - 48px);
            height: 540px;
            max-height: calc(100vh - 48px);
            background: var(--card);
            border: 1px solid var(--card-border);
            border-radius: 16px;
            box-shadow: 0 12px 48px rgba(0,0,0,0.15);
            z-index: 10000;
            display: none;
            flex-direction: column;
            overflow: hidden;
        }}
        .chat-panel.open {{
            display: flex;
            animation: chatSlideIn 0.25s ease;
        }}
        @keyframes chatSlideIn {{
            from {{ opacity: 0; transform: translateY(20px) scale(0.96); }}
            to {{ opacity: 1; transform: translateY(0) scale(1); }}
        }}

        .chat-header {{
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 14px 16px;
            background: linear-gradient(135deg, {COLORS['accent']}, {COLORS['accent2']});
            color: #fff;
            flex-shrink: 0;
        }}
        .chat-header-avatar {{
            width: 32px; height: 32px;
            border-radius: 50%;
            background: rgba(255,255,255,0.2);
            display: flex; align-items: center; justify-content: center;
            font-size: 16px; font-weight: 700;
        }}
        .chat-header-info {{
            flex: 1;
        }}
        .chat-header-name {{
            font-weight: 700; font-size: 14px;
        }}
        .chat-header-status {{
            font-size: 10px; opacity: 0.85;
        }}
        .chat-close {{
            background: rgba(255,255,255,0.15);
            border: none; cursor: pointer;
            color: #fff; font-size: 18px;
            width: 28px; height: 28px;
            border-radius: 50%;
            display: flex; align-items: center; justify-content: center;
        }}
        .chat-close:hover {{
            background: rgba(255,255,255,0.25);
        }}

        .chat-messages {{
            flex: 1;
            overflow-y: auto;
            padding: 16px;
            display: flex;
            flex-direction: column;
            gap: 12px;
        }}
        .chat-msg {{
            max-width: 88%;
            padding: 10px 14px;
            border-radius: 14px;
            font-size: 13px;
            line-height: 1.5;
            word-wrap: break-word;
        }}
        .chat-msg.user {{
            align-self: flex-end;
            background: {COLORS['accent']};
            color: #fff;
            border-bottom-right-radius: 4px;
        }}
        .chat-msg.assistant {{
            align-self: flex-start;
            background: var(--bg);
            color: var(--text);
            border: 1px solid var(--card-border);
            border-bottom-left-radius: 4px;
        }}
        .chat-msg.assistant strong {{ font-weight: 700; }}
        .chat-msg.assistant ul, .chat-msg.assistant ol {{
            margin: 4px 0; padding-left: 18px;
        }}
        .chat-msg.assistant li {{ margin-bottom: 2px; }}
        .chat-msg.assistant code {{
            background: rgba(0,0,0,0.06);
            padding: 1px 4px;
            border-radius: 3px;
            font-size: 12px;
        }}
        .chat-msg.system {{
            align-self: center;
            background: transparent;
            color: var(--text-muted);
            font-size: 11px;
            text-align: center;
            padding: 4px 8px;
        }}
        .chat-typing {{
            align-self: flex-start;
            display: flex;
            gap: 4px;
            padding: 12px 16px;
        }}
        .chat-typing span {{
            width: 7px; height: 7px;
            border-radius: 50%;
            background: {COLORS['accent']};
            animation: typingBounce 1.4s infinite;
        }}
        .chat-typing span:nth-child(2) {{ animation-delay: 0.15s; }}
        .chat-typing span:nth-child(3) {{ animation-delay: 0.3s; }}
        @keyframes typingBounce {{
            0%, 60%, 100% {{ transform: translateY(0); opacity: 0.4; }}
            30% {{ transform: translateY(-6px); opacity: 1; }}
        }}

        /* Chat tabs */
        .chat-tabs {{
            display: flex;
            border-bottom: 1px solid var(--card-border);
            flex-shrink: 0;
        }}
        .chat-tab {{
            flex: 1;
            padding: 8px 0;
            border: none;
            background: none;
            cursor: pointer;
            font-size: 12px;
            font-weight: 600;
            font-family: 'Assistant', sans-serif;
            color: var(--text-muted);
            transition: color 0.2s, border-color 0.2s;
            border-bottom: 2px solid transparent;
        }}
        .chat-tab.active {{
            color: {COLORS['accent']};
            border-bottom-color: {COLORS['accent']};
        }}
        .chat-tab:hover {{ color: {COLORS['accent']}; }}

        /* Categorised suggestions */
        .chat-suggestions {{
            display: block;
            padding: 0;
            max-height: 220px;
            overflow-y: auto;
            border-top: 1px solid var(--card-border);
            flex-shrink: 0;
        }}
        .chat-suggest-group {{
            border-bottom: 1px solid var(--card-border);
        }}
        .chat-suggest-group:last-child {{ border-bottom: none; }}
        .chat-suggest-header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 8px 16px;
            font-size: 12px;
            font-weight: 700;
            color: var(--text-muted);
            cursor: pointer;
            transition: color 0.2s;
        }}
        .chat-suggest-header:hover {{ color: {COLORS['accent']}; }}
        .chat-suggest-arrow {{
            font-size: 10px;
            transition: transform 0.2s;
        }}
        .chat-suggest-group.collapsed .chat-suggest-arrow {{
            transform: rotate(-90deg);
        }}
        .chat-suggest-group.collapsed .chat-suggest-items {{
            display: none;
        }}
        .chat-suggest-items {{
            display: flex;
            flex-wrap: wrap;
            gap: 5px;
            padding: 0 16px 8px;
        }}
        .chat-suggestion {{
            padding: 5px 10px;
            border: 1px solid var(--card-border);
            border-radius: 16px;
            background: var(--bg);
            color: var(--text-muted);
            font-size: 11px;
            cursor: pointer;
            transition: var(--transition);
            font-family: 'Assistant', sans-serif;
        }}
        .chat-suggestion:hover {{
            border-color: {COLORS['accent']};
            color: {COLORS['accent']};
            background: rgba(60,180,173,0.05);
        }}

        /* Reports list */
        .chat-reports {{
            flex: 1;
            overflow-y: auto;
            padding: 8px 0;
        }}
        .chat-report-item {{
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 10px 16px;
            cursor: pointer;
            transition: background 0.2s;
        }}
        .chat-report-item:hover {{
            background: rgba(60,180,173,0.05);
        }}
        .chat-report-icon {{
            font-size: 18px;
            width: 32px;
            height: 32px;
            border-radius: 8px;
            background: var(--surface2);
            display: flex;
            align-items: center;
            justify-content: center;
            flex-shrink: 0;
        }}
        .chat-report-info {{ flex: 1; min-width: 0; }}
        .chat-report-title {{
            font-size: 13px;
            font-weight: 600;
            color: var(--text);
        }}
        .chat-report-desc {{
            font-size: 11px;
            color: var(--text-muted);
            margin-top: 1px;
        }}
        .chat-report-arrow {{
            color: var(--text-muted);
            font-size: 14px;
            flex-shrink: 0;
        }}
        .chat-report-item:hover .chat-report-arrow {{
            color: {COLORS['accent']};
        }}
        .chat-report-loading {{
            position: absolute;
            inset: 0;
            background: rgba(255,255,255,0.92);
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            gap: 12px;
            z-index: 10;
            font-size: 13px;
            color: var(--text-muted);
        }}

        /* Per-message action buttons */
        .chat-msg-actions {{
            display: flex;
            gap: 4px;
            margin-top: 6px;
            padding-top: 4px;
            border-top: 1px solid var(--card-border);
            opacity: 0;
            transition: opacity 0.2s;
        }}
        .chat-msg.assistant:hover .chat-msg-actions {{ opacity: 1; }}
        .chat-action-btn {{
            background: none;
            border: 1px solid var(--card-border);
            border-radius: 4px;
            cursor: pointer;
            font-size: 12px;
            padding: 2px 6px;
            color: var(--text-muted);
            transition: color 0.2s, border-color 0.2s;
        }}
        .chat-action-btn:hover {{
            color: {COLORS['accent']};
            border-color: {COLORS['accent']};
        }}

        .chat-input-area {{
            display: flex;
            gap: 8px;
            padding: 12px 16px;
            border-top: 1px solid var(--card-border);
            background: var(--card);
            flex-shrink: 0;
        }}
        .chat-input {{
            flex: 1;
            border: 1px solid var(--card-border);
            border-radius: 20px;
            padding: 8px 14px;
            font-size: 13px;
            font-family: 'Assistant', sans-serif;
            outline: none;
            transition: border-color 0.2s;
            background: var(--bg);
            color: var(--text);
        }}
        .chat-input:focus {{
            border-color: {COLORS['accent']};
        }}
        .chat-input::placeholder {{
            color: var(--text-muted);
        }}
        .chat-send {{
            width: 36px; height: 36px;
            border-radius: 50%;
            border: none;
            background: {COLORS['accent']};
            color: #fff;
            cursor: pointer;
            display: flex; align-items: center; justify-content: center;
            font-size: 16px;
            transition: background 0.2s, opacity 0.2s;
            flex-shrink: 0;
        }}
        .chat-send:hover {{ background: {COLORS['accent2']}; }}
        .chat-send:disabled {{
            opacity: 0.4; cursor: not-allowed;
        }}
        .chat-error {{
            color: {COLORS['danger']};
            font-size: 11px;
            padding: 4px 16px;
            text-align: center;
        }}

        /* ============================================================
           eComplete AI — Full Page
           ============================================================ */
        .anna-section {{ padding: 0 !important; margin: 0; }}
        .anna-layout {{
            display: grid;
            grid-template-columns: 260px 1fr;
            height: calc(100vh - 56px);
            background: {COLORS['card']};
            border-radius: 12px;
            overflow: hidden;
            border: 1px solid {COLORS['card_border']};
        }}
        /* Sidebar */
        .anna-sidebar {{
            background: {COLORS['surface2']};
            border-right: 1px solid {COLORS['card_border']};
            padding: 12px;
            display: flex;
            flex-direction: column;
            gap: 4px;
            overflow-y: auto;
        }}
        .anna-new-chat {{
            width: 100%;
            padding: 10px 14px;
            background: linear-gradient(135deg, #3CB4AD, #334FB4);
            color: #fff;
            border: none;
            border-radius: 8px;
            font-size: 13px;
            font-weight: 700;
            font-family: 'Assistant', sans-serif;
            cursor: pointer;
            margin-bottom: 8px;
            transition: opacity 0.15s;
        }}
        .anna-new-chat:hover {{ opacity: 0.9; }}
        .anna-conv-list {{
            display: flex;
            flex-direction: column;
            gap: 2px;
            flex: 1;
            overflow-y: auto;
        }}
        .anna-conv-item {{
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 8px 10px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 12px;
            color: {COLORS['text']};
            transition: background 0.15s;
            border: none;
            background: none;
            text-align: left;
            font-family: 'Assistant', sans-serif;
            width: 100%;
        }}
        .anna-conv-item:hover {{ background: {COLORS['card_border']}60; }}
        .anna-conv-item.active {{
            background: {COLORS['card']};
            font-weight: 700;
            box-shadow: 0 1px 3px rgba(0,0,0,0.06);
        }}
        .anna-conv-item .conv-icon {{ font-size: 14px; flex-shrink: 0; }}
        .anna-conv-item .conv-label {{ flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
        .anna-conv-item .conv-delete {{
            opacity: 0; font-size: 11px; color: {COLORS['text_muted']}; cursor: pointer;
            border: none; background: none; padding: 2px 4px; border-radius: 4px;
        }}
        .anna-conv-item:hover .conv-delete {{ opacity: 1; }}
        .anna-conv-item .conv-delete:hover {{ color: {COLORS['danger']}; background: {COLORS['danger']}15; }}
        .anna-sidebar-divider {{
            height: 1px;
            background: {COLORS['card_border']};
            margin: 8px 0;
        }}
        .anna-sidebar-label {{
            font-size: 11px;
            font-weight: 700;
            color: {COLORS['text_muted']};
            text-transform: uppercase;
            letter-spacing: 0.04em;
            padding: 4px 10px 6px;
        }}
        .anna-report-btn {{
            display: flex;
            align-items: center;
            gap: 8px;
            width: 100%;
            padding: 7px 10px;
            border: none;
            border-radius: 6px;
            background: transparent;
            color: {COLORS['text']};
            font-size: 12px;
            font-family: 'Assistant', sans-serif;
            font-weight: 600;
            cursor: pointer;
            text-align: left;
            transition: all 0.15s;
        }}
        .anna-report-btn:hover {{
            background: {COLORS['accent']}12;
            color: {COLORS['accent']};
        }}
        .anna-report-btn span {{ font-size: 13px; }}
        /* Chat area */
        .anna-chat-area {{
            display: flex;
            flex-direction: column;
            min-width: 0;
        }}
        .anna-chat-header {{
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 12px 20px;
            border-bottom: 1px solid {COLORS['card_border']};
            flex-shrink: 0;
        }}
        .anna-avatar {{
            width: 34px; height: 34px; border-radius: 50%;
            background: linear-gradient(135deg, #3CB4AD, #334FB4);
            display: flex; align-items: center; justify-content: center;
            color: #fff; font-weight: 800; font-size: 14px; flex-shrink: 0;
        }}
        .anna-header-info {{ flex: 1; }}
        .anna-header-name {{ font-size: 14px; font-weight: 700; color: {COLORS['text']}; }}
        .anna-header-status {{ font-size: 11px; color: {COLORS['text_muted']}; }}
        .anna-header-btn {{
            background: none; border: 1px solid {COLORS['card_border']};
            border-radius: 6px; padding: 5px 8px; cursor: pointer;
            font-size: 13px; color: {COLORS['text_muted']}; transition: all 0.15s;
        }}
        .anna-header-btn:hover {{ color: {COLORS['text']}; border-color: {COLORS['text_muted']}; }}
        .anna-messages {{
            flex: 1;
            overflow-y: auto;
            padding: 20px 24px;
            display: flex;
            flex-direction: column;
            gap: 12px;
        }}
        /* Welcome screen */
        .anna-welcome {{
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            flex: 1;
            min-height: 300px;
            text-align: center;
            padding: 40px 20px;
        }}
        .anna-welcome-avatar {{
            width: 56px; height: 56px; border-radius: 50%;
            background: linear-gradient(135deg, #3CB4AD, #334FB4);
            display: flex; align-items: center; justify-content: center;
            color: #fff; font-weight: 800; font-size: 24px; margin-bottom: 16px;
        }}
        .anna-welcome-title {{
            font-size: 22px; font-weight: 800; color: {COLORS['text']}; margin-bottom: 6px;
        }}
        .anna-welcome-sub {{
            font-size: 13px; color: {COLORS['text_muted']}; max-width: 400px; margin-bottom: 24px; line-height: 1.5;
        }}
        .anna-suggestions {{
            display: flex; flex-wrap: wrap; gap: 6px; justify-content: center; max-width: 500px;
        }}
        .anna-suggest-btn {{
            padding: 7px 14px;
            border: 1px solid {COLORS['card_border']};
            border-radius: 20px;
            background: {COLORS['card']};
            color: {COLORS['text']};
            font-size: 12px;
            font-family: 'Assistant', sans-serif;
            cursor: pointer;
            transition: all 0.15s;
        }}
        .anna-suggest-btn:hover {{
            border-color: {COLORS['accent']};
            color: {COLORS['accent']};
            background: {COLORS['accent']}08;
        }}
        /* Message bubbles */
        .anna-messages .chat-msg {{
            font-size: 13px;
            line-height: 1.6;
            padding: 10px 14px;
            border-radius: 12px;
            max-width: 80%;
            word-wrap: break-word;
        }}
        .anna-messages .chat-msg.user {{
            background: {COLORS['accent']};
            color: #fff;
            align-self: flex-end;
            border-bottom-right-radius: 4px;
        }}
        .anna-messages .chat-msg.assistant {{
            background: {COLORS['surface2']};
            color: {COLORS['text']};
            align-self: flex-start;
            border-bottom-left-radius: 4px;
            max-width: 90%;
        }}
        .anna-messages .chat-msg.system {{
            background: transparent;
            color: {COLORS['text_muted']};
            font-size: 12px;
            text-align: center;
            align-self: center;
            max-width: 100%;
        }}
        /* Inline report card */
        .anna-report-card {{
            align-self: flex-start;
            max-width: 95%;
            width: 100%;
            border: 1px solid {COLORS['card_border']};
            border-radius: 12px;
            overflow: hidden;
            background: {COLORS['card']};
        }}
        .anna-report-card-header {{
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 14px 18px;
            background: linear-gradient(135deg, #3CB4AD08, #334FB408);
            border-bottom: 2px solid {COLORS['accent']};
        }}
        .anna-report-card-dot {{
            width: 24px; height: 24px; border-radius: 50%; background: {COLORS['accent']};
            display: flex; align-items: center; justify-content: center;
            font-size: 11px; font-weight: 800; color: #fff;
        }}
        .anna-report-card-title {{
            font-size: 14px; font-weight: 700; color: {COLORS['text']}; flex: 1;
        }}
        .anna-report-card-meta {{
            font-size: 10px; color: {COLORS['text_muted']};
        }}
        .anna-report-card-body {{
            padding: 18px;
            font-size: 13px;
            line-height: 1.65;
            color: {COLORS['text']};
        }}
        .anna-report-card-body strong {{ font-weight: 700; }}
        .anna-report-card-body ul, .anna-report-card-body ol {{ margin: 6px 0; padding-left: 20px; }}
        .anna-report-card-body li {{ margin-bottom: 3px; }}
        .anna-report-card-body code {{ background: {COLORS['surface2']}; padding: 1px 5px; border-radius: 3px; font-size: 12px; }}
        .anna-report-card-footer {{
            display: flex;
            gap: 6px;
            padding: 10px 18px;
            border-top: 1px solid {COLORS['card_border']};
            background: {COLORS['surface2']};
        }}
        .anna-report-action {{
            padding: 5px 12px;
            border: 1px solid {COLORS['card_border']};
            border-radius: 6px;
            background: {COLORS['card']};
            color: {COLORS['text']};
            font-size: 11px;
            font-weight: 600;
            font-family: 'Assistant', sans-serif;
            cursor: pointer;
            transition: all 0.15s;
        }}
        .anna-report-action:hover {{
            border-color: {COLORS['accent']};
            color: {COLORS['accent']};
        }}
        /* Input area */
        .anna-input-area {{
            display: flex;
            gap: 8px;
            padding: 14px 20px;
            border-top: 1px solid {COLORS['card_border']};
            flex-shrink: 0;
        }}
        .anna-input {{
            flex: 1;
            padding: 10px 16px;
            border: 1px solid {COLORS['card_border']};
            border-radius: 10px;
            font-size: 13px;
            font-family: 'Assistant', sans-serif;
            outline: none;
            background: {COLORS['surface2']};
            color: {COLORS['text']};
            transition: border-color 0.2s;
        }}
        .anna-input:focus {{ border-color: {COLORS['accent']}; }}
        .anna-send-btn {{
            padding: 10px 18px;
            background: linear-gradient(135deg, #3CB4AD, #334FB4);
            color: #fff;
            border: none;
            border-radius: 10px;
            font-size: 14px;
            font-weight: 700;
            cursor: pointer;
            transition: opacity 0.15s;
        }}
        .anna-send-btn:hover {{ opacity: 0.9; }}
        @media (max-width: 900px) {{
            .anna-layout {{ grid-template-columns: 1fr; height: auto; min-height: calc(100vh - 56px); }}
            .anna-sidebar {{ display: none; }}
        }}

        /* ============================================================
           Executive Summary — compact KPI strip & pillars
           ============================================================ */
        .exec-kpi-strip {{
            display: flex;
            gap: 6px;
            margin-bottom: 10px;
            flex-wrap: wrap;
        }}
        .exec-kpi {{
            flex: 1 1 0;
            min-width: 90px;
            background: {COLORS['card']};
            border: 1px solid {COLORS['card_border']};
            border-radius: 6px;
            padding: 8px 10px;
            text-align: center;
        }}
        .exec-kpi-val {{
            font-size: 18px;
            font-weight: 800;
            line-height: 1.2;
        }}
        .exec-kpi-label {{
            font-size: 10px;
            color: {COLORS['text_muted']};
            text-transform: uppercase;
            letter-spacing: 0.04em;
            margin-top: 2px;
        }}
        .exec-pillars {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 8px;
            margin-bottom: 10px;
        }}
        .exec-pillar {{
            background: {COLORS['card']};
            border: 1px solid {COLORS['card_border']};
            border-radius: 8px;
            padding: 14px 16px;
            transition: var(--transition);
        }}
        .exec-pillar:hover {{
            border-color: rgba(60,180,173,0.35);
            box-shadow: 0 4px 12px rgba(0,0,0,0.06);
        }}
        .exec-pillar-header {{
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 8px;
        }}
        .exec-pillar-icon {{
            width: 28px;
            height: 28px;
            border-radius: 6px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 14px;
            flex-shrink: 0;
        }}
        .exec-pillar-title {{
            font-size: 13px;
            font-weight: 700;
            color: {COLORS['text']};
            flex: 1;
        }}
        .exec-pillar-arrow {{
            font-size: 16px;
            opacity: 0;
            transition: opacity 0.2s;
        }}
        .exec-pillar:hover .exec-pillar-arrow {{ opacity: 1; }}
        .exec-pillar-points {{
            list-style: none;
            padding: 0;
            margin: 0;
        }}
        .exec-pillar-points li {{
            font-size: 11.5px;
            color: {COLORS['text_muted']};
            line-height: 1.5;
            padding: 2px 0;
            border-bottom: 1px solid {COLORS['card_border']};
        }}
        .exec-pillar-points li:last-child {{ border-bottom: none; }}
        .exec-pillar-points li strong {{ color: {COLORS['text']}; }}
        @media (max-width: 1100px) {{
            .exec-pillars {{ grid-template-columns: repeat(2, 1fr); }}
        }}
        @media (max-width: 600px) {{
            .exec-kpi-strip {{ flex-wrap: wrap; }}
            .exec-kpi {{ min-width: 70px; }}
            .exec-pillars {{ grid-template-columns: 1fr; }}
        }}

        @media print {{
            .chat-fab, .chat-panel {{ display: none !important; }}
        }}
    </style>'''


# ---------------------------------------------------------------------------
# JavaScript
# ---------------------------------------------------------------------------

def _build_js() -> str:
    """Build the interactive JavaScript for page-based SPA."""
    return '''
    <script>
    (function() {
        'use strict';

        // ------------------------------------------------------------------
        // Login gate — localStorage name persistence
        // ------------------------------------------------------------------
        var LOGIN_KEY = 'ecomplete_user';
        var loginOverlay = document.getElementById('login-overlay');
        var loginInput = document.getElementById('login-name');
        var storedUser = '';
        try { storedUser = localStorage.getItem(LOGIN_KEY) || ''; } catch(e) {}

        function updateSidebarUser(name) {
            var el = document.getElementById('sidebar-user-name');
            if (el) el.textContent = name || '';
        }

        if (storedUser) {
            // Already logged in — hide overlay immediately
            if (loginOverlay) loginOverlay.classList.add('hidden');
            updateSidebarUser(storedUser);
        } else {
            // Show overlay, prevent scroll
            document.body.style.overflow = 'hidden';
            if (loginInput) loginInput.focus();
        }

        window.doLogin = function() {
            var input = document.getElementById('login-name');
            var name = (input ? input.value : '').trim();
            if (!name) { if (input) input.focus(); return; }
            try { localStorage.setItem(LOGIN_KEY, name); } catch(e) {}
            var overlay = document.getElementById('login-overlay');
            if (overlay) overlay.classList.add('hidden');
            document.body.style.overflow = '';
            updateSidebarUser(name);
        };

        // Enter key support
        if (loginInput) {
            loginInput.addEventListener('keydown', function(e) {
                if (e.key === 'Enter') window.doLogin();
            });
        }

        // ------------------------------------------------------------------
        // Sidebar toggle (mobile)
        // ------------------------------------------------------------------
        window.toggleSidebar = function() {
            var sidebar = document.getElementById('sidebar');
            var toggle = document.getElementById('sidebar-toggle');
            var overlay = document.getElementById('sidebar-overlay');
            sidebar.classList.toggle('open');
            toggle.classList.toggle('open');
            if (overlay) overlay.classList.toggle('visible');
        };

        // Close sidebar when a link is clicked (mobile)
        document.querySelectorAll('.sidebar-link').forEach(function(link) {
            link.addEventListener('click', function() {
                if (window.innerWidth <= 1024) {
                    var sidebar = document.getElementById('sidebar');
                    var toggle = document.getElementById('sidebar-toggle');
                    var overlay = document.getElementById('sidebar-overlay');
                    sidebar.classList.remove('open');
                    toggle.classList.remove('open');
                    if (overlay) overlay.classList.remove('visible');
                }
            });
        });

        // ------------------------------------------------------------------
        // Page-based SPA navigation with LocalStorage (#51)
        // ------------------------------------------------------------------
        var LS_KEY = 'ecomplete_dash_prefs';
        function loadPrefs() {
            try { return JSON.parse(localStorage.getItem(LS_KEY) || '{}'); }
            catch(e) { return {}; }
        }
        function savePrefs(updates) {
            try {
                var p = loadPrefs();
                for (var k in updates) p[k] = updates[k];
                localStorage.setItem(LS_KEY, JSON.stringify(p));
            } catch(e) {}
        }

        // ------------------------------------------------------------------
        // Favourites (#fav)
        // ------------------------------------------------------------------
        var MODULES_MAP = {};
        document.querySelectorAll('.sidebar-link[data-page]').forEach(function(link) {
            MODULES_MAP[link.getAttribute('data-page')] = link.textContent.trim();
        });

        function getFavs() {
            var prefs = loadPrefs();
            return Array.isArray(prefs.favs) ? prefs.favs : [];
        }

        function renderFavs() {
            var favs = getFavs();
            var container = document.getElementById('sidebar-favs');
            var list = document.getElementById('sidebar-favs-list');
            if (!container || !list) return;

            // Show/hide favourites group
            if (favs.length === 0) {
                container.classList.remove('has-favs');
                list.innerHTML = '';
                return;
            }
            container.classList.add('has-favs');

            // Build fav links
            var html = '';
            for (var i = 0; i < favs.length; i++) {
                var fid = favs[i];
                var label = MODULES_MAP[fid] || fid;
                html += '<a href="javascript:void(0)" onclick="showPage(&#39;' + fid + '&#39;)" '
                    + 'class="sidebar-link" data-page="' + fid + '">' + label
                    + '<button class="sidebar-fav is-fav" data-fav="' + fid + '" '
                    + 'onclick="event.preventDefault();event.stopPropagation();toggleFav(&#39;' + fid + '&#39;)" '
                    + 'title="Remove favourite">&#9733;</button></a>';
            }
            list.innerHTML = html;

            // Update star states in main nav
            document.querySelectorAll('.sidebar-fav[data-fav]').forEach(function(btn) {
                var pid = btn.getAttribute('data-fav');
                if (favs.indexOf(pid) !== -1) {
                    btn.classList.add('is-fav');
                } else {
                    btn.classList.remove('is-fav');
                }
            });
        }

        window.toggleFav = function(pageId) {
            var favs = getFavs();
            var idx = favs.indexOf(pageId);
            if (idx === -1) {
                favs.push(pageId);
            } else {
                favs.splice(idx, 1);
            }
            savePrefs({favs: favs});
            renderFavs();
        };

        window.showPage = function(pageId) {
            // Hide all pages
            document.querySelectorAll('.dash-page').forEach(function(page) {
                page.classList.remove('active');
            });
            // Show the target page
            var target = document.getElementById('page-' + pageId);
            if (target) {
                target.classList.add('active');
            }
            // Update sidebar active link
            document.querySelectorAll('.sidebar-link').forEach(function(link) {
                link.classList.toggle('active', link.getAttribute('data-page') === pageId);
            });
            // Scroll to top of content area
            var main = document.getElementById('layout-main');
            if (main) main.scrollTop = 0;
            window.scrollTo(0, 0);
            // Re-trigger animations on the newly visible page
            if (target) {
                target.querySelectorAll('.glass-card, .stat-card').forEach(function(el) {
                    el.style.opacity = '0';
                    el.style.transform = 'translateY(20px)';
                    setTimeout(function() {
                        el.style.transition = 'opacity 0.5s ease, transform 0.5s ease';
                        el.style.opacity = '1';
                        el.style.transform = 'translateY(0)';
                    }, 50);
                });
            }
            // Hide chat FAB, freshness bar, and filter bar on Anna page
            var isAnna = (pageId === 'anna');
            var fab = document.getElementById('chat-fab');
            var freshBar = document.getElementById('freshness-bar');
            var filterBar = document.getElementById('filter-bar');
            if (fab) fab.style.display = isAnna ? 'none' : '';
            if (freshBar) freshBar.style.display = isAnna ? 'none' : '';
            if (filterBar) filterBar.style.display = isAnna ? 'none' : '';
            // Persist last page (#51)
            savePrefs({lastPage: pageId});
        };

        // Clickable KPI card navigation (#40)
        document.addEventListener('click', function(e) {
            var card = e.target.closest('.stat-card[data-nav-page]');
            if (card) {
                showPage(card.getAttribute('data-nav-page'));
            }
        });

        // Restore last page or default to executive (#51) + render favourites
        document.addEventListener('DOMContentLoaded', function() {
            renderFavs();
            var prefs = loadPrefs();
            var startPage = prefs.lastPage || 'executive';
            if (!document.getElementById('page-' + startPage)) startPage = 'executive';
            showPage(startPage);
        });

        // ------------------------------------------------------------------
        // Sortable tables
        // ------------------------------------------------------------------
        window.sortTable = function(tableId, colIdx) {
            var table = document.getElementById(tableId);
            if (!table) return;
            var tbody = table.querySelector('tbody');
            var rows = Array.from(tbody.querySelectorAll('tr'));
            var asc = table.getAttribute('data-sort-col') == colIdx
                      && table.getAttribute('data-sort-dir') !== 'asc';

            rows.sort(function(a, b) {
                var aText = a.children[colIdx] ? a.children[colIdx].textContent.trim() : '';
                var bText = b.children[colIdx] ? b.children[colIdx].textContent.trim() : '';

                // Try numeric comparison (strip currency symbols, commas, %)
                var aNum = parseFloat(aText.replace(/[^0-9.\\-]/g, ''));
                var bNum = parseFloat(bText.replace(/[^0-9.\\-]/g, ''));

                if (!isNaN(aNum) && !isNaN(bNum)) {
                    return asc ? aNum - bNum : bNum - aNum;
                }
                return asc ? aText.localeCompare(bText) : bText.localeCompare(aText);
            });

            rows.forEach(function(row) { tbody.appendChild(row); });
            table.setAttribute('data-sort-col', colIdx);
            table.setAttribute('data-sort-dir', asc ? 'asc' : 'desc');
        };

    })();
    </script>'''


def _build_supabase_js() -> str:
    """Build the Supabase live-fetch JavaScript module.

    Fetches latest metrics from Supabase Storage public URLs and updates
    KPIs on the executive summary page in real time.
    """
    sb_url = os.getenv("SUPABASE_URL", "").strip()

    if not sb_url:
        return ""

    storage_base = f"{sb_url}/storage/v1/object/public/dashboard-data"

    return f'''
    <script>
    (function() {{
        'use strict';

        var STORAGE = '{storage_base}';

        // ---- Format helpers (match Python _fmt_currency / _fmt_number / _fmt_pct) ----
        function fmtCurrency(v) {{
            if (v == null || isNaN(v)) return '\\u00a30';
            var abs = Math.abs(v);
            if (abs >= 1e6) return '\\u00a3' + (v / 1e6).toFixed(1) + 'M';
            if (abs >= 1e3) return '\\u00a3' + (v / 1e3).toFixed(0) + 'K';
            return '\\u00a3' + Math.round(v).toLocaleString();
        }}
        function fmtNumber(v) {{
            if (v == null || isNaN(v)) return '0';
            var abs = Math.abs(v);
            if (abs >= 1e6) return (v / 1e6).toFixed(1) + 'M';
            if (abs >= 1e3) return (v / 1e3).toFixed(1) + 'K';
            return Math.round(v).toLocaleString();
        }}
        function fmtPct(v) {{
            if (v == null || isNaN(v)) return '0%';
            return (v * 100).toFixed(1) + '%';
        }}

        var FORMATTERS = {{
            'pipeline_metrics.total_pipeline_value': fmtCurrency,
            'pipeline_metrics.weighted_pipeline_value': fmtCurrency,
            'pipeline_metrics.win_rate': fmtPct,
            'pipeline_metrics.open_deals_count': fmtNumber,
            'pipeline_metrics.avg_deal_size': fmtCurrency,
            'activity_metrics.total_activities': fmtNumber,
            'record_counts.contacts': fmtNumber,
            'lead_metrics.total_leads': fmtNumber,
            'insights.revenue_forecast.days_30': fmtCurrency,
            'insights.revenue_forecast.days_90': fmtCurrency
        }};

        function resolve(obj, path) {{
            var parts = path.split('.');
            var cur = obj;
            for (var i = 0; i < parts.length; i++) {{
                if (cur == null) return undefined;
                cur = cur[parts[i]];
            }}
            return cur;
        }}

        function setStatus(state, text) {{
            var bar = document.getElementById('freshness-bar');
            if (!bar) return;
            var el = document.getElementById('supabase-status');
            if (!el) {{
                el = document.createElement('span');
                el.id = 'supabase-status';
                el.className = 'supabase-status';
                bar.appendChild(el);
            }}
            el.className = 'supabase-status ' + state;
            if (state === 'live') {{
                el.innerHTML = '<span class="live-dot"></span> ' + text;
            }} else {{
                el.textContent = text;
            }}
        }}

        // ---- Fetch JSON from Supabase Storage (public URL, no auth needed) ----
        function fetchFile(filename) {{
            return fetch(STORAGE + '/' + filename + '?t=' + Date.now())
                .then(function(r) {{
                    if (!r.ok) throw new Error('HTTP ' + r.status);
                    return r.json();
                }});
        }}

        function updateKPIs(data) {{
            var cards = document.querySelectorAll('[data-metric]');
            var updated = 0;
            cards.forEach(function(card) {{
                var key = card.getAttribute('data-metric');
                var val = resolve(data, key);
                if (val === undefined || val === null) return;

                var formatter = FORMATTERS[key] || fmtNumber;
                var valueEl = card.querySelector('[data-role="stat-value"]');
                if (valueEl) {{
                    var newText = formatter(val);
                    if (valueEl.textContent !== newText) {{
                        valueEl.textContent = newText;
                        card.classList.add('kpi-updated');
                        setTimeout(function() {{ card.classList.remove('kpi-updated'); }}, 600);
                        updated++;
                    }}
                }}
            }});
            return updated;
        }}

        function updatePill(name, genAt) {{
            if (!genAt) return;
            var timeStr = genAt.substring(5, 16);
            var pills = document.querySelectorAll('.freshness-pill');
            pills.forEach(function(pill) {{
                if (pill.textContent.indexOf(name) === 0 && timeStr) {{
                    pill.textContent = name + ': ' + timeStr;
                    pill.title = 'Live from Supabase: ' + genAt;
                }}
            }});
        }}

        function init() {{
            setStatus('offline', 'Connecting...');

            fetchFile('hubspot_sales_metrics.json')
                .then(function(data) {{
                    updateKPIs(data);
                    var genAt = data.generated_at || '';
                    var timeStr = genAt.substring(5, 16);
                    setStatus('live', 'Live' + (timeStr ? ' \\u00b7 ' + timeStr : ''));
                    updatePill('HubSpot', genAt);
                    // Store for AI chat context
                    window.__sbHubspot = data;
                }})
                .catch(function(err) {{
                    console.warn('Supabase fetch failed:', err);
                    setStatus('error', 'Offline');
                }});

            fetchFile('monday_metrics.json')
                .then(function(data) {{
                    updatePill('Monday', data.generated_at || '');
                    window.__sbMonday = data;
                }})
                .catch(function() {{}});

            fetchFile('inbound_queue.json')
                .then(function(data) {{
                    updatePill('Queue', data.generated_at || '');
                    window.__sbQueue = data;
                }})
                .catch(function() {{}});

            // Refresh every 5 minutes
            setInterval(function() {{
                fetchFile('hubspot_sales_metrics.json')
                    .then(function(data) {{ updateKPIs(data); }})
                    .catch(function() {{}});
            }}, 300000);
        }}

        if (document.readyState === 'loading') {{
            document.addEventListener('DOMContentLoaded', init);
        }} else {{
            init();
        }}
    }})();
    </script>'''


# ---------------------------------------------------------------------------
# Inbound Queue
# ---------------------------------------------------------------------------

def _build_inbound_queue(data: dict) -> str:
    """Build the Inbound Queue page — prioritised action inbox from all sources."""
    queue_file = BASE_DIR / "data" / "processed" / "inbound_queue.json"
    queue: dict = {}
    if queue_file.exists():
        try:
            with open(queue_file, "r", encoding="utf-8") as f:
                queue = json.load(f)
        except Exception:
            pass

    items = queue.get("items", [])
    summary = queue.get("summary", {})
    by_priority = summary.get("by_priority", {})
    by_category = summary.get("by_category", {})
    by_source = summary.get("by_source", {})

    h = '<section class="dashboard-section">'
    h += f'''<div class="section-header">
        <h2 class="section-title">Inbound Queue</h2>
        <p class="section-subtitle">Prioritised action inbox — {summary.get("total", 0)} signals from HubSpot, Monday.com &amp; system alerts</p>
    </div>'''

    # KPI row
    critical = by_priority.get("critical", 0)
    high = by_priority.get("high", 0)
    medium = by_priority.get("medium", 0)
    low = by_priority.get("low", 0)
    h += '<div class="kpi-grid" style="grid-template-columns:repeat(4,1fr)">'
    h += _stat_card("Critical", str(critical), "need immediate action", "&#9888;", COLORS["danger"])
    h += _stat_card("High", str(high), "action today", "&#9650;", COLORS["warning"])
    h += _stat_card("Medium", str(medium), "this week", "&#9679;", COLORS["accent"])
    h += _stat_card("Low", str(low), "when convenient", "&#9660;", COLORS["accent4"])
    h += '</div>'

    # Category breakdown
    h += f'<div class="glass-card"><div class="card-title">Signal Categories</div>'
    h += '<div style="display:flex;flex-wrap:wrap;gap:8px;margin-top:6px">'
    cat_colors = {
        "stale_follow_up": COLORS["danger"], "new_lead": COLORS["success"],
        "deal_update": COLORS["accent2"], "ic_review": COLORS["accent3"],
        "nda_request": COLORS["accent5"], "web_signal": COLORS["accent"],
        "alert": COLORS["warning"], "meeting_request": COLORS["info"],
        "follow_up": COLORS["accent6"],
    }
    for cat, count in sorted(by_category.items(), key=lambda x: -x[1]):
        cc = cat_colors.get(cat, COLORS["text_muted"])
        label = cat.replace("_", " ").title()
        h += f'''<span style="font-size:11px;font-weight:600;color:{cc};
            background:{cc}12;padding:4px 10px;border-radius:6px;
            border:1px solid {cc}30">{label}: {count}</span>'''
    h += '</div></div>'

    # Source breakdown
    h += f'<div class="glass-card"><div class="card-title">By Source</div>'
    h += '<div style="display:flex;gap:16px;margin-top:6px">'
    src_icons = {"hubspot": "&#128200;", "monday": "&#128197;", "email": "&#9993;", "system": "&#9881;", "weekly": "&#128203;"}
    for src, count in sorted(by_source.items(), key=lambda x: -x[1]):
        icon = src_icons.get(src, "&#9679;")
        h += f'''<div style="text-align:center;padding:10px 16px;background:{COLORS["surface2"]};
            border-radius:8px;flex:1;min-width:80px">
            <div style="font-size:18px">{icon}</div>
            <div style="font-size:18px;font-weight:700;color:{COLORS["text"]};margin:4px 0">{count}</div>
            <div style="font-size:10px;color:{COLORS["text_muted"]};text-transform:capitalize">{src}</div>
        </div>'''
    h += '</div></div>'

    # Top items table — show critical + high priority items (max 50)
    top_items = [i for i in items if i.get("priority") in ("critical", "high")][:50]
    if not top_items:
        top_items = items[:30]

    h += f'<div class="glass-card"><div class="card-title">Top Priority Items ({len(top_items)} shown)</div>'
    h += f'''<div style="overflow-x:auto"><table style="width:100%;border-collapse:collapse;font-size:12px">
        <thead><tr style="border-bottom:2px solid {COLORS["card_border"]};text-align:left">
            <th style="padding:8px 6px;color:{COLORS["text_muted"]}">Priority</th>
            <th style="padding:8px 6px;color:{COLORS["text_muted"]}">Category</th>
            <th style="padding:8px 6px;color:{COLORS["text_muted"]}">Title</th>
            <th style="padding:8px 6px;color:{COLORS["text_muted"]}">Entity</th>
            <th style="padding:8px 6px;color:{COLORS["text_muted"]}">Action</th>
            <th style="padding:8px 6px;color:{COLORS["text_muted"]}">Source</th>
        </tr></thead><tbody>'''

    p_colors = {"critical": COLORS["danger"], "high": COLORS["warning"], "medium": COLORS["accent"], "low": COLORS["accent4"]}
    for item in top_items:
        pri = item.get("priority", "medium")
        pc = p_colors.get(pri, COLORS["text_muted"])
        cat = item.get("category", "").replace("_", " ").title()
        title = item.get("title", "")[:60]
        entity = item.get("entity", "")[:30]
        action = item.get("recommended_action", "")[:40]
        source = item.get("source", "")

        h += f'''<tr style="border-bottom:1px solid {COLORS["card_border"]}">
            <td style="padding:6px"><span style="font-size:10px;font-weight:700;color:{pc};
                background:{pc}12;padding:2px 6px;border-radius:3px;text-transform:uppercase">{pri}</span></td>
            <td style="padding:6px;color:{COLORS["text_muted"]}">{_esc(cat)}</td>
            <td style="padding:6px;font-weight:500;color:{COLORS["text"]}">{_esc(title)}</td>
            <td style="padding:6px;color:{COLORS["text_muted"]}">{_esc(entity)}</td>
            <td style="padding:6px;color:{COLORS["accent2"]};font-size:11px">{_esc(action)}</td>
            <td style="padding:6px;color:{COLORS["text_muted"]};text-transform:capitalize">{_esc(source)}</td>
        </tr>'''

    h += '</tbody></table></div></div>'

    # Remaining items by category (collapsed summary)
    remaining = len(items) - len(top_items)
    if remaining > 0:
        h += f'''<div class="glass-card" style="background:{COLORS["surface2"]}">
            <div style="font-size:12px;color:{COLORS["text_muted"]};text-align:center">
                + {remaining} more items in queue &mdash; run
                <code style="background:{COLORS["card"]};padding:2px 6px;border-radius:4px">python scripts/inbound_queue.py --top 100</code>
                for full details
            </div>
        </div>'''

    h += '</section>'
    return h


# ---------------------------------------------------------------------------
# Quick Actions
# ---------------------------------------------------------------------------

def _build_quick_actions(data: dict) -> str:
    """Build the Quick Actions page with email templates and recommended actions."""
    actions_file = BASE_DIR / "data" / "processed" / "email_actions.json"
    actions: dict = {}
    if actions_file.exists():
        try:
            with open(actions_file, "r", encoding="utf-8") as f:
                actions = json.load(f)
        except Exception:
            pass

    templates = actions.get("scheduling_templates", [])
    quick_responses = actions.get("quick_responses", [])
    suggestions = actions.get("suggested_actions", [])
    constraints = actions.get("scheduling_constraints", {})
    booking_link = actions.get("booking_link", "")

    html = '<section class="dashboard-section">'
    html += f'''<div class="section-header">
        <h2 class="section-title">Quick Actions</h2>
        <p class="section-subtitle">Email templates, scheduling, and recommended actions</p>
    </div>'''

    # KPIs
    html += '<div class="kpi-grid" style="grid-template-columns:repeat(4,1fr)">'
    html += _stat_card("Templates", str(len(templates)), "scheduling", "", COLORS["accent"])
    html += _stat_card("Quick Responses", str(len(quick_responses)), "pre-built", "", COLORS["accent2"])
    html += _stat_card("Suggested Actions", str(len(suggestions)), "from live data", "", COLORS["accent3"])
    days_str = ", ".join(constraints.get("days", []))
    html += _stat_card("Meeting Days", days_str or "Not set", f"{constraints.get('earliest', '')}-{constraints.get('latest', '')}", "", COLORS["accent4"])
    html += '</div>'

    # Suggested Actions (from live data)
    if suggestions:
        html += f'<div class="glass-card"><div class="card-title">Recommended Actions</div>'
        for s in suggestions:
            priority = s.get("priority", "medium")
            p_color = {"high": COLORS["danger"], "medium": "#f59e0b", "low": COLORS["accent"]}.get(priority, COLORS["text_muted"])
            p_icon = {"high": "&#9888;", "medium": "&#9679;", "low": "&#10003;"}.get(priority, "&#9679;")
            action_type = s.get("action", "")
            btn_label = {"schedule_call": "Schedule Call", "schedule_meeting": "Book Meeting", "send_email": "Send Email"}.get(action_type, "Take Action")

            html += f'''<div style="display:flex;align-items:center;gap:10px;padding:8px 0;
                border-bottom:1px solid {COLORS["card_border"]}">
                <span style="color:{p_color};font-size:14px">{p_icon}</span>
                <div style="flex:1">
                    <div style="font-size:13px;font-weight:600;color:{COLORS["text"]}">{_esc(s.get("title", ""))}</div>
                    <div style="font-size:11px;color:{COLORS["text_muted"]}">{_esc(s.get("detail", ""))}</div>
                </div>
                <span style="font-size:10px;font-weight:600;color:{p_color};
                    text-transform:uppercase;letter-spacing:0.05em;
                    padding:2px 8px;border-radius:4px;
                    background:{p_color}15">{priority}</span>
            </div>'''
        html += '</div>'

    # Scheduling Templates
    html += f'<div class="glass-card"><div class="card-title">Scheduling Templates</div>'
    if booking_link:
        html += f'<div style="margin-bottom:10px;padding:8px 12px;background:{COLORS["accent"]}10;border-radius:8px;border:1px solid {COLORS["accent"]}30">'
        html += f'<span style="font-size:11px;color:{COLORS["text_muted"]}">Booking Link:</span> '
        html += f'<span style="font-size:12px;font-weight:600;color:{COLORS["accent"]}">{_esc(booking_link)}</span></div>'
    else:
        html += f'<div style="margin-bottom:10px;padding:8px 12px;background:#f59e0b10;border-radius:8px;border:1px solid #f59e0b30">'
        html += f'<span style="font-size:11px;color:#f59e0b">Set your HubSpot booking link in config/email_templates.json</span></div>'

    for tmpl in templates:
        html += f'''<div style="display:flex;align-items:center;gap:10px;padding:8px 0;
            border-bottom:1px solid {COLORS["card_border"]}">
            <div style="width:28px;height:28px;border-radius:6px;background:{COLORS["accent"]}15;
                display:flex;align-items:center;justify-content:center;font-size:12px;
                color:{COLORS["accent"]}">&#9993;</div>
            <div style="flex:1">
                <div style="font-size:13px;font-weight:600;color:{COLORS["text"]}">{_esc(tmpl.get("name", ""))}</div>
                <div style="font-size:11px;color:{COLORS["text_muted"]}">{_esc(tmpl.get("use_when", ""))}</div>
            </div>
            <span style="font-size:10px;color:{COLORS["accent2"]};background:{COLORS["accent2"]}12;
                padding:2px 8px;border-radius:4px">{_esc(tmpl.get("key", ""))}</span>
        </div>'''
    html += '</div>'

    # Quick Responses
    html += f'<div class="glass-card"><div class="card-title">Quick Responses</div>'
    for qr in quick_responses:
        html += f'''<div style="display:flex;align-items:center;gap:10px;padding:8px 0;
            border-bottom:1px solid {COLORS["card_border"]}">
            <div style="width:28px;height:28px;border-radius:6px;background:{COLORS["accent3"]}15;
                display:flex;align-items:center;justify-content:center;font-size:12px;
                color:{COLORS["accent3"]}">&#9889;</div>
            <div style="flex:1">
                <div style="font-size:13px;font-weight:600;color:{COLORS["text"]}">{_esc(qr.get("name", ""))}</div>
            </div>
            <span style="font-size:10px;color:{COLORS["accent4"]};background:{COLORS["accent4"]}12;
                padding:2px 8px;border-radius:4px">{_esc(qr.get("key", ""))}</span>
        </div>'''
    html += '</div>'

    # Setup instructions
    html += f'''<div class="glass-card" style="background:{COLORS["surface2"]}">
        <div class="card-title">Setup</div>
        <div style="font-size:12px;color:{COLORS["text_muted"]};line-height:1.6">
            <strong>1.</strong> Set your HubSpot booking link in <code>config/email_templates.json</code><br>
            <strong>2.</strong> Customise templates to match your tone and style<br>
            <strong>3.</strong> Run <code>python scripts/email_actions.py --generate-dashboard</code> to refresh actions<br>
            <strong>4.</strong> Use <code>--template london_meeting --to email@example.com</code> for CLI mailto links
        </div>
    </div>'''

    html += '</section>'
    return html


# ---------------------------------------------------------------------------
# Merged page wrappers — combine related sections into single pages
# ---------------------------------------------------------------------------

def _build_leads_and_funnel(data: dict) -> str:
    """Leads & Conversion — merges Leads and Funnel sections into one page."""
    return _build_leads_section(data) + _build_funnel_section(data)


def _build_activities_and_contacts(data: dict) -> str:
    """Activity & Contacts — merges Activity Tracking and Contacts sections."""
    return _build_activity_section(data) + _build_contacts_section(data)


def _build_monday_pipeline_and_workspaces(data: dict) -> str:
    """M&A Pipeline — merges Monday Pipeline and Workspaces sections."""
    return _build_monday_pipeline(data) + _build_monday_workspaces(data)


def _build_inbound_and_actions(data: dict) -> str:
    """Inbound Queue — merges Inbound Queue and Quick Actions sections."""
    return _build_inbound_queue(data) + _build_quick_actions(data)


# ---------------------------------------------------------------------------
# Main assembly
# ---------------------------------------------------------------------------

def _build_sidebar() -> str:
    """Build the fixed left-hand navy sidebar with grouped sections, favourites, and AI link.
    Uses MODULES registry as single source of truth."""
    from collections import OrderedDict
    nav_groups: Dict[str, dict] = OrderedDict()
    for mod in MODULES:
        grp = mod["group"]
        if grp not in nav_groups:
            nav_groups[grp] = {"label": grp, "icon": mod["icon"], "items": []}
        nav_groups[grp]["items"].append((mod["id"], mod["label"]))

    groups_html = ''
    for g in nav_groups.values():
        items_html = ''.join(
            f'<a href="javascript:void(0)" onclick="showPage(\'{sid}\')" '
            f'class="sidebar-link" data-page="{sid}">{lbl}'
            f'<button class="sidebar-fav" data-fav="{sid}" onclick="event.preventDefault();event.stopPropagation();toggleFav(\'{sid}\')" '
            f'title="Toggle favourite">&#9733;</button></a>'
            for sid, lbl in g["items"]
        )
        groups_html += f'''
            <div class="sidebar-group">
                <div class="sidebar-group-label">{g["icon"]} {g["label"]}</div>
                {items_html}
            </div>'''
    return f'''<aside class="sidebar" id="sidebar">
        <div class="sidebar-brand">
            <span class="brand-dot">e</span>
            <span class="sidebar-brand-text">eComplete</span>
        </div>
        <div class="sidebar-user" id="sidebar-user">
            <span class="sidebar-user-icon">&#128100;</span>
            <span class="sidebar-user-name" id="sidebar-user-name"></span>
        </div>
        <nav class="sidebar-nav">
            <div class="sidebar-favs-group" id="sidebar-favs">
                <div class="sidebar-group-label">&#9733; Favourites</div>
                <div id="sidebar-favs-list"></div>
            </div>
            {groups_html}
        </nav>
        <div class="sidebar-footer">
            Sales &amp; M&amp;A &amp; AI Intelligence
        </div>
    </aside>
    <button class="sidebar-toggle" id="sidebar-toggle" onclick="toggleSidebar()" aria-label="Toggle menu">
        <span></span><span></span><span></span>
    </button>'''


# ---------------------------------------------------------------------------
# AI Chat Assistant (Anna)
# ---------------------------------------------------------------------------

def _build_chat_html() -> str:
    """Build the floating chat button and panel HTML with tabs, grouped suggestions, and reports."""
    return '''
    <!-- AI Chat Assistant -->
    <button class="chat-fab" id="chat-fab" onclick="window.AnnaChat.open()" aria-label="Ask eComplete AI" title="eComplete AI (Ctrl+K)">
        &#9889;
    </button>
    <div class="chat-panel" id="chat-panel">
        <div class="chat-header">
            <div class="chat-header-avatar">e</div>
            <div class="chat-header-info">
                <div class="chat-header-name">eComplete AI</div>
                <div class="chat-header-status">Sales &amp; M&amp;A Intelligence</div>
            </div>
            <button class="chat-close" onclick="window.AnnaChat.close()" aria-label="Close">&times;</button>
        </div>
        <div class="chat-tabs">
            <button class="chat-tab active" data-tab="chat" onclick="window.AnnaChat.switchTab(\'chat\')">&#9889; Chat</button>
            <button class="chat-tab" data-tab="reports" onclick="window.AnnaChat.switchTab(\'reports\')">&#128196; Reports</button>
        </div>
        <div class="chat-messages" id="chat-messages">
            <div class="chat-msg system">Ask me anything about your sales data, pipeline, M&amp;A projects, or team activity.</div>
        </div>
        <div class="chat-suggestions" id="chat-suggestions">
            <div class="chat-suggest-group">
                <div class="chat-suggest-header" onclick="window.AnnaChat.toggleGroup(this)">
                    &#9733; Pipeline &amp; Deals <span class="chat-suggest-arrow">&#9662;</span>
                </div>
                <div class="chat-suggest-items">
                    <button class="chat-suggestion" onclick="window.AnnaChat.ask(this.textContent)">Summarise deal flow this month</button>
                    <button class="chat-suggestion" onclick="window.AnnaChat.ask(this.textContent)">Which deals are stale or at risk?</button>
                    <button class="chat-suggestion" onclick="window.AnnaChat.ask(this.textContent)">Pipeline health &amp; coverage ratio</button>
                    <button class="chat-suggestion" onclick="window.AnnaChat.ask(this.textContent)">What is the current win rate?</button>
                </div>
            </div>
            <div class="chat-suggest-group">
                <div class="chat-suggest-header" onclick="window.AnnaChat.toggleGroup(this)">
                    &#10024; Leads &amp; Marketing <span class="chat-suggest-arrow">&#9662;</span>
                </div>
                <div class="chat-suggest-items">
                    <button class="chat-suggestion" onclick="window.AnnaChat.ask(this.textContent)">Summarise leads by source</button>
                    <button class="chat-suggestion" onclick="window.AnnaChat.ask(this.textContent)">Lead source effectiveness</button>
                    <button class="chat-suggestion" onclick="window.AnnaChat.ask(this.textContent)">MQL to SQL conversion trends</button>
                </div>
            </div>
            <div class="chat-suggest-group">
                <div class="chat-suggest-header" onclick="window.AnnaChat.toggleGroup(this)">
                    &#9993; Team Activity <span class="chat-suggest-arrow">&#9662;</span>
                </div>
                <div class="chat-suggest-items">
                    <button class="chat-suggestion" onclick="window.AnnaChat.ask(this.textContent)">Top performing rep this month</button>
                    <button class="chat-suggestion" onclick="window.AnnaChat.ask(this.textContent)">Team activity breakdown</button>
                    <button class="chat-suggestion" onclick="window.AnnaChat.ask(this.textContent)">Touches per won deal average</button>
                </div>
            </div>
            <div class="chat-suggest-group">
                <div class="chat-suggest-header" onclick="window.AnnaChat.toggleGroup(this)">
                    &#128188; M&amp;A <span class="chat-suggest-arrow">&#9662;</span>
                </div>
                <div class="chat-suggest-items">
                    <button class="chat-suggestion" onclick="window.AnnaChat.ask(this.textContent)">M&amp;A pipeline status</button>
                    <button class="chat-suggestion" onclick="window.AnnaChat.ask(this.textContent)">Stale M&amp;A projects</button>
                    <button class="chat-suggestion" onclick="window.AnnaChat.ask(this.textContent)">IC scorecard summary</button>
                </div>
            </div>
            <div class="chat-suggest-group">
                <div class="chat-suggest-header" onclick="window.AnnaChat.toggleGroup(this)">
                    &#9889; Quick Reports <span class="chat-suggest-arrow">&#9662;</span>
                </div>
                <div class="chat-suggest-items">
                    <button class="chat-suggestion" onclick="window.AnnaChat.ask(this.textContent)">Weekly summary</button>
                    <button class="chat-suggestion" onclick="window.AnnaChat.ask(this.textContent)">Revenue forecast next 90 days</button>
                    <button class="chat-suggestion" onclick="window.AnnaChat.ask(this.textContent)">Key risks and blockers</button>
                </div>
            </div>
        </div>
        <div class="chat-reports" id="chat-reports" style="display:none">
            <div class="chat-report-item" onclick="window.AnnaChat.runReport(\'monthly-deal-flow\')">
                <span class="chat-report-icon">&#9733;</span>
                <div class="chat-report-info">
                    <div class="chat-report-title">Monthly Deal Flow Summary</div>
                    <div class="chat-report-desc">Deals created, won, lost &amp; pipeline movement</div>
                </div>
                <span class="chat-report-arrow">&#8594;</span>
            </div>
            <div class="chat-report-item" onclick="window.AnnaChat.runReport(\'pipeline-health\')">
                <span class="chat-report-icon">&#9881;</span>
                <div class="chat-report-info">
                    <div class="chat-report-title">Pipeline Health Report</div>
                    <div class="chat-report-desc">Coverage ratio, stage distribution &amp; stale deals</div>
                </div>
                <span class="chat-report-arrow">&#8594;</span>
            </div>
            <div class="chat-report-item" onclick="window.AnnaChat.runReport(\'lead-source\')">
                <span class="chat-report-icon">&#10024;</span>
                <div class="chat-report-info">
                    <div class="chat-report-title">Lead Source Analysis</div>
                    <div class="chat-report-desc">Source effectiveness, MQL/SQL conversion rates</div>
                </div>
                <span class="chat-report-arrow">&#8594;</span>
            </div>
            <div class="chat-report-item" onclick="window.AnnaChat.runReport(\'weekly-activity\')">
                <span class="chat-report-icon">&#9993;</span>
                <div class="chat-report-info">
                    <div class="chat-report-title">Weekly Activity Report</div>
                    <div class="chat-report-desc">Calls, emails, meetings &amp; tasks by rep</div>
                </div>
                <span class="chat-report-arrow">&#8594;</span>
            </div>
            <div class="chat-report-item" onclick="window.AnnaChat.runReport(\'ma-pipeline\')">
                <span class="chat-report-icon">&#128188;</span>
                <div class="chat-report-info">
                    <div class="chat-report-title">M&amp;A Pipeline Status</div>
                    <div class="chat-report-desc">Active projects, stages &amp; owner summary</div>
                </div>
                <span class="chat-report-arrow">&#8594;</span>
            </div>
            <div class="chat-report-item" onclick="window.AnnaChat.runReport(\'rep-scorecard\')">
                <span class="chat-report-icon">&#9879;</span>
                <div class="chat-report-info">
                    <div class="chat-report-title">Rep Performance Scorecard</div>
                    <div class="chat-report-desc">Individual rep metrics, pipeline &amp; activities</div>
                </div>
                <span class="chat-report-arrow">&#8594;</span>
            </div>
        </div>
        <div class="chat-input-area" id="chat-input-area">
            <input class="chat-input" id="chat-input" type="text"
                   placeholder="Ask about your data..."
                   onkeydown="if(event.key===\'Enter\'&&!event.shiftKey){event.preventDefault();window.AnnaChat.send()}" />
            <button class="chat-send" id="chat-send" onclick="window.AnnaChat.send()" aria-label="Send">&#10148;</button>
        </div>
    </div>'''


def _build_chat_js() -> str:
    """Build the AI chat assistant JavaScript.

    Uses the Vercel serverless function `/api/ai-query` as the backend.
    Includes: categorised suggestions, tab switching, per-message export,
    report generation with branded PDF print windows.
    """
    return f'''
    <script>
    (function() {{
        'use strict';

        var FUNC_URL = '/api/ai-query';

        var history = [];
        var isOpen = false;
        var isLoading = false;

        // ---- Report prompts ----
        var REPORT_PROMPTS = {{
            'monthly-deal-flow': 'Generate a comprehensive Monthly Deal Flow Summary report. Include: total deals created vs closed this period, won vs lost breakdown with values in GBP, new pipeline added, average deal size, deal velocity, and comparison to prior period. Format with clear sections using headings and tables where appropriate.',
            'pipeline-health': 'Generate a Pipeline Health Report. Include: total pipeline value and weighted value in GBP, pipeline coverage ratio, stage-by-stage breakdown with deal counts and values, average time in each stage, stale deals requiring attention, and overall pipeline risk assessment. Use headings and bullet points.',
            'lead-source': 'Generate a Lead Source Analysis report. Include: total leads by source with counts, lead-to-MQL and MQL-to-SQL conversion rates by source, most effective channels, trend analysis, and recommendations for lead generation improvement. Format with clear sections.',
            'weekly-activity': 'Generate a Weekly Activity Report. Include: total activities (calls, emails, meetings, tasks, notes) by rep, activity-to-deal ratios, most active reps, engagement trends, and touches per won deal analysis. Format as a structured report with tables.',
            'ma-pipeline': 'Generate an M&A Pipeline Status report. Include: total active projects, stage distribution breakdown, stale projects requiring attention with days stale, owner workload summary, IC scorecard highlights, and upcoming decision points. Use clear headings.',
            'rep-scorecard': 'Generate a Rep Performance Scorecard. For each sales rep, include: deals owned (count and value in GBP), win rate, activity volume breakdown, average deal size, pipeline contribution, and relative performance. Format as a comparative table or structured list.'
        }};

        // ---- DOM refs ----
        function $(id) {{ return document.getElementById(id); }}

        // ---- Markdown-lite renderer ----
        function md(text) {{
            if (!text) return '';
            var s = text.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
            s = s.replace(/\\*\\*(.+?)\\*\\*/g, '<strong>$1</strong>');
            s = s.replace(/`([^`]+)`/g, '<code>$1</code>');
            s = s.replace(/^[\\-\\*] (.+)$/gm, '<li>$1</li>');
            s = s.replace(/(<li>.*<\\/li>)/gs, '<ul>$1</ul>');
            s = s.replace(/<\\/ul>\\s*<ul>/g, '');
            s = s.replace(/^\\d+\\. (.+)$/gm, '<li>$1</li>');
            s = s.replace(/\\n/g, '<br>');
            s = s.replace(/(<br>){{3,}}/g, '<br><br>');
            return s;
        }}

        // ---- Branded print window ----
        function openPrintWindow(title, htmlContent) {{
            var now = new Date();
            var dateStr = now.toLocaleDateString('en-GB', {{ day: 'numeric', month: 'long', year: 'numeric' }});
            var timeStr = now.toLocaleTimeString('en-GB', {{ hour: '2-digit', minute: '2-digit' }});

            var w = window.open('', '_blank');
            if (!w) {{ alert('Please allow pop-ups to export reports.'); return; }}

            var html = '<!DOCTYPE html><html><head>'
                + '<meta charset="UTF-8">'
                + '<title>' + title + '</title>'
                + '<link href="https://fonts.googleapis.com/css2?family=Assistant:wght@400;600;700;800&display=swap" rel="stylesheet">'
                + '<style>'
                + 'body {{ font-family: "Assistant", sans-serif; color: #121212; margin: 0; padding: 40px; line-height: 1.6; }}'
                + '.rpt-header {{ border-bottom: 3px solid #3CB4AD; padding-bottom: 16px; margin-bottom: 24px; }}'
                + '.rpt-brand {{ display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }}'
                + '.rpt-dot {{ width: 28px; height: 28px; border-radius: 50%; background: #3CB4AD; display: flex; align-items: center; justify-content: center; font-size: 14px; font-weight: 800; color: #fff; }}'
                + '.rpt-name {{ font-size: 18px; font-weight: 800; color: #242833; }}'
                + '.rpt-title {{ font-size: 22px; font-weight: 700; color: #242833; margin: 8px 0 4px; }}'
                + '.rpt-meta {{ font-size: 12px; color: #6b7280; }}'
                + '.rpt-body {{ font-size: 14px; }}'
                + '.rpt-body strong {{ font-weight: 700; }}'
                + '.rpt-body ul, .rpt-body ol {{ margin: 8px 0; padding-left: 24px; }}'
                + '.rpt-body li {{ margin-bottom: 4px; }}'
                + '.rpt-body code {{ background: #f3f4f6; padding: 2px 5px; border-radius: 3px; font-size: 13px; }}'
                + '.rpt-footer {{ margin-top: 40px; padding-top: 16px; border-top: 1px solid #e2e5ea; font-size: 11px; color: #6b7280; text-align: center; }}'
                + '@media print {{ body {{ padding: 20px; }} .rpt-header {{ border-bottom-width: 2px; }} }}'
                + '</style></head><body>'
                + '<div class="rpt-header">'
                + '<div class="rpt-brand"><div class="rpt-dot">e</div><span class="rpt-name">eComplete</span></div>'
                + '<div class="rpt-title">' + title + '</div>'
                + '<div class="rpt-meta">Generated by eComplete AI &middot; ' + dateStr + ' at ' + timeStr + '</div>'
                + '</div>'
                + '<div class="rpt-body">' + htmlContent + '</div>'
                + '<div class="rpt-footer">eComplete &mdash; Sales &amp; M&amp;A Intelligence Dashboard &middot; Confidential</div>'
                + '<scr' + 'ipt>window.onload=function(){{ window.print(); }}</scr' + 'ipt>'
                + '</body></html>';
            w.document.write(html);
            w.document.close();
        }}

        // ---- Add message to chat ----
        function addMessage(role, content) {{
            var msgs = $('chat-messages');
            if (!msgs) return;
            var div = document.createElement('div');
            div.className = 'chat-msg ' + role;
            if (role === 'assistant') {{
                div.innerHTML = md(content);
                // Action bar: copy + export
                var actions = document.createElement('div');
                actions.className = 'chat-msg-actions';
                actions.innerHTML = '<button class="chat-action-btn" title="Copy to clipboard" onclick="window.AnnaChat.copyMsg(this)">&#128203; Copy</button>'
                    + '<button class="chat-action-btn" title="Export as PDF" onclick="window.AnnaChat.exportMsg(this)">&#128196; Export</button>';
                div.appendChild(actions);
                div.setAttribute('data-raw', content);
            }} else {{
                div.textContent = content;
            }}
            msgs.appendChild(div);
            msgs.scrollTop = msgs.scrollHeight;
        }}

        function showTyping() {{
            var msgs = $('chat-messages');
            if (!msgs) return;
            var div = document.createElement('div');
            div.className = 'chat-typing';
            div.id = 'chat-typing';
            div.innerHTML = '<span></span><span></span><span></span>';
            msgs.appendChild(div);
            msgs.scrollTop = msgs.scrollHeight;
        }}

        function hideTyping() {{
            var el = $('chat-typing');
            if (el) el.remove();
        }}

        function setLoading(loading) {{
            isLoading = loading;
            var btn = $('chat-send');
            var input = $('chat-input');
            if (btn) btn.disabled = loading;
            if (input) input.disabled = loading;
            if (loading) showTyping(); else hideTyping();
        }}

        // ---- Send message ----
        function sendMessage(text) {{
            if (!text || isLoading) return;
            text = text.trim();
            if (!text) return;

            // Hide suggestions after first message
            var suggestions = $('chat-suggestions');
            if (suggestions) suggestions.style.display = 'none';

            addMessage('user', text);
            history.push({{ role: 'user', content: text }});

            var input = $('chat-input');
            if (input) input.value = '';

            setLoading(true);

            fetch(FUNC_URL, {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify({{
                    question: text,
                    history: history.slice(-6)
                }})
            }})
            .then(function(r) {{
                if (!r.ok) {{
                    return r.json().then(function(d) {{
                        throw new Error(d.error || 'Request failed (' + r.status + ')');
                    }});
                }}
                return r.json();
            }})
            .then(function(data) {{
                setLoading(false);
                var answer = data.answer || 'No response received.';
                addMessage('assistant', answer);
                history.push({{ role: 'assistant', content: answer }});
            }})
            .catch(function(err) {{
                setLoading(false);
                var msg = err.message || String(err);
                if (msg.indexOf('Failed to fetch') !== -1 || msg.indexOf('NetworkError') !== -1) {{
                    msg = 'Cannot reach the AI service. Please try again in a moment.';
                }}
                addMessage('system', 'Error: ' + msg);
            }});
        }}

        // ---- Public API ----
        window.AnnaChat = {{
            open: function() {{
                var panel = $('chat-panel');
                var fab = $('chat-fab');
                if (panel) panel.classList.add('open');
                if (fab) fab.classList.add('has-panel');
                isOpen = true;
                var input = $('chat-input');
                if (input) setTimeout(function() {{ input.focus(); }}, 100);
            }},
            close: function() {{
                var panel = $('chat-panel');
                var fab = $('chat-fab');
                if (panel) panel.classList.remove('open');
                if (fab) fab.classList.remove('has-panel');
                isOpen = false;
            }},
            send: function() {{
                var input = $('chat-input');
                if (input) sendMessage(input.value);
            }},
            ask: function(text) {{
                sendMessage(text);
            }},
            toggleGroup: function(headerEl) {{
                var group = headerEl.parentElement;
                if (group) group.classList.toggle('collapsed');
            }},
            switchTab: function(tab) {{
                var chatMsgs = $('chat-messages');
                var chatSuggestions = $('chat-suggestions');
                var reports = $('chat-reports');
                var inputArea = $('chat-input-area');
                var tabs = document.querySelectorAll('.chat-tab');
                for (var i = 0; i < tabs.length; i++) {{
                    if (tabs[i].getAttribute('data-tab') === tab) {{
                        tabs[i].classList.add('active');
                    }} else {{
                        tabs[i].classList.remove('active');
                    }}
                }}
                if (tab === 'chat') {{
                    if (chatMsgs) chatMsgs.style.display = '';
                    if (chatSuggestions && history.length === 0) chatSuggestions.style.display = '';
                    if (reports) reports.style.display = 'none';
                    if (inputArea) inputArea.style.display = '';
                }} else {{
                    if (chatMsgs) chatMsgs.style.display = 'none';
                    if (chatSuggestions) chatSuggestions.style.display = 'none';
                    if (reports) reports.style.display = '';
                    if (inputArea) inputArea.style.display = 'none';
                }}
            }},
            copyMsg: function(btn) {{
                var msgDiv = btn.closest('.chat-msg');
                if (!msgDiv) return;
                var raw = msgDiv.getAttribute('data-raw') || msgDiv.textContent;
                navigator.clipboard.writeText(raw).then(function() {{
                    var orig = btn.innerHTML;
                    btn.innerHTML = '&#10003; Copied';
                    setTimeout(function() {{ btn.innerHTML = orig; }}, 1500);
                }});
            }},
            exportMsg: function(btn) {{
                var msgDiv = btn.closest('.chat-msg');
                if (!msgDiv) return;
                var raw = msgDiv.getAttribute('data-raw') || '';
                openPrintWindow('eComplete AI Response', md(raw));
            }},
            runReport: function(reportId) {{
                var prompt = REPORT_PROMPTS[reportId];
                if (!prompt) return;
                // Open window immediately in click context to avoid popup blocker
                var w = window.open('', '_blank');
                if (!w) {{ alert('Please allow pop-ups to export reports.'); return; }}
                w.document.write('<!DOCTYPE html><html><head><title>Generating Report...</title>'
                    + '<link href="https://fonts.googleapis.com/css2?family=Assistant:wght@400;600;700;800&display=swap" rel="stylesheet">'
                    + '<style>body{{font-family:"Assistant",sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;color:#6b7280;margin:0;}}</style>'
                    + '</head><body><div style="text-align:center"><div style="font-size:24px;margin-bottom:8px">&#9889; Generating report...</div>'
                    + '<div>This may take a few seconds</div></div></body></html>');
                w.document.close();

                var title = reportId.replace(/-/g, ' ').replace(/\\b\\w/g, function(c) {{ return c.toUpperCase(); }});

                fetch(FUNC_URL, {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{
                        question: prompt,
                        history: [],
                        report: true
                    }})
                }})
                .then(function(r) {{
                    if (!r.ok) throw new Error('Request failed (' + r.status + ')');
                    return r.json();
                }})
                .then(function(data) {{
                    var answer = data.answer || 'No response received.';
                    var now = new Date();
                    var dateStr = now.toLocaleDateString('en-GB', {{ day: 'numeric', month: 'long', year: 'numeric' }});
                    var timeStr = now.toLocaleTimeString('en-GB', {{ hour: '2-digit', minute: '2-digit' }});
                    w.document.open();
                    w.document.write('<!DOCTYPE html><html><head>'
                        + '<meta charset="UTF-8"><title>' + title + '</title>'
                        + '<link href="https://fonts.googleapis.com/css2?family=Assistant:wght@400;600;700;800&display=swap" rel="stylesheet">'
                        + '<style>'
                        + 'body {{ font-family: "Assistant", sans-serif; color: #121212; margin: 0; padding: 40px; line-height: 1.6; }}'
                        + '.rpt-header {{ border-bottom: 3px solid #3CB4AD; padding-bottom: 16px; margin-bottom: 24px; }}'
                        + '.rpt-brand {{ display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }}'
                        + '.rpt-dot {{ width: 28px; height: 28px; border-radius: 50%; background: #3CB4AD; display: flex; align-items: center; justify-content: center; font-size: 14px; font-weight: 800; color: #fff; }}'
                        + '.rpt-name {{ font-size: 18px; font-weight: 800; color: #242833; }}'
                        + '.rpt-title {{ font-size: 22px; font-weight: 700; color: #242833; margin: 8px 0 4px; }}'
                        + '.rpt-meta {{ font-size: 12px; color: #6b7280; }}'
                        + '.rpt-body {{ font-size: 14px; }}'
                        + '.rpt-body strong {{ font-weight: 700; }}'
                        + '.rpt-body ul, .rpt-body ol {{ margin: 8px 0; padding-left: 24px; }}'
                        + '.rpt-body li {{ margin-bottom: 4px; }}'
                        + '.rpt-body code {{ background: #f3f4f6; padding: 2px 5px; border-radius: 3px; font-size: 13px; }}'
                        + '.rpt-footer {{ margin-top: 40px; padding-top: 16px; border-top: 1px solid #e2e5ea; font-size: 11px; color: #6b7280; text-align: center; }}'
                        + '@media print {{ body {{ padding: 20px; }} }}'
                        + '</style></head><body>'
                        + '<div class="rpt-header">'
                        + '<div class="rpt-brand"><div class="rpt-dot">e</div><span class="rpt-name">eComplete</span></div>'
                        + '<div class="rpt-title">' + title + '</div>'
                        + '<div class="rpt-meta">Generated by eComplete AI &middot; ' + dateStr + ' at ' + timeStr + '</div>'
                        + '</div>'
                        + '<div class="rpt-body">' + md(answer) + '</div>'
                        + '<div class="rpt-footer">eComplete &mdash; Sales &amp; M&amp;A Intelligence Dashboard &middot; Confidential</div>'
                        + '<scr' + 'ipt>window.onload=function(){{ window.print(); }}</scr' + 'ipt>'
                        + '</body></html>');
                    w.document.close();
                }})
                .catch(function(err) {{
                    w.document.open();
                    w.document.write('<html><body style="font-family:Assistant,sans-serif;padding:40px"><h2>Error generating report</h2><p>' + (err.message || String(err)) + '</p></body></html>');
                    w.document.close();
                }});
            }}
        }};

        // Keyboard shortcut: Ctrl+K or Cmd+K to toggle chat
        document.addEventListener('keydown', function(e) {{
            if ((e.ctrlKey || e.metaKey) && e.key === 'k') {{
                e.preventDefault();
                if (isOpen) window.AnnaChat.close();
                else window.AnnaChat.open();
            }}
        }});

        // Collapse all suggestion groups except the first
        document.addEventListener('DOMContentLoaded', function() {{
            var groups = document.querySelectorAll('.chat-suggest-group');
            for (var i = 1; i < groups.length; i++) {{
                groups[i].classList.add('collapsed');
            }}
        }});

        // ---- AnnaPage: full-page chat with multi-conversation + inline reports ----
        var AP_STORE_KEY = 'ecomplete_anna_convs';
        var apConvs = [];  // {{id, title, messages:[]}}
        var apActiveId = null;
        var apLoading = false;

        function apLoadConvs() {{
            try {{ apConvs = JSON.parse(localStorage.getItem(AP_STORE_KEY) || '[]'); }} catch(e) {{ apConvs = []; }}
        }}
        function apSaveConvs() {{
            try {{ localStorage.setItem(AP_STORE_KEY, JSON.stringify(apConvs)); }} catch(e) {{}}
        }}
        function apGetActive() {{
            return apConvs.find(function(c) {{ return c.id === apActiveId; }});
        }}

        function apRenderConvList() {{
            var list = document.getElementById('anna-conv-list');
            if (!list) return;
            var html = '';
            for (var i = apConvs.length - 1; i >= 0; i--) {{
                var c = apConvs[i];
                var active = c.id === apActiveId ? ' active' : '';
                html += '<button class="anna-conv-item' + active + '" data-cid="' + c.id + '" onclick="window.AnnaPage.switchConv(this.getAttribute(&#39;data-cid&#39;))">'
                    + '<span class="conv-icon">&#128172;</span>'
                    + '<span class="conv-label">' + (c.title || 'New Chat') + '</span>'
                    + '<span class="conv-delete" onclick="event.stopPropagation();window.AnnaPage.deleteConv(&#39;' + c.id + '&#39;)" title="Delete">&#10005;</span>'
                    + '</button>';
            }}
            list.innerHTML = html;
        }}

        function apRenderMessages() {{
            var msgs = document.getElementById('anna-page-msgs');
            if (!msgs) return;
            var conv = apGetActive();
            msgs.innerHTML = '';
            if (!conv || conv.messages.length === 0) {{
                // Show welcome
                var w = document.getElementById('anna-welcome');
                if (!w) {{
                    msgs.innerHTML = '<div class="anna-welcome" id="anna-welcome">'
                        + '<div class="anna-welcome-avatar">e</div>'
                        + '<div class="anna-welcome-title">eComplete AI</div>'
                        + '<div class="anna-welcome-sub">Your sales &amp; M&amp;A intelligence assistant. Ask me anything about your dashboard data.</div>'
                        + '<div class="anna-suggestions" id="anna-suggestions">'
                        + '<button class="anna-suggest-btn" onclick="window.AnnaPage.ask(this.textContent)">Summarise deal flow this month</button>'
                        + '<button class="anna-suggest-btn" onclick="window.AnnaPage.ask(this.textContent)">Which deals are stale or at risk?</button>'
                        + '<button class="anna-suggest-btn" onclick="window.AnnaPage.ask(this.textContent)">Pipeline health &amp; coverage</button>'
                        + '<button class="anna-suggest-btn" onclick="window.AnnaPage.ask(this.textContent)">Lead source effectiveness</button>'
                        + '<button class="anna-suggest-btn" onclick="window.AnnaPage.ask(this.textContent)">Top performing rep this month</button>'
                        + '<button class="anna-suggest-btn" onclick="window.AnnaPage.ask(this.textContent)">M&amp;A pipeline status</button>'
                        + '<button class="anna-suggest-btn" onclick="window.AnnaPage.ask(this.textContent)">Revenue forecast next 90 days</button>'
                        + '<button class="anna-suggest-btn" onclick="window.AnnaPage.ask(this.textContent)">Weekly summary</button>'
                        + '</div></div>';
                }}
                return;
            }}
            for (var i = 0; i < conv.messages.length; i++) {{
                var m = conv.messages[i];
                apAddMsgDOM(m.role, m.content, m.reportTitle || null);
            }}
            msgs.scrollTop = msgs.scrollHeight;
        }}

        function apAddMsgDOM(role, content, reportTitle) {{
            var msgs = document.getElementById('anna-page-msgs');
            if (!msgs) return;
            // Remove welcome
            var w = msgs.querySelector('.anna-welcome');
            if (w) w.remove();

            if (reportTitle) {{
                // Render as branded report card
                var now = new Date();
                var dateStr = now.toLocaleDateString('en-GB', {{ day: 'numeric', month: 'long', year: 'numeric' }});
                var card = document.createElement('div');
                card.className = 'anna-report-card';
                card.innerHTML = '<div class="anna-report-card-header">'
                    + '<div class="anna-report-card-dot">e</div>'
                    + '<div class="anna-report-card-title">' + reportTitle + '</div>'
                    + '<div class="anna-report-card-meta">eComplete AI &middot; ' + dateStr + '</div>'
                    + '</div>'
                    + '<div class="anna-report-card-body">' + md(content) + '</div>'
                    + '<div class="anna-report-card-footer">'
                    + '<button class="anna-report-action" onclick="window.AnnaPage.copyReport(this)">&#128203; Copy</button>'
                    + '<button class="anna-report-action" onclick="window.AnnaPage.downloadReport(this)">&#128196; Download PDF</button>'
                    + '</div>';
                card.setAttribute('data-raw', content);
                card.setAttribute('data-title', reportTitle);
                msgs.appendChild(card);
            }} else {{
                var div = document.createElement('div');
                div.className = 'chat-msg ' + role;
                if (role === 'assistant') {{
                    div.innerHTML = md(content);
                    var actions = document.createElement('div');
                    actions.className = 'chat-msg-actions';
                    actions.style.opacity = '1';
                    actions.innerHTML = '<button class="chat-action-btn" title="Copy" onclick="window.AnnaChat.copyMsg(this)">&#128203; Copy</button>';
                    div.appendChild(actions);
                    div.setAttribute('data-raw', content);
                }} else if (role === 'user') {{
                    div.textContent = content;
                }} else {{
                    div.innerHTML = content;
                }}
                msgs.appendChild(div);
            }}
            msgs.scrollTop = msgs.scrollHeight;
        }}

        function apShowTyping() {{
            var msgs = document.getElementById('anna-page-msgs');
            if (!msgs) return;
            var div = document.createElement('div');
            div.className = 'chat-typing';
            div.id = 'anna-page-typing';
            div.innerHTML = '<span></span><span></span><span></span>';
            msgs.appendChild(div);
            msgs.scrollTop = msgs.scrollHeight;
        }}

        function apHideTyping() {{
            var el = document.getElementById('anna-page-typing');
            if (el) el.remove();
        }}

        function apEnsureConv() {{
            if (!apActiveId || !apGetActive()) {{
                var id = 'conv_' + Date.now();
                apConvs.push({{ id: id, title: '', messages: [] }});
                apActiveId = id;
                apSaveConvs();
                apRenderConvList();
            }}
        }}

        function apSend(text) {{
            if (!text || apLoading) return;
            text = text.trim();
            if (!text) return;

            apEnsureConv();
            var conv = apGetActive();
            if (!conv) return;

            // Set title from first message
            if (!conv.title) {{
                conv.title = text.length > 40 ? text.substring(0, 40) + '...' : text;
                apRenderConvList();
            }}

            conv.messages.push({{ role: 'user', content: text }});
            apSaveConvs();
            apAddMsgDOM('user', text, null);

            var input = document.getElementById('anna-page-input');
            if (input) input.value = '';

            apLoading = true;
            apShowTyping();

            fetch(FUNC_URL, {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify({{
                    question: text,
                    history: conv.messages.slice(-6)
                }})
            }})
            .then(function(r) {{
                if (!r.ok) return r.json().then(function(d) {{ throw new Error(d.error || 'Request failed'); }});
                return r.json();
            }})
            .then(function(data) {{
                apLoading = false;
                apHideTyping();
                var answer = data.answer || 'No response received.';
                conv.messages.push({{ role: 'assistant', content: answer }});
                apSaveConvs();
                apAddMsgDOM('assistant', answer, null);
            }})
            .catch(function(err) {{
                apLoading = false;
                apHideTyping();
                apAddMsgDOM('system', 'Error: ' + (err.message || String(err)), null);
            }});
        }}

        function apRunReport(reportId) {{
            var prompt = REPORT_PROMPTS[reportId];
            if (!prompt || apLoading) return;
            var title = reportId.replace(/-/g, ' ').replace(/\\b\\w/g, function(c) {{ return c.toUpperCase(); }});

            apEnsureConv();
            var conv = apGetActive();
            if (!conv) return;

            if (!conv.title) {{
                conv.title = '📄 ' + title;
                apRenderConvList();
            }}

            apLoading = true;
            apShowTyping();

            fetch(FUNC_URL, {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify({{
                    question: prompt,
                    history: [],
                    report: true
                }})
            }})
            .then(function(r) {{
                if (!r.ok) throw new Error('Request failed (' + r.status + ')');
                return r.json();
            }})
            .then(function(data) {{
                apLoading = false;
                apHideTyping();
                var answer = data.answer || 'No response received.';
                conv.messages.push({{ role: 'assistant', content: answer, reportTitle: title }});
                apSaveConvs();
                apAddMsgDOM('assistant', answer, title);
            }})
            .catch(function(err) {{
                apLoading = false;
                apHideTyping();
                apAddMsgDOM('system', 'Error generating report: ' + (err.message || String(err)), null);
            }});
        }}

        // Init AnnaPage on load
        document.addEventListener('DOMContentLoaded', function() {{
            apLoadConvs();
            if (apConvs.length > 0) {{
                apActiveId = apConvs[apConvs.length - 1].id;
            }}
            apRenderConvList();
            apRenderMessages();
        }});

        window.AnnaPage = {{
            send: function() {{
                var input = document.getElementById('anna-page-input');
                if (input) apSend(input.value);
            }},
            ask: function(text) {{
                apSend(text);
            }},
            newChat: function() {{
                var id = 'conv_' + Date.now();
                apConvs.push({{ id: id, title: '', messages: [] }});
                apActiveId = id;
                apSaveConvs();
                apRenderConvList();
                apRenderMessages();
                var input = document.getElementById('anna-page-input');
                if (input) input.focus();
            }},
            switchConv: function(cid) {{
                apActiveId = cid;
                apRenderConvList();
                apRenderMessages();
            }},
            deleteConv: function(cid) {{
                apConvs = apConvs.filter(function(c) {{ return c.id !== cid; }});
                if (apActiveId === cid) {{
                    apActiveId = apConvs.length > 0 ? apConvs[apConvs.length - 1].id : null;
                }}
                apSaveConvs();
                apRenderConvList();
                apRenderMessages();
            }},
            clearChat: function() {{
                var conv = apGetActive();
                if (conv) {{
                    conv.messages = [];
                    conv.title = '';
                    apSaveConvs();
                    apRenderConvList();
                    apRenderMessages();
                }}
            }},
            runReport: function(reportId) {{
                apRunReport(reportId);
            }},
            copyReport: function(btn) {{
                var card = btn.closest('.anna-report-card');
                if (!card) return;
                var raw = card.getAttribute('data-raw') || '';
                navigator.clipboard.writeText(raw).then(function() {{
                    var orig = btn.innerHTML;
                    btn.innerHTML = '&#10003; Copied';
                    setTimeout(function() {{ btn.innerHTML = orig; }}, 1500);
                }});
            }},
            downloadReport: function(btn) {{
                var card = btn.closest('.anna-report-card');
                if (!card) return;
                var raw = card.getAttribute('data-raw') || '';
                var title = card.getAttribute('data-title') || 'Report';
                openPrintWindow(title, md(raw));
            }}
        }};

    }})();
    </script>'''


def generate_dashboard(data: dict) -> str:
    """Generate the complete HTML dashboard from metrics data."""
    _normalize_metrics(data)
    _register_builders()
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    # Load Monday.com metrics if available
    monday_data_file = BASE_DIR / "data" / "processed" / "monday_metrics.json"
    if monday_data_file.exists():
        try:
            with open(monday_data_file, "r", encoding="utf-8") as mf:
                data["monday"] = json.load(mf)
            logger.info("Loaded Monday.com metrics")
        except Exception as exc:
            logger.warning("Failed to load Monday.com metrics: %s", exc)

    # --- Data freshness timestamps (#45) ---
    freshness: Dict[str, str] = {}
    hs_gen = data.get("generated_at", "")
    if hs_gen:
        freshness["HubSpot"] = str(hs_gen)[:19]
    monday_gen = _safe_get(data, "monday", "generated_at", default="")
    if monday_gen:
        freshness["Monday"] = str(monday_gen)[:19]
    queue_file = BASE_DIR / "data" / "processed" / "inbound_queue.json"
    if queue_file.exists():
        try:
            with open(queue_file, "r", encoding="utf-8") as qf:
                q_meta = json.load(qf)
            q_gen = q_meta.get("generated_at", "")
            if q_gen:
                freshness["Queue"] = str(q_gen)[:19]
        except Exception:
            pass

    freshness_html = ""
    if freshness:
        pills = " ".join(
            f'<span class="freshness-pill" title="Last sync: {v}">{k}: {v[5:16] if len(v) > 16 else v}</span>'
            for k, v in freshness.items()
        )
        freshness_html = f'<div class="freshness-bar" id="freshness-bar">{pills}</div>'

    # --- Build sections from MODULES registry (#56) ---
    sections = []
    for mod in MODULES:
        page_id = mod["id"]
        label = mod["label"]
        builder = _MODULE_BUILDERS.get(page_id)
        if not builder:
            logger.warning(f"No builder for module '{page_id}'")
            continue
        try:
            content = builder(data)
            sections.append(f'<div class="dash-page" id="page-{page_id}">{content}</div>')
        except Exception as e:
            logger.warning(f"Section '{label}' failed: {e}")
            sections.append(f'<div class="dash-page" id="page-{page_id}"><section class="dashboard-section"><div class="glass-card" style="padding:40px;text-align:center;color:{COLORS["text_muted"]}"><h3>{_esc(label)}</h3><p>Data unavailable — {_esc(str(e))}</p></div></section></div>')

    record_counts = _safe_get(data, "record_counts", default={})
    footer_stats = " | ".join([
        f"Contacts: {_fmt_number(record_counts.get('contacts', 0))}",
        f"Companies: {_fmt_number(record_counts.get('companies', 0))}",
        f"Deals: {_fmt_number(record_counts.get('deals', 0))}",
    ])

    # Serialize time_series and yoy_summary for JS embedding
    ts_data = data.get("time_series", {})
    yoy_data = data.get("yoy_summary", {})
    has_time_series = bool(ts_data)

    # Build filter bar HTML
    filter_bar = ''
    if has_time_series:
        filter_bar = f'''
    <div class="filter-bar" id="filter-bar">
        <div class="filter-inner">
            <span class="filter-label">Period</span>
            <button class="filter-btn" data-period="this_week" onclick="applyFilter('this_week')">This Week</button>
            <button class="filter-btn" data-period="last_week" onclick="applyFilter('last_week')">Last Week</button>
            <button class="filter-btn" data-period="mtd" onclick="applyFilter('mtd')">MTD</button>
            <button class="filter-btn active" data-period="ytd" onclick="applyFilter('ytd')">YTD</button>
            <button class="filter-btn" data-period="last_year" onclick="applyFilter('last_year')">Last Year</button>
            <button class="filter-btn" data-period="all" onclick="applyFilter('all')">All Time</button>
            <span class="filter-period-label" id="filter-period-label">Year to Date</span>
        </div>
    </div>'''

    # Build the filtering JavaScript
    filter_js = ''
    if has_time_series:
        ts_json = json.dumps(ts_data, default=str)
        yoy_json = json.dumps(yoy_data, default=str)
        filter_js = f'''
    <script>
    (function() {{
        var TS = {ts_json};
        var YOY = {yoy_json};

        var PERIOD_LABELS = {{
            'this_week': 'This Week',
            'last_week': 'Last Week',
            'mtd': 'Month to Date',
            'ytd': 'Year to Date',
            'last_year': 'Last Year',
            'all': 'All Time'
        }};

        function getDateRange(period) {{
            var now = new Date();
            var y = now.getFullYear();
            var m = now.getMonth();
            var d = now.getDate();
            var day = now.getDay();
            var mondayOffset = day === 0 ? 6 : day - 1;
            var start, end;

            switch(period) {{
                case 'this_week':
                    start = new Date(y, m, d - mondayOffset);
                    end = now;
                    break;
                case 'last_week':
                    start = new Date(y, m, d - mondayOffset - 7);
                    end = new Date(y, m, d - mondayOffset - 1);
                    break;
                case 'mtd':
                    start = new Date(y, m, 1);
                    end = now;
                    break;
                case 'ytd':
                    start = new Date(y, 0, 1);
                    end = now;
                    break;
                case 'last_year':
                    start = new Date(y - 1, 0, 1);
                    end = new Date(y - 1, 11, 31);
                    break;
                case 'all':
                default:
                    return null;
            }}
            return {{
                start: formatDate(start),
                end: formatDate(end)
            }};
        }}

        function formatDate(d) {{
            var yy = d.getFullYear();
            var mm = String(d.getMonth() + 1).padStart(2, '0');
            var dd = String(d.getDate()).padStart(2, '0');
            return yy + '-' + mm + '-' + dd;
        }}

        function sumDaily(series, range) {{
            if (!series) return 0;
            var total = 0;
            for (var key in series) {{
                if (range === null || (key >= range.start && key <= range.end)) {{
                    var val = series[key];
                    if (typeof val === 'number') total += val;
                }}
            }}
            return total;
        }}

        function sumActivitiesDaily(series, range) {{
            if (!series) return 0;
            var total = 0;
            for (var key in series) {{
                if (range === null || (key >= range.start && key <= range.end)) {{
                    var counts = series[key];
                    for (var t in counts) total += (counts[t] || 0);
                }}
            }}
            return total;
        }}

        function getActivityBreakdown(series, range) {{
            var result = {{calls: 0, emails: 0, meetings: 0, tasks: 0, notes: 0}};
            if (!series) return result;
            for (var key in series) {{
                if (range === null || (key >= range.start && key <= range.end)) {{
                    var counts = series[key];
                    for (var t in counts) {{
                        if (result.hasOwnProperty(t)) result[t] += (counts[t] || 0);
                    }}
                }}
            }}
            return result;
        }}

        function filterDailyToMonthly(series, range) {{
            if (!series) return {{}};
            var months = {{}};
            for (var key in series) {{
                if (range === null || (key >= range.start && key <= range.end)) {{
                    var mk = key.substring(0, 7);
                    months[mk] = (months[mk] || 0) + (typeof series[key] === 'number' ? series[key] : 0);
                }}
            }}
            return months;
        }}

        function fmtNum(v) {{
            if (v === null || v === undefined) return '0';
            if (v >= 1000000) return (v / 1000000).toFixed(1) + 'M';
            if (v >= 1000) return (v / 1000).toFixed(1) + 'K';
            return v.toLocaleString('en-GB', {{maximumFractionDigits: 0}});
        }}

        function fmtCurrency(v) {{
            if (v === null || v === undefined) return '\\u00a30';
            if (v >= 1000000) return '\\u00a3' + (v / 1000000).toFixed(1) + 'M';
            if (v >= 1000) return '\\u00a3' + (v / 1000).toFixed(1) + 'K';
            return '\\u00a3' + v.toLocaleString('en-GB', {{maximumFractionDigits: 0}});
        }}

        function yoyBadge(metricKey) {{
            var yoy = YOY[metricKey];
            if (!yoy || yoy.change_pct === null || yoy.change_pct === undefined) return '';
            var pct = yoy.change_pct;
            var cls = pct > 0 ? 'up' : pct < 0 ? 'down' : 'neutral';
            var arrow = pct > 0 ? '\\u2191' : pct < 0 ? '\\u2193' : '\\u2192';
            var sign = pct > 0 ? '+' : '';
            return '<span class="yoy-badge ' + cls + '">' + arrow + ' ' + sign + pct.toFixed(1) + '% YoY</span>';
        }}

        function renderMiniBar(containerId, data, maxItems) {{
            var el = document.getElementById(containerId);
            if (!el) return;
            maxItems = maxItems || 8;
            var sorted = Object.entries(data).sort(function(a, b) {{ return b[1] - a[1]; }}).slice(0, maxItems);
            if (sorted.length === 0) {{ el.innerHTML = '<div style="text-align:center;padding:20px;color:#6b7280;font-size:13px">No data for this period</div>'; return; }}
            var maxVal = sorted[0][1] || 1;
            var palette = ['#3CB4AD','#334FB4','#a78bfa','#34d399','#f472b6','#f59e0b','#60a5fa','#ef4444'];
            var html = '';
            sorted.forEach(function(item, i) {{
                var label = item[0].length > 20 ? item[0].substring(0, 18) + '..' : item[0];
                var val = item[1];
                var pct = Math.max(2, (val / maxVal) * 100);
                var color = palette[i % palette.length];
                html += '<div style="margin-bottom:5px">'
                    + '<div style="display:flex;justify-content:space-between;margin-bottom:3px;font-size:12px">'
                    + '<span style="color:#6b7280">' + label + '</span>'
                    + '<span style="color:#121212;font-weight:600">' + fmtNum(val) + '</span></div>'
                    + '<div style="height:6px;background:#e5e7eb;border-radius:3px;overflow:hidden">'
                    + '<div style="height:100%;width:' + pct.toFixed(1) + '%;background:' + color + ';border-radius:3px;'
                    + 'transition:width 0.6s cubic-bezier(.25,.1,.25,1)"></div></div></div>';
            }});
            el.innerHTML = html;
        }}

        function renderSparkline(containerId, data, color) {{
            var el = document.getElementById(containerId);
            if (!el) return;
            color = color || '#3CB4AD';
            var entries = Object.entries(data).sort();
            if (entries.length < 2) {{ el.innerHTML = ''; return; }}
            var vals = entries.map(function(e) {{ return e[1]; }});
            var w = 180, h = 36, pad = 2;
            var mn = Math.min.apply(null, vals);
            var mx = Math.max.apply(null, vals);
            var rng = mx - mn || 1;
            var cw = w - pad * 2, ch = h - pad * 2;
            var pts = vals.map(function(v, i) {{
                return (pad + (i / (vals.length - 1)) * cw).toFixed(1) + ',' + (pad + ch - ((v - mn) / rng) * ch).toFixed(1);
            }});
            var polyline = pts.join(' ');
            var lastPt = pts[pts.length - 1].split(',');
            el.innerHTML = '<svg width="' + w + '" height="' + h + '" viewBox="0 0 ' + w + ' ' + h + '">'
                + '<polyline points="' + polyline + '" fill="none" stroke="' + color + '" stroke-width="2" stroke-linecap="round"/>'
                + '<circle cx="' + lastPt[0] + '" cy="' + lastPt[1] + '" r="3" fill="' + color + '"/>'
                + '</svg>';
        }}

        var MONTH_SHORT = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
        function renderMonthlyBarChart(containerId, data, color, isCurrency) {{
            var el = document.getElementById(containerId);
            if (!el) return;
            color = color || '#3CB4AD';
            var entries = Object.entries(data).sort();
            // Take last 6 months only
            if (entries.length > 6) entries = entries.slice(entries.length - 6);
            if (entries.length === 0) {{ el.innerHTML = '<span style="color:#64748b;font-size:11px">No data</span>'; return; }}
            var vals = entries.map(function(e) {{ return e[1]; }});
            var labels = entries.map(function(e) {{
                var parts = e[0].split('-');
                return MONTH_SHORT[parseInt(parts[1], 10) - 1] || e[0];
            }});
            var mx = Math.max.apply(null, vals) || 1;
            var w = 260, barH = 90, padTop = 4, padBot = 18, padL = 4, padR = 4;
            var chartH = barH - padTop - padBot;
            var n = entries.length;
            var gap = 6;
            var barW = Math.floor((w - padL - padR - gap * (n - 1)) / n);
            if (barW < 20) barW = 20;
            var totalW = padL + n * barW + (n - 1) * gap + padR;
            var svg = '<svg width="100%" height="' + barH + '" viewBox="0 0 ' + totalW + ' ' + barH + '" preserveAspectRatio="xMidYMid meet">';
            // Axis line
            svg += '<line x1="' + padL + '" y1="' + (padTop + chartH) + '" x2="' + (totalW - padR) + '" y2="' + (padTop + chartH) + '" stroke="#334155" stroke-width="1" opacity="0.3"/>';
            for (var i = 0; i < n; i++) {{
                var x = padL + i * (barW + gap);
                var v = vals[i];
                var h = Math.max((v / mx) * chartH, 2);
                var y = padTop + chartH - h;
                // Bar with rounded top
                svg += '<rect x="' + x + '" y="' + y + '" width="' + barW + '" height="' + h + '" rx="3" fill="' + color + '" opacity="0.85"/>';
                // Value inside bar (or above if bar too short)
                var valStr = isCurrency ? (v >= 1000 ? '\u00A3' + (v / 1000).toFixed(v >= 10000 ? 0 : 1) + 'k' : '\u00A3' + Math.round(v)) : (v >= 1000 ? (v / 1000).toFixed(v >= 10000 ? 0 : 1) + 'k' : String(Math.round(v)));
                var fontSize = barW < 30 ? 9 : 10;
                var textY = h > 18 ? (y + h / 2 + 4) : (y - 3);
                var textColor = h > 18 ? '#fff' : color;
                svg += '<text x="' + (x + barW / 2) + '" y="' + textY + '" text-anchor="middle" fill="' + textColor + '" font-size="' + fontSize + '" font-weight="600" font-family="Assistant,sans-serif">' + valStr + '</text>';
                // Month label below axis
                svg += '<text x="' + (x + barW / 2) + '" y="' + (padTop + chartH + 14) + '" text-anchor="middle" fill="#94a3b8" font-size="10" font-family="Assistant,sans-serif">' + labels[i] + '</text>';
            }}
            svg += '</svg>';
            el.innerHTML = svg;
        }}

        // ----------------------------------------------------------------
        // Main filter application
        // ----------------------------------------------------------------
        window.applyFilter = function(period) {{
            var range = getDateRange(period);
            var showYoY = (period === 'ytd' || period === 'all' || period === 'last_year');

            // Update button states
            document.querySelectorAll('.filter-btn').forEach(function(btn) {{
                btn.classList.toggle('active', btn.getAttribute('data-period') === period);
            }});
            var label = document.getElementById('filter-period-label');
            if (label) label.textContent = PERIOD_LABELS[period] || '';

            // ---- Compute filtered values ----
            var leads = sumDaily(TS.leads_by_day, range);
            var contacts = sumDaily(TS.contacts_created_by_day, range);
            var dealsWon = sumDaily(TS.deals_won_by_day, range);
            var dealsLost = sumDaily(TS.deals_lost_by_day, range);
            var dealsCreated = sumDaily(TS.deals_created_by_day, range);
            var revenue = sumDaily(TS.deals_won_value_by_day, range);
            var activities = sumActivitiesDaily(TS.activities_by_type_by_day, range);
            var mqls = sumDaily(TS.mqls_by_day, range);
            var sqls = sumDaily(TS.sqls_by_day, range);
            var actBreakdown = getActivityBreakdown(TS.activities_by_type_by_day, range);
            var avgDeal = dealsWon > 0 ? revenue / dealsWon : 0;
            var winRate = (dealsWon + dealsLost) > 0 ? (dealsWon / (dealsWon + dealsLost) * 100) : 0;

            // ---- Update KPI cards ----
            // Find stat-card elements and update by matching title text
            var cards = document.querySelectorAll('.stat-card');
            cards.forEach(function(card) {{
                var titleEl = card.querySelector('div[style*="text-transform:uppercase"]');
                if (!titleEl) return;
                var title = titleEl.textContent.trim().toLowerCase();
                var valueEl = card.querySelector('[data-role="stat-value"]');
                if (!valueEl) return;

                switch(title) {{
                    case 'total leads':
                        valueEl.innerHTML = fmtNum(leads) + (showYoY ? yoyBadge('leads') : '');
                        break;
                    case 'total contacts':
                        valueEl.innerHTML = fmtNum(contacts) + (showYoY ? yoyBadge('contacts_created') : '');
                        break;
                    case 'total activities':
                        valueEl.innerHTML = fmtNum(activities) + (showYoY ? yoyBadge('activities') : '');
                        break;
                    case 'mql count':
                        valueEl.innerHTML = fmtNum(mqls) + (showYoY ? yoyBadge('mqls') : '');
                        break;
                    case 'sql count':
                        valueEl.innerHTML = fmtNum(sqls);
                        break;
                    case 'win rate':
                        valueEl.innerHTML = winRate.toFixed(1) + '%';
                        break;
                    case 'avg deal size':
                        valueEl.innerHTML = fmtCurrency(avgDeal) + (showYoY ? yoyBadge('avg_deal_size') : '');
                        break;
                    case 'pipeline value':
                    case 'total pipeline':
                        valueEl.innerHTML = fmtCurrency(revenue) + (showYoY ? yoyBadge('revenue_won') : '');
                        break;
                    case 'open deals':
                        valueEl.innerHTML = fmtNum(dealsCreated) + (showYoY ? yoyBadge('deals_won') : '');
                        break;
                    case 'calls':
                        valueEl.innerHTML = fmtNum(actBreakdown.calls);
                        break;
                    case 'emails':
                        valueEl.innerHTML = fmtNum(actBreakdown.emails);
                        break;
                    case 'meetings':
                        valueEl.innerHTML = fmtNum(actBreakdown.meetings);
                        break;
                    case 'tasks':
                        valueEl.innerHTML = fmtNum(actBreakdown.tasks);
                        break;
                    case 'notes':
                        valueEl.innerHTML = fmtNum(actBreakdown.notes);
                        break;
                }}
            }});

            // ---- Update dynamic chart containers ----
            // Leads by source (filtered monthly)
            var leadSrcMonthly = {{}};
            if (TS.leads_by_source_by_month) {{
                for (var month in TS.leads_by_source_by_month) {{
                    if (range === null || (month + '-01' >= range.start && month + '-01' <= range.end)
                        || (month + '-28' >= range.start && month + '-01' <= range.end)) {{
                        var srcs = TS.leads_by_source_by_month[month];
                        for (var src in srcs) {{
                            leadSrcMonthly[src] = (leadSrcMonthly[src] || 0) + srcs[src];
                        }}
                    }}
                }}
            }}
            renderMiniBar('dynamic-leads-by-source', leadSrcMonthly);

            // Leads over time bar chart
            var leadsMonthly = filterDailyToMonthly(TS.leads_by_day, range);
            renderMonthlyBarChart('dynamic-leads-barchart', leadsMonthly, '#3CB4AD', false);

            // Activity trend sparkline
            var actDaily = {{}};
            if (TS.activities_by_type_by_day) {{
                for (var day in TS.activities_by_type_by_day) {{
                    if (range === null || (day >= range.start && day <= range.end)) {{
                        var c = TS.activities_by_type_by_day[day];
                        var mk = day.substring(0, 7);
                        var total = 0;
                        for (var t in c) total += c[t];
                        actDaily[mk] = (actDaily[mk] || 0) + total;
                    }}
                }}
            }}
            renderMonthlyBarChart('dynamic-activity-barchart', actDaily, '#a78bfa', false);

            // Activity breakdown bars
            renderMiniBar('dynamic-activity-breakdown', actBreakdown);

            // Revenue by month sparkline
            var revMonthly = {{}};
            if (TS.deals_won_value_by_day) {{
                for (var day in TS.deals_won_value_by_day) {{
                    if (range === null || (day >= range.start && day <= range.end)) {{
                        var mk = day.substring(0, 7);
                        revMonthly[mk] = (revMonthly[mk] || 0) + TS.deals_won_value_by_day[day];
                    }}
                }}
            }}
            renderMonthlyBarChart('dynamic-revenue-barchart', revMonthly, '#34d399', true);

            // Deals created bar chart
            var dealsMonthly = filterDailyToMonthly(TS.deals_created_by_day, range);
            renderMonthlyBarChart('dynamic-deals-barchart', dealsMonthly, '#38bdf8', false);
        }};

        // ---- Initialize on page load ----
        document.addEventListener('DOMContentLoaded', function() {{
            applyFilter('ytd');
        }});
    }})();
    </script>'''

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>eComplete &mdash; Sales &amp; M&amp;A Intelligence</title>
    <meta name="description" content="eComplete Sales &amp; M&amp;A Intelligence Dashboard — HubSpot CRM + Monday.com">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Assistant:wght@400;600;700;800&amp;display=swap" rel="stylesheet">
    {_build_css()}
</head>
<body>
    <div class="login-overlay" id="login-overlay">
        <div class="login-card">
            <div class="login-brand">
                <span class="brand-dot">e</span>
                <span>eComplete</span>
            </div>
            <div class="login-title">Welcome</div>
            <p class="login-subtitle">Enter your name to continue</p>
            <input class="login-input" id="login-name" type="text" placeholder="Your name..." autofocus />
            <button class="login-btn" id="login-btn" onclick="window.doLogin()">Continue &#10148;</button>
        </div>
    </div>

    {_build_sidebar()}
    <div class="sidebar-overlay" id="sidebar-overlay" onclick="toggleSidebar()"></div>

    <div class="layout-main" id="layout-main">
        {filter_bar}
        {freshness_html}
        <main class="main-content">
            {''.join(sections)}
        </main>

        <footer class="dashboard-footer">
            <p><span class="brand">eComplete</span> &mdash; Sales &amp; M&amp;A Intelligence Dashboard</p>
            <p style="margin-top:4px">{footer_stats}</p>
            <p style="margin-top:4px">Generated: {timestamp}</p>
        </footer>
    </div>

    {_build_chat_html()}

    {_build_js()}
    {filter_js}
    {_build_supabase_js()}
    {_build_chat_js()}
</body>
</html>'''

    return html


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Read metrics JSON and generate the dashboard HTML."""
    logger.info("=== HubSpot Dashboard Generator ===")
    logger.info("Data file: %s", DATA_FILE)
    logger.info("Output:    %s", OUTPUT_FILE)

    # Load data
    if not DATA_FILE.exists():
        logger.error("Metrics file not found: %s", DATA_FILE)
        logger.error("Run hubspot_sales_analyzer.py first to generate the metrics.")
        sys.exit(1)

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        logger.info("Loaded metrics data (%d top-level keys)", len(data))
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse JSON: %s", exc)
        sys.exit(1)
    except Exception as exc:
        logger.error("Failed to read metrics file: %s", exc)
        sys.exit(1)

    # Generate HTML
    logger.info("Building dashboard HTML...")
    html_content = generate_dashboard(data)
    logger.info("Generated %s characters of HTML", f"{len(html_content):,}")

    # Write output
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write(html_content)
        logger.info("Dashboard written to %s", OUTPUT_FILE)
    except Exception as exc:
        logger.error("Failed to write dashboard: %s", exc)
        sys.exit(1)

    logger.info("=== Dashboard generation complete ===")


if __name__ == "__main__":
    main()
