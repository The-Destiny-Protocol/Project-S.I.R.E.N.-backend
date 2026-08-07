"""
app/schemas/incident.py
───────────────────────
Pydantic V2 schemas for Emergency SOS request / response.
"""

import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class SOSRequest(BaseModel):
    """
    Payload sent by the ambulance driver or edge-AI system to trigger an SOS.
    """

    lat: float = Field(
        ...,
        description="Latitude of the SOS event (WGS-84).",
        examples=[20.2960],
    )
    lng: float = Field(
        ...,
        description="Longitude of the SOS event (WGS-84).",
        examples=[85.8245],
    )
    trigger_type: Literal["MANUAL_DRIVER_SOS", "AUTO_VISION_ANOMALY"] = Field(
        ...,
        description=(
            "Source of the SOS trigger. "
            "'MANUAL_DRIVER_SOS' = driver pressed the panic button. "
            "'AUTO_VISION_ANOMALY' = edge-AI vision system detected a blockage."
        ),
        examples=["MANUAL_DRIVER_SOS"],
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "lat": 20.2960,
                    "lng": 85.8245,
                    "trigger_type": "MANUAL_DRIVER_SOS",
                }
            ]
        }
    }


class SOSResponse(BaseModel):
    """
    Response returned immediately after a successful SOS dispatch.
    The audio alert is sent asynchronously in the background.
    """

    incident_id: uuid.UUID = Field(
        ...,
        description="UUID of the newly created EmergencyIncident record.",
    )
    police_unit_code: Optional[str] = Field(
        None,
        description="Unit code of the dispatched police unit (e.g. 'OD-PCR-001').",
        examples=["OD-PCR-001"],
    )
    radio_channel_id: Optional[str] = Field(
        None,
        description="Radio channel assigned to the dispatched police unit.",
        examples=["ALPHA-7"],
    )
    ambulance_status: str = Field(
        ...,
        description="Updated ambulance status after SOS is triggered.",
        examples=["SOS_ACTIVE"],
    )
    status: str = Field(
        ...,
        description="Incident status.",
        examples=["DISPATCHED"],
    )
    message: str = Field(
        ...,
        description="Human-readable confirmation message.",
        examples=["SOS dispatched. Voice alert queued for OD-PCR-001 on channel ALPHA-7."],
    )
    created_at: datetime = Field(
        ...,
        description="UTC timestamp when the incident was created.",
    )

    model_config = {"from_attributes": True}


# ── Supporting nested schemas ─────────────────────────────────────────────────

class AmbulanceSummary(BaseModel):
    """Minimal ambulance context embedded inside an active incident response."""

    id: uuid.UUID
    status: str
    operator_type: str
    vehicle_number: str
    driver_name: str
    contact_number: str
    equipment_level: str
    radio_channel_id: Optional[str]

    model_config = {"from_attributes": True}


class PoliceUnitSummary(BaseModel):
    """Minimal police unit context embedded inside an active incident response."""

    id: uuid.UUID
    unit_code: str
    radio_channel_id: Optional[str]

    model_config = {"from_attributes": True}


# ── GET /incidents/active ─────────────────────────────────────────────────────

class IncidentDetailResponse(BaseModel):
    """
    Full incident record returned by GET /incidents/active,
    with nested ambulance and police_unit context for the dashboard.
    """

    id: uuid.UUID = Field(..., description="Unique ID of the incident.")
    ambulance_id: uuid.UUID
    police_unit_id: Optional[uuid.UUID]
    trigger_source: str = Field(
        ...,
        description="'MANUAL_DRIVER_SOS' or 'AUTO_VISION_ANOMALY'.",
        examples=["MANUAL_DRIVER_SOS"],
    )
    status: str = Field(..., examples=["DISPATCHED"])
    created_at: datetime

    # Nested objects resolved from FK joins
    ambulance: Optional[AmbulanceSummary] = None
    police_unit: Optional[PoliceUnitSummary] = None

    model_config = {"from_attributes": True}


# ── PATCH /incidents/{id}/resolve ─────────────────────────────────────────────

class IncidentResolveResponse(BaseModel):
    """Response returned after successfully resolving an incident."""

    incident_id: uuid.UUID
    status: str = Field(..., examples=["RESOLVED"])
    message: str = Field(..., examples=["Incident e89c6cbc-... resolved successfully."])
    resolved_at: datetime

    model_config = {"from_attributes": True}
