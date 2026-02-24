"""
Annas AI Hub — WebSocket Manager
==================================
Manages WebSocket connections for live dashboard push updates.

Usage:
    from dashboard.api.websocket import ws_manager, websocket_endpoint

    # In pipeline_orchestrator or data_sync:
    await ws_manager.broadcast({"event": "pipeline_complete", "data": {...}})

    # In FastAPI:
    app.add_api_websocket_route("/ws/dashboard", websocket_endpoint)
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Dict, Set

from fastapi import WebSocket, WebSocketDisconnect

from scripts.lib.logger import setup_logger

logger = setup_logger("websocket")


class WebSocketManager:
    """Manages active WebSocket connections and broadcasts events."""

    def __init__(self):
        self._connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        """Accept and register a new WebSocket connection."""
        await websocket.accept()
        self._connections.add(websocket)
        logger.info(
            "WebSocket connected. Active connections: %d", len(self._connections)
        )

    def disconnect(self, websocket: WebSocket):
        """Remove a disconnected WebSocket."""
        self._connections.discard(websocket)
        logger.info(
            "WebSocket disconnected. Active connections: %d", len(self._connections)
        )

    async def broadcast(self, message: Dict[str, Any]):
        """Send a message to all connected clients."""
        if not self._connections:
            return

        payload = json.dumps(
            {
                **message,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            default=str,
        )

        disconnected = set()
        for ws in self._connections:
            try:
                await ws.send_text(payload)
            except Exception:
                disconnected.add(ws)

        for ws in disconnected:
            self._connections.discard(ws)

    async def send_to(self, websocket: WebSocket, message: Dict[str, Any]):
        """Send a message to a specific connection."""
        payload = json.dumps(
            {
                **message,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            default=str,
        )
        try:
            await websocket.send_text(payload)
        except Exception:
            self._connections.discard(websocket)

    @property
    def connection_count(self) -> int:
        return len(self._connections)


# Singleton manager
ws_manager = WebSocketManager()


async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for dashboard live updates.

    Clients connect to ws://host/ws/dashboard and receive:
    - pipeline_complete: after a pipeline run finishes
    - data_refreshed: after normalised data sync
    - alert_fired: when an alert triggers
    """
    await ws_manager.connect(websocket)

    # Send initial connection acknowledgement
    await ws_manager.send_to(websocket, {
        "event": "connected",
        "data": {"message": "Connected to Annas AI Hub live feed"},
    })

    try:
        while True:
            # Keep connection alive, handle client messages
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                # Handle ping/pong
                if msg.get("type") == "ping":
                    await ws_manager.send_to(websocket, {
                        "event": "pong",
                        "data": {},
                    })
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception:
        ws_manager.disconnect(websocket)


def broadcast_sync(message: Dict[str, Any]):
    """
    Synchronous wrapper for broadcasting from non-async code (e.g. pipeline_orchestrator).

    Creates a new event loop if needed, or schedules on the existing one.
    """
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(ws_manager.broadcast(message))
    except RuntimeError:
        # No running loop — create one
        asyncio.run(ws_manager.broadcast(message))
