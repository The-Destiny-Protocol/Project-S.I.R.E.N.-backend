"""
app/routers/emergency.py
────────────────────────
REST endpoints for the Emergency SOS / RoIP dispatch pipeline.

Routes:
    POST /api/v1/emergency/ambulances/{ambulance_id}/sos
        Trigger an SOS for a specific ambulance:
          1. Update ambulance status → "SOS_ACTIVE"
          2. Find the nearest police unit (PostGIS ST_Distance)
          3. Persist an EmergencyIncident record
          4. Queue a background voice alert (pyttsx3 → RoIP gateway)
          5. Return SOSResponse immediately (non-blocking)

    POST /api/v1/emergency/mock-roip-gateway
        Development stub that accepts the dispatched .wav bytes and logs them.
        Replace with a real RoIP gateway URL in production.
"""

import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from geoalchemy2.shape import from_shape
from shapely.geometry import Point
from sqlalchemy.orm import Session

from app.api.deps import RoleChecker
from app.database import get_db
from app.models.ambulance import Ambulance
from app.models.incident import EmergencyIncident
from app.models.user import User
from app.schemas.incident import SOSRequest, SOSResponse
from app.services.geospatial import find_nearest_police_unit
from app.services.roip_service import generate_and_dispatch_audio

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/emergency", tags=["Emergency Dispatch"])


# ── SOS Trigger Endpoint ──────────────────────────────────────────────────────
@router.post(
    "/ambulances/{ambulance_id}/sos",
    response_model=SOSResponse,
    status_code=status.HTTP_200_OK,
    summary="Trigger an Emergency SOS",
    description=(
        "Triggers an SOS for the specified ambulance. "
        "Locates the nearest police unit via PostGIS, records an EmergencyIncident, "
        "and asynchronously dispatches a voice alert to the RoIP gateway. "
        "Returns immediately — audio dispatch runs in the background."
    ),
)
def trigger_sos(
    ambulance_id: str,
    body: SOSRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(RoleChecker(["StandardUser", "Dispatcher", "Admin"])),
) -> SOSResponse:
    # ── 1. Fetch and validate the ambulance ────────────────────────────────────
    try:
        amb_uuid = uuid.UUID(ambulance_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid ambulance_id format: '{ambulance_id}' is not a valid UUID.",
        )

    ambulance = db.get(Ambulance, amb_uuid)
    if ambulance is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ambulance with id '{ambulance_id}' not found.",
        )

    # ── 2. Update ambulance status to SOS_ACTIVE ───────────────────────────────
    try:
        ambulance.status = "SOS_ACTIVE"
        ambulance.location = from_shape(Point(body.lng, body.lat), srid=4326)
        db.commit()
        db.refresh(ambulance)
    except Exception as exc:
        db.rollback()
        logger.exception("❌  Failed to update ambulance status: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error while updating ambulance: {exc}",
        )

    logger.info(
        "🚨  SOS triggered | ambulance_id=%s trigger=%s lat=%.5f lng=%.5f",
        ambulance_id, body.trigger_type, body.lat, body.lng,
    )

    # ── 3. Find nearest police unit ────────────────────────────────────────────
    nearest_unit = find_nearest_police_unit(lat=body.lat, lng=body.lng, db=db)

    if nearest_unit is None:
        logger.warning("⚠️   No police units registered — cannot dispatch RoIP alert.")

    # ── 4. Create EmergencyIncident record ─────────────────────────────────────
    incident = EmergencyIncident(
        id=uuid.uuid4(),
        ambulance_id=amb_uuid,
        police_unit_id=nearest_unit.id if nearest_unit else None,
        trigger_source=body.trigger_type,
        location=from_shape(Point(body.lng, body.lat), srid=4326),
        status="DISPATCHED",
    )

    try:
        db.add(incident)
        db.commit()
        db.refresh(incident)
    except Exception as exc:
        db.rollback()
        logger.exception("❌  Failed to persist EmergencyIncident: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error while creating incident: {exc}",
        )

    logger.info("📋  EmergencyIncident created | incident_id=%s", incident.id)

    # ── 5. Queue background voice alert ───────────────────────────────────────
    if nearest_unit:
        background_tasks.add_task(
            generate_and_dispatch_audio,
            police_unit_code=nearest_unit.unit_code,
            ambulance_id=ambulance_id,
            trigger_type=body.trigger_type,
            radio_channel_id=nearest_unit.radio_channel_id,
        )
        logger.info(
            "🔊  Voice alert queued for unit=%s channel=%s",
            nearest_unit.unit_code,
            nearest_unit.radio_channel_id,
        )

    # ── 6. Build and return response ───────────────────────────────────────────
    unit_code = nearest_unit.unit_code if nearest_unit else None
    channel = nearest_unit.radio_channel_id if nearest_unit else None

    if unit_code:
        msg = f"SOS dispatched. Voice alert queued for {unit_code}"
        msg += f" on channel {channel}." if channel else "."
    else:
        msg = "SOS recorded. No police units currently registered — manual dispatch required."

    return SOSResponse(
        incident_id=incident.id,
        police_unit_code=unit_code,
        radio_channel_id=channel,
        ambulance_status="SOS_ACTIVE",
        status="DISPATCHED",
        message=msg,
        created_at=incident.created_at,
    )


# ── Mock RoIP Gateway (Dev Stub) ──────────────────────────────────────────────
@router.post(
    "/mock-roip-gateway",
    summary="[Dev] Mock RoIP Gateway",
    description=(
        "Development stub that simulates a Radio-over-IP gateway. "
        "Accepts a raw .wav audio payload and logs it. "
        "Replace the target URL in `roip_service.py` with a real gateway in production."
    ),
    tags=["Emergency Dispatch"],
)
async def mock_roip_gateway(request: Request) -> dict:
    body_bytes = await request.body()
    police_unit = request.headers.get("X-Police-Unit", "UNKNOWN")
    ambulance_id = request.headers.get("X-Ambulance-Id", "UNKNOWN")
    trigger = request.headers.get("X-Trigger-Type", "UNKNOWN")
    content_type = request.headers.get("Content-Type", "unknown")

    logger.info(
        "📻  [MOCK RoIP GATEWAY] Received audio dispatch | "
        "unit=%s ambulance=%s trigger=%s content-type=%s size=%d bytes",
        police_unit, ambulance_id, trigger, content_type, len(body_bytes),
    )

    return {
        "status": "received",
        "gateway": "mock-roip",
        "police_unit": police_unit,
        "ambulance_id": ambulance_id,
        "trigger_type": trigger,
        "audio_size_bytes": len(body_bytes),
        "message": "Audio payload received by mock gateway. In production, this would be broadcast over radio.",
    }
