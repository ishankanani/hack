"""
Live-data providers with honest status.

States:
    LIVE
    STALE
    ERROR
    NOT_CONFIGURED

Providers:
    - Weather:  Open-Meteo (keyless)
    - Holidays: provided kalender.csv
    - Routing:  OSRM public server
    - Traffic:  TomTom Traffic Flow API

Environment variables:
    TOMTOM_API_KEY
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import httpx


# How long successful data remains considered fresh.
STALE_AFTER_S = {
    "weather": 1800,    # 30 minutes
    "traffic": 600,     # 10 minutes
    "routing": 86400,   # 24 hours
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Provider:
    def __init__(
        self,
        key: str,
        name: str,
        configured: bool,
        kind: str,
    ):
        self.key = key
        self.name = name
        self.configured = configured
        self.kind = kind

        self.last_success: datetime | None = None
        self.last_attempt: datetime | None = None
        self.data_timestamp: datetime | None = None
        self.error: str | None = None

        self._cache: Any = None

    def status(self) -> str:
        if not self.configured:
            return "NOT_CONFIGURED"

        if self.error and self.last_success is None:
            return "ERROR"

        if self.last_success is None:
            return "ERROR"

        age = (_now() - self.last_success).total_seconds()

        if age > STALE_AFTER_S.get(self.key, 3600):
            return "STALE"

        return "LIVE"

    def to_dict(self) -> dict:
        def iso(value: datetime | None):
            return value.isoformat() if value else None

        return {
            "key": self.key,
            "name": self.name,
            "status": self.status(),
            "configured": self.configured,
            "kind": self.kind,
            "last_success": iso(self.last_success),
            "last_attempt": iso(self.last_attempt),
            "data_timestamp": iso(self.data_timestamp),
            "error": self.error,
        }


# ============================================================
# WEATHER
# ============================================================

class WeatherProvider(Provider):
    def __init__(self):
        super().__init__(
            "weather",
            "Open-Meteo",
            True,
            "LIVE",
        )

    def fetch(self, lat: float, lon: float) -> dict:
        self.last_attempt = _now()

        try:
            response = httpx.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current": (
                        "temperature_2m,"
                        "precipitation,"
                        "weather_code,"
                        "wind_speed_10m,"
                        "visibility"
                    ),
                },
                timeout=5.0,
            )

            response.raise_for_status()

            data = response.json()
            current = data["current"]

            self.last_success = _now()
            self.data_timestamp = _now()
            self.error = None

            return {
                "observed": True,
                "status": "LIVE",
                "temp_c": current.get("temperature_2m"),
                "precipitation": current.get("precipitation"),
                "wind_kmh": current.get("wind_speed_10m"),
                "visibility_m": current.get("visibility"),
                "code": current.get("weather_code"),
                "source": "Open-Meteo",
                "timestamp": self.data_timestamp.isoformat(),
            }

        except Exception as ex:
            self.error = str(ex)[:160]

            return {
                "observed": False,
                "status": self.status(),
                "error": self.error,
                "last_success": (
                    self.last_success.isoformat()
                    if self.last_success
                    else None
                ),
            }


# ============================================================
# TRAFFIC - TOMTOM
# ============================================================

class TrafficProvider(Provider):
    """
    TomTom Traffic Flow provider.

    Requires:

        TOMTOM_API_KEY

    Example PowerShell:

        $env:TOMTOM_API_KEY="your-key"

    The provider uses TomTom Traffic Flow to obtain current
    speed/travel-time information near the requested point.

    IMPORTANT:
    The provider reports LIVE only after a successful TomTom
    HTTP request.
    """

    def __init__(self):
        key = os.environ.get("TOMTOM_API_KEY", "").strip()

        super().__init__(
            "traffic",
            "TomTom Traffic",
            bool(key),
            "LIVE",
        )

        self._api_key = key

    def leg(
        self,
        from_ll: tuple[float, float],
        to_ll: tuple[float, float],
    ) -> dict:
        """
        Get live traffic information for a route leg.

        from_ll / to_ll:
            (latitude, longitude)

        Returns:
            traffic delay, current speed, free-flow speed, etc.
        """

        self.last_attempt = _now()

        if not self.configured:
            return {
                "status": "NOT_CONFIGURED",
                "delay_minutes": 0,
                "note": "Set TOMTOM_API_KEY for live traffic.",
            }

        try:
            # ----------------------------------------------------
            # Use the midpoint of the leg for the traffic query.
            # TomTom Flow Segment API accepts a point.
            # ----------------------------------------------------

            from_lat, from_lon = from_ll
            to_lat, to_lon = to_ll

            midpoint_lat = (from_lat + to_lat) / 2
            midpoint_lon = (from_lon + to_lon) / 2

            url = (
                "https://api.tomtom.com/traffic/services/4/"
                "flowSegmentData/absolute/10/json"
            )

            response = httpx.get(
                url,
                params={
                    "key": self._api_key,
                    "point": f"{midpoint_lat},{midpoint_lon}",
                    "unit": "KMPH",
                },
                timeout=6.0,
            )

            response.raise_for_status()

            payload = response.json()

            flow = payload.get("flowSegmentData")

            if not flow:
                raise RuntimeError(
                    "TomTom response did not contain flowSegmentData"
                )

            current_speed = flow.get("currentSpeed")
            free_flow_speed = flow.get("freeFlowSpeed")

            current_travel_time = flow.get("currentTravelTime")
            free_flow_travel_time = flow.get("freeFlowTravelTime")

            # ----------------------------------------------------
            # Calculate traffic delay.
            # ----------------------------------------------------

            delay_seconds = 0

            if (
                current_travel_time is not None
                and free_flow_travel_time is not None
            ):
                delay_seconds = max(
                    0,
                    current_travel_time - free_flow_travel_time,
                )

            delay_minutes = round(delay_seconds / 60)

            # ----------------------------------------------------
            # Traffic congestion ratio.
            # ----------------------------------------------------

            congestion_ratio = None

            if free_flow_speed and free_flow_speed > 0:
                congestion_ratio = round(
                    current_speed / free_flow_speed,
                    3,
                )

            # ----------------------------------------------------
            # Determine simple traffic level.
            # ----------------------------------------------------

            traffic_level = "UNKNOWN"

            if congestion_ratio is not None:
                if congestion_ratio >= 0.85:
                    traffic_level = "FREE_FLOW"
                elif congestion_ratio >= 0.65:
                    traffic_level = "MODERATE"
                elif congestion_ratio >= 0.45:
                    traffic_level = "HEAVY"
                else:
                    traffic_level = "SEVERE"

            # ----------------------------------------------------
            # SUCCESS
            # ----------------------------------------------------

            self.last_success = _now()
            self.data_timestamp = _now()
            self.error = None

            return {
                "status": "LIVE",
                "observed": True,

                "delay_minutes": delay_minutes,

                "current_speed_kmh": current_speed,
                "free_flow_speed_kmh": free_flow_speed,

                "current_travel_time_seconds": current_travel_time,
                "free_flow_travel_time_seconds": free_flow_travel_time,

                "congestion_ratio": congestion_ratio,
                "traffic_level": traffic_level,

                "latitude": midpoint_lat,
                "longitude": midpoint_lon,

                "source": "TomTom Traffic Flow",
                "timestamp": self.data_timestamp.isoformat(),
            }

        except httpx.HTTPStatusError as ex:
            self.error = (
                f"TomTom HTTP {ex.response.status_code}: "
                f"{ex.response.text[:120]}"
            )

            return {
                "status": self.status(),
                "observed": False,
                "delay_minutes": 0,
                "error": self.error,
            }

        except Exception as ex:
            self.error = str(ex)[:160]

            return {
                "status": self.status(),
                "observed": False,
                "delay_minutes": 0,
                "error": self.error,
            }


# ============================================================
# ROUTING - OSRM
# ============================================================

class RoutingProvider(Provider):
    def __init__(self):
        super().__init__(
            "routing",
            "OSRM (public)",
            True,
            "LIVE",
        )

    def leg(
        self,
        from_ll: tuple[float, float],
        to_ll: tuple[float, float],
    ) -> dict:

        self.last_attempt = _now()

        try:
            from_lat, from_lon = from_ll
            to_lat, to_lon = to_ll

            url = (
                "https://router.project-osrm.org/"
                f"route/v1/driving/"
                f"{from_lon},{from_lat};"
                f"{to_lon},{to_lat}"
            )

            response = httpx.get(
                url,
                params={
                    "overview": "simplified",
                    "geometries": "geojson",
                },
                timeout=6.0,
            )

            response.raise_for_status()

            data = response.json()

            routes = data.get("routes", [])

            if not routes:
                raise RuntimeError(
                    "OSRM returned no routes"
                )

            route = routes[0]

            self.last_success = _now()
            self.data_timestamp = _now()
            self.error = None

            return {
                "status": "LIVE",
                "duration_minutes": round(
                    route["duration"] / 60
                ),
                "distance_km": round(
                    route["distance"] / 1000
                ),
                "geometry": route["geometry"]["coordinates"],
                "source": "OSRM",
                "timestamp": self.data_timestamp.isoformat(),
            }

        except Exception as ex:
            self.error = str(ex)[:160]

            return {
                "status": self.status(),
                "geometry": None,
                "error": self.error,
            }


# ============================================================
# HOLIDAYS
# ============================================================

class HolidayProvider(Provider):
    """
    Regulatory/calendar data from the supplied kalender.csv.
    """

    def __init__(self, holidays: dict):
        super().__init__(
            "holidays",
            "kalender.csv (BW)",
            True,
            "REGULATORY",
        )

        self.holidays = holidays

        self.last_success = _now()
        self.data_timestamp = _now()

    def status(self) -> str:
        return "LIVE"


# ============================================================
# PROVIDER REGISTRY
# ============================================================

class Providers:
    def __init__(self, holidays: dict):
        self.weather = WeatherProvider()
        self.traffic = TrafficProvider()
        self.routing = RoutingProvider()
        self.holidays = HolidayProvider(holidays)

    def all(self) -> list[dict]:
        return [
            self.weather.to_dict(),
            self.traffic.to_dict(),
            self.routing.to_dict(),
            self.holidays.to_dict(),
        ]