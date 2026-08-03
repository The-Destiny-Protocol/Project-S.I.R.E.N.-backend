"""
app/routers/corridor.py
───────────────────────
REST endpoints for live corridor status.

Routes:
    GET /api/v1/corridor/status  —  Return live locations of all active units.
"""

import logging
from typing import List

from fastapi import APIRouter, Depends
from geoalchemy2.shape import to_shape
from sqlalchemy.orm import Session

from app.api.deps import RoleChecker
from app.database import get_db
from app.models.ambulance import Ambulance
from app.models.police_unit import PoliceUnit
from app.models.user import User
from app.schemas.ambulance import AmbulanceResponse
from app.schemas.police_unit import PoliceUnitResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/corridor", tags=["Corridor"])


class CorridorStatusResponse:
    pass


@router.get(
    "/status",
    summary="Live corridor status",
    description=(
        "Returns the current GPS positions of all active ambulances and all "
        "registered police units. Intended for the command-centre dashboard."
    ),
)
def get_corridor_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(RoleChecker(["Admin", "Dispatcher"])),
) -> dict:
    """
    Fetch and serialize all active ambulances + all police units.

    Returns:
        {
          "ambulances": [ { id, operator_type, status, lat, lng, updated_at } ],
          "police_units": [ { id, unit_code, lat, lng, updated_at } ]
        }
    """
    # ── Active ambulances ──────────────────────────────────────────────────────
    ambulance_rows = (
        db.query(Ambulance)
        .filter(Ambulance.status.in_(["active", "blocked"]))
        .all()
    )

    ambulances: List[dict] = []
    for amb in ambulance_rows:
        lat, lng = (None, None)
        if amb.location is not None:
            pt = to_shape(amb.location)
            lat, lng = pt.y, pt.x
        ambulances.append(
            {
                "id": str(amb.id),
                "operator_type": amb.operator_type,
                "status": amb.status,
                "lat": lat,
                "lng": lng,
                "updated_at": amb.updated_at.isoformat() if amb.updated_at else None,
            }
        )

    # ── Police units ───────────────────────────────────────────────────────────
    police_rows = db.query(PoliceUnit).all()

    police_units: List[dict] = []
    for unit in police_rows:
        lat, lng = (None, None)
        if unit.location is not None:
            pt = to_shape(unit.location)
            lat, lng = pt.y, pt.x
        police_units.append(
            {
                "id": str(unit.id),
                "unit_code": unit.unit_code,
                "lat": lat,
                "lng": lng,
                "updated_at": unit.updated_at.isoformat() if unit.updated_at else None,
            }
        )

    logger.debug(
        "Corridor status: %d ambulances, %d police units",
        len(ambulances),
        len(police_units),
    )

    return {"ambulances": ambulances, "police_units": police_units}
