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

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db
from app.mqtt.client import mqtt

# Import handlers so @mqtt decorator side-effects are executed at import time.
import app.mqtt.handlers  # noqa: F401

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

    yield  # Application is running

    logger.info("🛑  Shutting down. Closing MQTT Connection...")
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
        allow_origins=["*"],   # Tighten this in production
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Routers ────────────────────────────────────────────────────────────────
    from app.api.routers import auth as auth_router
    app.include_router(auth_router.router, prefix="/api/v1")
    app.include_router(ambulance_router.router, prefix="/api/v1")
    app.include_router(corridor_router.router, prefix="/api/v1")

    # ── Health check ───────────────────────────────────────────────────────────
    @app.get("/health", tags=["Health"])
    def health_check():
        return {"status": "ok", "version": settings.app_version}

    return app


app = create_app()
