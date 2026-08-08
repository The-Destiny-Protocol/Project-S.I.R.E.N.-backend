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
import asyncio

from geoalchemy2.shape import from_shape, to_shape
from shapely.geometry import Point, shape
from sqlalchemy.orm import Session
from sqlalchemy import func, cast
from geoalchemy2.types import Geography

from app.database import SessionLocal
from app.models.ambulance import Ambulance
from app.models.traffic import TrafficSignal
from app.models.hospital import Hospital
from app.mqtt.client import mqtt
from app.services.geospatial import find_nearest_police_unit
from app.services.routing_service import calculate_route
from app.services.roip_service import generate_and_dispatch_audio

logger = logging.getLogger(__name__)

# ── Topic constants ────────────────────────────────────────────────────────────
# '+' is the single-level wildcard — matches exactly one topic segment (the ambulance_id).
# '#' would also work at the end but '+' is more precise and avoids matching sub-levels.
TELEMETRY_TOPIC = "sih/ambulance/telemetry/+"
TRIGGER_TOPIC_TEMPLATE = "sih/police/trigger/{police_id}"


# ── Connection callback ────────────────────────────────────────────────────────
@mqtt.on_connect()
def handle_connect(client, flags, rc, properties):
    """
    Called once the MQTT client connects (or reconnects) to the broker.

    gmqtt with MQTT v5 passes rc as a ReasonCode object; MQTT v3.1.1 passes
    a plain int. We normalise both to an int value for comparison.
    rc == 0  → success.
    """
    # Normalise ReasonCode object (gmqtt MQTT v5) or plain int (MQTT v3)
    rc_value = rc.value if hasattr(rc, "value") else int(rc)

    if rc_value == 0:
        logger.info(
            "✅  Connected to MQTT broker at %s — rc=%s. Subscribing to: %s",
            client._host if hasattr(client, "_host") else "broker",
            rc_value,
            TELEMETRY_TOPIC,
        )
        # Subscribe inside on_connect so it auto-resubscribes on reconnection
        client.subscribe(TELEMETRY_TOPIC, qos=1)
    else:
        logger.error(
            "❌  MQTT connection FAILED — rc=%s (%s). Check broker URL, port, credentials, and TLS config.",
            rc_value,
            rc,
        )


# ── Disconnect callback ────────────────────────────────────────────────────────
@mqtt.on_disconnect()
def handle_disconnect(client, packet, exc=None):
    logger.warning("⚠️   MQTT disconnected. Will attempt reconnect. exc=%s", exc)


# ── Message callback ───────────────────────────────────────────────────────────
@mqtt.on_message()
async def handle_message(client, topic: str, payload: bytes, qos: int, properties):
    """
    Dispatches incoming MQTT messages based on topic.

    Expected topic format: sih/ambulance/telemetry/{ambulance_id}
    """
    # Promoted to INFO so every inbound message is visible at default log level
    logger.info(
        "📩  MQTT message received | topic=%s | qos=%s | payload=%s",
        topic,
        qos,
        payload.decode("utf-8", errors="replace"),
    )

    topic_parts = topic.split("/")

    # ── Ambulance telemetry ────────────────────────────────────────────────────
    if len(topic_parts) == 4 and topic_parts[:3] == ["sih", "ambulance", "telemetry"]:
        ambulance_id = topic_parts[3]

        # Parse payload once here so we can broadcast without re-decoding
        try:
            payload_dict: dict = json.loads(payload.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            payload_dict = {"raw": payload.decode("utf-8", errors="replace")}

        # ── Broadcast to all connected WebSocket clients (Live Map) ───────────
        from app.services.ws_manager import live_map_manager  # local import avoids circular deps
        asyncio.create_task(
            live_map_manager.broadcast({"topic": topic, "payload": payload_dict})
        )

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
        if status.lower() == "blocked":
            await _trigger_nearest_police(ambulance_id, lat, lng, db)
            
        # ── 4. Automated Traffic Light Preemption (Route-Aware) ──────────────
        if status.lower() in ["active", "dispatched", "blocked"]:
            if ambulance.active_route_geom is not None:
                # Construct WKT string for the live point so ST_GeogFromText can parse it natively
                ambulance_point_wkt = f"SRID=4326;POINT({lng} {lat})"
                
                # Auto-Rerouting (Route Deviation Check)
                deviation_dist = db.query(
                    func.ST_Distance(
                        cast(func.ST_GeogFromText(ambulance_point_wkt), Geography),
                        cast(func.ST_GeomFromEWKB(ambulance.active_route_geom), Geography)
                    )
                ).scalar()

                if deviation_dist and deviation_dist > 50:
                    logger.warning("🗺️  Ambulance %s deviated from route by %.1fm! Recalculating...", ambulance_id, deviation_dist)
                    hospital = db.get(Hospital, ambulance.target_hospital_id)
                    if hospital:
                        hosp_pt = to_shape(hospital.geom)
                        route_geom, _ = await calculate_route(
                            origin_lat=lat,
                            origin_lng=lng,
                            dest_lat=hosp_pt.y,
                            dest_lng=hosp_pt.x
                        )
                        if route_geom:
                            ambulance.active_route_geom = from_shape(shape(route_geom), srid=4326)
                            db.commit()
                            logger.info("🗺️  Successfully auto-rerouted ambulance %s to %s", ambulance_id, hospital.name)

                
                # Preempt if signal is within 500m of the ambulance AND within 20m of the route
                nearby_signals = db.query(TrafficSignal).filter(
                    func.ST_DWithin(
                        cast(TrafficSignal.geom, Geography),
                        func.ST_GeogFromText(ambulance_point_wkt),
                        500
                    ),
                    func.ST_DWithin(
                        cast(TrafficSignal.geom, Geography),
                        cast(func.ST_GeomFromEWKB(ambulance.active_route_geom), Geography),
                        20
                    )
                ).all()
            else:
                nearby_signals = []

            hospital_name = None
            if ambulance.target_hospital_id:
                hospital_name = db.query(Hospital.name).filter(Hospital.id == ambulance.target_hospital_id).scalar()

            for signal in nearby_signals:
                # Publish Traffic Light Override
                override_topic = f"sih/traffic/signals/{signal.id}/override"
                override_payload = json.dumps({
                    "status": "GREEN", 
                    "ambulance_id": ambulance_id, 
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })
                mqtt.publish(override_topic, override_payload, qos=1)
                logger.info(
                    "🚦  Green Corridor Active! Override published → topic=%s", 
                    override_topic
                )

                # Publish RoIP Walkie-Talkie TTS Alert via MQTT
                if ambulance.radio_channel_id:
                    roip_topic = f"sih/roip/channel/{ambulance.radio_channel_id}/broadcast"
                    roip_payload = json.dumps({
                        "action": "play_tts",
                        "text": f"Alert: Emergency vehicle {ambulance.vehicle_number} is approaching {signal.intersection_name}. Please clear the intersection immediately.",
                        "priority": "HIGH",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    })
                    mqtt.publish(roip_topic, roip_payload, qos=1)
                    logger.info(
                        "📻  RoIP TTS published → topic=%s", 
                        roip_topic
                    )
                
                # Generate and dispatch actual audio to Discord RoIP Gateway
                asyncio.create_task(
                    generate_and_dispatch_audio(
                        police_unit_code="DISPATCH",
                        ambulance_id=str(ambulance.id),
                        vehicle_number=ambulance.vehicle_number,
                        driver_name=ambulance.driver_name or "Unknown",
                        contact_number=ambulance.contact_number or "Unknown",
                        trigger_type="GREEN_CORRIDOR",
                        location_name=signal.intersection_name,
                        destination_name=hospital_name,
                        radio_channel_id=ambulance.radio_channel_id
                    )
                )

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

    mqtt.publish(trigger_topic, trigger_payload, qos=1)

    logger.info(
        "🚨  Trigger published → topic=%s  police_unit_code=%s",
        trigger_topic,
        nearest.unit_code,
    )
