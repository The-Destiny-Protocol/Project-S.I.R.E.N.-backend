"""
app/services/ws_manager.py
──────────────────────────
WebSocket Connection Manager for the Live Map real-time bridge.

Maintains a registry of connected frontend clients and broadcasts
telemetry payloads received from the MQTT pipeline to all of them.

Usage:
    from app.services.ws_manager import live_map_manager

    # In the WebSocket endpoint:
    await live_map_manager.connect(websocket)

    # In the MQTT handler (from an async context):
    asyncio.create_task(live_map_manager.broadcast({"topic": ..., "payload": ...}))
"""

import json
import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    Manages a pool of active WebSocket connections.

    Thread-safety note: FastAPI runs on a single-threaded asyncio event loop,
    so list mutations here do not need locks. All methods are async to allow
    awaiting socket I/O without blocking.
    """

    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        """Accept the WebSocket handshake and register the connection."""
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(
            "[WS] Client connected | total_connections=%d | client=%s",
            len(self.active_connections),
            websocket.client,
        )

    def disconnect(self, websocket: WebSocket) -> None:
        """Remove a disconnected WebSocket from the active pool."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(
            "[WS] Client disconnected | total_connections=%d | client=%s",
            len(self.active_connections),
            websocket.client,
        )

    async def broadcast(self, message: dict[str, Any]) -> None:
        """
        Serialize `message` to JSON and send it to every connected client.
        Dead connections are removed gracefully — a single broken client
        will not interrupt delivery to other clients.
        """
        if not self.active_connections:
            return  # fast-path: no clients, nothing to do

        text = json.dumps(message, default=str)
        dead: list[WebSocket] = []

        for connection in self.active_connections:
            try:
                await connection.send_text(text)
            except Exception as exc:
                logger.warning(
                    "[WS] Failed to send to client %s — marking for removal: %s",
                    connection.client,
                    exc,
                )
                dead.append(connection)

        # Prune broken connections after iterating
        for ws in dead:
            self.disconnect(ws)


# ── Singleton shared across the application ───────────────────────────────────
live_map_manager = ConnectionManager()
