"""
app/routers/hospital.py
───────────────────────
REST endpoints for hospital resource management.

Routes:
    GET /api/v1/hospitals  —  Get all hospitals in GeoJSON format.
"""

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import RoleChecker
from app.database import get_db
from app.models.hospital import Hospital
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/hospitals", tags=["Hospitals"])


@router.get(
    "",
    response_model=dict[str, Any],
    summary="Get all hospitals as GeoJSON",
    description="Retrieve all hospitals formatted as a GeoJSON FeatureCollection for Mapbox rendering.",
)
def get_hospitals(
    db: Session = Depends(get_db),
    current_user: User = Depends(RoleChecker(["Admin", "Dispatcher"])),
) -> dict[str, Any]:
    """
    Fetch all hospitals and return as GeoJSON FeatureCollection.
    """
    stmt = select(
        Hospital.id, 
        Hospital.name, 
        func.ST_AsGeoJSON(Hospital.geom).label("geojson")
    )
    rows = db.execute(stmt).all()

    features = []
    for row in rows:
        features.append({
            "type": "Feature",
            "geometry": json.loads(row.geojson),
            "properties": {
                "id": str(row.id),
                "name": row.name
            }
        })

    return {
        "type": "FeatureCollection",
        "features": features
    }
