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
    height: int = 300,
    color: str = "#3CB4AD",
    show_values: bool = True,
) -> str:
    """Horizontal bar chart.  data = [(label, value), ...]."""
    if not data:
        return _no_data_svg(width, height)
    bar_height = 32
    gap = 8
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
    size: int = 220,
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
    width: int = 600,
    height: int = 400,
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
    width: int = 600,
    height: int = 250,
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
            short = str(labels[i])[-5:]  # last 5 chars e.g. "01-25"
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


def _no_data_svg(width: int = 400, height: int = 200) -> str:
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
) -> str:
    """Metric KPI card with optional sparkline."""
    spark_html = ""
    if sparkline_values and len(sparkline_values) >= 2:
        spark_html = f'''<div style="margin-top:8px">
            {_svg_sparkline(sparkline_values, 130, 32, color)}
        </div>'''

    icon_html = ""
    if icon:
        icon_html = f'''<div style="width:30px;height:30px;border-radius:8px;
            background:linear-gradient(135deg,{color}22,{color}11);
            display:flex;align-items:center;justify-content:center;
            font-size:14px;flex-shrink:0;margin-bottom:4px;
            border:1px solid {color}33">{icon}</div>'''

    return f'''<div class="stat-card" style="--accent:{color}">
        {icon_html}
        <div style="font-size:10px;color:{COLORS['text_muted']};text-transform:uppercase;
                    letter-spacing:0.05em;margin-bottom:2px">{_esc(title)}</div>
        <div data-role="stat-value" style="font-size:22px;font-weight:800;color:{COLORS['text']};
                    line-height:1.1;margin-bottom:1px">{_esc(value)}</div>
        <div style="font-size:11px;color:{COLORS['text_muted']}">{_esc(subtitle)}</div>
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

    return f'''<div style="margin-bottom:12px">
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

def _build_executive_summary(data: dict) -> str:
    """Section 1: Executive Summary KPI cards and highlights."""
    pipeline = _safe_get(data, "pipeline_metrics", default={})
    activity = _safe_get(data, "activity_metrics", default={})
    leads = _safe_get(data, "lead_metrics", default={})
    contacts = _safe_get(data, "contact_metrics", default={})
    counts = _safe_get(data, "record_counts", default={})
    rev_eng = _safe_get(data, "reverse_engineering", default={})
    insights = _safe_get(data, "insights", default={})

    # Sparkline data - handle both dict {key: value} and list [{key: val}] formats
    leads_over_time = _safe_get(leads, "leads_over_time", default={})
    if isinstance(leads_over_time, dict):
        lead_sparkline = list(leads_over_time.values())
    elif isinstance(leads_over_time, list):
        lead_sparkline = [item.get("count", 0) if isinstance(item, dict) else item for item in leads_over_time]
    else:
        lead_sparkline = []

    daily_trend = _safe_get(activity, "daily_trend", default={})
    if isinstance(daily_trend, dict):
        activity_sparkline = list(daily_trend.values())
    elif isinstance(daily_trend, list):
        activity_sparkline = [item.get("count", 0) if isinstance(item, dict) else item for item in daily_trend]
    else:
        activity_sparkline = []

    sales_cycle_trend = _safe_get(insights, "sales_cycle_trend", default={})
    if isinstance(sales_cycle_trend, dict):
        cycle_sparkline = list(sales_cycle_trend.values())
    elif isinstance(sales_cycle_trend, list):
        cycle_sparkline = [item.get("avg_days", 0) if isinstance(item, dict) else item for item in sales_cycle_trend]
    else:
        cycle_sparkline = []

    forecast = _safe_get(insights, "revenue_forecast", default={})

    html = _section_header("executive", "Executive Summary",
                           "Key performance indicators at a glance",
                           "\U0001F4CA")

    # Row 1 - Primary KPIs
    html += '<div class="kpi-grid">'
    html += _stat_card("Pipeline Value", _fmt_currency(pipeline.get("total_pipeline_value", 0)),
                       f"Weighted: {_fmt_currency(pipeline.get('weighted_pipeline_value', 0))}",
                       "\U0001F4B0", COLORS['accent'])
    html += _stat_card("Win Rate", _fmt_pct(pipeline.get("win_rate", 0)),
                       f"Won: {pipeline.get('won_deals_count', 0)} | Lost: {pipeline.get('lost_deals_count', 0)}",
                       "\U0001F3AF", COLORS['accent4'])
    html += _stat_card("Open Deals", _fmt_number(pipeline.get("open_deals_count", 0)),
                       f"Avg size: {_fmt_currency(pipeline.get('avg_deal_size', 0))}",
                       "\U0001F4C1", COLORS['accent2'])
    html += _stat_card("Total Activities", _fmt_number(activity.get("total_activities", 0)),
                       f"Touches/won deal: {_fmt_number(activity.get('touches_per_won_deal', 0))}",
                       "\u26A1", COLORS['accent3'],
                       activity_sparkline)
    html += '</div>'

    # Row 2 - Secondary KPIs
    html += '<div class="kpi-grid">'
    html += _stat_card("Total Contacts", _fmt_number(counts.get("contacts", 0)),
                       f"New 30d: {_fmt_number(_safe_get(contacts, 'new_contacts_30d', default=0))}",
                       "\U0001F465", COLORS['accent5'])
    html += _stat_card("Avg Deal Size", _fmt_currency(pipeline.get("avg_deal_size", 0)),
                       f"Cycle: {_fmt_number(pipeline.get('avg_sales_cycle_days', 0))} days",
                       "\U0001F4B7", COLORS['accent6'])
    html += _stat_card("Total Leads", _fmt_number(leads.get("total_leads", 0)),
                       f"New 30d: {_fmt_number(leads.get('new_leads_30d', 0))}",
                       "\U0001F4E5", COLORS['info'],
                       lead_sparkline)
    html += _stat_card("30-Day Forecast", _fmt_currency(forecast.get("days_30", 0)),
                       f"90d: {_fmt_currency(forecast.get('days_90', 0))}",
                       "\U0001F52E", COLORS['warning'])
    html += '</div>'

    # Dynamic charts row (populated by JS)
    html += f'''<div class="grid-2" style="margin-top:16px">
        <div class="glass-card">
            <div class="card-title">Leads Trend <span style="font-size:11px;font-weight:400;color:{COLORS['text_muted']}">(filtered)</span></div>
            <div id="dynamic-leads-sparkline"></div>
        </div>
        <div class="glass-card">
            <div class="card-title">Revenue Trend <span style="font-size:11px;font-weight:400;color:{COLORS['text_muted']}">(filtered)</span></div>
            <div id="dynamic-revenue-sparkline"></div>
        </div>
    </div>'''
    html += f'''<div class="grid-2" style="margin-top:16px">
        <div class="glass-card">
            <div class="card-title">Deals Created <span style="font-size:11px;font-weight:400;color:{COLORS['text_muted']}">(filtered)</span></div>
            <div id="dynamic-deals-sparkline"></div>
        </div>
        <div class="glass-card">
            <div class="card-title">Activity Trend <span style="font-size:11px;font-weight:400;color:{COLORS['text_muted']}">(filtered)</span></div>
            <div id="dynamic-activity-sparkline"></div>
        </div>
    </div>'''

    # Revenue target progress
    rev_target = _safe_get(rev_eng, "revenue_target", default={})
    monthly_target = rev_target.get("monthly", 100000)
    weighted = pipeline.get("weighted_pipeline_value", 0)
    html += f'''<div class="glass-card" style="margin-top:16px">
        <h3 style="font-size:14px;color:{COLORS['text_muted']};margin-bottom:12px;
            text-transform:uppercase;letter-spacing:0.05em">Revenue Target Progress</h3>
        {_progress_bar(weighted, monthly_target, COLORS['accent4'],
                       f"Weighted Pipeline vs Monthly Target ({_fmt_currency(monthly_target)})")}
    </div>'''

    html += '</section>'
    return html


def _build_leads_section(data: dict) -> str:
    """Section 2: Leads & Sources."""
    leads = _safe_get(data, "lead_metrics", default={})
    html = _section_header("leads", "Leads & Sources",
                           "Lead volume, source breakdown, and effectiveness",
                           "\U0001F4E5")

    # KPI row
    html += '<div class="kpi-grid kpi-grid-3">'
    html += _stat_card("Total Leads", _fmt_number(leads.get("total_leads", 0)),
                       f"New 30d: {_fmt_number(leads.get('new_leads_30d', 0))}",
                       "\U0001F4CA", COLORS['accent'])
    html += _stat_card("MQL Count", _fmt_number(leads.get("mql_count", 0)),
                       f"Lead-to-MQL: {_fmt_pct(leads.get('lead_to_mql_rate', 0))}",
                       "\U0001F31F", COLORS['accent2'])
    html += _stat_card("SQL Count", _fmt_number(leads.get("sql_count", 0)),
                       f"Avg response: {_fmt_number(leads.get('avg_lead_response_hours', 0))}h",
                       "\U0001F525", COLORS['accent4'])
    html += '</div>'

    # Dynamic leads by source (JS-filtered)
    html += f'''<div class="glass-card" style="margin-top:16px">
        <h3 class="card-title">Leads by Source <span style="font-size:11px;font-weight:400;color:{COLORS['text_muted']}">(filtered by period)</span></h3>
        <div id="dynamic-leads-by-source"></div>
    </div>'''

    # Static source breakdown (all-time reference)
    sources = leads.get("leads_by_source", {})
    if sources:
        source_data = sorted(sources.items(), key=lambda x: x[1], reverse=True)[:12]
        html += f'''<div class="grid-2" style="margin-top:16px">
            <div class="glass-card">
                <h3 class="card-title">Leads by Source (All Time)</h3>
                {_svg_bar_chart(source_data, 500, max(200, len(source_data) * 40))}
            </div>
            <div class="glass-card">
                <h3 class="card-title">Source Distribution</h3>
                {_svg_donut(source_data[:8], 240)}
            </div>
        </div>'''

    # New leads trend
    leads_over_time = leads.get("leads_over_time", [])
    if leads_over_time:
        trend_data = [(item.get("month", ""), item.get("count", 0)) for item in leads_over_time]
        html += f'''<div class="glass-card" style="margin-top:16px">
            <h3 class="card-title">New Leads Over Time</h3>
            {_svg_line_chart(trend_data, 700, 250, COLORS['accent'])}
        </div>'''

    # Lead status distribution
    status_dist = leads.get("lead_status_distribution", {})
    if status_dist:
        html += f'''<div class="glass-card" style="margin-top:16px">
            <h3 class="card-title">Lead Status Distribution</h3>'''
        max_status = max(status_dist.values()) if status_dist else 1
        for status, count in sorted(status_dist.items(), key=lambda x: x[1], reverse=True):
            html += _svg_horizontal_bar(status, count, max_status, COLORS['accent2'])
        html += '</div>'

    # Source effectiveness table
    effectiveness = leads.get("source_effectiveness", [])
    if effectiveness:
        rows = []
        for item in effectiveness:
            rows.append([
                _esc(item.get("source", "")),
                _fmt_number(item.get("lead_count", 0)),
                _fmt_number(item.get("mql_count", 0)),
                _fmt_pct(item.get("conversion_rate", 0)),
            ])
        html += f'''<div class="glass-card" style="margin-top:16px">
            <h3 class="card-title">Source Effectiveness</h3>
            {_data_table(["Source", "Leads", "MQLs", "Conversion Rate"], rows, "source_eff")}
        </div>'''

    html += '</section>'
    return html


def _build_funnel_section(data: dict) -> str:
    """Section 3: Qualified Leads & Funnel."""
    leads = _safe_get(data, "lead_metrics", default={})
    rev_eng = _safe_get(data, "reverse_engineering", default={})

    html = _section_header("funnel", "Qualified Leads & Funnel",
                           "Conversion funnel from lead to customer",
                           "\U0001F3AF")

    # Build funnel stages
    total_leads = leads.get("total_leads", 0)
    mql = leads.get("mql_count", 0)
    sql = leads.get("sql_count", 0)
    opps = rev_eng.get("required_opps", 0) if rev_eng else 0
    pipeline = _safe_get(data, "pipeline_metrics", default={})
    won = pipeline.get("won_deals_count", 0)

    # Try to get actual values from conversion_rates
    conversion_rates = leads.get("conversion_rates", {})

    funnel_stages = [
        ("Leads", total_leads, f"{_fmt_number(total_leads)} total leads"),
        ("MQLs", mql, f"{_fmt_pct(leads.get('lead_to_mql_rate', 0))} conversion"),
        ("SQLs", sql, f"{_fmt_pct(conversion_rates.get('mql_to_sql', 0))} from MQL"),
        ("Opportunities", pipeline.get("open_deals_count", 0) + won + pipeline.get("lost_deals_count", 0),
         f"{_fmt_number(pipeline.get('open_deals_count', 0) + won + pipeline.get('lost_deals_count', 0))} total"),
        ("Customers (Won)", won, f"{_fmt_pct(pipeline.get('win_rate', 0))} win rate"),
    ]

    html += f'''<div class="glass-card">
        <h3 class="card-title">Conversion Funnel</h3>
        <div style="max-width:650px;margin:0 auto">
            {_svg_funnel(funnel_stages, 650, 420)}
        </div>
    </div>'''

    # Conversion rates detail
    if conversion_rates:
        html += f'''<div class="glass-card" style="margin-top:16px">
            <h3 class="card-title">Stage Conversion Rates</h3>
            <div class="kpi-grid kpi-grid-3">'''
        rate_labels = {
            "lead_to_mql": ("Lead \u2192 MQL", COLORS['accent']),
            "mql_to_sql": ("MQL \u2192 SQL", COLORS['accent2']),
            "sql_to_opp": ("SQL \u2192 Opp", COLORS['accent3']),
            "opp_to_won": ("Opp \u2192 Won", COLORS['accent4']),
            "lead_to_customer": ("Lead \u2192 Customer", COLORS['accent5']),
        }
        for key, (label, color) in rate_labels.items():
            val = conversion_rates.get(key, 0)
            if val or key in conversion_rates:
                html += _stat_card(label, _fmt_pct(val), "", "", color)
        html += '</div></div>'

    # Time in stage
    time_in_stage = leads.get("time_in_stage", {})
    if time_in_stage:
        html += f'''<div class="glass-card" style="margin-top:16px">
            <h3 class="card-title">Average Time in Stage (days)</h3>'''
        safe_vals = [v for v in time_in_stage.values() if v is not None and v > 0]
        max_days = max(safe_vals) if safe_vals else 1
        for stage, days in sorted(time_in_stage.items(), key=lambda x: (x[1] or 0), reverse=True):
            html += _svg_horizontal_bar(stage, days, max_days, COLORS['accent3'], show_pct=False)
        html += '</div>'

    html += '</section>'
    return html


def _build_target_section(data: dict) -> str:
    """Section 4: Target Setting & Reverse Engineering."""
    rev_eng = _safe_get(data, "reverse_engineering", default={})
    if not rev_eng:
        html = _section_header("targets", "Target Setting & Reverse Engineering",
                               "Revenue targets and required volumes", "\U0001F4C8")
        html += f'''<div class="glass-card"><p style="color:{COLORS['text_muted']};
            text-align:center;padding:32px">No reverse engineering data available</p></div>'''
        html += '</section>'
        return html

    html = _section_header("targets", "Target Setting & Reverse Engineering",
                           "Revenue targets and required volumes",
                           "\U0001F4C8")

    # Revenue targets
    rev_target = rev_eng.get("revenue_target", {})
    html += '<div class="kpi-grid kpi-grid-3">'
    html += _stat_card("Monthly Target", _fmt_currency(rev_target.get("monthly", 0)),
                       "", "\U0001F4B7", COLORS['accent'])
    html += _stat_card("Quarterly Target", _fmt_currency(rev_target.get("quarterly", 0)),
                       "", "\U0001F4C5", COLORS['accent2'])
    html += _stat_card("Annual Target", _fmt_currency(rev_target.get("annual", 0)),
                       "", "\U0001F3C6", COLORS['accent4'])
    html += '</div>'

    # Required volume chain
    chain_items = [
        ("Required Leads", rev_eng.get("required_leads", 0), COLORS['accent']),
        ("Required MQLs", rev_eng.get("required_mqls", 0), COLORS['accent2']),
        ("Required SQLs", rev_eng.get("required_sqls", 0), COLORS['accent3']),
        ("Required Opps", rev_eng.get("required_opps", 0), COLORS['accent5']),
        ("Required Deals", rev_eng.get("required_deals", 0), COLORS['accent4']),
    ]
    html += '''<div class="glass-card" style="margin-top:16px">
        <h3 class="card-title">Required Volume Chain (Monthly)</h3>
        <div class="volume-chain">'''
    for i, (label, val, color) in enumerate(chain_items):
        arrow = '<div class="chain-arrow">\u27A1</div>' if i > 0 else ''
        html += f'''{arrow}
            <div class="chain-item" style="border-color:{color}">
                <div class="chain-value" style="color:{color}">{_fmt_number(val)}</div>
                <div class="chain-label">{_esc(label)}</div>
            </div>'''
    html += '</div></div>'

    # Gap analysis
    gap = rev_eng.get("gap_analysis", {})
    if gap:
        html += f'''<div class="glass-card" style="margin-top:16px">
            <h3 class="card-title">Gap Analysis</h3>'''
        for key, val in gap.items():
            label = key.replace("_", " ").title()
            if isinstance(val, (int, float)):
                color = COLORS['success'] if val >= 0 else COLORS['danger']
                display = _fmt_number(val) if abs(val) < 1000 else _fmt_currency(val)
                prefix = "+" if val > 0 else ""
                html += f'''<div style="display:flex;justify-content:space-between;
                    padding:8px 0;border-bottom:1px solid {COLORS['card_border']}22;font-size:13px">
                    <span style="color:{COLORS['text_muted']}">{_esc(label)}</span>
                    <span style="color:{color};font-weight:600">{prefix}{display}</span>
                </div>'''
        html += '</div>'

    # Daily/Weekly requirements
    daily = rev_eng.get("daily_requirements", {})
    weekly = rev_eng.get("weekly_requirements", {})
    if daily or weekly:
        html += '''<div class="grid-2" style="margin-top:16px">'''
        if daily:
            html += f'''<div class="glass-card">
                <h3 class="card-title">Daily Requirements</h3>'''
            for key, val in daily.items():
                label = key.replace("_", " ").title()
                html += f'''<div style="display:flex;justify-content:space-between;
                    padding:6px 0;font-size:13px;border-bottom:1px solid {COLORS['card_border']}22">
                    <span style="color:{COLORS['text_muted']}">{_esc(label)}</span>
                    <span style="color:{COLORS['text']};font-weight:600">{_fmt_number(val)}</span>
                </div>'''
            html += '</div>'
        if weekly:
            html += f'''<div class="glass-card">
                <h3 class="card-title">Weekly Requirements</h3>'''
            for key, val in weekly.items():
                label = key.replace("_", " ").title()
                html += f'''<div style="display:flex;justify-content:space-between;
                    padding:6px 0;font-size:13px;border-bottom:1px solid {COLORS['card_border']}22">
                    <span style="color:{COLORS['text_muted']}">{_esc(label)}</span>
                    <span style="color:{COLORS['text']};font-weight:600">{_fmt_number(val)}</span>
                </div>'''
            html += '</div>'
        html += '</div>'

    # What-if scenarios
    scenarios = rev_eng.get("what_if_scenarios", [])
    if scenarios:
        rows = []
        for s in scenarios:
            rows.append([
                f"+{_fmt_number(s.get('improvement_pct', 0))}%",
                _fmt_pct(s.get("new_lead_to_mql", 0)),
                _fmt_number(s.get("required_leads", 0)),
                _fmt_number(s.get("leads_saved", 0)),
            ])
        html += f'''<div class="glass-card" style="margin-top:16px">
            <h3 class="card-title">What-If Scenarios</h3>
            <p style="font-size:12px;color:{COLORS['text_muted']};margin-bottom:12px">
                Impact of improving lead-to-MQL conversion rate</p>
            {_data_table(["Improvement", "New Rate", "Leads Needed", "Leads Saved"], rows, "whatif")}
        </div>'''

    html += '</section>'
    return html


def _build_pipeline_section(data: dict) -> str:
    """Section 5: Pipeline View."""
    pipeline = _safe_get(data, "pipeline_metrics", default={})
    html = _section_header("pipeline", "Pipeline View",
                           "Deal stages, rep performance, and velocity",
                           "\U0001F4B0")

    # KPIs
    html += '<div class="kpi-grid">'
    html += _stat_card("Total Pipeline", _fmt_currency(pipeline.get("total_pipeline_value", 0)),
                       f"Weighted: {_fmt_currency(pipeline.get('weighted_pipeline_value', 0))}",
                       "\U0001F4B0", COLORS['accent'])
    html += _stat_card("Pipeline Coverage", f"{_fmt_number(pipeline.get('pipeline_coverage', 0))}x",
                       "vs revenue target", "\U0001F6E1", COLORS['accent2'])
    html += _stat_card("Avg Sales Cycle", f"{_fmt_number(pipeline.get('avg_sales_cycle_days', 0))}d",
                       f"Avg deal: {_fmt_currency(pipeline.get('avg_deal_size', 0))}",
                       "\u23F1", COLORS['accent3'])
    html += _stat_card("Win Rate", _fmt_pct(pipeline.get("win_rate", 0)),
                       f"Won {pipeline.get('won_deals_count', 0)} | Lost {pipeline.get('lost_deals_count', 0)}",
                       "\U0001F3AF", COLORS['accent4'])
    html += '</div>'

    # Pipeline velocity
    velocity = pipeline.get("pipeline_velocity", {})
    if velocity and isinstance(velocity, dict):
        html += f'''<div class="glass-card" style="margin-top:16px">
            <h3 class="card-title">Pipeline Velocity</h3>
            <div class="kpi-grid kpi-grid-3">'''
        for key, val in velocity.items():
            if not isinstance(val, (int, float)):
                continue
            label = key.replace("_", " ").title()
            display = _fmt_currency(val) if "value" in key.lower() or "revenue" in key.lower() else _fmt_number(val)
            html += f'''<div style="text-align:center;padding:12px">
                <div style="font-size:11px;color:{COLORS['text_muted']};text-transform:uppercase;
                    letter-spacing:0.05em;margin-bottom:4px">{_esc(label)}</div>
                <div style="font-size:22px;font-weight:700;color:{COLORS['text']}">{display}</div>
            </div>'''
        html += '</div></div>'

    # Stage breakdown
    stages = pipeline.get("deals_by_stage", [])
    if stages:
        rows = []
        for s in stages:
            rows.append([
                _esc(s.get("label", s.get("stage", ""))),
                _fmt_number(s.get("count", 0)),
                _fmt_currency(s.get("value", 0)),
                _fmt_currency(s.get("weighted_value", 0)),
                _fmt_pct(s.get("probability", 0)),
                _fmt_number(s.get("avg_days_in_stage", 0)),
            ])
        html += f'''<div class="glass-card" style="margin-top:16px">
            <h3 class="card-title">Deals by Stage</h3>
            {_data_table(["Stage", "Deals", "Value", "Weighted", "Probability", "Avg Days"],
                         rows, "pipeline_stages")}
        </div>'''

        # Visual stage bars
        max_stage_val = max((s.get("value", 0) for s in stages), default=1) or 1
        html += f'''<div class="glass-card" style="margin-top:16px">
            <h3 class="card-title">Stage Value Distribution</h3>'''
        for i, s in enumerate(stages):
            html += _svg_horizontal_bar(
                s.get("label", s.get("stage", "")),
                s.get("value", 0),
                max_stage_val,
                _color_at(i),
                show_pct=False,
            )
        html += '</div>'

    # Pipeline by rep
    by_owner = pipeline.get("pipeline_by_owner", [])
    if by_owner:
        rows = []
        for rep in by_owner:
            rows.append([
                _esc(rep.get("owner_name", "Unknown")),
                _fmt_number(rep.get("deal_count", 0)),
                _fmt_currency(rep.get("total_value", 0)),
                _fmt_currency(rep.get("weighted_value", 0)),
                _fmt_currency(rep.get("avg_deal_size", 0)),
                _fmt_pct(rep.get("win_rate", 0)),
            ])
        html += f'''<div class="glass-card" style="margin-top:16px">
            <h3 class="card-title">Pipeline by Rep</h3>
            {_data_table(["Rep", "Deals", "Total Value", "Weighted", "Avg Deal", "Win Rate"],
                         rows, "pipeline_reps")}
        </div>'''

    # Stale deals
    stale = pipeline.get("stale_deals", [])
    if stale:
        html += f'''<div class="glass-card alert-card" style="margin-top:16px;
            border-color:{COLORS['warning']}44">
            <h3 class="card-title" style="color:{COLORS['warning']}">
                \u26A0 Stale Deals ({len(stale)})</h3>
            <p style="font-size:12px;color:{COLORS['text_muted']};margin-bottom:12px">
                Deals with no activity beyond threshold</p>'''
        stale_rows = []
        for d in stale[:20]:
            stale_rows.append([
                _esc(d.get("name", d.get("deal_name", "Unknown"))),
                _fmt_currency(d.get("amount", d.get("value", 0))),
                _esc(d.get("stage", "")),
                _fmt_number(d.get("days_stale", d.get("days_inactive", 0))),
                _esc(d.get("owner", d.get("owner_name", ""))),
            ])
        html += _data_table(["Deal", "Value", "Stage", "Days Stale", "Owner"],
                            stale_rows, "stale_deals")
        html += '</div>'

    # Close date distribution
    close_dist = pipeline.get("close_date_distribution", {})
    if close_dist:
        chart_data = [(k, v) for k, v in sorted(close_dist.items())]
        html += f'''<div class="glass-card" style="margin-top:16px">
            <h3 class="card-title">Expected Close Date Distribution</h3>
            {_svg_line_chart(chart_data, 700, 220, COLORS['accent2'])}
        </div>'''

    html += '</section>'
    return html


def _build_activity_section(data: dict) -> str:
    """Section 6: Activity Tracking."""
    activity = _safe_get(data, "activity_metrics", default={})
    html = _section_header("activities", "Activity Tracking",
                           "Sales activities, rep engagement, and trends",
                           "\u26A1")

    # Activity type KPIs
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

    html += '<div class="kpi-grid">'
    html += _stat_card("Total Activities", _fmt_number(activity.get("total_activities", 0)),
                       f"{len(by_type)} activity types", "\u26A1", COLORS['accent6'])
    for act_type, count in sorted(by_type.items(), key=lambda x: x[1], reverse=True)[:4]:
        icon = icon_map.get(act_type.lower(), "\U0001F4CB")
        color = color_map.get(act_type.lower(), COLORS['info'])
        html += _stat_card(act_type.title(), _fmt_number(count), "", icon, color)
    html += '</div>'

    # Dynamic activity breakdown (JS-filtered)
    html += f'''<div class="glass-card" style="margin-top:16px">
        <h3 class="card-title">Activity Breakdown <span style="font-size:11px;font-weight:400;color:{COLORS['text_muted']}">(filtered by period)</span></h3>
        <div id="dynamic-activity-breakdown"></div>
    </div>'''

    # Activity by type donut
    if by_type:
        type_segments = [(k.title(), v) for k, v in sorted(by_type.items(), key=lambda x: x[1], reverse=True)]
        html += f'''<div class="grid-2" style="margin-top:16px">
            <div class="glass-card">
                <h3 class="card-title">Activity Distribution</h3>
                {_svg_donut(type_segments, 260)}
            </div>'''
    else:
        html += '<div class="grid-2" style="margin-top:16px"><div></div>'

    # Activity trend
    daily_trend = activity.get("daily_trend", [])
    if daily_trend:
        trend_data = [(item.get("date", ""), item.get("count", 0)) for item in daily_trend]
        html += f'''<div class="glass-card">
            <h3 class="card-title">Daily Activity Trend</h3>
            {_svg_line_chart(trend_data[-60:], 500, 250, COLORS['accent2'])}
        </div>'''
    else:
        html += '<div></div>'
    html += '</div>'

    # Activity by rep
    by_rep = activity.get("by_rep", [])
    if by_rep:
        rows = []
        for rep in by_rep:
            rows.append([
                _esc(rep.get("owner_name", "Unknown")),
                _fmt_number(rep.get("calls", 0)),
                _fmt_number(rep.get("emails", 0)),
                _fmt_number(rep.get("meetings", 0)),
                _fmt_number(rep.get("tasks", 0)),
                _fmt_number(rep.get("notes", 0)),
                f'<strong>{_fmt_number(rep.get("total", 0))}</strong>',
            ])
        html += f'''<div class="glass-card" style="margin-top:16px">
            <h3 class="card-title">Activity by Rep</h3>
            {_data_table(["Rep", "Calls", "Emails", "Meetings", "Tasks", "Notes", "Total"],
                         rows, "activity_reps")}
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

    # KPIs
    html += '<div class="kpi-grid kpi-grid-3">'
    html += _stat_card("Total Contacts", _fmt_number(counts.get("contacts", 0)),
                       f"New 30d: {_fmt_number(contacts.get('new_contacts_30d', 0))}",
                       "\U0001F465", COLORS['accent'])
    html += _stat_card("Companies", _fmt_number(counts.get("companies", 0)),
                       "", "\U0001F3E2", COLORS['accent2'])
    html += _stat_card("Owners/Reps", _fmt_number(counts.get("owners", 0)),
                       "", "\U0001F464", COLORS['accent3'])
    html += '</div>'

    # Lifecycle distribution
    lifecycle = contacts.get("by_lifecycle", {})
    if lifecycle:
        lc_segments = sorted(lifecycle.items(), key=lambda x: x[1], reverse=True)
        html += f'''<div class="grid-2" style="margin-top:16px">
            <div class="glass-card">
                <h3 class="card-title">Lifecycle Distribution</h3>
                {_svg_donut(lc_segments, 260)}
            </div>
            <div class="glass-card">
                <h3 class="card-title">Lifecycle Breakdown</h3>'''
        max_lc = max(lifecycle.values()) if lifecycle else 1
        for stage, count in lc_segments:
            html += _svg_horizontal_bar(stage, count, max_lc, COLORS['accent2'], show_pct=False)
        html += '</div></div>'

    # Top engaged contacts
    engaged = contacts.get("top_engaged", [])
    if engaged:
        rows = []
        for c in engaged[:15]:
            rows.append([
                _esc(c.get("name", "")),
                _esc(c.get("email", "")),
                _fmt_number(c.get("page_views", 0)),
                _fmt_number(c.get("visits", 0)),
                _fmt_number(c.get("events", 0)),
            ])
        html += f'''<div class="glass-card" style="margin-top:16px">
            <h3 class="card-title">Top Engaged Contacts</h3>
            {_data_table(["Name", "Email", "Page Views", "Visits", "Events"],
                         rows, "top_engaged")}
        </div>'''

    # Companies summary
    companies = contacts.get("companies_summary", {})
    if companies:
        if isinstance(companies, dict):
            # Summary object format: {total, with_deals, by_industry, by_size}
            html += f'''<div class="glass-card" style="margin-top:16px">
                <h3 class="card-title">Companies Overview</h3>
                <div class="kpi-grid kpi-grid-3">'''
            html += _stat_card("Total", _fmt_number(companies.get("total", 0)), "", "", COLORS['accent2'])
            html += _stat_card("With Deals", _fmt_number(companies.get("with_deals", 0)), "", "", COLORS['accent3'])
            by_industry = companies.get("by_industry", {})
            if isinstance(by_industry, dict):
                top_industry = max(by_industry, key=by_industry.get, default="N/A") if by_industry else "N/A"
                html += _stat_card("Top Industry", _esc(str(top_industry)), "", "", COLORS['accent4'])
            html += '</div></div>'
        elif isinstance(companies, list):
            rows = []
            for co in companies[:20]:
                rows.append([
                    _esc(co.get("name", "")),
                    _esc(co.get("domain", "")),
                    _fmt_number(co.get("contacts", 0)),
                    _fmt_number(co.get("deals", 0)),
                    _fmt_currency(co.get("revenue", 0)),
                ])
            html += f'''<div class="glass-card" style="margin-top:16px">
                <h3 class="card-title">Companies Summary</h3>
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

    # Win/Loss analysis
    wl = insights.get("win_loss_analysis", {})
    if wl:
        html += f'''<div class="grid-2" style="margin-top:16px">
            <div class="glass-card">
                <h3 class="card-title">Win/Loss Analysis</h3>
                {_svg_donut([
                    ("Won", wl.get("won_count", 0)),
                    ("Lost", wl.get("lost_count", 0)),
                ], 200)}
                <div style="text-align:center;margin-top:8px;font-size:14px;
                    color:{COLORS['text']}">
                    Win Rate: <strong style="color:{COLORS['accent4']}">{_fmt_pct(wl.get("win_rate", 0))}</strong>
                </div>
            </div>'''

        # Lost reasons + Won reasons
        html += f'''<div class="glass-card">
                <h3 class="card-title">Win/Loss Reasons</h3>'''
        won_reasons = wl.get("won_reasons", {})
        lost_reasons = wl.get("lost_reasons", {})
        if won_reasons:
            html += f'<h4 style="font-size:12px;color:{COLORS["accent4"]};margin:8px 0 4px;text-transform:uppercase">Won Reasons</h4>'
            if isinstance(won_reasons, dict):
                for reason, count in sorted(won_reasons.items(), key=lambda x: x[1], reverse=True)[:5]:
                    html += f'''<div style="font-size:13px;padding:4px 0;color:{COLORS['text_muted']}">
                        {_esc(reason)}: <strong style="color:{COLORS['text']}">{_fmt_number(count)}</strong></div>'''
            elif isinstance(won_reasons, list):
                for item in won_reasons[:5]:
                    html += f'<div style="font-size:13px;padding:4px 0;color:{COLORS["text_muted"]}">{_esc(str(item))}</div>'
        if lost_reasons:
            html += f'<h4 style="font-size:12px;color:{COLORS["danger"]};margin:12px 0 4px;text-transform:uppercase">Lost Reasons</h4>'
            if isinstance(lost_reasons, dict):
                for reason, count in sorted(lost_reasons.items(), key=lambda x: x[1], reverse=True)[:5]:
                    html += f'''<div style="font-size:13px;padding:4px 0;color:{COLORS['text_muted']}">
                        {_esc(reason)}: <strong style="color:{COLORS['text']}">{_fmt_number(count)}</strong></div>'''
            elif isinstance(lost_reasons, list):
                for item in lost_reasons[:5]:
                    html += f'<div style="font-size:13px;padding:4px 0;color:{COLORS["text_muted"]}">{_esc(str(item))}</div>'
        html += '</div></div>'

    # Sales cycle trend
    cycle_trend = insights.get("sales_cycle_trend", [])
    if cycle_trend:
        trend_data = [(item.get("month", ""), item.get("avg_days", 0)) for item in cycle_trend]
        html += f'''<div class="glass-card" style="margin-top:16px">
            <h3 class="card-title">Sales Cycle Trend (Avg Days)</h3>
            {_svg_line_chart(trend_data, 700, 220, COLORS['accent3'])}
        </div>'''

    # Deal size distribution
    deal_sizes = insights.get("deal_size_distribution", [])
    if deal_sizes:
        size_data = [(item.get("range", ""), item.get("count", 0)) for item in deal_sizes]
        html += f'''<div class="glass-card" style="margin-top:16px">
            <h3 class="card-title">Deal Size Distribution</h3>
            {_svg_bar_chart(size_data, 600, max(200, len(size_data) * 45))}
        </div>'''

    # Rep performance leaderboard
    rep_perf = insights.get("rep_performance", [])
    if rep_perf:
        rows = []
        for i, rep in enumerate(sorted(rep_perf, key=lambda x: x.get("revenue", 0), reverse=True)):
            medal = ["\U0001F947", "\U0001F948", "\U0001F949"][i] if i < 3 else f"#{i+1}"
            rows.append([
                f"{medal} {_esc(rep.get('name', 'Unknown'))}",
                _fmt_number(rep.get("deals_won", 0)),
                _fmt_number(rep.get("deals_lost", 0)),
                _fmt_currency(rep.get("revenue", 0)),
                _fmt_pct(rep.get("win_rate", 0)),
                _fmt_currency(rep.get("avg_deal_size", 0)),
                _fmt_number(rep.get("avg_cycle_days", 0)),
            ])
        html += f'''<div class="glass-card" style="margin-top:16px">
            <h3 class="card-title">Rep Performance Leaderboard</h3>
            {_data_table(["Rep", "Won", "Lost", "Revenue", "Win Rate", "Avg Deal", "Avg Cycle"],
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
        html += f'''<div class="glass-card" style="margin-top:16px">
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
    flow_html = '<div class="glass-card" style="margin-bottom:16px;padding:16px 20px">'
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
    projects = ma.get("projects", [])
    # Remove dormant (5+ months no update)
    fresh_projects = [p for p in projects if not _is_dormant(p.get("updated_at", ""))]
    # Sort by most recently updated
    fresh_projects.sort(key=lambda p: p.get("updated_at") or "", reverse=True)
    active_list = [p for p in fresh_projects if p.get("is_active")]
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
    html += f'''<div class="glass-card" style="margin-top:16px;padding:12px 16px">
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

            html += f'''<div class="glass-card" style="margin-top:16px">
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

        html += f'''<div class="glass-card" style="margin-top:16px;padding:0;overflow:hidden">
            <div style="padding:16px 20px;border-bottom:1px solid {COLORS['card_border']}">
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

    # ── Stale Projects Warning (show 10 with expand) ──
    stale = ma.get("stale_projects", [])
    # Sort stale by days_stale desc
    stale.sort(key=lambda sp: sp.get("days_stale", 0), reverse=True)
    # Filter out stale items that are also dormant (5+ months)
    stale = [sp for sp in stale if sp.get("days_stale", 0) < DORMANCY_MONTHS * 30]
    if stale:
        STALE_LIMIT = 10
        stale_html = ""
        for i, sp in enumerate(stale):
            days = sp.get("days_stale", 0)
            urgency_color = MONDAY_RED if days > 21 else MONDAY_YELLOW
            hidden = ' style="display:none"' if i >= STALE_LIMIT else ''
            extra_cls = ' stale-extra-row' if i >= STALE_LIMIT else ''
            stale_html += f'''<div class="stale-item{extra_cls}" {hidden if i >= STALE_LIMIT else ''}>
                <div style="display:flex;justify-content:space-between;align-items:center;
                    padding:10px 12px;border-bottom:1px solid {COLORS['card_border']}">
                    <div>
                        <span style="font-size:13px;color:{COLORS['text']};font-weight:500">{_esc(sp.get("name", ""))}</span>
                        <span style="font-size:11px;color:{COLORS['text_muted']};margin-left:8px">{_esc(sp.get("stage", "").title())}</span>
                    </div>
                    <span style="font-size:12px;font-weight:600;color:{urgency_color}">{days}d stale</span>
                </div>
            </div>'''

        stale_more = ""
        if len(stale) > STALE_LIMIT:
            remaining = len(stale) - STALE_LIMIT
            stale_more = f'''<div style="text-align:center;padding:10px">
                <button id="stale-show-more" onclick="toggleExpandList('stale-extra-row','stale-show-more',{len(stale)},{STALE_LIMIT})"
                    style="background:none;border:1px solid {COLORS['card_border']};border-radius:8px;
                    padding:6px 20px;color:{COLORS['text_muted']};font-size:12px;font-weight:600;
                    cursor:pointer">Show all {len(stale)} ({remaining} more)</button>
            </div>'''

        html += f'''<div class="glass-card" style="margin-top:16px;border:1px solid {MONDAY_RED}44">
            <h3 class="card-title" style="color:{MONDAY_RED}">\u26A0\uFE0F Stale Projects ({len(stale)})</h3>
            <p style="font-size:12px;color:{COLORS['text_muted']};margin-bottom:8px">No updates in 14+ days (dormant 5mo+ hidden)</p>
            {stale_html}
            {stale_more}
        </div>'''

    # ── Owner Summary (show 10 with expand) ──
    owner_summary = ma.get("owner_summary", [])
    if owner_summary:
        OWNER_LIMIT = 10
        rows = []
        for o in owner_summary[:OWNER_LIMIT]:
            rows.append([
                _esc(o.get("owner", "Unknown")),
                _fmt_number(o.get("total_deals", 0)),
                _fmt_number(o.get("active_deals", 0)),
                _fmt_currency(o.get("total_value", 0)),
            ])
        html += f'''<div class="glass-card" style="margin-top:16px">
            <h3 class="card-title">\U0001F465 M&A by Owner
                <span style="font-size:12px;font-weight:400;color:{COLORS['text_muted']}">
                    (showing {min(OWNER_LIMIT, len(owner_summary))} of {len(owner_summary)})
                </span>
            </h3>
            {_data_table(["Owner", "Total Deals", "Active", "Total Value"], rows, "ma_owners")}
        </div>'''

    # ── Stage Distribution chart ──
    stage_dist = ma.get("stage_distribution", {})
    if stage_dist:
        stage_data = [(k.replace("_", " ").title(), v) for k, v in
                      sorted(stage_dist.items(), key=lambda x: x[1], reverse=True)]
        html += f'''<div class="glass-card" style="margin-top:16px">
            <h3 class="card-title">\U0001F4CA Stage Distribution</h3>
            {_svg_bar_chart(stage_data, 650, max(200, len(stage_data) * 44))}
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
    ic_flow_html = f'<div class="glass-card" style="margin-bottom:16px;padding:16px 20px">'
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
        board_html += f'''<div class="board-header-row" style="grid-template-columns:2fr 70px 70px 110px 1fr 90px 20px">
            <div>Project</div>
            <div>Total</div>
            <div>Avg</div>
            <div>Status</div>
            <div>Gate Scores</div>
            <div>Owner</div>
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
                f'style="grid-template-columns:2fr 70px 70px 110px 1fr 90px 20px'
                f'{";display:none" if idx >= IC_LIMIT else ""}">'
                f'<div style="font-weight:500;color:{COLORS["text"]}">{name}</div>'
                f'<div>{bar_html}</div>'
                f'<div style="font-size:12px;color:{COLORS["text_muted"]}">{avg:.1f}</div>'
                f'<div>{_monday_stage_badge(status) if status else "<span style=\'color:#64748b\'>—</span>"}</div>'
                f'<div style="display:flex;flex-wrap:wrap;gap:2px">{gate_html}</div>'
                f'<div style="font-size:11px;color:{COLORS["text_muted"]}">{owner}</div>'
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

        html += f'''<div class="glass-card" style="margin-top:12px;padding:0;overflow:hidden;border-top:3px solid {MONDAY_PURPLE}">
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
            html += f'''<div class="glass-card" style="margin-top:16px">
                <h3 class="card-title">\U0001F4CA IC Score by Category (Averages)</h3>
                {_svg_bar_chart(cat_data, 650, max(200, len(cat_data) * 44), MONDAY_PURPLE)}
            </div>'''

    # ── Charts row: Trend + Decision Distribution ──
    score_trend = ic.get("score_trend", {})
    if score_trend or decisions:
        html += '<div class="grid-2" style="margin-top:16px">'
        if score_trend:
            trend_data = [(month, stats.get("avg_score", 0))
                          for month, stats in sorted(score_trend.items())]
            if trend_data:
                html += f'''<div class="glass-card">
                    <h3 class="card-title">\U0001F4C8 IC Score Trend (Monthly Avg)</h3>
                    {_svg_line_chart(trend_data, 700, 220, MONDAY_PURPLE)}
                </div>'''
        if decisions:
            decision_data = [(k, v) for k, v in sorted(decisions.items(),
                                                        key=lambda x: x[1], reverse=True)]
            html += f'''<div class="glass-card">
                <h3 class="card-title">\U0001F3DB\uFE0F IC Decision Distribution</h3>
                {_svg_donut(decision_data, 240)}
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

        html += f'''<div class="glass-card" style="margin-top:16px;padding:0;overflow:hidden">
            <div style="padding:16px 20px;border-bottom:1px solid {COLORS['card_border']}">
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
            --radius:      14px;
            --radius-sm:   8px;
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
            padding: 14px 20px;
        }}

        /* ============================================================
           Sections
           ============================================================ */
        .dashboard-section {{
            margin-bottom: 20px;
        }}

        @keyframes fade-in-up {{
            to {{ opacity: 1; transform: translateY(0); }}
        }}

        .section-header {{
            margin-bottom: 12px;
            padding-bottom: 8px;
            border-bottom: 1px solid var(--card-border);
        }}
        .section-title {{
            font-size: 18px;
            font-weight: 800;
            color: var(--text);
            letter-spacing: -0.02em;
        }}
        .section-subtitle {{
            font-size: 12px;
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
            padding: 14px 16px;
            box-shadow: var(--shadow);
            transition: var(--transition);
        }}
        .glass-card:hover {{
            border-color: rgba(60, 180, 173, 0.25);
            box-shadow: var(--shadow-lg);
        }}
        .card-title {{
            font-size: 13px;
            font-weight: 700;
            color: var(--text);
            margin-bottom: 10px;
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
            gap: 10px;
            margin-bottom: 10px;
        }}
        .kpi-grid-3 {{
            grid-template-columns: repeat(3, 1fr);
        }}
        .stat-card {{
            background: var(--card);
            border: 1px solid var(--card-border);
            border-radius: var(--radius-sm);
            padding: 12px 14px;
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
            gap: 16px;
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
            padding: 16px 0;
        }}
        .chain-item {{
            text-align: center;
            padding: 16px 20px;
            border: 2px solid var(--card-border);
            border-radius: var(--radius);
            background: var(--surface2);
            min-width: 100px;
            transition: var(--transition);
        }}
        .chain-item:hover {{
            transform: scale(1.05);
            box-shadow: 0 4px 16px rgba(60, 180, 173, 0.12);
        }}
        .chain-value {{
            font-size: 24px;
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
            font-size: 11px;
            padding: 12px 14px;
            text-align: left;
            border-bottom: 2px solid var(--card-border);
            white-space: nowrap;
        }}
        .data-table td {{
            padding: 10px 14px;
            border-bottom: 1px solid var(--card-border);
            color: var(--text);
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
            padding: 16px 20px;
            color: var(--text-muted);
            font-size: 11px;
            border-top: 1px solid var(--card-border);
            margin-top: 20px;
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
           Print
           ============================================================ */
        @media print {{
            body {{ background: white; color: #1a1a1a; display: block; }}
            .sidebar {{ display: none; }}
            .sidebar-toggle {{ display: none; }}
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
            padding: 16px 0;
            margin-bottom: 16px;
            scrollbar-width: thin;
        }}
        .deal-flow-step {{
            display: flex;
            align-items: center;
            gap: 0;
            white-space: nowrap;
        }}
        .deal-flow-step .step-dot {{
            width: 28px;
            height: 28px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 11px;
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
            gap: 10px;
            padding: 10px 16px;
            cursor: pointer;
            transition: background 0.15s ease;
            user-select: none;
            background: var(--surface2);
        }}
        .board-group-header:hover {{
            background: #eef0f3;
        }}
        .board-group-header .group-color {{
            width: 6px;
            height: 32px;
            border-radius: 3px;
            flex-shrink: 0;
        }}
        .board-group-header .group-title {{
            font-size: 14px;
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
            padding: 8px 16px 8px 32px;
            border-bottom: 1px solid var(--card-border);
            font-size: 13px;
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
            padding: 6px 16px 6px 32px;
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
        // Page-based SPA navigation
        // ------------------------------------------------------------------
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
        };

        // Show first page on load
        document.addEventListener('DOMContentLoaded', function() {
            showPage('executive');
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


# ---------------------------------------------------------------------------
# Main assembly
# ---------------------------------------------------------------------------

def _build_sidebar() -> str:
    """Build the fixed left-hand navy sidebar with grouped sections and page switching."""
    nav_groups = [
        {
            "label": "Overview",
            "icon": "&#9679;",
            "items": [("executive", "Executive Summary")],
        },
        {
            "label": "Sales",
            "icon": "&#9733;",
            "items": [
                ("leads", "Leads & Sources"),
                ("funnel", "Qualified Leads"),
                ("pipeline", "Pipeline View"),
            ],
        },
        {
            "label": "Planning",
            "icon": "&#9881;",
            "items": [("targets", "Targets & Rev Eng")],
        },
        {
            "label": "Activity",
            "icon": "&#9993;",
            "items": [
                ("activities", "Activity Tracking"),
                ("contacts", "Contacts & Co."),
            ],
        },
        {
            "label": "Intelligence",
            "icon": "&#10024;",
            "items": [("insights", "Insights & Forecast")],
        },
        {
            "label": "M&A",
            "icon": "&#128188;",
            "items": [
                ("monday-pipeline", "M&A Pipeline"),
                ("monday-ic", "IC Scorecards"),
                ("monday-workspaces", "Workspaces"),
            ],
        },
        {
            "label": "AI",
            "icon": "&#129302;",
            "items": [("ai-roadmap", "AI Roadmap")],
        },
    ]
    groups_html = ''
    for g in nav_groups:
        items_html = ''.join(
            f'<a href="javascript:void(0)" onclick="showPage(\'{sid}\')" '
            f'class="sidebar-link" data-page="{sid}">{lbl}</a>'
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
        <nav class="sidebar-nav">
            {groups_html}
        </nav>
        <div class="sidebar-footer">
            Sales &amp; M&amp;A &amp; AI Intelligence
        </div>
    </aside>
    <button class="sidebar-toggle" id="sidebar-toggle" onclick="toggleSidebar()" aria-label="Toggle menu">
        <span></span><span></span><span></span>
    </button>'''


def generate_dashboard(data: dict) -> str:
    """Generate the complete HTML dashboard from metrics data."""
    _normalize_metrics(data)
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

    section_builders = [
        ("Executive Summary", _build_executive_summary),
        ("Leads & Sources", _build_leads_section),
        ("Qualified Leads & Funnel", _build_funnel_section),
        ("Target Setting", _build_target_section),
        ("Pipeline View", _build_pipeline_section),
        ("Activity Tracking", _build_activity_section),
        ("Contacts & Companies", _build_contacts_section),
        ("Insights & Forecast", _build_insights_section),
        ("M&A Pipeline", _build_monday_pipeline),
        ("IC Scorecards", _build_monday_ic),
        ("Workspaces", _build_monday_workspaces),
        ("AI Roadmap", _build_ai_section),
    ]
    page_ids = ["executive", "leads", "funnel", "targets", "pipeline",
                "activities", "contacts", "insights",
                "monday-pipeline", "monday-ic", "monday-workspaces",
                "ai-roadmap"]

    sections = []
    for i, (name, builder) in enumerate(section_builders):
        page_id = page_ids[i] if i < len(page_ids) else f"page-{i}"
        try:
            content = builder(data)
            sections.append(f'<div class="dash-page" id="page-{page_id}">{content}</div>')
        except Exception as e:
            logger.warning(f"Section '{name}' failed: {e}")
            sections.append(f'<div class="dash-page" id="page-{page_id}"><section class="dashboard-section"><div class="glass-card" style="padding:40px;text-align:center;color:{COLORS["text_muted"]}"><h3>{_esc(name)}</h3><p>Data unavailable — {_esc(str(e))}</p></div></section></div>')

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
                html += '<div style="margin-bottom:8px">'
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
            var w = 200, h = 48, pad = 2;
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

            // Leads over time sparkline
            var leadsMonthly = filterDailyToMonthly(TS.leads_by_day, range);
            renderSparkline('dynamic-leads-sparkline', leadsMonthly, '#3CB4AD');

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
            renderSparkline('dynamic-activity-sparkline', actDaily, '#a78bfa');

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
            renderSparkline('dynamic-revenue-sparkline', revMonthly, '#34d399');

            // Deals created sparkline
            var dealsMonthly = filterDailyToMonthly(TS.deals_created_by_day, range);
            renderSparkline('dynamic-deals-sparkline', dealsMonthly, '#38bdf8');
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
    {_build_sidebar()}
    <div class="sidebar-overlay" id="sidebar-overlay" onclick="toggleSidebar()"></div>

    <div class="layout-main" id="layout-main">
        {filter_bar}
        <main class="main-content">
            {''.join(sections)}
        </main>

        <footer class="dashboard-footer">
            <p><span class="brand">eComplete</span> &mdash; Sales &amp; M&amp;A Intelligence Dashboard</p>
            <p style="margin-top:4px">{footer_stats}</p>
            <p style="margin-top:4px">Generated: {timestamp}</p>
        </footer>
    </div>

    {_build_js()}
    {filter_js}
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
