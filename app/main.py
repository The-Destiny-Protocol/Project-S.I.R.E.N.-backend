"""
app/main.py
───────────
FastAPI application factory.

Startup sequence:
  1. init_db()       — enable PostGIS extension + create all tables.
  2. mqtt.init_app() — connect FastMQTT to the broker and register handlers.

All MQTT topic callbacks are registered by importing app.mqtt.handlers
(the @mqtt decorator side-effects register them on the shared `mqtt` instance).
"""

import logging
from contextlib import asynccontextmanager
import asyncio

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db
from app.mqtt.client import mqtt

# Import handlers so @mqtt decorator side-effects are executed at import time.
import app.mqtt.handlers  # noqa: F401
from app.mqtt.handlers import flush_telemetry_to_db

from app.routers import ambulance as ambulance_router
from app.routers import corridor as corridor_router

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG if settings.app_env == "development" else logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ── Lifespan (startup / shutdown) ──────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle application startup and shutdown events."""
    logger.info("🚀  Starting %s v%s [env=%s]", settings.app_title, settings.app_version, settings.app_env)

    # 1. Database — create PostGIS extension + all tables
    logger.info("🗄️   Initialising database …")
    init_db()
    logger.info("🗄️   Database ready.")

    # 1.5. Clear Ghost States
    logger.info("🚦  Resetting all Traffic Signals to 'AUTO' state...")
    from app.database import SessionLocal
    from app.models.traffic import TrafficSignal
    db = SessionLocal()
    try:
        db.query(TrafficSignal).update({TrafficSignal.status: "AUTO"})
        db.commit()
    except Exception as exc:
        logger.error("Failed to reset traffic signals: %s", exc)
        db.rollback()
    finally:
        db.close()

    # ── MQTT ───────────────────────────────────────────────────────────────────
    logger.info("📡  Initiating MQTT Connection to %s:%s …", settings.mqtt_broker_url, settings.mqtt_port)
    try:
        await mqtt.mqtt_startup()
    except Exception as exc:
        logger.warning(
            "⚠️  MQTT broker connection failed at startup: %s\n"
            "    REST endpoints will still work. MQTT will retry via reconnect logic.",
            exc,
        )

    # ── Background Tasks ───────────────────────────────────────────────────────
    logger.info("🕒  Starting background task: flush_telemetry_to_db")
    flush_task = asyncio.create_task(flush_telemetry_to_db())

    yield  # Application is running

    logger.info("🛑  Shutting down. Cancelling background tasks...")
    flush_task.cancel()
    await mqtt.mqtt_shutdown()


# ── App factory ────────────────────────────────────────────────────────────────
def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_title,
        version=settings.app_version,
        description=(
            "Backend API for the Intelligent Ambulance Priority & De-Congestion System. "
            "Ingests live GPS telemetry over MQTT, performs PostGIS spatial queries to "
            "locate the nearest police unit, and publishes flash-trigger alerts."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )
    mqtt.init_app(app)

    # ── CORS ───────────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Routers ────────────────────────────────────────────────────────────────
    from app.api.routers import auth as auth_router
    from app.api.routers import map as map_router
    from app.api.routers import websockets as ws_router
    from app.routers import emergency as emergency_router
    from app.routers import police as police_router
    from app.routers import traffic as traffic_router
    from app.routers import routing as routing_router
    from app.routers import hospital as hospital_router

    app.include_router(auth_router.router, prefix="/api/v1")
    app.include_router(ambulance_router.router, prefix="/api/v1")
    app.include_router(corridor_router.router, prefix="/api/v1")
    app.include_router(police_router.router, prefix="/api/v1")
    app.include_router(emergency_router.router, prefix="/api/v1")
    app.include_router(map_router.router, prefix="/api/v1")
    app.include_router(ws_router.router, prefix="/api/v1")
    app.include_router(traffic_router.router, prefix="/api/v1")
    app.include_router(routing_router.router, prefix="/api/v1")
    app.include_router(hospital_router.router, prefix="/api/v1")



    # ── Health check ───────────────────────────────────────────────────────────
    @app.get("/health", tags=["Health"])
    def health_check():
        return {"status": "ok", "version": settings.app_version}

    # ── Dedicated Telemetry WebSocket (Bypasses all checks) ────────────────────
    @app.websocket("/ws/telemetry")
    async def telemetry_websocket(websocket: WebSocket):
        from app.services.ws_manager import live_map_manager
        await live_map_manager.connect(websocket)
        logger.info("[WS] Legacy /ws/telemetry client connected: %s", websocket.client)
        try:
            while True:
                data = await websocket.receive_text()
        except WebSocketDisconnect:
            live_map_manager.disconnect(websocket)
            logger.info("[WS] /ws/telemetry client disconnected")
        except Exception as exc:
            logger.exception("[WS] Unexpected error for /ws/telemetry client: %s", exc)
            live_map_manager.disconnect(websocket)

    return app


app = create_app()
