"""
app/schemas/ambulance.py
────────────────────────
Pydantic schemas for the Ambulance resource.
"""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

# ── Bhubaneswar, Odisha test coordinates ──────────────────────────────────────
_DEFAULT_LAT = 20.2960
_DEFAULT_LNG = 85.8245


class AmbulanceRegisterRequest(BaseModel):
    """Body for POST /api/v1/ambulances/register."""

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "operator_type": "GOVT",
                    "lat": _DEFAULT_LAT,
                    "lng": _DEFAULT_LNG,
                }
            ]
        }
    }

    operator_type: str = Field(
        "GOVT",
        min_length=1,
        max_length=50,
        examples=["GOVT"],
        description="Operator category, e.g. GOVT, PRIVATE, NGO.",
    )
    lat: float = Field(
        _DEFAULT_LAT,
        ge=-90.0,
        le=90.0,
        examples=[_DEFAULT_LAT],
        description="Initial latitude (WGS-84). Default: Bhubaneswar, India.",
    )
    lng: float = Field(
        _DEFAULT_LNG,
        ge=-180.0,
        le=180.0,
        examples=[_DEFAULT_LNG],
        description="Initial longitude (WGS-84). Default: Bhubaneswar, India.",
    )


class AmbulanceResponse(BaseModel):
    """Response schema for a registered or queried ambulance."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    operator_type: str
    status: str
    lat: Optional[float] = None
    lng: Optional[float] = None
    updated_at: Optional[datetime] = None


class AmbulanceRegisterResponse(BaseModel):
    """Minimal response returned after successful registration."""

    id: uuid.UUID
    message: str = "Ambulance registered successfully."
