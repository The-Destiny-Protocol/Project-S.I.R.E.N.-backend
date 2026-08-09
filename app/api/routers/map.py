"""
app/api/routers/map.py
──────────────────────
GeoJSON "World State" endpoints for the Emergency Command Center dashboard.

These endpoints return standard GeoJSON FeatureCollection payloads that
Mapbox GL JS can consume directly to render map markers.

PostGIS handles the geometry → GeoJSON conversion via ST_AsGeoJSON(),
which is more efficient than pulling raw WKB and parsing it in Python.

Routes:
    GET /api/v1/map/ambulances  — All ambulances as a GeoJSON FeatureCollection
    GET /api/v1/map/police      — All police units (with location) as GeoJSON
"""

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import RoleChecker
from app.database import get_db
from app.models.ambulance import Ambulance
from app.models.police_unit import PoliceUnit
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/map", tags=["Map / GeoJSON"])


def _build_feature_collection(features: list[dict[str, Any]]) -> dict[str, Any]:
    """Wrap a list of GeoJSON Feature dicts into a FeatureCollection."""
    return {
        "type": "FeatureCollection",
        "features": features,
    }


# ── GET /ambulances ────────────────────────────────────────────────────────────
@router.get(
    "/ambulances",
    summary="Ambulance World State (GeoJSON)",
    description=(
        "Returns all ambulance records as a GeoJSON FeatureCollection. "
        "Each Feature's geometry is a Point in WGS-84 (SRID 4326). "
        "Properties include: `id`, `status`, `operator_type`, `updated_at`. "
        "Ambulances with no location recorded have a `null` geometry."
    ),
)
def get_ambulances_geojson(
    db: Session = Depends(get_db),
    current_user: User = Depends(RoleChecker(["Admin", "Dispatcher"])),
) -> JSONResponse:
    """
    Query ambulances with PostGIS ST_AsGeoJSON for efficient DB-side conversion.
    The JSON string returned by ST_AsGeoJSON is parsed into a Python dict so
    FastAPI/JSONResponse does not double-escape it.
    """
    rows = db.query(
        Ambulance.id,
        Ambulance.status,
        Ambulance.operator_type,
        Ambulance.updated_at,
        func.ST_AsGeoJSON(Ambulance.location).label("geojson"),
        func.ST_AsGeoJSON(Ambulance.active_route_geom).label("route_geojson"),
    ).all()

    features: list[dict[str, Any]] = []
    for row in rows:
        # ST_AsGeoJSON returns a JSON *string* — parse it so it embeds cleanly.
        geometry = json.loads(row.geojson) if row.geojson else None
        route_geojson = json.loads(row.route_geojson) if row.route_geojson else None

        features.append({
            "type": "Feature",
            "geometry": geometry,
            "properties": {
                "id": str(row.id),
                "status": row.status,
                "operator_type": row.operator_type,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
                "route_geojson": route_geojson,
            },
        })

    logger.debug("GeoJSON /ambulances → %d features", len(features))
    return JSONResponse(content=_build_feature_collection(features))


# ── GET /police ────────────────────────────────────────────────────────────────
@router.get(
    "/police",
    summary="Police Unit World State (GeoJSON)",
    description=(
        "Returns all police units that have a recorded location as a GeoJSON "
        "FeatureCollection. Each Feature's geometry is a Point in WGS-84 (SRID 4326). "
        "Properties include: `id`, `unit_code`, `radio_channel_id`, `updated_at`."
    ),
)
def get_police_geojson(
    db: Session = Depends(get_db),
    current_user: User = Depends(RoleChecker(["Admin", "Dispatcher"])),
) -> JSONResponse:
    """
    Only returns units where location IS NOT NULL, filtered in the DB query.
    ST_AsGeoJSON handles the WKB → GeoJSON Point conversion server-side.
    """
    rows = db.query(
        PoliceUnit.id,
        PoliceUnit.unit_code,
        PoliceUnit.radio_channel_id,
        PoliceUnit.updated_at,
        func.ST_AsGeoJSON(PoliceUnit.location).label("geojson"),
    ).filter(
        PoliceUnit.location.isnot(None)
    ).all()

    features: list[dict[str, Any]] = []
    for row in rows:
        # Parse the JSON string so it nests correctly — no double-escaping.
        geometry = json.loads(row.geojson) if row.geojson else None

        features.append({
            "type": "Feature",
            "geometry": geometry,
            "properties": {
                "id": str(row.id),
                "unit_code": row.unit_code,
                "radio_channel_id": row.radio_channel_id,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            },
        })

    logger.debug("GeoJSON /police → %d features", len(features))
    return JSONResponse(content=_build_feature_collection(features))
