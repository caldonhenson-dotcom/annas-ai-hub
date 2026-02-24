"""
Annas AI Hub — API Key Auth Middleware
=======================================
Validates X-API-Key header against the api_keys table in Supabase.
Scoped permissions: read, write, admin.

Public endpoints (health, docs, dashboard) bypass auth.
"""
from __future__ import annotations

import hashlib
import time
from typing import Optional

from fastapi import HTTPException, Request, Security
from fastapi.security import APIKeyHeader
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from scripts.lib.logger import setup_logger

logger = setup_logger("api_middleware")

# Header-based API key
API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)

# Paths that don't require auth
PUBLIC_PATHS = {
    "/api/health",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/",
    "/dashboard",
}

# Prefix paths that are public (static files, frontend)
PUBLIC_PREFIXES = ("/static/",)


def _hash_key(key: str) -> str:
    """SHA-256 hash of an API key for storage comparison."""
    return hashlib.sha256(key.encode()).hexdigest()


class APIKeyMiddleware(BaseHTTPMiddleware):
    """
    Middleware that validates API keys from the X-API-Key header.

    If no api_keys table exists or Supabase is unavailable, all requests
    pass through (graceful degradation for development).
    """

    def __init__(self, app, require_auth: bool = False):
        super().__init__(app)
        self.require_auth = require_auth
        self._cache: dict[str, dict] = {}  # key_hash -> {scope, expires_at}
        self._cache_ttl = 300  # 5 minutes

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        path = request.url.path

        # Skip auth for public paths
        if path in PUBLIC_PATHS or any(path.startswith(p) for p in PUBLIC_PREFIXES):
            return await call_next(request)

        # Skip auth for WebSocket upgrades (handled separately)
        if request.headers.get("upgrade", "").lower() == "websocket":
            return await call_next(request)

        api_key = request.headers.get("X-API-Key")

        if not api_key:
            if self.require_auth:
                raise HTTPException(
                    status_code=401,
                    detail="Missing X-API-Key header",
                )
            # No auth required — pass through (development mode)
            request.state.api_scope = "admin"
            return await call_next(request)

        # Validate key
        key_info = await self._validate_key(api_key)
        if not key_info:
            raise HTTPException(
                status_code=403,
                detail="Invalid API key",
            )

        request.state.api_scope = key_info.get("scope", "read")
        return await call_next(request)

    async def _validate_key(self, key: str) -> Optional[dict]:
        """Check key against Supabase api_keys table (with caching)."""
        key_hash = _hash_key(key)

        # Check cache
        cached = self._cache.get(key_hash)
        if cached and cached.get("_cached_at", 0) + self._cache_ttl > time.time():
            return cached

        try:
            from scripts.lib.supabase_client import get_client

            client = get_client()
            result = (
                client.table("api_keys")
                .select("id, scope, active")
                .eq("key_hash", key_hash)
                .eq("active", True)
                .limit(1)
                .execute()
            )

            if result.data:
                info = result.data[0]
                info["_cached_at"] = time.time()
                self._cache[key_hash] = info

                # Update last_used_at (fire and forget)
                try:
                    from datetime import datetime, timezone
                    client.table("api_keys").update({
                        "last_used_at": datetime.now(timezone.utc).isoformat()
                    }).eq("id", info["id"]).execute()
                except Exception:
                    pass

                return info
            return None

        except Exception as e:
            logger.warning("API key validation failed (allowing through): %s", e)
            # Graceful degradation — allow through if Supabase unavailable
            return {"scope": "read", "_cached_at": time.time()}


def require_scope(required: str):
    """
    Dependency to enforce minimum API scope on an endpoint.

    Usage:
        @router.get("/admin-only", dependencies=[Depends(require_scope("admin"))])
    """
    SCOPE_LEVELS = {"read": 0, "write": 1, "admin": 2}

    async def _check(request: Request):
        current = getattr(request.state, "api_scope", "read")
        if SCOPE_LEVELS.get(current, 0) < SCOPE_LEVELS.get(required, 0):
            raise HTTPException(
                status_code=403,
                detail=f"Requires '{required}' scope, current: '{current}'",
            )

    return _check
