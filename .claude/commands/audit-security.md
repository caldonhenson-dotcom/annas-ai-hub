---
description: Security audit of the codebase focusing on OWASP top 10
user-invocable: true
---

Run a security audit on this Vanilla JS + Python FastAPI codebase:

1. **Authentication gaps**: Check FastAPI route decorators cover all protected endpoints in `api/routers/`. Verify HubSpot PAT and Supabase service key handling. Check WebSocket auth in `api/websocket.py`.
2. **Injection**: Search for unsanitised user input in Supabase `.rpc()` calls, raw SQL queries, FastAPI route params, `eval()` usage in Python, and `innerHTML` assignments in frontend JS.
3. **Secrets exposure**: Check for hardcoded tokens, API keys, or credentials in source (not `.env`). Check `.gitignore` covers `.env` files and `credentials/` directories.
4. **CSRF**: Check API routes that mutate data have proper origin/referer checks or CORS configuration in `api/main.py`.
5. **XSS**: Search for unescaped user content injected via `innerHTML`, `insertAdjacentHTML`, or template string interpolation in `dashboard/frontend/js/`.
6. **Rate limiting**: Identify public API routes in `api/routers/` missing rate limiting middleware.
7. **Dependency vulnerabilities**: Run `pip audit` (or `safety check`) on `tools/requirements.txt` and report critical/high findings.
8. **CORS configuration**: Check `api/main.py` CORS middleware for overly permissive origins.
9. **WebSocket security**: Check `api/websocket.py` for auth on connection and message validation.

Output a severity-ranked list (Critical -> Low) with file:line references and fix recommendations.
