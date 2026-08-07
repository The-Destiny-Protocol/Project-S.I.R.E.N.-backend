"""
app/schemas/traffic.py
────────────────────────
Pydantic schemas for the Traffic Signal resource.
"""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

class TrafficSignalResponse(BaseModel):
    """Response schema for a traffic signal."""

    model_config = {"from_attributes": True}

    id: uuid.UUID = Field(..., description="Unique identifier for the traffic signal.")
    intersection_name: str = Field(..., description="Name of the intersection.")
    status: str = Field(..., description="Current status of the signal (e.g. AUTO, GREEN, RED).")
    lat: Optional[float] = Field(None, description="Latitude (WGS-84).")
    lng: Optional[float] = Field(None, description="Longitude (WGS-84).")
    updated_at: Optional[datetime] = Field(None, description="Timestamp of the last update.")
