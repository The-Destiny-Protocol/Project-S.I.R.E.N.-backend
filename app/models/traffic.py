"""
app/models/traffic.py
───────────────────────
ORM model for a traffic signal.
"""

import uuid
from datetime import datetime, timezone

from geoalchemy2 import Geometry
from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TrafficSignal(Base):
    __tablename__ = "traffic_signals"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    intersection_name: Mapped[str] = mapped_column(String(200), nullable=False)

    # Lifecycle state: "AUTO" | "GREEN" | "RED"
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="AUTO")

    # GPS position as a PostGIS POINT (longitude, latitude) in WGS-84
    geom: Mapped[object] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self) -> str:
        return f"<TrafficSignal id={self.id} intersection={self.intersection_name} status={self.status}>"
