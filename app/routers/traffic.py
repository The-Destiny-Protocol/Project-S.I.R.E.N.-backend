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


@router.get(
    "",
    response_model=list[TrafficSignalResponse],
    summary="Get all traffic signals",
    description="Retrieve all traffic signals with their current geographic coordinates.",
)
def get_traffic_signals(
    db: Session = Depends(get_db),
    current_user: User = Depends(RoleChecker(["Admin", "Dispatcher"])),
) -> list[TrafficSignalResponse]:
    """
    Fetch all traffic signals from the database.
    """
    signals = db.query(TrafficSignal).all()
    results = []
    for sig in signals:
        pt = to_shape(sig.geom)
        results.append(
            TrafficSignalResponse(
                id=sig.id,
                intersection_name=sig.intersection_name,
                status=sig.status,
                lat=pt.y,
                lng=pt.x,
                updated_at=sig.updated_at,
            )
        )
    return results
