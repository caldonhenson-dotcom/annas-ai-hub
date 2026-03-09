# eComplete AI — Anna's AI Hub

## Project Overview
Sales & M&A Intelligence Dashboard powered by HubSpot data, Supabase backend, and Chart.js visualisations. Vanilla JS SPA with lazy-loaded HTML fragments, Python FastAPI backend, and GitHub Actions automation.

**Business**: eComplete is an eCommerce accelerator. The dashboard serves Anna Younger (MD) and her team with real-time pipeline visibility, M&A target intelligence, marketing performance, and operational KPIs.

## Key Rules
- **E2E verification is MANDATORY** for any change touching >1 file — trace data from database to user's screen, check all consumers, verify empty/error/loading states. A change that compiles but doesn't render correctly is NOT done. Run `/verify-e2e`.
- **NO NEW SECTIONS for existing entities.** Each entity has ONE canonical location. New features MUST be added as tabs, panels, or sub-views within the existing section — NEVER as a new top-level nav item or separate page.
- **British English** in all user-facing copy, comments, and documentation.
- **No emojis** in code, HTML templates, or page titles unless explicitly requested.
- **Chart.js only** — no inline SVG charts. Use shared helpers from `charts.js`.
- **IIFE renderer pattern** — every `render-*.js` wraps in `(function() { 'use strict'; ... })()`, exposes single `window.renderXxx` function.
- **pl-* CSS classes** are the design standard — all pages use `pl-card`, `pl-grid-2`, `pl-act-card`, `pl-filter-pill` from `css/pipeline.css`.
- **Data flows through TS and STATIC** — `window.TS` (timeseries), `window.YOY` (year-over-year), `window.STATIC` (snapshots).
- **Currency is GBP** — use `fmtCurrency()` which prefixes with £.
- **No page exceeds 300 lines** — HTML skeletons ~50-75 lines, JS renderers ~200-280 lines.

## Business Context

### Company
eComplete is a UK-based eCommerce accelerator that acquires and scales eCommerce brands. Revenue target: £1.2M annual (£100K/month, £300K/quarter).

### Departments
| Department | Focus | Key Stakeholders |
|-----------|-------|-----------------|
| **Delivery** | Client fulfilment, project execution | Team leads |
| **Supply Chain** | Logistics, procurement, vendor management | Operations team |
| **CDD** | Commercial Due Diligence for M&A targets | M&A team, analysts |

### Named Reps (HubSpot Users)
Anna Younger, Caldon Henson, Jake Heath, James Carberry, Josh Elliott, Kirill Kopica, Rose Galbally, Skye Whitton

### Deal Pipeline Stages (HubSpot)
1. **Inbound Lead** — Initial contact received
2. **Engaged** — Two-way communication established
3. **First Meeting Booked** — Discovery call scheduled
4. **Second Meeting Booked** — Follow-up/deep-dive scheduled
5. **Proposal Shared** — Commercial proposal sent
6. **Decision Maker Bought-In** — Budget holder aligned
7. **Contract Sent** — Legal documents in review
8. **Closed Won** — Deal signed
9. **Closed Lost** — Deal did not proceed
10. **Disqualified** — Not a fit / removed from pipeline

### Revenue Targets
| Period | Target | Tracking |
|--------|--------|----------|
| Monthly | £100,000 | `TARGETS.monthly` in render-targets.js |
| Quarterly | £300,000 | `TARGETS.quarterly` |
| Annual | £1,200,000 | `TARGETS.annual` |

### Conversion Rates (Benchmarks)
| Metric | Rate | Used in |
|--------|------|---------|
| Lead → MQL | 5% | `TARGETS.mql_rate` |
| MQL → SQL | 50% | `TARGETS.sql_rate` |
| SQL → Opportunity | 50% | `TARGETS.opp_rate` |
| Opportunity → Won | 27% | `TARGETS.win_rate` |
| Average Deal Value | £15,714 | `TARGETS.avg_deal` |

### Lead Sources
OFFLINE, DIRECT_TRAFFIC, ORGANIC_SEARCH, PAID_SEARCH, REFERRALS, SOCIAL_MEDIA

### Weekly Cadence
- **Monday**: Marketing performance review (channel KPIs, campaign status)
- **Friday**: Pipeline review (deal progression, stuck deals, forecast update)
- **Daily**: Pipeline health check runs via GitHub Actions at 06:00 UTC

## Canonical Entity Locations

| Entity | Canonical Route/Page | How to extend |
|--------|---------------------|---------------|
| Executive Summary | `pages/executive.html` | Add KPI cards or comparison widgets |
| Pipeline & Sales | `pages/pipeline.html` | Add tabs, filters, or chart panels within |
| Leads & Conversion | `pages/leads.html` | Add source breakdowns or funnel stages |
| Activity Tracking | `pages/activities.html` | Add rep views or activity type panels |
| Insights & Forecast | `pages/insights.html` | Add forecast models or win/loss analysis |
| Targets | `pages/targets.html` | Add gap analysis or scenario panels |
| M&A Hub | `pages/ma-hub.html` | Add IC scorecards, deal sections |
| Inbound Queue | `pages/inbound-queue.html` | Add queue views or priority filters |
| Skills Engine | `pages/skills.html` | Add skill categories via registry |
| AI Roadmap | `pages/ai-roadmap.html` | Add board groups or status views |
| Outreach Engine | `pages/outreach.html` | Add campaign types or templates |
| Anna (AI Assistant) | `pages/anna.html` | Add memory panels or persona widgets |

**When adding a feature:**
1. Find the canonical location above
2. Add it as a tab, panel, filter, or sub-view within that page
3. NEVER create a new route for an existing entity
4. If unsure, ask — don't create a new page

## Architecture

### Frontend (Vanilla JS SPA)
- **Entry**: `dashboard/frontend/index.html`
- **Router**: `js/router.js` — `PAGE_SCRIPTS` + `PAGE_RENDERERS` maps
- **Styles**: CSS variables in `css/tokens.css`, component styles in `css/pipeline.css`
- **Charts**: `js/charts.js` — shared Chart.js helpers (`ensureCanvas`, `chartOpts`, `isDark`, etc.)
- **Utils**: `js/utils.js` — date ranges, formatting, markdown, toast
- **Components**: `js/components.js` — `window.UI` factory functions
- **Filters**: `js/filters.js` — `window.applyFilter(period)` drives KPI updates
- **Data**: `js/data.js` — generated daily, exposes `window.TS`, `window.YOY`, `window.STATIC`

### TS Data Keys (window.TS)
| Key | Shape | Used by |
|-----|-------|---------|
| `leads_by_day` | `{ "YYYY-MM-DD": N }` | Leads, Executive |
| `leads_by_source_by_month` | `{ "YYYY-MM": { source: N } }` | Leads |
| `contacts_created_by_day` | `{ "YYYY-MM-DD": N }` | Activities, Leads |
| `mqls_by_day` | `{ "YYYY-MM-DD": N }` | Leads, Targets |
| `sqls_by_day` | `{ "YYYY-MM-DD": N }` | Leads, Targets |
| `deals_created_by_day` | `{ "YYYY-MM-DD": N }` | Pipeline, Targets |
| `deals_won_by_day` | `{ "YYYY-MM-DD": N }` | Pipeline, Insights, Targets |
| `deals_won_value_by_day` | `{ "YYYY-MM-DD": N }` | Pipeline, Insights, Targets |
| `deals_lost_by_day` | `{ "YYYY-MM-DD": N }` | Insights |
| `deals_by_stage_by_month` | `{ "YYYY-MM": { stage: N } }` | Pipeline |
| `revenue_won_by_month` | `{ "YYYY-MM": N }` | Targets, Executive |
| `pipeline_value_by_month` | `{ "YYYY-MM": N }` | Targets, Insights |
| `activities_by_type_by_day` | `{ "YYYY-MM-DD": { type: N } }` | Activities |
| `activities_by_rep_by_month` | `{ "YYYY-MM": { rep: N } }` | Activities |

### Backend (Python FastAPI)
- **API**: `api/main.py` — FastAPI on port 8001
- **HubSpot**: `integrations/hubspot.py` — async client, Bearer PAT auth
- **WebSocket**: `api/websocket.py` — `/ws/dashboard` broadcast
- **Pipeline**: `scripts/pipeline_orchestrator.py` — 6-phase daily pipeline

### Infrastructure
- **Supabase**: PostgreSQL + Edge Functions + Storage
- **Vercel**: Static frontend auto-deploy
- **GitHub Actions**: `.github/workflows/annas-pipeline.yml` at 06:00 UTC
- **Repo**: github.com/caldonhenson-dotcom/annas-ai-hub

## AI Engineering Framework (Personas + GSD + Ralph Loop)

### Orchestrator Mode
When the user says "orchestrate", "use the orchestrator", "have the team decide", "figure out what to do", "what should we work on", "run the team", or gives a task "as a team" — follow `.claude/commands/orchestrate.md`:
1. Gather intel (git status, techniques status, memory files) in parallel
2. Assess: Broken → Dirty → Risky → Missing → Stale
3. Assemble 3-5 personas from `.claude/personas.md`
4. Decide the single highest-impact action and execute immediately
5. Choose execution mode based on task size (see below)

If the user gives a specific task with orchestrator language (e.g. "have the team build X"), skip the assessment and route directly to the right personas for that task.

### Persona Framework
- **34 personas** total: 29 core + 4 eComplete domain specialists + 1 UX & Motion specialist
- **Core** (#1-29): Governance, Engineering, Commercial, Compliance, Thinking Styles
- **Domain** (#30-33): Head of M&A, eCommerce Strategist, HubSpot Specialist, Data Pipeline Engineer
- **Creative** (#34): UX & Motion Designer — micro-interactions, loading states, animation, visual polish
- **167 executable skills** with unique IDs (SK-XXX-NN)
- Load via Orchestrator, max 3-5 active at once

### Execution Modes
| Size | Mode | How |
|------|------|-----|
| Small (<15 min) | Direct | Just do it |
| Medium (15-60 min) | GSD Quick | Fresh agent, no heavy planning |
| Large (1-4 hours) | GSD Full | Atomic plans, fresh subagents per task |
| Grind (overnight) | Ralph Loop (`ralph.sh`) | Autonomous loop, fresh context each iteration |

### Self-Improvement Loop
The system learns and refines itself:
- `/retro` — Full retrospective: error patterns, drift detection, process improvements
- `/drift-check` — Quick convention scan (6 categories)
- After every major action, the orchestrator runs a mini-retro
- `memory/retro-log.md` — Append-only log of lessons learned
- `memory/ai-engineering-techniques.md` — 50 techniques, 12 implemented
- Errors don't just get logged — they get turned into prevention rules in CLAUDE.md

### Key Files
- `.claude/personas.md` — 33-persona framework (load via Orchestrator, max 3-5 at once)
- `.claude/commands/orchestrate.md` — Full orchestrator protocol
- `.claude/commands/retro.md` — Self-improvement retrospective
- `.claude/commands/drift-check.md` — Convention drift detector
- `.claude/commands/verify-e2e.md` — End-to-end verification
- `ralph.sh` — Ralph Loop runner (project root)
- `memory/ai-engineering-techniques.md` — 50 techniques with implementation status
- `memory/retro-log.md` — Lessons learned log (append-only)

### Available Slash Commands
- `/orchestrate` — Intelligent orchestrator: assess, decide, act
- `/verify-e2e [change]` — End-to-end verification protocol
- `/retro` — Self-improvement retrospective
- `/drift-check` — Convention drift detector
- `/review-api [path]` — API security + performance audit
- `/clean-dead-code` — Dead code analysis
- `/audit-security` — OWASP security scan
- `/plan-feature [description]` — Feature planning with personas
- `/test-gen [path]` — Generate tests (pytest for Python, test plans for JS)
- `/optimize-bundle` — Frontend + backend performance analysis
- `/ralph-prep [task]` — Prepare Ralph Loop session
