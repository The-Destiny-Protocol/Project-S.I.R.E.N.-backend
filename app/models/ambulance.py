"""
app/models/ambulance.py
───────────────────────
ORM model for an ambulance unit.

PostGIS POINT geometry stores the last-known GPS position in WGS-84 (SRID 4326).
"""

import uuid
from datetime import datetime, timezone

from geoalchemy2 import Geometry
from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Ambulance(Base):
    __tablename__ = "ambulances"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Human-readable operator category, e.g. "GOVT", "PRIVATE", "NGO"
    operator_type: Mapped[str] = mapped_column(String(50), nullable=False)

    # Lifecycle state: "active" | "blocked" | "inactive"
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")

    # Last-known GPS position as a PostGIS POINT (longitude, latitude) in WGS-84
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
        return f"<Ambulance id={self.id} status={self.status}>"
