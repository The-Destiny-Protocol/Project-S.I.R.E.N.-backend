"""
app/models/police_unit.py
─────────────────────────
ORM model for a police unit.

PostGIS POINT geometry stores the officer/vehicle's current GPS position in WGS-84.
"""

import uuid
from datetime import datetime, timezone

from geoalchemy2 import Geometry
from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PoliceUnit(Base):
    __tablename__ = "police_units"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Human-readable badge / call-sign, e.g. "DL-PCR-042"
    unit_code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)

    # Radio channel / call-sign used for RoIP / walkie-talkie dispatch
    # e.g. "ALPHA-7", "CH-04". Nullable for units not yet assigned a radio.
    radio_channel_id: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Current GPS position as a PostGIS POINT (longitude, latitude) in WGS-84
    location: Mapped[object] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326),
        nullable=True,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self) -> str:
        return f"<PoliceUnit id={self.id} unit_code={self.unit_code}>"
