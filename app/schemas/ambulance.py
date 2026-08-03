"""
app/schemas/ambulance.py
────────────────────────
Pydantic schemas for the Ambulance resource.
"""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class AmbulanceRegisterRequest(BaseModel):
    """Body for POST /api/v1/ambulances/register."""

    operator_type: str = Field(
        ...,
        min_length=1,
        max_length=50,
        examples=["GOVT"],
        description="Operator category, e.g. GOVT, PRIVATE, NGO.",
    )
    lat: float = Field(..., ge=-90.0, le=90.0, description="Initial latitude (WGS-84).")
    lng: float = Field(..., ge=-180.0, le=180.0, description="Initial longitude (WGS-84).")


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
