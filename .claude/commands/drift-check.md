---
description: Convention drift detector — checks recent code against project rules
user-invocable: true
---

Scan recent changes for convention violations. This is a lightweight, fast check — not a full retro.

## Checks to Run (in parallel)

### 1. CLAUDE.md Rule Compliance
Read CLAUDE.md "Key Rules" section. For each rule, search recent changed files (last 5 commits) for violations.
Common patterns to check:
- British English in user-facing copy and comments
- No emojis in code, HTML templates, or page titles
- Currency uses `fmtCurrency()` (GBP), not hardcoded symbols
- IIFE renderer pattern: `(function() { 'use strict'; ... })()`
- Single `window.renderXxx` export per renderer file
- `pl-*` CSS classes used (not custom one-off styles)
- Data flows through `window.TS` / `window.STATIC` (not new fetch calls)

### 2. Auth Gaps
Check any new API routes (files in `api/routers/`, modified in last 5 commits) for missing auth checks. Compare against the auth strategy defined in CLAUDE.md.

### 3. Dead Code Introduction
Grep for unused functions, orphaned HTML pages, and JS files not referenced in `js/router.js`. Flag any NEW unused exports or files not present in previous runs.

### 4. Frontend Consistency
Check for:
- `innerHTML` used safely (no raw user input without sanitisation)
- Chart.js instances properly destroyed before recreation (check for `chartInstances[id]` cleanup pattern)
- Page renderers follow the canonical pattern from `render-pipeline.js`
- All new pages registered in both `PAGE_SCRIPTS` and `PAGE_RENDERERS` in `router.js`

### 5. Anti-Bloat Check
Check if any new pages/routes were created that duplicate an entity already covered by the "Canonical Entity Locations" table in CLAUDE.md. New features should be tabs/panels within existing pages, not new routes.

### 6. Python Backend Consistency
Check for:
- `.env` variables used (not hardcoded credentials)
- Supabase queries use parameterised inputs
- FastAPI routes use proper type hints and Pydantic models
- New dependencies added to `tools/requirements.txt`
- No circular imports between Python modules

## Output

Present as a traffic light report:

```
## Drift Check — [DATE]

PASS/FAIL Convention compliance: [PASS/issues found]
PASS/FAIL Auth coverage: [PASS/issues found]
PASS/FAIL Dead code: [PASS/issues found]
PASS/FAIL Frontend consistency: [PASS/issues found]
PASS/FAIL Anti-bloat: [PASS/issues found]
PASS/FAIL Python backend: [PASS/issues found]

Overall: [CLEAN / N issues found]
```

If issues found, fix them immediately (they're convention violations, not feature work).
