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
    "bg":           "#0f172a",
    "card":         "#1e293b",
    "card_border":  "#334155",
    "text":         "#e2e8f0",
    "text_muted":   "#94a3b8",
    "accent":       "#fb923c",       # HubSpot orange
    "accent2":      "#38bdf8",       # sky-400
    "accent3":      "#a78bfa",       # violet-400
    "accent4":      "#34d399",       # emerald-400
    "accent5":      "#f472b6",       # pink-400
    "accent6":      "#facc15",       # yellow-400
    "success":      "#22c55e",
    "danger":       "#ef4444",
    "warning":      "#f59e0b",
    "info":         "#3b82f6",
    "surface":      "#1e293b",
    "surface2":     "#0f1729",
}

CHART_PALETTE = [
    "#fb923c", "#38bdf8", "#a78bfa", "#34d399", "#f472b6",
    "#facc15", "#60a5fa", "#f87171", "#2dd4bf", "#c084fc",
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
    color: str = "#fb923c",
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
    color: str = "#fb923c",
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
    color: str = "#fb923c",
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
    color: str = "#fb923c",
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
        icon_html = f'''<div style="width:42px;height:42px;border-radius:12px;
            background:linear-gradient(135deg,{color}22,{color}11);
            display:flex;align-items:center;justify-content:center;
            font-size:18px;flex-shrink:0;margin-bottom:8px;
            border:1px solid {color}33">{icon}</div>'''

    return f'''<div class="stat-card" style="--accent:{color}">
        {icon_html}
        <div style="font-size:12px;color:{COLORS['text_muted']};text-transform:uppercase;
                    letter-spacing:0.05em;margin-bottom:4px">{_esc(title)}</div>
        <div style="font-size:28px;font-weight:800;color:{COLORS['text']};
                    line-height:1.1;margin-bottom:2px">{_esc(value)}</div>
        <div style="font-size:12px;color:{COLORS['text_muted']}">{_esc(subtitle)}</div>
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
    color: str = "#fb923c",
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
# CSS stylesheet
# ---------------------------------------------------------------------------

def _build_css() -> str:
    """Build the complete CSS for the dashboard."""
    return f'''
    <style>
        /* ============================================================
           CSS Custom Properties
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
            --shadow:      0 4px 24px rgba(0,0,0,0.3);
            --shadow-lg:   0 8px 40px rgba(0,0,0,0.45);
            --transition:  all 0.3s cubic-bezier(.25,.1,.25,1);
        }}

        /* ============================================================
           Reset & Base
           ============================================================ */
        *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
        html {{ scroll-behavior: smooth; scroll-padding-top: 120px; }}
        body {{
            background: var(--bg);
            color: var(--text);
            font-family: 'Inter', 'Segoe UI', system-ui, -apple-system, sans-serif;
            line-height: 1.6;
            min-height: 100vh;
            -webkit-font-smoothing: antialiased;
            overflow-x: hidden;
        }}

        /* Scrollbar styling */
        ::-webkit-scrollbar {{ width: 8px; height: 8px; }}
        ::-webkit-scrollbar-track {{ background: var(--bg); }}
        ::-webkit-scrollbar-thumb {{ background: var(--card-border); border-radius: 4px; }}
        ::-webkit-scrollbar-thumb:hover {{ background: var(--text-muted); }}

        /* ============================================================
           Top Navigation
           ============================================================ */
        .top-nav {{
            position: sticky;
            top: 0;
            z-index: 100;
            background: rgba(15, 23, 42, 0.85);
            backdrop-filter: blur(20px) saturate(180%);
            -webkit-backdrop-filter: blur(20px) saturate(180%);
            border-bottom: 1px solid var(--card-border);
            padding: 0 24px;
            transition: var(--transition);
        }}
        .nav-inner {{
            max-width: 1400px;
            margin: 0 auto;
            display: flex;
            align-items: center;
            height: 60px;
            gap: 8px;
        }}
        .nav-brand {{
            font-weight: 800;
            font-size: 16px;
            color: var(--accent);
            margin-right: 24px;
            white-space: nowrap;
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        .nav-brand .brand-dot {{
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: var(--accent);
            box-shadow: 0 0 8px var(--accent), 0 0 20px rgba(251,146,60,0.3);
            animation: pulse-glow 2s ease-in-out infinite;
        }}
        @keyframes pulse-glow {{
            0%, 100% {{ opacity: 1; transform: scale(1); }}
            50% {{ opacity: 0.7; transform: scale(1.2); }}
        }}
        .nav-links {{
            display: flex;
            align-items: center;
            gap: 2px;
            overflow-x: auto;
            scrollbar-width: none;
            -ms-overflow-style: none;
            flex: 1;
        }}
        .nav-links::-webkit-scrollbar {{ display: none; }}
        .nav-link {{
            padding: 8px 14px;
            font-size: 12px;
            font-weight: 500;
            color: var(--text-muted);
            text-decoration: none;
            border-radius: var(--radius-sm);
            white-space: nowrap;
            transition: var(--transition);
            position: relative;
        }}
        .nav-link:hover {{
            color: var(--text);
            background: rgba(255,255,255,0.05);
        }}
        .nav-link.active {{
            color: var(--accent);
            background: rgba(251,146,60,0.1);
        }}
        .nav-link.active::after {{
            content: '';
            position: absolute;
            bottom: -1px;
            left: 14px;
            right: 14px;
            height: 2px;
            background: var(--accent);
            border-radius: 2px;
        }}

        /* ============================================================
           Layout
           ============================================================ */
        .main-content {{
            max-width: 1400px;
            margin: 0 auto;
            padding: 24px;
        }}

        /* ============================================================
           Sections
           ============================================================ */
        .dashboard-section {{
            margin-bottom: 48px;
            opacity: 0;
            transform: translateY(20px);
            animation: fade-in-up 0.6s ease-out forwards;
        }}
        .dashboard-section:nth-child(1) {{ animation-delay: 0.1s; }}
        .dashboard-section:nth-child(2) {{ animation-delay: 0.15s; }}
        .dashboard-section:nth-child(3) {{ animation-delay: 0.2s; }}
        .dashboard-section:nth-child(4) {{ animation-delay: 0.25s; }}
        .dashboard-section:nth-child(5) {{ animation-delay: 0.3s; }}
        .dashboard-section:nth-child(6) {{ animation-delay: 0.35s; }}
        .dashboard-section:nth-child(7) {{ animation-delay: 0.4s; }}
        .dashboard-section:nth-child(8) {{ animation-delay: 0.45s; }}

        @keyframes fade-in-up {{
            to {{ opacity: 1; transform: translateY(0); }}
        }}

        .section-header {{
            margin-bottom: 20px;
            padding-bottom: 12px;
            border-bottom: 1px solid var(--card-border);
        }}
        .section-title {{
            font-size: 22px;
            font-weight: 800;
            color: var(--text);
            letter-spacing: -0.02em;
        }}
        .section-subtitle {{
            font-size: 13px;
            color: var(--text-muted);
            margin-top: 2px;
        }}

        /* ============================================================
           Glassmorphism Cards
           ============================================================ */
        .glass-card {{
            background: linear-gradient(135deg,
                rgba(30, 41, 59, 0.8) 0%,
                rgba(30, 41, 59, 0.5) 100%);
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
            border: 1px solid rgba(51, 65, 85, 0.6);
            border-radius: var(--radius);
            padding: 24px;
            box-shadow: var(--shadow);
            transition: var(--transition);
        }}
        .glass-card:hover {{
            border-color: rgba(251,146,60,0.2);
            box-shadow: var(--shadow-lg), 0 0 30px rgba(251,146,60,0.05);
            transform: translateY(-2px);
        }}
        .card-title {{
            font-size: 14px;
            font-weight: 700;
            color: var(--text);
            margin-bottom: 16px;
            text-transform: uppercase;
            letter-spacing: 0.04em;
        }}
        .alert-card {{
            border-left: 3px solid var(--warning);
        }}

        /* ============================================================
           Stat Cards (KPI)
           ============================================================ */
        .kpi-grid {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 16px;
            margin-bottom: 16px;
        }}
        .kpi-grid-3 {{
            grid-template-columns: repeat(3, 1fr);
        }}
        .stat-card {{
            background: linear-gradient(135deg,
                rgba(30, 41, 59, 0.9) 0%,
                rgba(15, 23, 42, 0.7) 100%);
            border: 1px solid var(--card-border);
            border-radius: var(--radius);
            padding: 20px;
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
            border-color: rgba(251,146,60,0.3);
            transform: translateY(-3px);
            box-shadow: 0 8px 30px rgba(0,0,0,0.3), 0 0 20px rgba(251,146,60,0.06);
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
            background: rgba(15,23,42,0.5);
            min-width: 100px;
            transition: var(--transition);
        }}
        .chain-item:hover {{
            transform: scale(1.05);
            box-shadow: 0 0 20px rgba(251,146,60,0.1);
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
            background: rgba(15,23,42,0.6);
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
            border-bottom: 1px solid rgba(51,65,85,0.3);
            color: var(--text);
        }}
        .data-table tbody tr {{
            transition: background 0.15s ease;
        }}
        .data-table tbody tr:hover {{
            background: rgba(251,146,60,0.04);
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
            padding: 32px 24px;
            color: var(--text-muted);
            font-size: 12px;
            border-top: 1px solid var(--card-border);
            margin-top: 48px;
        }}
        .dashboard-footer .brand {{
            color: var(--accent);
            font-weight: 700;
        }}

        /* ============================================================
           Responsive
           ============================================================ */
        @media (max-width: 1024px) {{
            .kpi-grid {{ grid-template-columns: repeat(2, 1fr); }}
            .kpi-grid-3 {{ grid-template-columns: repeat(2, 1fr); }}
            .grid-2 {{ grid-template-columns: 1fr; }}
            .volume-chain {{ gap: 8px; }}
            .chain-item {{ min-width: 80px; padding: 12px; }}
            .chain-value {{ font-size: 18px; }}
        }}
        @media (max-width: 640px) {{
            .kpi-grid {{ grid-template-columns: 1fr; }}
            .kpi-grid-3 {{ grid-template-columns: 1fr; }}
            .nav-brand {{ font-size: 14px; margin-right: 12px; }}
            .nav-link {{ font-size: 11px; padding: 6px 10px; }}
            .main-content {{ padding: 16px; }}
            .glass-card {{ padding: 16px; }}
            .stat-card {{ padding: 14px; }}
            .section-title {{ font-size: 18px; }}
            .volume-chain {{ flex-direction: column; }}
            .chain-arrow {{ transform: rotate(90deg); }}
        }}

        /* ============================================================
           Filter Bar
           ============================================================ */
        .filter-bar {{
            position: sticky;
            top: 60px;
            z-index: 99;
            background: rgba(15, 23, 42, 0.88);
            backdrop-filter: blur(20px) saturate(180%);
            -webkit-backdrop-filter: blur(20px) saturate(180%);
            border-bottom: 1px solid rgba(51, 65, 85, 0.4);
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
            background: rgba(30, 41, 59, 0.6);
            border: 1px solid rgba(51, 65, 85, 0.5);
            border-radius: 20px;
            cursor: pointer;
            transition: all 0.25s cubic-bezier(.25,.1,.25,1);
            white-space: nowrap;
            font-family: inherit;
        }}
        .filter-btn:hover {{
            color: var(--text);
            background: rgba(51, 65, 85, 0.5);
            border-color: rgba(148, 163, 184, 0.3);
        }}
        .filter-btn.active {{
            color: #fff;
            background: linear-gradient(135deg, var(--accent), #ea580c);
            border-color: var(--accent);
            box-shadow: 0 2px 12px rgba(251, 146, 60, 0.3);
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
            color: #22c55e;
            background: rgba(34, 197, 94, 0.12);
        }}
        .yoy-badge.down {{
            color: #ef4444;
            background: rgba(239, 68, 68, 0.12);
        }}
        .yoy-badge.neutral {{
            color: var(--text-muted);
            background: rgba(148, 163, 184, 0.12);
        }}
        @media (max-width: 640px) {{
            .filter-bar {{ padding: 8px 16px; top: 56px; }}
            .filter-btn {{ padding: 5px 12px; font-size: 11px; }}
            .filter-period-label {{ display: none; }}
        }}

        /* ============================================================
           Print
           ============================================================ */
        @media print {{
            body {{ background: white; color: #1a1a1a; }}
            .top-nav {{ position: static; background: white; border-bottom: 2px solid #ccc; }}
            .glass-card, .stat-card {{
                background: white;
                border: 1px solid #ddd;
                box-shadow: none;
                break-inside: avoid;
            }}
            .nav-link.active {{ color: #d97706; }}
            .dashboard-section {{ opacity: 1; transform: none; animation: none; }}
            .data-table th {{ background: #f5f5f5; color: #333; }}
            .data-table td {{ color: #333; }}
            .section-title {{ color: #1a1a1a; }}
            .section-subtitle, .card-title {{ color: #666; }}
        }}
    </style>'''


# ---------------------------------------------------------------------------
# JavaScript
# ---------------------------------------------------------------------------

def _build_js() -> str:
    """Build the interactive JavaScript."""
    return '''
    <script>
    (function() {
        'use strict';

        // ------------------------------------------------------------------
        // Intersection Observer for nav highlighting
        // ------------------------------------------------------------------
        const sections = document.querySelectorAll('.dashboard-section');
        const navLinks = document.querySelectorAll('.nav-link');

        const observerOpts = {
            root: null,
            rootMargin: '-80px 0px -60% 0px',
            threshold: 0
        };

        const observer = new IntersectionObserver(function(entries) {
            entries.forEach(function(entry) {
                if (entry.isIntersecting) {
                    const id = entry.target.id;
                    navLinks.forEach(function(link) {
                        link.classList.toggle('active',
                            link.getAttribute('href') === '#' + id);
                    });
                }
            });
        }, observerOpts);

        sections.forEach(function(sec) { observer.observe(sec); });

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

        // ------------------------------------------------------------------
        // Smooth scroll for nav links
        // ------------------------------------------------------------------
        navLinks.forEach(function(link) {
            link.addEventListener('click', function(e) {
                e.preventDefault();
                var target = document.querySelector(this.getAttribute('href'));
                if (target) {
                    target.scrollIntoView({ behavior: 'smooth', block: 'start' });
                }
            });
        });

        // ------------------------------------------------------------------
        // Animate elements on scroll (fade-in)
        // ------------------------------------------------------------------
        var animateObserver = new IntersectionObserver(function(entries) {
            entries.forEach(function(entry) {
                if (entry.isIntersecting) {
                    entry.target.style.opacity = '1';
                    entry.target.style.transform = 'translateY(0)';
                }
            });
        }, { threshold: 0.05 });

        document.querySelectorAll('.glass-card, .stat-card').forEach(function(el) {
            animateObserver.observe(el);
        });

    })();
    </script>'''


# ---------------------------------------------------------------------------
# Main assembly
# ---------------------------------------------------------------------------

def _build_nav() -> str:
    """Build the sticky top navigation."""
    nav_items = [
        ("executive", "Executive"),
        ("leads", "Leads"),
        ("funnel", "Funnel"),
        ("targets", "Targets"),
        ("pipeline", "Pipeline"),
        ("activities", "Activities"),
        ("contacts", "Contacts"),
        ("insights", "Insights"),
    ]
    links = ''.join(
        f'<a href="#{sid}" class="nav-link">{label}</a>'
        for sid, label in nav_items
    )
    return f'''<nav class="top-nav">
        <div class="nav-inner">
            <div class="nav-brand">
                <span class="brand-dot"></span> Annas AI Hub
            </div>
            <div class="nav-links">{links}</div>
        </div>
    </nav>'''


def generate_dashboard(data: dict) -> str:
    """Generate the complete HTML dashboard from metrics data."""
    _normalize_metrics(data)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    section_builders = [
        ("Executive Summary", _build_executive_summary),
        ("Leads & Sources", _build_leads_section),
        ("Qualified Leads & Funnel", _build_funnel_section),
        ("Target Setting", _build_target_section),
        ("Pipeline View", _build_pipeline_section),
        ("Activity Tracking", _build_activity_section),
        ("Contacts & Companies", _build_contacts_section),
        ("Insights & Forecast", _build_insights_section),
    ]
    sections = []
    for name, builder in section_builders:
        try:
            sections.append(builder(data))
        except Exception as e:
            logger.warning(f"Section '{name}' failed: {e}")
            sections.append(f'<section class="dashboard-section"><div class="glass-card" style="padding:40px;text-align:center;color:{COLORS["text_muted"]}"><h3>{_esc(name)}</h3><p>Data unavailable — {_esc(str(e))}</p></div></section>')

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
            if (sorted.length === 0) {{ el.innerHTML = '<div style="text-align:center;padding:20px;color:#94a3b8;font-size:13px">No data for this period</div>'; return; }}
            var maxVal = sorted[0][1] || 1;
            var palette = ['#fb923c','#38bdf8','#a78bfa','#34d399','#f472b6','#facc15','#60a5fa','#f87171'];
            var html = '';
            sorted.forEach(function(item, i) {{
                var label = item[0].length > 20 ? item[0].substring(0, 18) + '..' : item[0];
                var val = item[1];
                var pct = Math.max(2, (val / maxVal) * 100);
                var color = palette[i % palette.length];
                html += '<div style="margin-bottom:8px">'
                    + '<div style="display:flex;justify-content:space-between;margin-bottom:3px;font-size:12px">'
                    + '<span style="color:#94a3b8">' + label + '</span>'
                    + '<span style="color:#e2e8f0;font-weight:600">' + fmtNum(val) + '</span></div>'
                    + '<div style="height:6px;background:#334155;border-radius:3px;overflow:hidden">'
                    + '<div style="height:100%;width:' + pct.toFixed(1) + '%;background:' + color + ';border-radius:3px;'
                    + 'transition:width 0.6s cubic-bezier(.25,.1,.25,1)"></div></div></div>';
            }});
            el.innerHTML = html;
        }}

        function renderSparkline(containerId, data, color) {{
            var el = document.getElementById(containerId);
            if (!el) return;
            color = color || '#fb923c';
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
            var showYoY = (period === 'ytd' || period === 'all');

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
                var valueEl = card.querySelector('div[style*="font-size:28px"]');
                if (!valueEl) return;

                var yoyHtml = '';
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
            renderSparkline('dynamic-leads-sparkline', leadsMonthly, '#fb923c');

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
    <title>Annas AI Hub &mdash; HubSpot Sales Dashboard</title>
    <meta name="description" content="HubSpot CRM Sales Dashboard - Generated by Annas AI Hub">
    {_build_css()}
</head>
<body>
    {_build_nav()}
    {filter_bar}

    <main class="main-content">
        {''.join(sections)}
    </main>

    <footer class="dashboard-footer">
        <p><span class="brand">Annas AI Hub</span> &mdash; HubSpot Sales Dashboard v2</p>
        <p style="margin-top:4px">{footer_stats}</p>
        <p style="margin-top:4px">Generated: {timestamp}</p>
    </footer>

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
