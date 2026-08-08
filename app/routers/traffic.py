"""
app/routers/traffic.py
────────────────────────
REST endpoints for traffic signal resource management.

Routes:
    GET /api/v1/traffic-signals  —  Get all traffic signals.
"""

import logging

from fastapi import APIRouter, Depends
from geoalchemy2.shape import to_shape
from sqlalchemy.orm import Session

from app.api.deps import RoleChecker
from app.database import get_db
from app.models.traffic import TrafficSignal
from app.models.user import User
from app.schemas.traffic import TrafficSignalResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/traffic-signals", tags=["Traffic Signals"])


import json
from typing import Any
from sqlalchemy import func, select

@router.get(
    "",
    response_model=dict[str, Any],
    summary="Get all traffic signals as GeoJSON",
    description="Retrieve all traffic signals formatted as a GeoJSON FeatureCollection.",
)
def get_traffic_signals(
    db: Session = Depends(get_db),
    current_user: User = Depends(RoleChecker(["Admin", "Dispatcher"])),
) -> dict[str, Any]:
    """
    Fetch all traffic signals and return as GeoJSON FeatureCollection.
    """
    stmt = select(
        TrafficSignal.id,
        TrafficSignal.intersection_name,
        TrafficSignal.status,
        func.ST_AsGeoJSON(TrafficSignal.geom).label("geojson")
    )
    rows = db.execute(stmt).all()

    features = []
    for row in rows:
        features.append({
            "type": "Feature",
            "geometry": json.loads(row.geojson),
            "properties": {
                "id": str(row.id),
                "name": row.intersection_name,
                "status": row.status
            }
        })

    return {
        "type": "FeatureCollection",
        "features": features
    }
