"""
app/routers/police.py
─────────────────────
REST endpoints for police unit management and state retrieval.
"""

from fastapi import APIRouter, Depends
from geoalchemy2.shape import to_shape
from sqlalchemy.orm import Session

from app.api.deps import RoleChecker
from app.database import get_db
from app.models.police_unit import PoliceUnit
from app.models.user import User
from app.schemas.police_unit import PoliceUnitResponse

router = APIRouter(prefix="/police", tags=["Police"])


@router.get(
    "/units",
    response_model=list[PoliceUnitResponse],
    summary="Get all police units",
    description="Retrieve all police units with their latest geographic coordinates.",
)
def get_police_units(
    db: Session = Depends(get_db),
    current_user: User = Depends(RoleChecker(["Admin", "Dispatcher"])),
) -> list[PoliceUnitResponse]:
    """
    Fetch all police units from the database.
    Standard frontend and simulation clients can access this.
    """
    units = db.query(PoliceUnit).all()
    results = []
    for unit in units:
        pt = to_shape(unit.location)
        results.append(
            PoliceUnitResponse(
                id=unit.id,
                unit_code=unit.unit_code,
                lat=pt.y,
                lng=pt.x,
                updated_at=unit.updated_at,
            )
        )
    return results
