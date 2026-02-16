"""
Annas AI Hub — HubSpot CRM Integration API
============================================

Endpoints:
  GET  /api/health              - Health check
  GET  /api/hubspot/status      - Integration status
  GET  /api/hubspot/metrics     - Sales dashboard metrics
  GET  /api/hubspot/contacts    - List contacts
  GET  /api/hubspot/contacts/{id} - Get single contact
  POST /api/hubspot/contacts/search - Search contacts
  GET  /api/hubspot/deals       - List deals
  GET  /api/hubspot/companies   - List companies
  POST /api/hubspot/activity    - Log activity
  GET  /dashboard               - Sales intelligence dashboard
"""

import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional

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


@asynccontextmanager
async def lifespan(app):
    """Application startup and shutdown."""
    logger.info("Starting Annas AI Hub...")
    from integrations.hubspot import HubSpotIntegration
    app.state.hubspot = HubSpotIntegration()
    status = "configured" if app.state.hubspot.is_configured else "not configured (add HUBSPOT_API_KEY to .env)"
    logger.info(f"HubSpot integration: {status}")
    logger.info("Annas AI Hub ready")
    yield
    logger.info("Shutting down Annas AI Hub...")


cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:8001").split(",")

app = FastAPI(title="Annas AI Hub", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Request Models ───────────────────────────────────────────

class ContactSearchRequest(BaseModel):
    query: str


class LogActivityRequest(BaseModel):
    contact_id: str
    activity_type: str
    details: str


# ─── Health ───────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    return {
        "status": "healthy",
        "service": "Annas AI Hub",
        "timestamp": datetime.utcnow().isoformat(),
    }


# ─── HubSpot Endpoints ───────────────────────────────────────

@app.get("/api/hubspot/status")
async def hubspot_status():
    """Get HubSpot integration status."""
    return app.state.hubspot.get_status()


@app.get("/api/hubspot/contacts")
async def hubspot_contacts(limit: int = Query(50, ge=1, le=100)):
    """List HubSpot contacts."""
    if not app.state.hubspot.is_configured:
        raise HTTPException(status_code=503, detail="HubSpot not configured. Add HUBSPOT_API_KEY to .env")
    contacts = await app.state.hubspot.get_contacts(limit=limit)
    return {"results": contacts, "count": len(contacts)}


@app.get("/api/hubspot/contacts/{contact_id}")
async def hubspot_contact(contact_id: str):
    """Get a specific HubSpot contact."""
    if not app.state.hubspot.is_configured:
        raise HTTPException(status_code=503, detail="HubSpot not configured")
    contact = await app.state.hubspot.get_contact(contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    return contact


@app.post("/api/hubspot/contacts/search")
async def hubspot_search(req: ContactSearchRequest):
    """Search HubSpot contacts."""
    if not app.state.hubspot.is_configured:
        raise HTTPException(status_code=503, detail="HubSpot not configured")
    results = await app.state.hubspot.search_contacts(req.query)
    return {"results": results, "count": len(results)}


@app.get("/api/hubspot/deals")
async def hubspot_deals(limit: int = Query(50, ge=1, le=100)):
    """List HubSpot deals."""
    if not app.state.hubspot.is_configured:
        raise HTTPException(status_code=503, detail="HubSpot not configured")
    deals = await app.state.hubspot.get_deals(limit=limit)
    return {"results": deals, "count": len(deals)}


@app.get("/api/hubspot/companies")
async def hubspot_companies(limit: int = Query(50, ge=1, le=100)):
    """List HubSpot companies."""
    if not app.state.hubspot.is_configured:
        raise HTTPException(status_code=503, detail="HubSpot not configured")
    companies = await app.state.hubspot.get_companies(limit=limit)
    return {"results": companies, "count": len(companies)}


@app.post("/api/hubspot/activity")
async def hubspot_log_activity(req: LogActivityRequest):
    """Log an activity against a HubSpot contact."""
    if not app.state.hubspot.is_configured:
        raise HTTPException(status_code=503, detail="HubSpot not configured")
    success = await app.state.hubspot.log_activity(req.contact_id, req.activity_type, req.details)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to log activity")
    return {"status": "logged", "contact_id": req.contact_id}


# ─── Sales Metrics ───────────────────────────────────────────

@app.get("/api/hubspot/metrics")
async def hubspot_metrics():
    """Get processed sales dashboard metrics."""
    metrics_path = PROCESSED_DIR / "hubspot_sales_metrics.json"
    if not metrics_path.exists():
        raise HTTPException(status_code=404, detail="No metrics data. Run: python scripts/hubspot_sales_analyzer.py")
    try:
        with open(metrics_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return JSONResponse(content=data)
    except Exception as e:
        logger.error(f"Failed to load metrics: {e}")
        raise HTTPException(status_code=500, detail="Failed to load metrics data")


# ─── Frontend ─────────────────────────────────────────────────

if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    @app.get("/dashboard", response_class=HTMLResponse)
    async def serve_sales_dashboard():
        """Serve the comprehensive sales intelligence dashboard."""
        dash = FRONTEND_DIR / "dashboard-v2.html"
        if dash.exists():
            return FileResponse(str(dash))
        return HTMLResponse("<h1>Dashboard not generated yet</h1><p>Run: python scripts/generate_hubspot_dashboard.py</p>")

    @app.get("/", response_class=HTMLResponse)
    async def serve_dashboard():
        """Serve the main dashboard - redirects to sales dashboard if available."""
        dash = FRONTEND_DIR / "dashboard-v2.html"
        if dash.exists():
            return FileResponse(str(dash))
        index = FRONTEND_DIR / "index.html"
        if index.exists():
            return FileResponse(str(index))
        return HTMLResponse("<h1>Annas AI Hub</h1><p>Dashboard frontend not found.</p>")
