"""
app/api/routers/websockets.py
──────────────────────────────
WebSocket endpoints for the real-time Live Map bridge.

Clients (React frontend) connect here and receive live MQTT telemetry
broadcasts as JSON messages whenever a vehicle position update arrives.

Route:
    WS  /api/v1/ws/live-map

Message format pushed to clients:
    {
        "topic":   "sih/ambulance/telemetry/<ambulance_id>",
        "payload": {
            "status": "active",
            "lat": 20.2960,
            "lng": 85.8245
        }
    }

JavaScript usage:
    const ws = new WebSocket("ws://localhost:8000/api/v1/ws/live-map");
    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        // update Mapbox marker at data.payload.lat / data.payload.lng
    };
"""

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.ws_manager import live_map_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ws", tags=["WebSocket / Live Map"])


@router.websocket("/live-map")
async def live_map_endpoint(websocket: WebSocket) -> None:
    """
    WebSocket endpoint for the Command Center Live Map.

    Lifecycle:
      1. Accept the connection and register with the ConnectionManager.
      2. Enter a keep-alive loop — the client can send any text
         (e.g., a ping), which we simply acknowledge.
      3. On disconnect (client closes tab / network drop), remove from pool.
    """
    await live_map_manager.connect(websocket)
    logger.info("[WS] Live-map client connected: %s", websocket.client)

    try:
        while True:
            # Keep the connection alive; handle optional client-sent messages.
            # The real data flows in via broadcast() called from the MQTT handler.
            data = await websocket.receive_text()
            logger.debug("[WS] Client %s sent: %s", websocket.client, data)

    except WebSocketDisconnect:
        live_map_manager.disconnect(websocket)
        logger.info("[WS] Live-map client disconnected: %s", websocket.client)

    except Exception as exc:
        logger.exception("[WS] Unexpected error for client %s: %s", websocket.client, exc)
        live_map_manager.disconnect(websocket)
