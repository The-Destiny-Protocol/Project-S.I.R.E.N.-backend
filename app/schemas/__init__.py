"""app/schemas/__init__.py — Schemas sub-package."""

from app.schemas.ambulance import (
    AmbulanceRegisterRequest,
    AmbulanceRegisterResponse,
    AmbulanceResponse,
)
from app.schemas.police_unit import PoliceUnitRegisterRequest, PoliceUnitResponse

__all__ = [
    "AmbulanceRegisterRequest",
    "AmbulanceRegisterResponse",
    "AmbulanceResponse",
    "PoliceUnitRegisterRequest",
    "PoliceUnitResponse",
]
