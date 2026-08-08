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
                    "vehicle_number": "OD-02-A-108",
                    "driver_name": "Rajesh Mohanty",
                    "contact_number": "+919876543210",
                    "equipment_level": "BLS",
                    "radio_channel_id": "CH-01",
                    "status": "active",
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
    vehicle_number: str = Field(
        ...,
        examples=["OD-02-A-108"],
        description="Unique vehicle registration number."
    )
    driver_name: str = Field(
        ...,
        examples=["Rajesh Mohanty"],
        description="Name of the ambulance driver."
    )
    contact_number: str = Field(
        ...,
        examples=["+919876543210"],
        description="Contact number for the driver/vehicle."
    )
    equipment_level: str = Field(
        "BLS",
        examples=["BLS"],
        description="Equipment level (e.g. ALS, BLS)."
    )
    radio_channel_id: Optional[str] = Field(
        None,
        examples=["CH-01"],
        description="Assigned RoIP radio channel."
    )
    status: Optional[str] = Field(
        default="active",
        examples=["active"],
        description="Operational status (e.g. active, inactive, blocked)."
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

    id: uuid.UUID = Field(
        ..., 
        description="Unique identifier for the ambulance.", 
        examples=["123e4567-e89b-12d3-a456-426614174000"]
    )
    operator_type: str = Field(
        ...,
        description="Operator category, e.g. GOVT, PRIVATE, NGO.",
        examples=["GOVT"]
    )
    vehicle_number: str = Field(
        ...,
        description="Unique vehicle registration number."
    )
    driver_name: str = Field(
        ...,
        description="Name of the ambulance driver."
    )
    contact_number: str = Field(
        ...,
        description="Contact number for the driver/vehicle."
    )
    equipment_level: str = Field(
        ...,
        description="Equipment level (e.g. ALS, BLS)."
    )
    radio_channel_id: Optional[str] = Field(
        None,
        description="Assigned RoIP radio channel."
    )
    status: str = Field(
        ...,
        description="Current operational status (e.g. active, inactive, dispatched).",
        examples=["active"]
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


class AmbulanceRegisterResponse(BaseModel):
    """Minimal response returned after successful registration."""

    id: uuid.UUID
    message: str = "Ambulance registered successfully."
