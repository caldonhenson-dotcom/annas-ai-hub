---
description: Plan a new feature using persona framework + spec-driven development
user-invocable: true
---

Plan the feature described in $ARGUMENTS using the persona framework:

1. **Orchestrator (#1)**: Route to 3-5 relevant personas based on the feature domain
2. **Head of Product (#5)**: Define the user story, acceptance criteria, and what's explicitly OUT of scope
3. **Solutions Architect (#7)**: Design the technical approach — which files to create/modify, data model changes, API routes needed
4. **Sentinel (#4)**: Flag any security, performance, or consistency risks before implementation

Output a structured spec:
- User story (As a... I want... So that...)
- Acceptance criteria (testable bullets)
- Technical plan (files, routes, schema changes)
- Out of scope (what we're NOT doing)
- Risks and mitigations
- Estimated complexity (S/M/L)

This spec becomes the contract for implementation. Do NOT write code.
