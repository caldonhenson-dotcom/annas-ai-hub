---
description: Review an API route for security, performance, and best practices
user-invocable: true
---

Review the API route at $ARGUMENTS for:

1. **Security**: Auth checks (verify FastAPI dependency injection for auth), input validation via Pydantic models, SQL injection (raw Supabase queries), XSS in responses.
2. **Performance**: N+1 queries against Supabase, missing database indexes, unbounded queries (no LIMIT), response size (large payloads without pagination).
3. **Error handling**: Try/except blocks, proper HTTP status codes (FastAPI HTTPException), error messages that don't leak internals or stack traces.
4. **Consistency**: Uses project's Supabase client pattern, follows existing router structure in `api/routers/`, returns JSON with consistent shape.
5. **Rate limiting**: Check if rate limiting middleware is applied where needed (public endpoints, webhook receivers).
6. **CORS**: Verify route respects the CORS configuration in `api/main.py`.
7. **Async**: Verify route handlers are `async def` where they make I/O calls (Supabase, external APIs).

Output a brief pass/fail for each category with specific line numbers for any issues.
