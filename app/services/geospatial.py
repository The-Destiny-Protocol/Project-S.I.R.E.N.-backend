"""
app/services/geospatial.py
──────────────────────────
Core geospatial query logic using GeoAlchemy2 and PostGIS.

Key function:
    find_nearest_police_unit(lat, lng, db) → PoliceUnit | None

PostGIS approach:
  - Cast both geometries to ::geography so ST_Distance returns metres (not degrees).
  - ORDER BY distance ASC, LIMIT 1  →  O(n) table scan; acceptable for MVP scale.
  - For production with large datasets, add a GIST index on the location column and
    consider ST_DWithin for a radius pre-filter.
"""

import logging
from typing import Optional

from geoalchemy2.functions import ST_Distance, ST_MakePoint, ST_SetSRID
from sqlalchemy import cast, func
from sqlalchemy.orm import Session

from app.models.police_unit import PoliceUnit

logger = logging.getLogger(__name__)

# PostGIS geography type string (used for accurate metre-based distance)
_GEOGRAPHY = "geography"


def find_nearest_police_unit(
    lat: float,
    lng: float,
    db: Session,
) -> Optional[PoliceUnit]:
    """
    Return the PoliceUnit geographically closest to (lat, lng).

    Uses ST_Distance with ::geography cast so distances are in metres,
    not degree-units (which are not uniform across latitudes).

    Args:
        lat: Latitude of the query point (WGS-84).
        lng: Longitude of the query point (WGS-84).
        db:  Active SQLAlchemy Session.

    Returns:
        The nearest PoliceUnit ORM object, or None if no units are registered.
    """
    # Build the query point: ST_SetSRID(ST_MakePoint(lng, lat), 4326)::geography
    # Note: PostGIS convention is (longitude, latitude) for ST_MakePoint.
    query_point = cast(
        ST_SetSRID(ST_MakePoint(lng, lat), 4326),
        _GEOGRAPHY,
    )

    nearest: Optional[PoliceUnit] = (
        db.query(PoliceUnit)
        .filter(PoliceUnit.location.isnot(None))
        .order_by(
            ST_Distance(
                cast(PoliceUnit.location, _GEOGRAPHY),
                query_point,
            )
        )
        .first()
    )

    if nearest:
        logger.info(
            "Nearest police unit found: id=%s unit_code=%s",
            nearest.id,
            nearest.unit_code,
        )
    else:
        logger.warning("No police units found in the database.")

    return nearest


def haversine_distance_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """
    Pure-Python Haversine distance (metres) — useful for logging / unit tests
    without a DB connection.  Not used in the hot path.
    """
    import math

    R = 6_371_000  # Earth radius in metres
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
