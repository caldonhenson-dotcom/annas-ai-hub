"""Generate dashboard/frontend/js/monday-data.js from processed Monday metrics."""
import json
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

    # Filter projects to the primary board
    board_projects = [p for p in ma.get("projects", []) if str(p.get("board_id")) == PRIMARY_BOARD]
    ic_items = [i for i in ic.get("items", []) if str(i.get("board_id")) == PRIMARY_BOARD]

    # Find board metadata from overview
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
        "owner_summary": ma.get("owner_summary", []),
        "funnel": ma.get("funnel", []),
    }

    js = "/* Monday.com data — generated {} */\nwindow.MONDAY = {};\n".format(
        datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        json.dumps(payload, default=str, ensure_ascii=False),
    )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(js)

    print(f"Generated {OUTPUT_PATH.relative_to(PROJECT_ROOT)} — {len(board_projects)} projects, {len(ic_items)} IC items")


if __name__ == "__main__":
    main()
