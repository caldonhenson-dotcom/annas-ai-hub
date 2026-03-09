# Retro Log — Anna's AI Hub

> Append-only log of lessons learned. Max 30 lines per entry.

---

## Retro — 2026-02-23 (Initial Session)

### What went well
- Rebuilt 4 legacy pages (Leads, Activities, Insights, Targets) from ~1,338 lines of static HTML to ~245 lines of skeleton HTML + ~1,060 lines of dynamic Chart.js renderers
- Installed 33-persona AI Framework Kit with 11 adapted slash commands
- Created 4 eComplete domain personas (M&A Lead, eCommerce Strategist, HubSpot Specialist, Data Pipeline Engineer)
- Established memory system: retro-log.md + ai-engineering-techniques.md
- 12 of 50 AI engineering techniques now marked DONE

### What went wrong
- Write tool requires fresh Read before each write — caused batch failures when reads were too old
- Parallel Write calls fail as a group if one sibling errors — need sequential fallback strategy
- Context compaction lost file read state — always re-read before writing after long operations

### Errors detected
- Write precondition: "File has not been read yet" → Always Read immediately before Write, even if file was read earlier in the conversation
- Sibling tool errors: One failed Write cascades to all parallel siblings → Read all files in one batch, then Write all in the next batch

### System updates made
- All 11 .claude/commands/*.md: Adapted from Next.js/TypeScript to vanilla JS/Python stack
- .claude/personas.md: Added Part 3 with 4 domain personas (#30-33) and 12 domain skills
- CLAUDE.md: Added full business context (departments, pipeline stages, conversion rates, TS data keys, weekly cadence)
- memory/ai-engineering-techniques.md: 12 techniques marked DONE (was 0)

### Techniques status change
- #8 JIT context loading: TODO → DONE
- #9 Layered CLAUDE.md: TODO → DONE
- #16 File system memory: TODO → DONE
- #17 Functional memory taxonomy: TODO → DONE
- #18 Dead code detection: TODO → DONE
- #21 Bundle analysis: TODO → DONE
- #25 Test generation: TODO → DONE
- #34 Custom slash commands: TODO → DONE
- #39 Agentic remediation: TODO → DONE
- #45 Self-learning from sessions: TODO → DONE
- #46 Daily behaviour review: TODO → DONE
