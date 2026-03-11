"""Generate dashboard/frontend/js/monday-data.js from processed Monday metrics."""
import json
from collections import Counter
from pathlib import Path
from datetime import datetime, timezone

PROJECT_ROOT = Path(__file__).resolve().parent.parent
METRICS_PATH = PROJECT_ROOT / "data" / "processed" / "monday_metrics.json"
OUTPUT_PATH = PROJECT_ROOT / "dashboard" / "frontend" / "js" / "monday-data.js"
PRIMARY_BOARD = "1674745475"


def main():
    with open(METRICS_PATH, encoding="utf-8") as f:
        raw = json.load(f)

    ma = raw.get("ma_metrics", {})
    ic = raw.get("ic_metrics", {})
    overview = raw.get("board_overview", {})

    # Filter to primary board
    board_projects = [p for p in ma.get("projects", []) if str(p.get("board_id")) == PRIMARY_BOARD]
    ic_items = [i for i in ic.get("items", []) if str(i.get("board_id")) == PRIMARY_BOARD]

    # Build IC lookup by item ID for column merge
    ic_lookup = {}
    for item in ic_items:
        ic_lookup[str(item.get("id", ""))] = item

    # Merge IC columns + subitems into project records
    for proj in board_projects:
        ic_match = ic_lookup.get(str(proj.get("id", "")), {})
        proj["columns"] = ic_match.get("columns", {})
        proj["subitems"] = ic_match.get("subitems", [])
        proj["scores"] = ic_match.get("scores", {})
        proj["total_score"] = ic_match.get("total_score", 0)
        proj["avg_score"] = ic_match.get("avg_score", 0)

    # Pre-aggregate status counts for KPIs
    status_counts = Counter()
    for p in board_projects:
        s = (p.get("status") or "").strip()
        if s:
            status_counts[s] += 1

    # Pre-aggregate items by creation month
    items_by_month = Counter()
    for p in board_projects:
        ca = p.get("created_at", "")
        if ca and len(ca) >= 7:
            items_by_month[ca[:7]] += 1

    # Board metadata from overview
    board_meta = {}
    for ws in overview.get("workspaces", []):
        for b in ws.get("boards", []):
            if str(b.get("id")) == PRIMARY_BOARD:
                board_meta = {**b, "workspace": ws.get("name", "")}
                break

    payload = {
        "generated_at": raw.get("generated_at", datetime.now(timezone.utc).isoformat()),
        "board": board_meta,
        "projects": board_projects,
        "ic_items": ic_items,
        "status_counts": dict(status_counts),
        "items_by_month": dict(sorted(items_by_month.items())),
        "owner_summary": ma.get("owner_summary", []),
    }

    js = "/* Monday.com data — generated {} */\nwindow.MONDAY = {};\n".format(
        datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        json.dumps(payload, default=str, ensure_ascii=False),
    )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(js)

    merged = sum(1 for p in board_projects if p.get("columns"))
    print(f"Generated {OUTPUT_PATH.relative_to(PROJECT_ROOT)} — {len(board_projects)} projects ({merged} with IC columns), {len(ic_items)} IC items")


if __name__ == "__main__":
    main()
