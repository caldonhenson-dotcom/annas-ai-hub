"""
Annas AI Hub — API Server
============================

Live API layer serving data from normalised Supabase tables.
Includes HubSpot live CRM integration, WebSocket push, and API key auth.

Route groups:
  /api/health              - Health check
  /api/hubspot/*           - Live HubSpot CRM integration
  /api/metrics/*           - Aggregated metrics (materialised views)
  /api/deals/*             - Filterable deal queries
  /api/contacts/*          - Filterable contact queries
  /api/activities/*        - Filterable activity queries
  /api/monday/*            - Monday.com M&A + IC scores
  /api/pipeline-runs/*     - Pipeline execution history
  /api/outreach/pillars/*  - Service pillar management
  /api/outreach/prospects/* - Prospect management + import
  /api/linkedin/*          - LinkedIn DM Power Inbox (28 endpoints)
  /api/outreach/ai/*       - AI research, drafting, classification, logs
  /api/outreach/queue/*    - Approval queue, send, correspondence monitor
  /api/outreach/enrollments/* - Sequence enrollment management
  /api/outreach/scoring/*  - Lead scoring, leaderboard, HubSpot sync
  /api/outreach/analytics/* - Outreach analytics, funnel, AI usage
  /ws/dashboard            - WebSocket live feed
"""

import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv()

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
FRONTEND_DIR = BASE_DIR / "dashboard" / "frontend"
PROCESSED_DIR = BASE_DIR / "data" / "processed"


# ─── Lifespan ─────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app):
    """Application startup and shutdown."""
    logger.info("Starting Annas AI Hub...")

    # HubSpot live integration (optional)
    try:
        from integrations.hubspot import HubSpotIntegration
        app.state.hubspot = HubSpotIntegration()
        status = "configured" if app.state.hubspot.is_configured else "not configured"
        logger.info("HubSpot live integration: %s", status)
    except Exception as e:
        logger.warning("HubSpot integration not available: %s", e)
        app.state.hubspot = None

    # Supabase connection check
    try:
        from scripts.lib.supabase_client import get_client
        get_client()
        logger.info("Supabase connected")
    except Exception as e:
        logger.warning("Supabase not available: %s", e)

    logger.info("Annas AI Hub ready")
    yield
    logger.info("Shutting down Annas AI Hub...")


# ─── App Setup ────────────────────────────────────────────────

cors_origins = os.getenv(
    "CORS_ORIGINS", "http://localhost:3000,http://localhost:8001"
).split(",")

app = FastAPI(
    title="Annas AI Hub",
    version="4.0.0",
    description="Sales & M&A Intelligence Platform — Full Intelligent Outreach Engine",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API key middleware (graceful — won't block if Supabase unavailable)
try:
    from dashboard.api.middleware import APIKeyMiddleware
    require_auth = os.getenv("REQUIRE_API_KEY", "false").lower() == "true"
    app.add_middleware(APIKeyMiddleware, require_auth=require_auth)
except Exception as e:
    logger.warning("API key middleware not loaded: %s", e)


# ─── Include Routers ──────────────────────────────────────────

from dashboard.api.routers.metrics import router as metrics_router
from dashboard.api.routers.deals import router as deals_router
from dashboard.api.routers.contacts import router as contacts_router
from dashboard.api.routers.activities import router as activities_router
from dashboard.api.routers.monday import router as monday_router
from dashboard.api.routers.pipeline_runs import router as pipeline_runs_router
from dashboard.api.routers.outreach_pillars import router as outreach_pillars_router
from dashboard.api.routers.outreach_prospects import router as outreach_prospects_router
from dashboard.api.routers.linkedin import router as linkedin_router
from dashboard.api.routers.outreach_ai import router as outreach_ai_router
from dashboard.api.routers.outreach_queue import router as outreach_queue_router
from dashboard.api.routers.outreach_enrollments import router as outreach_enrollments_router
from dashboard.api.routers.outreach_scoring import router as outreach_scoring_router
from dashboard.api.routers.outreach_analytics import router as outreach_analytics_router

app.include_router(metrics_router)
app.include_router(deals_router)
app.include_router(contacts_router)
app.include_router(activities_router)
app.include_router(monday_router)
app.include_router(pipeline_runs_router)
app.include_router(outreach_pillars_router)
app.include_router(outreach_prospects_router)
app.include_router(linkedin_router)
app.include_router(outreach_ai_router)
app.include_router(outreach_queue_router)
app.include_router(outreach_enrollments_router)
app.include_router(outreach_scoring_router)
app.include_router(outreach_analytics_router)


# ─── WebSocket ────────────────────────────────────────────────

from dashboard.api.websocket import websocket_endpoint

app.add_api_websocket_route("/ws/dashboard", websocket_endpoint)


# ─── Request Models ───────────────────────────────────────────

class ContactSearchRequest(BaseModel):
    query: str


class LogActivityRequest(BaseModel):
    contact_id: str
    activity_type: str
    details: str


# ─── Health ───────────────────────────────────────────────────

@app.get("/api/health", tags=["system"])
async def health():
    """Health check with service status."""
    supabase_ok = False
    try:
        from scripts.lib.supabase_client import get_client
        get_client()
        supabase_ok = True
    except Exception:
        pass

    hubspot_ok = (
        app.state.hubspot is not None
        and hasattr(app.state.hubspot, "is_configured")
        and app.state.hubspot.is_configured
    )

    from dashboard.api.websocket import ws_manager

    return {
        "status": "healthy",
        "service": "Annas AI Hub",
        "version": "4.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "integrations": {
            "supabase": supabase_ok,
            "hubspot": hubspot_ok,
        },
        "websocket_connections": ws_manager.connection_count,
    }


# ─── HubSpot Live CRM Endpoints ──────────────────────────────
# These call HubSpot API directly (not cached Supabase data)

@app.get("/api/hubspot/status", tags=["hubspot-live"])
async def hubspot_status():
    """Get HubSpot integration status."""
    if not app.state.hubspot:
        raise HTTPException(status_code=503, detail="HubSpot integration not loaded")
    return app.state.hubspot.get_status()


@app.get("/api/hubspot/contacts", tags=["hubspot-live"])
async def hubspot_contacts(limit: int = Query(50, ge=1, le=100)):
    """List contacts from HubSpot API (live)."""
    if not app.state.hubspot or not app.state.hubspot.is_configured:
        raise HTTPException(status_code=503, detail="HubSpot not configured")
    contacts = await app.state.hubspot.get_contacts(limit=limit)
    return {"results": contacts, "count": len(contacts)}


@app.get("/api/hubspot/contacts/{contact_id}", tags=["hubspot-live"])
async def hubspot_contact(contact_id: str):
    """Get a specific contact from HubSpot API (live)."""
    if not app.state.hubspot or not app.state.hubspot.is_configured:
        raise HTTPException(status_code=503, detail="HubSpot not configured")
    contact = await app.state.hubspot.get_contact(contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    return contact


@app.post("/api/hubspot/contacts/search", tags=["hubspot-live"])
async def hubspot_search(req: ContactSearchRequest):
    """Search contacts via HubSpot API (live)."""
    if not app.state.hubspot or not app.state.hubspot.is_configured:
        raise HTTPException(status_code=503, detail="HubSpot not configured")
    results = await app.state.hubspot.search_contacts(req.query)
    return {"results": results, "count": len(results)}


@app.get("/api/hubspot/deals", tags=["hubspot-live"])
async def hubspot_deals(limit: int = Query(50, ge=1, le=100)):
    """List deals from HubSpot API (live)."""
    if not app.state.hubspot or not app.state.hubspot.is_configured:
        raise HTTPException(status_code=503, detail="HubSpot not configured")
    deals = await app.state.hubspot.get_deals(limit=limit)
    return {"results": deals, "count": len(deals)}


@app.get("/api/hubspot/companies", tags=["hubspot-live"])
async def hubspot_companies(limit: int = Query(50, ge=1, le=100)):
    """List companies from HubSpot API (live)."""
    if not app.state.hubspot or not app.state.hubspot.is_configured:
        raise HTTPException(status_code=503, detail="HubSpot not configured")
    companies = await app.state.hubspot.get_companies(limit=limit)
    return {"results": companies, "count": len(companies)}


@app.post("/api/hubspot/activity", tags=["hubspot-live"])
async def hubspot_log_activity(req: LogActivityRequest):
    """Log an activity via HubSpot API (live, requires write scope)."""
    if not app.state.hubspot or not app.state.hubspot.is_configured:
        raise HTTPException(status_code=503, detail="HubSpot not configured")
    success = await app.state.hubspot.log_activity(
        req.contact_id, req.activity_type, req.details
    )
    if not success:
        raise HTTPException(status_code=500, detail="Failed to log activity")
    return {"status": "logged", "contact_id": req.contact_id}


# ─── Legacy Metrics Endpoint (backwards compatible) ───────────

@app.get("/api/hubspot/metrics", tags=["legacy"])
async def hubspot_metrics():
    """
    Get processed sales metrics.
    Tries Supabase snapshot first, falls back to JSON file.
    """
    # Try Supabase first
    try:
        from scripts.lib.supabase_client import get_latest_snapshot
        data = get_latest_snapshot("hubspot_sales")
        if data:
            return JSONResponse(content=data)
    except Exception:
        pass

    # Fallback to JSON file
    metrics_path = PROCESSED_DIR / "hubspot_sales_metrics.json"
    if not metrics_path.exists():
        raise HTTPException(
            status_code=404,
            detail="No metrics data. Run: python scripts/hubspot_sales_analyzer.py",
        )
    try:
        with open(metrics_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return JSONResponse(content=data)
    except Exception as e:
        logger.error("Failed to load metrics: %s", e)
        raise HTTPException(status_code=500, detail="Failed to load metrics data")


# ─── Frontend ─────────────────────────────────────────────────

if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    @app.get("/dashboard", response_class=HTMLResponse, tags=["frontend"])
    async def serve_sales_dashboard():
        """Serve the sales intelligence dashboard."""
        dash = FRONTEND_DIR / "dashboard-v2.html"
        if dash.exists():
            return FileResponse(str(dash))
        return HTMLResponse(
            "<h1>Dashboard not generated yet</h1>"
            "<p>Run: python scripts/generate_hubspot_dashboard.py</p>"
        )

    @app.get("/", response_class=HTMLResponse, tags=["frontend"])
    async def serve_dashboard():
        """Serve the main dashboard."""
        dash = FRONTEND_DIR / "dashboard-v2.html"
        if dash.exists():
            return FileResponse(str(dash))
        index = FRONTEND_DIR / "index.html"
        if index.exists():
            return FileResponse(str(index))
        return HTMLResponse(
            "<h1>Annas AI Hub</h1><p>Dashboard frontend not found.</p>"
        )
