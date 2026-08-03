"""
app/mqtt/handlers.py
────────────────────
MQTT topic callbacks.

Topic subscriptions:
  sih/ambulance/telemetry/{ambulance_id}
      Inbound GPS telemetry from ambulance hardware.
      Expected JSON payload:
          { "status": "blocked" | "active", "lat": float, "lng": float }

  sih/police/trigger/{police_unit_id}
      Outbound alert published to the nearest police unit.
      Published JSON payload:
          { "flash": true, "ambulance_id": "<uuid>" }

Flow for a "blocked" event:
  1. Parse and validate incoming JSON.
  2. Update the ambulance's location and status in the DB.
  3. Call find_nearest_police_unit() — PostGIS ST_Distance query.
  4. Publish {"flash": true} to sih/police/trigger/{nearest_police_id}.
"""

import json
import logging
from datetime import datetime, timezone

from geoalchemy2.shape import from_shape
from shapely.geometry import Point
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.ambulance import Ambulance
from app.mqtt.client import mqtt
from app.services.geospatial import find_nearest_police_unit

logger = logging.getLogger(__name__)

# ── Topic constants ────────────────────────────────────────────────────────────
TELEMETRY_TOPIC = "sih/ambulance/telemetry/#"  # wildcard — matches all ambulance IDs
TRIGGER_TOPIC_TEMPLATE = "sih/police/trigger/{police_id}"


# ── Connection callback ────────────────────────────────────────────────────────
@mqtt.on_connect()
def handle_connect(client, flags, rc, properties):
    """Called once the MQTT client successfully connects to the broker."""
    if rc == 0:
        logger.info("✅  MQTT connected to broker. Subscribing to telemetry topic.")
        mqtt.client.subscribe(TELEMETRY_TOPIC, qos=1)
    else:
        logger.error("❌  MQTT connection failed with return code: %s", rc)


# ── Disconnect callback ────────────────────────────────────────────────────────
@mqtt.on_disconnect()
def handle_disconnect(client, packet, exc=None):
    logger.warning("⚠️   MQTT disconnected. exc=%s", exc)


# ── Message callback ───────────────────────────────────────────────────────────
@mqtt.on_message()
async def handle_message(client, topic: str, payload: bytes, qos: int, properties):
    """
    Dispatches incoming MQTT messages based on topic.

    Expected topic format: sih/ambulance/telemetry/{ambulance_id}
    """
    logger.debug("📨  MQTT message received | topic=%s qos=%s", topic, qos)

    topic_parts = topic.split("/")

    # ── Ambulance telemetry ────────────────────────────────────────────────────
    if len(topic_parts) == 4 and topic_parts[:3] == ["sih", "ambulance", "telemetry"]:
        ambulance_id = topic_parts[3]
        await _handle_telemetry(ambulance_id, payload)
    else:
        logger.debug("Unhandled topic: %s", topic)


# ── Telemetry handler ──────────────────────────────────────────────────────────
async def _handle_telemetry(ambulance_id: str, raw_payload: bytes) -> None:
    """
    Process a single telemetry message from an ambulance.

    Steps:
      1. Decode and validate the JSON payload.
      2. Upsert the ambulance's location in the database.
      3. If status == "blocked", find the nearest police unit and publish a trigger.
    """
    # ── 1. Parse payload ───────────────────────────────────────────────────────
    try:
        data: dict = json.loads(raw_payload.decode("utf-8"))
        status: str = data["status"]
        lat: float = float(data["lat"])
        lng: float = float(data["lng"])
    except (json.JSONDecodeError, KeyError, ValueError) as exc:
        logger.error(
            "❌  Invalid telemetry payload from ambulance %s: %s | raw=%s",
            ambulance_id,
            exc,
            raw_payload,
        )
        return

    logger.info(
        "🚑  Telemetry | ambulance_id=%s status=%s lat=%.6f lng=%.6f",
        ambulance_id,
        status,
        lat,
        lng,
    )

    # ── 2. Persist location update ─────────────────────────────────────────────
    db: Session = SessionLocal()
    try:
        ambulance: Ambulance | None = db.get(Ambulance, ambulance_id)
        if ambulance is None:
            logger.warning(
                "⚠️   Telemetry received for unknown ambulance_id=%s. Skipping DB update.",
                ambulance_id,
            )
            # We still proceed with the blocked logic if needed, but cannot update DB.
        else:
            ambulance.status = status
            ambulance.location = from_shape(Point(lng, lat), srid=4326)
            ambulance.updated_at = datetime.now(timezone.utc)
            db.commit()

        # ── 3. Trigger nearest police unit if blocked ──────────────────────────
        if status == "blocked":
            await _trigger_nearest_police(ambulance_id, lat, lng, db)

    except Exception as exc:
        db.rollback()
        logger.exception("❌  DB error while processing telemetry: %s", exc)
    finally:
        db.close()


async def _trigger_nearest_police(
    ambulance_id: str,
    lat: float,
    lng: float,
    db: Session,
) -> None:
    """
    Find the nearest police unit and publish a flash-trigger MQTT message.
    """
    nearest = find_nearest_police_unit(lat=lat, lng=lng, db=db)

    if nearest is None:
        logger.error(
            "❌  BLOCKED alert for ambulance %s — no police units registered!",
            ambulance_id,
        )
        return

    trigger_topic = TRIGGER_TOPIC_TEMPLATE.format(police_id=str(nearest.id))
    trigger_payload = json.dumps({"flash": True, "ambulance_id": ambulance_id})

    await mqtt.publish(trigger_topic, trigger_payload, qos=1)

    logger.info(
        "🚨  Trigger published → topic=%s  police_unit_code=%s",
        trigger_topic,
        nearest.unit_code,
    )
