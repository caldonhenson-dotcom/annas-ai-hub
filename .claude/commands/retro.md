---
description: Post-session retrospective — learn from errors, drift, and progress to refine the system
user-invocable: true
---

You are the **Sentinel (Persona #4)** running a self-improvement retrospective. Your job is to analyse what happened, detect patterns, and update the system to prevent repeated mistakes.

## Step 1: Gather Evidence (do all in parallel)

- Run `git log --oneline -20` — recent commits (what was done)
- Run `git diff HEAD~5..HEAD --stat` — scope of recent changes
- Scan `dashboard/frontend/js/pages/` — check all renderers follow IIFE pattern, single `window.renderXxx` export
- Scan `dashboard/frontend/pages/` — check all HTML skeletons are under 100 lines
- Check Python scripts in `tools/scripts/` — any syntax errors or broken imports
- Read `memory/ai-engineering-techniques.md` — technique implementation status
- Read `memory/retro-log.md` — previous retro entries (if exists)
- Read `CLAUDE.md` — current rules to check compliance against

## Step 2: Error Pattern Analysis

Check for recurring patterns across recent work:

### Code Errors
- Were the same types of errors introduced repeatedly? (e.g., missing null checks, wrong data key names in TS object)
- Were there rendering failures? (charts not displaying, KPIs showing NaN)
- Did any deleted files get recreated or any fixed bugs get reintroduced?
- Are Chart.js instances leaking? (check `chartInstances` cleanup)

### Process Errors
- Was context lost to compaction? (check if handoff notes were used)
- Did an agent loop or retry the same failing approach?
- Were there scope creep issues (started on X, ended up touching Y, Z, W)?
- Did the orchestrator pick the wrong execution mode? (e.g., used direct for a large task)

### Convention Drift
- Check recent commits against CLAUDE.md rules:
  - British English used consistently?
  - No emojis in code or page titles?
  - IIFE renderer pattern followed?
  - `pl-*` CSS classes used (not custom one-off styles)?
  - Data flows through `window.TS` / `window.STATIC`?
  - Currency uses `fmtCurrency()` with GBP?
  - Page line counts within limits?
  - Charts use Chart.js only (no inline SVG)?

## Step 3: Improvement Actions

Based on findings, take CONCRETE actions:

### If errors found → Update guard rails
- Add specific patterns to CLAUDE.md "Key Rules" section to prevent recurrence
- If a data key error repeats, document the correct key names
- If a convention keeps being violated, make it more explicit in CLAUDE.md

### If drift detected → Course correct
- Update CLAUDE.md with the correct convention (make it explicit, not implied)
- If personas are being assembled wrong, update the orchestrator's team routing table
- If the wrong execution mode keeps being chosen, refine the decision logic in orchestrate.md

### If techniques implemented → Update tracking
- Update `memory/ai-engineering-techniques.md` status (TODO → DONE)
- Add implementation notes (what worked, what didn't)
- If a technique didn't work well, add a warning note

### If process improvements needed → Evolve the system
- Update `orchestrate.md` with new decision logic learned from experience
- Add new slash commands for repeated manual workflows
- Update persona descriptions in `.claude/personas.md` with new skills/triggers

## Step 4: Write Retrospective

Append findings to `memory/retro-log.md` (create if doesn't exist):

```markdown
## Retro — [DATE]

### What went well
- ...

### What went wrong
- ...

### Errors detected
- [Error]: [Pattern] → [Fix applied]

### Drift detected
- [Convention]: [Violation] → [Correction applied]

### System updates made
- [File]: [Change] — [Why]

### Techniques status change
- [#N]: [TODO → DONE] or [DONE but ineffective → notes]
```

## Step 5: Confidence Check

Rate the current system health:

| Dimension | Score (1-5) | Notes |
|-----------|-------------|-------|
| Code quality | ? | Renderer patterns, Chart.js usage, data flow |
| Convention adherence | ? | CLAUDE.md rules followed? |
| Process efficiency | ? | Right tools used? Context managed well? |
| Documentation accuracy | ? | CLAUDE.md, memory files up to date? |
| Technique adoption | ? | Are implemented techniques being used? |

If any dimension scores 2 or below, flag it as the PRIORITY for the next orchestrator run.

## Rules
- Be honest. If the system is working well, say so. Don't invent problems.
- Every error pattern MUST result in a concrete prevention mechanism (rule, hook, or check).
- Don't just log problems — fix them. Update the actual files.
- Keep `retro-log.md` append-only and concise (max 30 lines per entry).
- If you update CLAUDE.md or orchestrate.md, verify the changes don't break existing instructions.
