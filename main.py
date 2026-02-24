"""
Annas AI Hub — Entry Point
============================

Run: python main.py
"""

import logging
import os
import sys

from dotenv import load_dotenv

load_dotenv()

# Configure logging
logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO")),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("annas-ai-hub")

PORT = int(os.getenv("DASHBOARD_PORT", "8001"))

if __name__ == "__main__":
    import uvicorn

    logger.info("=" * 60)
    logger.info("  ANNAS AI HUB — Sales & M&A Intelligence")
    logger.info("=" * 60)
    logger.info(f"  Environment : {os.getenv('ENVIRONMENT', 'development')}")
    logger.info(f"  Server      : http://0.0.0.0:{PORT}")
    logger.info(f"  Dashboard   : http://localhost:{PORT}")
    logger.info(f"  API Docs    : http://localhost:{PORT}/docs")
    logger.info(f"  WebSocket   : ws://localhost:{PORT}/ws/dashboard")
    logger.info(f"  Debug       : {os.getenv('DEBUG', 'false')}")
    logger.info("=" * 60)

    uvicorn.run(
        "dashboard.api.main:app",
        host="0.0.0.0",
        port=PORT,
        reload=os.getenv("DEBUG", "false").lower() == "true",
    )
