"""
app/routers/ambulance.py
────────────────────────
REST endpoints for ambulance resource management.

Routes:
    POST /api/v1/ambulances/register  —  Register a new ambulance unit.
    POST /api/v1/ambulances/seed-police  —  (Dev helper) Seed a police unit.
"""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from geoalchemy2.shape import from_shape, to_shape
from shapely.geometry import Point
from sqlalchemy.orm import Session
from sqlalchemy import func
import json

from app.api.deps import RoleChecker
from app.database import get_db
from app.models.ambulance import Ambulance
from app.models.police_unit import PoliceUnit
from app.models.user import User
from app.schemas.ambulance import (
    AmbulanceRegisterRequest,
    AmbulanceRegisterResponse,
    AmbulanceResponse,
)
from app.schemas.police_unit import PoliceUnitRegisterRequest, PoliceUnitResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ambulances", tags=["Ambulances"])


@router.post(
    "/register",
    response_model=AmbulanceRegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new ambulance",
    description=(
        "Creates a new Ambulance record with an initial GPS position. "
        "The device should subsequently publish live telemetry to the MQTT topic "
        "`sih/ambulance/telemetry/{returned_id}`."
    ),
)
def register_ambulance(
    body: AmbulanceRegisterRequest,
    db: Session = Depends(get_db),
    current_admin: User = Depends(RoleChecker(["Admin"])),
) -> AmbulanceRegisterResponse:
    ambulance = Ambulance(
        id=uuid.uuid4(),
        operator_type=body.operator_type,
        vehicle_number=body.vehicle_number,
        driver_name=body.driver_name,
        contact_number=body.contact_number,
        equipment_level=body.equipment_level,
        radio_channel_id=body.radio_channel_id,
        status=body.status,
        location=from_shape(Point(body.lng, body.lat), srid=4326),
    )

    try:
        db.add(ambulance)
        db.commit()          # ← explicit COMMIT; only runs if no exception above
        db.refresh(ambulance)
    except Exception as exc:
        db.rollback()        # ← explicit ROLLBACK on any DB error
        logger.exception("❌  Failed to register ambulance: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error while registering ambulance: {exc}",
        )

    logger.info("🚑  Registered ambulance id=%s operator=%s", ambulance.id, ambulance.operator_type)
    return AmbulanceRegisterResponse(id=ambulance.id)


@router.get(
    "/active",
    response_model=list[AmbulanceResponse],
    summary="Get active ambulances",
    description="Retrieve all currently active ambulances with their latest geographic coordinates.",
)
def get_active_ambulances(
    db: Session = Depends(get_db),
    current_user: User = Depends(RoleChecker(["Admin", "Dispatcher"])),
) -> list[AmbulanceResponse]:
    """
    Fetch all active ambulances from the database.
    Standard frontend and simulation clients can access this.
    """
    ambulances = db.query(
        Ambulance, 
        func.ST_AsGeoJSON(Ambulance.active_route_geom).label("route_geojson")
    ).filter(Ambulance.status == "active").all()
    
    results = []
    for amb, route_geojson_str in ambulances:
        if amb.location is None:
            continue
            
        pt = to_shape(amb.location)
        route_geojson = json.loads(route_geojson_str) if route_geojson_str else None
        
        results.append(
            AmbulanceResponse(
                id=amb.id,
                operator_type=amb.operator_type,
                vehicle_number=amb.vehicle_number,
                driver_name=amb.driver_name,
                contact_number=amb.contact_number,
                equipment_level=amb.equipment_level,
                radio_channel_id=amb.radio_channel_id,
                status=amb.status,
                lat=pt.y,
                lng=pt.x,
                updated_at=amb.updated_at,
                route_geojson=route_geojson,
            )
        )
    return results


# ── Dev-helper: seed a police unit ────────────────────────────────────────────
@router.post(
    "/seed-police",
    response_model=PoliceUnitResponse,
    status_code=status.HTTP_201_CREATED,
    summary="[Dev] Seed a police unit",
    description=(
        "Creates a PoliceUnit for local testing. "
        "In production, police units should be managed via a dedicated admin API."
    ),
)
def seed_police_unit(
    body: PoliceUnitRegisterRequest,
    db: Session = Depends(get_db),
    current_admin: User = Depends(RoleChecker(["Admin"])),
) -> PoliceUnitResponse:
    # ── Duplicate check ────────────────────────────────────────────────────────
    try:
        existing = db.query(PoliceUnit).filter(PoliceUnit.unit_code == body.unit_code).first()
    except Exception as exc:
        logger.exception("❌  DB error during duplicate check: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error during duplicate check: {exc}",
        )

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"PoliceUnit with unit_code '{body.unit_code}' already exists.",
        )

    # ── Insert ─────────────────────────────────────────────────────────────────
    unit = PoliceUnit(
        id=uuid.uuid4(),
        unit_code=body.unit_code,
        location=from_shape(Point(body.lng, body.lat), srid=4326),
    )

    try:
        db.add(unit)
        db.commit()          # ← explicit COMMIT
        db.refresh(unit)
    except Exception as exc:
        db.rollback()        # ← explicit ROLLBACK on any DB error
        logger.exception("❌  Failed to seed police unit: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error while seeding police unit: {exc}",
        )

    logger.info("🚔  Seeded police unit id=%s code=%s", unit.id, unit.unit_code)

    # Extract lat/lng from PostGIS geometry for the response
    pt = to_shape(unit.location)
    return PoliceUnitResponse(
        id=unit.id,
        unit_code=unit.unit_code,
        lat=pt.y,
        lng=pt.x,
        updated_at=unit.updated_at,
    )
