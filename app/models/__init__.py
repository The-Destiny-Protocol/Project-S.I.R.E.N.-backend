"""app/models/__init__.py — re-export all ORM models for convenient importing."""

from app.models.ambulance import Ambulance
from app.models.police_unit import PoliceUnit

__all__ = ["Ambulance", "PoliceUnit"]
