"""
app/services/routing_service.py
───────────────────────────────
Integration with Mapbox Directions API for calculating optimal routes.
"""

import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

async def calculate_route(
    origin_lat: float, origin_lng: float, dest_lat: float, dest_lng: float
) -> tuple[dict[str, Any] | None, float]:
    """
    Calls the Mapbox Directions API to calculate the driving route.

    Returns:
        A tuple of (geometry_geojson_dict, duration_seconds).
        If the request fails, returns (None, 0.0).
    """
    if not settings.mapbox_access_token:
        logger.error("❌ Mapbox access token is missing in settings.")
        return None, 0.0

    url = (
        f"https://api.mapbox.com/directions/v5/mapbox/driving-traffic/"
        f"{origin_lng},{origin_lat};{dest_lng},{dest_lat}"
    )
    
    params = {
        "geometries": "geojson",
        "access_token": settings.mapbox_access_token,
        "overview": "full",
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params, timeout=10.0)
            response.raise_for_status()
            data = response.json()

            if data.get("code") != "Ok" or not data.get("routes"):
                logger.error("❌ Mapbox API returned no routes: %s", data)
                return None, 0.0

            route = data["routes"][0]
            geometry = route.get("geometry")
            duration = route.get("duration", 0.0)

            return geometry, duration

    except httpx.HTTPError as exc:
        logger.exception("❌ HTTP error while calling Mapbox Directions API: %s", exc)
        return None, 0.0
    except Exception as exc:
        logger.exception("❌ Unexpected error while calculating route: %s", exc)
        return None, 0.0
