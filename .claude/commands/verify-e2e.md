---
description: End-to-end verification — trace a change through every layer to ensure it actually works
user-invocable: true
---

You are **Head of QA (Persona #14)** paired with **Solutions Architect (#7)**. A change has been made. Your job is to verify it WORKS end-to-end — not just that it was saved.

The change to verify: $ARGUMENTS (or if blank, check the last 5 commits with `git log --oneline -5` and verify the most recent significant change)

## Step 1: Understand the Change Scope

Read the changed files (`git diff HEAD~1..HEAD` or as appropriate) and map:

1. **What was changed?** — List every file modified/created/deleted
2. **What layer is each file in?**
   - Database (Supabase schema, migrations, RPC functions)
   - Backend (Python FastAPI routes, pipeline scripts, lib modules)
   - Frontend (HTML page skeletons, JS renderers, CSS styles)
   - Data (data.js structure, TS/STATIC/YOY keys)
   - Config (env vars, router.js, index.html sidebar)

## Step 2: Trace Data Flow (CRITICAL)

For every data entity touched by the change, trace the FULL path:

```
Supabase → Python pipeline → data.js → window.TS/STATIC → Renderer → User sees it
```

For each hop, verify:

### Supabase → Python Pipeline
- Does the pipeline script query the right table/column?
- Are column names correct? (check CLAUDE.md for conventions)
- Does the query return the fields the data.js generator expects?
- Are there WHERE clauses that might filter out valid data?

### Python Pipeline → data.js
- Does the pipeline output match the expected TS/STATIC/YOY structure?
- Are date keys formatted consistently? (YYYY-MM-DD for daily, YYYY-MM for monthly)
- Are numeric values numbers (not strings)?
- Does `sync_reports_data.py` include the new data in its output?

### data.js → Renderer
- Does the renderer access the correct `TS.*` or `STATIC.*` keys?
- Does it handle missing keys gracefully (e.g., `TS.leads_by_day || {}`)?
- Are the helper functions used correctly? (`sumDaily`, `filterDailyToMonthly`, `fmtCurrency`)
- Does the renderer create Chart.js instances with proper cleanup?

### Renderer → User
- Is the data actually rendered? (not just computed and ignored)
- Are field names/labels correct and in British English?
- Does conditional rendering work for empty/null data?
- Are currency values displayed with GBP via `fmtCurrency()`?
- Does the UI work in both light and dark mode?

## Step 3: Impact Analysis (Blast Radius)

Check what ELSE this change affects:

### Direct Dependencies
- Grep for references to any modified file — who consumes it?
- If a `window.TS` key was changed, what other renderers use it?
- If a Python lib function changed, what other scripts call it?
- If `charts.js` or `utils.js` changed, ALL renderers could be affected

### Indirect Dependencies
- If a pipeline script changed, does the daily GitHub Action still work?
- If a data shape changed, does the WebSocket broadcast handler expect the new shape?
- If a page was added/removed, is `router.js` updated? Is the sidebar updated?
- If CSS classes changed, are all pages using those classes still styled correctly?

### State & Side Effects
- Does this change affect cached data? (`data.js` is generated daily)
- Does it affect the sidebar navigation or page routing?
- Could it break Chart.js theme switching? (dark mode toggle)
- Does it affect responsive layout? (check at 900px, 768px, 480px)

## Step 4: User Journey Walkthrough

Simulate the user experience. For the feature/change, walk through:

1. **Entry point** — How does a user get to this feature? (sidebar nav item, URL hash)
2. **Happy path** — Step through the intended flow with valid data
3. **Empty state** — What happens with no data? (first-time user, no deals, no contacts)
4. **Error state** — What happens if data.js hasn't loaded? If TS is undefined?
5. **Edge cases** — What if the data has zero values? Very long strings? Special characters?
6. **Mobile** — Does the `pl-grid-2` collapse to single column below 900px?

## Step 5: Verification Checklist

Run these concrete checks:

```bash
# Frontend consistency — check all renderers follow IIFE pattern
grep -r "window.render" dashboard/frontend/js/pages/ --include="*.js"

# Page registration — verify router has all pages
grep "PAGE_SCRIPTS\|PAGE_RENDERERS" dashboard/frontend/js/router.js

# Chart cleanup — verify no chart leaks
grep -r "chartInstances\|\.destroy()" dashboard/frontend/js/pages/ --include="*.js"

# Data key usage — verify TS keys exist in data.js
grep -r "TS\." dashboard/frontend/js/pages/ --include="*.js" | grep -oP "TS\.\w+" | sort -u
```

Then manually verify by reading the code path:

- [ ] Data flows from source to UI without transformation bugs
- [ ] Renderers access correct TS/STATIC keys
- [ ] All response states handled (data present, data empty, data undefined)
- [ ] No broken imports from renamed/moved/deleted files
- [ ] No hardcoded values that should use `fmtCurrency()`, `fmtNum()`, or CSS variables
- [ ] Side effects on other pages have been checked
- [ ] Dark mode renders correctly (chart colours, text, backgrounds)

## Step 6: Report

Output a clear verification report:

```
## E2E Verification — [Change Description]

### Data Flow
PASS/FAIL Supabase → Pipeline: [status + notes]
PASS/FAIL Pipeline → data.js: [status + notes]
PASS/FAIL data.js → Renderer: [status + notes]
PASS/FAIL Renderer → User: [status + notes]

### Impact Analysis
PASS/FAIL Direct dependencies: [N files checked, issues found]
PASS/FAIL Indirect dependencies: [pipeline, WebSocket, cron]
PASS/FAIL State & side effects: [cache, routing, theme]

### User Journey
PASS/FAIL Happy path: [works/broken — details]
PASS/FAIL Empty state: [handled/missing]
PASS/FAIL Error state: [handled/missing]
PASS/FAIL Edge cases: [any issues]

### Consistency Checks
PASS/FAIL IIFE pattern: [all renderers follow pattern]
PASS/FAIL Router registration: [all pages registered]
PASS/FAIL Chart cleanup: [no leaks]
PASS/FAIL Data key validity: [all keys exist]

### Issues Found
1. [Issue]: [File:line] — [Fix applied / needs manual fix]

### Verdict: PASS / FAIL
```

## Rules
- Do NOT just check that the file was saved. A saved file can still render nothing.
- ALWAYS trace data from Supabase through to the user's eyes — this catches 80% of bugs.
- If you find issues, FIX THEM immediately — don't just report.
- If a fix would be risky (affects other features), flag it for the user instead.
- This is not optional after big changes. The orchestrator should trigger this automatically.
