"""
app/models/incident.py
──────────────────────
ORM model for an emergency SOS incident.

Created when an ambulance triggers an SOS (manually by the driver, or
automatically by the onboard AI vision system).  Records which police unit
was dispatched and the GPS snapshot of the incident location.
"""

import uuid
from datetime import datetime, timezone

from geoalchemy2 import Geometry
from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class EmergencyIncident(Base):
    __tablename__ = "emergency_incidents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # ── Foreign Keys ────────────────────────────────────────────────────────────
    ambulance_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ambulances.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Nullable: a unit might not be found if no police units are registered.
    police_unit_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("police_units.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # ── Trigger metadata ────────────────────────────────────────────────────────
    # Allowed values: "MANUAL_DRIVER_SOS" | "AUTO_VISION_ANOMALY"
    trigger_source: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="MANUAL_DRIVER_SOS",
    )

    # GPS snapshot at the time of the SOS event (longitude, latitude in WGS-84)
    location: Mapped[object] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326),
        nullable=True,
    )

    # Lifecycle state: "DISPATCHED" | "RESOLVED" | "CANCELLED"
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="DISPATCHED",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    # ── Relationships (for convenience; not required by the endpoint) ───────────
    ambulance = relationship("Ambulance", foreign_keys=[ambulance_id], lazy="select")
    police_unit = relationship("PoliceUnit", foreign_keys=[police_unit_id], lazy="select")

    def __repr__(self) -> str:
        return (
            f"<EmergencyIncident id={self.id} trigger={self.trigger_source} "
            f"status={self.status}>"
        )
