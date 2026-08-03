"""
app/schemas/police_unit.py
──────────────────────────
Pydantic schemas for the PoliceUnit resource.
"""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class PoliceUnitResponse(BaseModel):
    """Response schema for a police unit returned in corridor status."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    unit_code: str
    lat: Optional[float] = None
    lng: Optional[float] = None
    updated_at: Optional[datetime] = None


class PoliceUnitRegisterRequest(BaseModel):
    """Body for seeding/registering a new police unit (admin use)."""

    unit_code: str = Field(..., min_length=1, max_length=50, examples=["DL-PCR-042"])
    lat: float = Field(..., ge=-90.0, le=90.0)
    lng: float = Field(..., ge=-180.0, le=180.0)
