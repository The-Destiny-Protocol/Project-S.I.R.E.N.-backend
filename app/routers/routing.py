"""
app/routers/routing.py
───────────────────────
Endpoints for ambulance routing and dispatch.
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from geoalchemy2.shape import from_shape, to_shape
from shapely.geometry import shape
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.api.deps import RoleChecker
from app.database import get_db
from app.models.ambulance import Ambulance
from app.models.hospital import Hospital
from app.models.user import User
from app.services.routing_service import calculate_route

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ambulances", tags=["Routing"])


@router.post(
    "/{ambulance_id}/dispatch",
    summary="Dispatch ambulance to nearest hospital",
    description="Calculates optimal route to the nearest hospital and saves the active route for traffic preemption.",
)
async def dispatch_ambulance(
    ambulance_id: str,
    db: Session = Depends(get_db),
    current_admin: User = Depends(RoleChecker(["Admin", "Dispatcher"])),
) -> dict[str, Any]:
    # 1. Fetch ambulance
    ambulance = db.get(Ambulance, ambulance_id)
    if not ambulance:
        raise HTTPException(status_code=404, detail="Ambulance not found")
    
    if not ambulance.location:
        raise HTTPException(status_code=400, detail="Ambulance has no active location data")

    # 2. Find nearest hospital
    nearest_hospital = db.query(Hospital).order_by(
        func.ST_Distance(Hospital.geom, ambulance.location)
    ).first()

    if not nearest_hospital:
        raise HTTPException(status_code=404, detail="No hospitals found in database")

    # 3. Calculate route
    amb_pt = to_shape(ambulance.location)
    hosp_pt = to_shape(nearest_hospital.geom)

    route_geom, duration = await calculate_route(
        origin_lat=amb_pt.y,
        origin_lng=amb_pt.x,
        dest_lat=hosp_pt.y,
        dest_lng=hosp_pt.x
    )

    if not route_geom:
        raise HTTPException(status_code=500, detail="Failed to calculate route via Mapbox")

    # 4. Save to DB
    try:
        route_shape = shape(route_geom)
        ambulance.active_route_geom = from_shape(route_shape, srid=4326)
        ambulance.target_hospital_id = nearest_hospital.id
        ambulance.status = "dispatched"
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.exception("❌ DB error saving active route: %s", exc)
        raise HTTPException(status_code=500, detail="Database error saving route")

    logger.info("🚑 Dispatching %s to %s. ETA: %.1fs", ambulance_id, nearest_hospital.name, duration)

    return {
        "message": f"Successfully dispatched to {nearest_hospital.name}",
        "hospital": {
            "id": str(nearest_hospital.id),
            "name": nearest_hospital.name
        },
        "eta_seconds": duration,
        "route_geojson": route_geom
    }
