"""
app/schemas/police_unit.py
──────────────────────────
Pydantic schemas for the PoliceUnit resource.
"""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

# ── Bhubaneswar, Odisha test coordinates ──────────────────────────────────────
_DEFAULT_LAT = 20.2960
_DEFAULT_LNG = 85.8245


class PoliceUnitResponse(BaseModel):
    """Response schema for a police unit returned in corridor status."""

    model_config = {"from_attributes": True}

    id: uuid.UUID = Field(
        ...,
        description="Unique identifier for the police unit.",
        examples=["550e8400-e29b-41d4-a716-446655440000"]
    )
    unit_code: str = Field(
        ...,
        description="Human-readable police unit call-sign, e.g. OD-PCR-001.",
        examples=["OD-PCR-001"]
    )
    lat: Optional[float] = Field(
        None,
        description="Latest latitude (WGS-84).",
        examples=[20.2960]
    )
    lng: Optional[float] = Field(
        None,
        description="Latest longitude (WGS-84).",
        examples=[85.8245]
    )
    updated_at: Optional[datetime] = Field(
        None,
        description="Timestamp of the last telemetry update."
    )


class PoliceUnitRegisterRequest(BaseModel):
    """Body for seeding/registering a new police unit (admin use)."""

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "unit_code": "OD-PCR-001",
                    "lat": _DEFAULT_LAT,
                    "lng": _DEFAULT_LNG,
                }
            ]
        }
    }

    unit_code: str = Field(
        "OD-PCR-001",
        min_length=1,
        max_length=50,
        examples=["OD-PCR-001"],
        description="Human-readable police unit call-sign, e.g. OD-PCR-001.",
    )
    lat: float = Field(
        _DEFAULT_LAT,
        ge=-90.0,
        le=90.0,
        examples=[_DEFAULT_LAT],
        description="Latitude (WGS-84). Default: Bhubaneswar, India.",
    )
    lng: float = Field(
        _DEFAULT_LNG,
        ge=-180.0,
        le=180.0,
        examples=[_DEFAULT_LNG],
        description="Longitude (WGS-84). Default: Bhubaneswar, India.",
    )
