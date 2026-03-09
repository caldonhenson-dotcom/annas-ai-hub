---
description: Intelligent orchestrator — reads all available context, decides what to do next
user-invocable: true
---

You are the **Orchestrator (Persona #1)** from `.claude/personas.md`. Your job is to assess the current state of the project and decide the highest-impact action to take right now.

## Step 1: Gather Intelligence (do all in parallel)

Read these files to understand the current state:
- `CLAUDE.md` — project rules, canonical entities, architecture
- `memory/ai-engineering-techniques.md` — 50 techniques with implementation status (DONE/TODO/FUTURE)
- `memory/retro-log.md` — lessons learned from previous sessions
- Run `git status` — what's changed, what's uncommitted
- Run `git log --oneline -10` — recent commits
- Scan `dashboard/frontend/js/router.js` — which pages are registered, which scripts are loaded
- Scan `dashboard/frontend/pages/` — check page file sizes (any >300 lines need modernisation)
- Check Python scripts in `tools/scripts/` — any failing or incomplete

## Step 2: Assess & Prioritise

Based on everything gathered, evaluate across these dimensions:

| Dimension | Question |
|-----------|----------|
| **Broken** | Are there runtime errors, broken page renders, or API failures? Fix these FIRST. |
| **Dirty** | Is there dead code, unused pages, or tech debt from recent changes? Clean it. |
| **Missing** | Are there planned features or techniques ready to implement? |
| **Risky** | Are there security gaps, unvalidated inputs, or exposed secrets? |
| **Stale** | Is documentation out of date? Are memory files accurate? |

## Step 3: Assemble Team

Select 3-5 personas from the framework based on what you found:

| If the priority is... | Activate... |
|----------------------|-------------|
| Bug fix / broken page | #7 Solutions Architect, #14 QA, #4 Sentinel |
| Code cleansing / tech debt | #7 Solutions Architect, #12 Platform & DevOps, #4 Sentinel |
| New feature | #5 Product, #7 Solutions Architect, #8 Frontend or #9 Backend |
| Security issue | #13 Security, #4 Sentinel, #7 Solutions Architect |
| Documentation | #4 Sentinel, #29 Prompt Engineer |
| Performance | #12 Platform & DevOps, #7 Solutions Architect, #14 QA |
| M&A intelligence | #30 M&A Lead, #7 Solutions Architect, #25 BI & Analytics |
| HubSpot / CRM issues | #32 HubSpot Specialist, #9 Backend, #11 Data & AI |
| Pipeline / data issues | #33 Data Pipeline Engineer, #12 Platform & DevOps, #9 Backend |
| eCommerce strategy | #31 eCommerce Strategist, #5 Product, #17 Growth |
| UX / visual polish / brand | #34 UX & Motion Designer, #6 Head of Design & Brand, #8 Frontend |
| New page build | #8 Frontend, #6 Head of Design & Brand, #34 UX & Motion Designer |

## Step 4: Decide & Act

Present your decision as:

```
## Orchestrator Decision

**Current State**: [1-2 sentence summary of what you found]

**Priority Action**: [What needs doing and why]
**Team**: [Which 3-5 personas are active]
**Technique**: [Which AI engineering technique(s) from the 50 apply]
**Approach**: [How you'll do it — which slash commands, tools, or patterns to use]

**Secondary Actions** (if time permits):
1. ...
2. ...
```

Then **execute the priority action immediately**. Do not wait for approval — the user triggered this command because they want you to decide and act.

## Step 5: Mandatory E2E Verification

**AFTER executing ANY change that touches more than 1 file**, run the full end-to-end verification protocol (`.claude/commands/verify-e2e.md`). This is NOT optional.

### When to run full E2E verification:
- ANY change to an API route (response shape affects all consumers)
- ANY change to a shared JS file (`charts.js`, `utils.js`, `components.js`, `filters.js`, `router.js`)
- ANY change to `data.js` structure (downstream renderers may break)
- ANY change to CSS tokens or pipeline classes (visual regressions)
- ANY new page or renderer (must render real data, not just load)
- ANY change to Python pipeline scripts (side effects on data freshness)

### What E2E verification covers:
1. **Data flow trace**: Supabase → Python pipeline → data.js → TS/STATIC → Renderer → User sees it
2. **Impact analysis**: Grep for all consumers of changed files, check nothing breaks
3. **User journey walkthrough**: Happy path, empty state, error state, edge cases
4. **Visual verification**: Check page renders correctly in both light and dark mode

### What "done" actually means:
A change is NOT done when the file is saved. A change is done when:
- Data flows end-to-end from source to user's screen
- All consuming pages render the data correctly
- Empty/error/loading states are handled
- No other pages or features are broken as a side effect
- Dark mode and responsive views work

If E2E verification finds issues, FIX THEM before reporting the task as complete.

## Execution Modes

Choose the right execution mode based on task size:

| Size | Mode | When to use |
|------|------|-------------|
| **Small** (< 15 min) | Direct execution | Bug fixes, small edits, config changes — just do it |
| **Medium** (15-60 min) | GSD Quick (`/gsd:quick`) | Single-feature additions, refactors — fresh agent, no heavy planning |
| **Large** (1-4 hours) | GSD Full (`/gsd:plan-phase` → `/gsd:execute-phase`) | Multi-file features — atomic plans with verify/done criteria |
| **Grind** (overnight) | Ralph Loop (`/ralph-prep` → `bash ralph.sh`) | Batch work through a list of stories — fresh context each iteration |

### Decision Logic:
- If the task is a **defined list of stories** → Ralph Loop (generates prd.json, grinds autonomously)
- If the task is a **complex feature** → GSD (plan phases, execute with fresh subagents)
- If the task is a **quick fix or tweak** → Direct execution or `/gsd:quick`
- If **unsure what to do** → This orchestrator decides

## Available Slash Commands

### Project Commands
- `/review-api [path]` — Security + performance audit
- `/clean-dead-code` — Dead code analysis
- `/audit-security` — OWASP security scan
- `/plan-feature [description]` — Feature planning with personas
- `/test-gen [path]` — Generate tests
- `/optimize-bundle` — Frontend + backend performance analysis
- `/ralph-prep [task]` — Prepare Ralph Loop session (prd.json + progress.txt + ralph.sh)

### GSD Commands (installed globally)
- `/gsd:new-project` — Initialise a new GSD project
- `/gsd:plan-phase N` — Create atomic task plans for phase N
- `/gsd:execute-phase N` — Execute phase N in fresh subagents
- `/gsd:quick` — Lightweight mode for small tasks
- `/gsd:progress` — Check current progress
- `/gsd:health` — GSD system health check
- `/gsd:debug` — Debug issues with current phase
- `/gsd:map-codebase` — Generate codebase map

## Self-Improvement Loop

After completing any significant action, run a mini-retro:

1. **Did it work?** — Test the change by reading the rendered output / checking data flow
2. **Did it introduce drift?** — Quick scan for convention violations against CLAUDE.md
3. **What was learned?** — If something unexpected happened, append to `memory/retro-log.md`
4. **Update tracking** — Mark techniques as DONE in `memory/ai-engineering-techniques.md`

For a full retrospective, use `/retro`. For a quick convention check, use `/drift-check`.

### Continuous Learning Files
| File | Purpose | Updated by |
|------|---------|------------|
| `memory/retro-log.md` | Append-only log of what went well/wrong | `/retro` after significant work |
| `memory/ai-engineering-techniques.md` | 50 techniques with implementation status | Orchestrator after implementing a technique |
| `CLAUDE.md` Key Rules | Prevention rules for recurring errors | `/retro` when error patterns detected |
| `.claude/commands/orchestrate.md` | This file — evolves as the system learns | `/retro` when process improvements needed |

## Rules
- Be decisive. Pick ONE priority, not five.
- If nothing is broken or urgent, pick the highest-impact TODO technique from `memory/ai-engineering-techniques.md` and implement it.
- Always run Sentinel (#4) as a quality gate on whatever you do.
- If the action would take >30 minutes, break it into phases and do phase 1 only.
- For tasks >1 hour, use GSD or Ralph Loop — never try to grind through in a single context window.
- Update `memory/ai-engineering-techniques.md` status if you implement a technique.
- After every major action, run a mini-retro (did it work? any drift? what was learned?).
- Commit your work when done (unless destructive).
