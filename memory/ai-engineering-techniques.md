# AI Engineering Techniques — Reference

> 50 techniques across 10 categories | Track implementation status per project
> Integrated with 33-persona framework (Ralph Loop + GSD + Personas + Domain Specialists)

## Integration Model
- **Personas (Orchestrator #1)** → Routes tasks, assembles review teams
- **GSD (/gsd:plan-phase)** → Atomic plans with verify/done criteria
- **Ralph Loop (ralph.sh)** → Grinds through plans autonomously, fresh context each iteration
- **Sentinel (#4)** → PostToolUse hooks for quality gates
- **Domain Specialists (#30-33)** → M&A, eCommerce, HubSpot, Data Pipeline expertise

## A. Autonomy & Unattended Operation
1. Auto-approve permissions — `.claude/settings.json` allowedTools | TODO
2. Dangerously skip permissions — for Ralph loops only (--dangerously-skip-permissions) | TODO
3. PreCompact hooks — save state before context compaction | TODO
4. PostToolUse auto-lint/test — auto-run linter/type-check after edits | TODO
5. SessionStart auto-context — load progress.txt on session start | TODO
6. Background agents (Ctrl+B) — parallel work | AVAILABLE

## B. Context Engineering
7. Auto-compact tuning — compact at ~70%, /compact between tasks | AVAILABLE
8. Just-in-time context loading — references not content in CLAUDE.md | DONE — CLAUDE.md uses references to .claude/commands/ and memory/ files, not inline content
9. Layered CLAUDE.md with @imports — modular docs | DONE — CLAUDE.md references personas.md, commands/, memory/ as separate files
10. KV-cache-aware prompt design — stable prefixes, append-only | FUTURE
11. Repository maps (AST + PageRank) — tree-sitter + RepoMapper MCP | FUTURE
12. Context-aware tool masking — state machine controls tool availability | FUTURE

## C. Memory Systems
13. Vector-indexed codebase (CodeRAG) — pgvector or Chroma embeddings | TODO
14. MCP semantic search — @zilliz/claude-context-mcp | TODO
15. Temporal knowledge graphs — Graphiti/Zep | FUTURE
16. File system as externalised memory — progress.txt pattern | DONE — memory/retro-log.md + memory/ai-engineering-techniques.md as persistent memory
17. Functional memory taxonomy — factual/experiential/working | DONE — retro-log.md (experiential), CLAUDE.md (factual), techniques tracker (working)

## D. Code Cleansing & Tech Debt
18. Dead code detection — find unused files/exports/functions | DONE — /clean-dead-code command adapted for vanilla JS + Python stack
19. Dependency graph analysis — cross-reference router.js, pipeline scripts | TODO
20. Automated redundancy detection — AI scans for duplicate logic | TODO
21. Bundle analysis — frontend asset optimisation | DONE — /optimize-bundle command adapted for vanilla JS SPA
22. Predictive debt management — CodeScene patterns | FUTURE
23. Automated migration scripts — scripted data migrations with verification | TODO

## E. Testing & Verification
24. Spec-driven development (SDD) — specs as contracts | TODO
25. Autonomous test generation — AI generates tests from code | DONE — /test-gen command adapted for pytest + vanilla JS test plans
26. Self-healing tests — intent-based, not selector-based | FUTURE
27. PostToolUse test hooks — auto-run tests on file change | TODO
28. Verification loops (Spotify pattern) — generate→lint→build→test→retry | TODO
29. Contract testing for APIs — input/output schema validation | TODO

## F. Multi-Agent Patterns
30. Git worktree parallel agents — N agents, N branches, 1/Nth time | AVAILABLE
31. Agent teams — lead + teammates with shared task list | AVAILABLE
32. Task DAGs — dependency-aware task orchestration | FUTURE
33. Fan-out research agents — parallel exploration | AVAILABLE

## G. Workflow & Automation
34. Custom slash commands — .claude/commands/ library | DONE — 11 commands adapted for project stack (audit-security, clean-dead-code, drift-check, optimize-bundle, orchestrate, plan-feature, ralph-prep, retro, review-api, test-gen, verify-e2e)
35. Cron-triggered agent runs — overnight Ralph loops | TODO
36. Model routing — cheaper models for simple tasks, Opus for complex | FUTURE
37. Prompt caching — stable prefixes for 10x cheaper tokens | FUTURE
38. Behavioural diversity injection — break repetitive loops | FUTURE

## H. Security & Quality Gates
39. Agentic remediation — AI scans + patches own vulnerabilities | DONE — /audit-security command with OWASP checks adapted for FastAPI + vanilla JS
40. Pre-commit security scanning — semgrep/eslint-security hooks | TODO
41. Sentinel persona as hook — Persona #4 in PostToolUse | TODO
42. Secret detection — gitleaks/trufflehog pre-commit | TODO

## I. Observability & Learning
43. Agent action logging — structured log of all tool calls | TODO
44. Token budget tracking — usage per task type | FUTURE
45. Self-learning from past sessions — experiential memory (/retro) | DONE — /retro command adapted, memory/retro-log.md established
46. Daily behaviour review automation — /retro + /drift-check | DONE — Both commands adapted for project stack, /drift-check covers 6 check categories

## J. Infrastructure
47. MCP server ecosystem — custom servers for integrations | TODO
48. Vector DB for semantic search — pgvector/Chroma/Pinecone | TODO
49. Edge function offloading — heavy compute to serverless | FUTURE
50. Incremental re-indexing — only re-embed changed files | FUTURE

## Status Summary
- DONE: 12 techniques (implemented and active)
- TODO: 22 techniques (ready to implement)
- AVAILABLE (built-in): 4 techniques
- FUTURE: 12 techniques (longer-term)

## Key Resources
- Ralph Loop: github.com/snarktank/ralph
- GSD: github.com/gsd-build/get-shit-done
- Claude Context MCP: @zilliz/claude-context-mcp
- RepoMapper MCP: github.com/pdavis68/RepoMapper
- Spotify Honk pattern: engineering.atspotify.com
