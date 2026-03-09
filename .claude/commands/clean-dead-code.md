---
description: Dead code analysis — find unused files, functions, and CSS
user-invocable: true
---

Run dead code analysis on this Vanilla JS + Python project:

## Frontend (dashboard/frontend/)

1. **Unused JS files**: Cross-reference `js/router.js` PAGE_SCRIPTS map against all files in `js/pages/` and `js/`. Any JS file not imported by `index.html` or referenced in PAGE_SCRIPTS is potentially dead.
2. **Unused CSS classes**: Grep all `pl-*` and custom classes defined in `css/pipeline.css` and `css/tokens.css`. Check if each class is actually used in any HTML page or JS renderer.
3. **Unused functions**: Search for functions defined on `window` (e.g., `window.renderXxx`, `window.UI.*`) and check if they're called anywhere.
4. **Orphaned HTML pages**: Check `pages/*.html` files — any page not referenced in `js/router.js` PAGE_SCRIPTS or linked in the sidebar nav of `index.html` is dead.
5. **Legacy inline scripts**: Search for `<script>` tags with inline JS in HTML pages (should be zero — all JS should be in separate files).

## Backend (Python)

6. **Unused Python scripts**: Cross-reference `tools/scripts/*.py` against GitHub Actions workflows (`.github/workflows/`) and `scripts/pipeline_orchestrator.py`. Any script not called by the pipeline or a workflow is potentially dead.
7. **Unused imports**: Search Python files for `import` statements where the imported module/function is never used in the file.
8. **Dead API routes**: Check `api/routers/*.py` — any endpoint not called by the frontend or by cron is potentially dead.

## Analysis

For each finding, check git blame to see when it was last meaningfully edited. Categorise:
- **Safe to delete**: Files with no imports anywhere, old/replaced implementations
- **Verify first**: Files that might be dynamically imported or used by scripts
- **Keep**: Files that are entry points the analysis doesn't understand (cron handlers, CLI scripts)

Do NOT delete anything — report only. Present as a prioritised cleanup checklist.
