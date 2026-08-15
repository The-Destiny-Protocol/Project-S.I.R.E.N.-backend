import json
import logging
from fastapi import APIRouter, status
from pydantic import BaseModel

from app.mqtt.client import mqtt

logger = logging.getLogger(__name__)

router = APIRouter(tags=["SOS"])

class SOSHTTPPayload(BaseModel):
    ambulance_id: str
    lat: float
    lng: float
    status: str

@router.post(
    "/sos",
    status_code=status.HTTP_200_OK,
    summary="HTTP fallback for SOS MQTT publish",
    description=(
        "Accepts SOS payload over plain HTTP POST and publishes it internally to the "
        "HiveMQ MQTT broker. This is a fallback for constrained hardware (e.g., SIM900A) "
        "that struggles with persistent MQTT+TLS connections."
    )
)
async def trigger_sos_http(payload: SOSHTTPPayload):
    topic = f"sih/ambulance/telemetry/{payload.ambulance_id}"
    mqtt_payload = json.dumps({
        "status": payload.status,
        "lat": payload.lat,
        "lng": payload.lng
    })
    
    mqtt.publish(topic, mqtt_payload, qos=1)
    
    logger.info("📡 [HTTP -> MQTT] Forwarded SOS payload for %s to %s", payload.ambulance_id, topic)
    
    return {
        "status": "published",
        "message": f"Payload successfully forwarded to internal MQTT pipeline.",
        "topic": topic
    }
