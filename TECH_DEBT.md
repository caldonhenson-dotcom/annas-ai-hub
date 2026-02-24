# Technical Debt Register — Annas AI Hub

| # | Description | Severity | Effort | Date Added | Rule Violated |
|---|-------------|----------|--------|------------|---------------|
| 1 | `dashboard-v2.html` is 16,600+ lines — needs splitting into components | High | Large | 2025-02-23 | Rule 2: Max 300 lines/file |
| 2 | `ai-query.js` handler is ~100 lines — at limit, needs service extraction | Medium | Small | 2025-02-23 | Rule 2: Max 100 lines/handler |
| 3 | No AbortController timeouts on Groq or Supabase fetch calls | Medium | Small | 2025-02-23 | Rule 3: Always set timeouts |
| 4 | No request deduplication — concurrent identical AI calls not prevented | Medium | Medium | 2025-02-23 | Rule 3: Never duplicate concurrent calls |
| 5 | No AI response caching — identical prompts re-call Groq every time | Medium | Medium | 2025-02-23 | Rule 5: Cache AI responses by prompt hash |
| 6 | No token counting before Groq calls — could exceed model limits | Low | Small | 2025-02-23 | Rule 5: Count tokens before sending |
| 7 | Rate limiting is in-memory only — resets on Vercel cold starts | Low | Medium | 2025-02-23 | Rule 3: Needs Upstash Redis for production |
| 8 | No circuit breaker on Groq API calls | Medium | Medium | 2025-02-23 | Rule 3: Circuit breaker for unreliable services |
| 9 | No retry with exponential backoff on transient Groq failures | Medium | Small | 2025-02-23 | Rule 6: Retry transient failures |
| 10 | `console.error` used in production code paths (should be structured logging) | Low | Small | 2025-02-23 | Rule 10: No console.log in production |
| 11 | No automated tests — 0% coverage | High | Large | 2025-02-23 | Rule 10: All tests pass |
| 12 | No custom error classes — uses plain objects | Low | Small | 2025-02-23 | Rule 6: Use custom error classes |
| 13 | Supabase queries use string interpolation for prospect_id (mitigated with regex) | Low | Small | 2025-02-23 | Rule 7: Parameterise all queries |
| 14 | No `npm audit` in CI/CD pipeline | Medium | Small | 2025-02-23 | Rule 7: Check npm audit |
| 15 | No ESLint configuration | Medium | Small | 2025-02-23 | Rule 10: ESLint zero warnings |
