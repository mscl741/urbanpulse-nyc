"""
Flood / storm risk helpers for UrbanPulse accessibility alerts.

Uses:
- Static NYC flood-prone neighborhood pins (hackathon-friendly proxy for Flood Hazard Mapper)
- Live precipitation forecast via Open-Meteo (no API key)
- NASA POWER satellite weather aid (observed rain / humidity / wind — no API key)
- Official NYC OEM / FloodNet references shown in the UI
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests

from nasa_weather import NasaWeatherAid, fetch_nasa_weather
from nyc_areas import NYC_BOROUGHS, haversine_m
from safety_profile import SafetyProfile

# Approximate centers of historically flood-exposed / low-lying areas (not official FEMA polygons).
# For production, swap in FloodNet sensors + NYC Flood Hazard Mapper / MapPLUTO overlays.
FLOOD_HOTSPOTS: list[dict[str, Any]] = [
    {"name": "Lower East Side / East River", "latitude": 40.7150, "longitude": -73.9843, "level": "high"},
    {"name": "Financial District waterfront", "latitude": 40.7040, "longitude": -74.0120, "level": "high"},
    {"name": "Red Hook", "latitude": 40.6740, "longitude": -74.0100, "level": "high"},
    {"name": "Gowanus / Carroll Gardens low areas", "latitude": 40.6750, "longitude": -73.9920, "level": "medium"},
    {"name": "Coney Island / Brighton Beach", "latitude": 40.5755, "longitude": -73.9680, "level": "high"},
    {"name": "Rockaway Beach", "latitude": 40.5860, "longitude": -73.8110, "level": "high"},
    {"name": "Howard Beach / Jamaica Bay", "latitude": 40.6570, "longitude": -73.8430, "level": "high"},
    {"name": "Hunts Point / South Bronx waterfront", "latitude": 40.8120, "longitude": -73.8840, "level": "medium"},
    {"name": "Astoria / LIC East River edge", "latitude": 40.7500, "longitude": -73.9450, "level": "medium"},
    {"name": "Stapleton / North Shore SI", "latitude": 40.6270, "longitude": -74.0770, "level": "medium"},
    {"name": "East Harlem / Harlem River", "latitude": 40.7947, "longitude": -73.9300, "level": "medium"},
    {"name": "Sunset Park waterfront", "latitude": 40.6455, "longitude": -74.0200, "level": "medium"},
]

RESOURCES = {
    "know_your_zone": "https://www.nyc.gov/knowyourzone",
    "oem_hurricane": "https://www.nyc.gov/site/em/ready/hurricane-evacuation.page",
    "oem_afn": "https://www.nyc.gov/site/em/ready/disabilities-access-functional-needs.page",
    "floodnet": "https://www.floodnet.nyc/",
    "flood_hazard_mapper": "https://www.nyc.gov/site/planning/zoning/districts-tools/flood-text.page",
    "call_311": "https://portal.311.nyc.gov/",
}


@dataclass
class FloodAssessment:
    in_hotspot: bool
    hotspot_name: str | None
    hotspot_level: str | None
    distance_m: float | None
    precip_next_6h_mm: float | None
    precip_observed_24h_mm: float | None
    precip_observed_3d_mm: float | None
    heavy_rain_likely: bool
    wet_ground_signal: bool
    priority_alert: bool
    messages: list[str]
    nasa: NasaWeatherAid | None = None


def nearest_hotspot(lat: float, lon: float, *, radius_m: float = 2500.0) -> tuple[dict | None, float | None]:
    best = None
    best_d = None
    for spot in FLOOD_HOTSPOTS:
        d = haversine_m(lat, lon, spot["latitude"], spot["longitude"])
        if best_d is None or d < best_d:
            best, best_d = spot, d
    if best is None or best_d is None or best_d > radius_m:
        return None, best_d
    return best, best_d


def forecast_precip_mm(lat: float, lon: float) -> float | None:
    """Sum next ~6 hours precipitation from Open-Meteo (free)."""
    try:
        resp = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat,
                "longitude": lon,
                "hourly": "precipitation",
                "forecast_days": 1,
                "timezone": "America/New_York",
            },
            timeout=5,
        )
        resp.raise_for_status()
        hourly = (resp.json().get("hourly") or {}).get("precipitation") or []
        window = hourly[:6]
        if not window:
            return None
        return float(sum(float(x or 0) for x in window))
    except Exception:
        return None


def assess_flood_risk(
    lat: float,
    lon: float,
    profile: SafetyProfile,
) -> FloodAssessment:
    spot, dist = nearest_hotspot(lat, lon)
    precip = forecast_precip_mm(lat, lon)
    nasa = fetch_nasa_weather(lat, lon)
    forecast_heavy = precip is not None and precip >= 8.0  # mm in ~6h — early threshold
    observed_wet = bool(nasa.available and nasa.wet_signal)
    heavy = forecast_heavy or observed_wet
    in_hotspot = spot is not None
    messages: list[str] = []

    if in_hotspot and spot:
        messages.append(
            f"You are near a historically flood-exposed area: **{spot['name']}** "
            f"({spot['level']} relative exposure, ~{int(dist or 0)} m)."
        )
    else:
        messages.append(
            "No mapped flood hotspot within ~1.5 miles of this pin — still check "
            "[Know Your Zone](https://www.nyc.gov/knowyourzone) for official coastal zones."
        )

    messages.extend(nasa.public_lines())

    if precip is not None:
        messages.append(f"Forecast rain (next ~6 hours): **{precip:.1f} mm**.")
        if forecast_heavy:
            messages.append(
                "Rain looks elevated ahead. For basement apartments and limited mobility, "
                "NYC OEM notes it is safer to move early rather than wait for a late alert."
            )
    else:
        messages.append("Short-range rain forecast unavailable right now — check OEM alerts.")

    if observed_wet and not forecast_heavy:
        messages.append(
            "Recent satellite rain is already elevated even if the next few hours look quieter — "
            "watch for ponding and basement seepage."
        )

    wet_or_hot = in_hotspot or heavy
    if profile.lives_in_basement and wet_or_hot:
        messages.append(
            "**Basement / low-lying residence:** flash-flood water rises fast downstairs — "
            "prioritize early relocation if rain is building."
        )
    if profile.limited_mobility and wet_or_hot:
        messages.append(
            "**Limited mobility:** leave extra lead time. Access-A-Ride and other transit "
            "may shut down hours before a storm (NYC Emergency Management)."
        )
    if profile.depends_on_medical_power and wet_or_hot:
        messages.append(
            "**Electric medical equipment:** flooding can trigger local outages — "
            "charge devices, pack backup batteries/meds, and plan a powered destination."
        )

    priority = profile.is_high_priority() and wet_or_hot and (
        profile.notify_early_flood or profile.notify_power_risk
    )

    return FloodAssessment(
        in_hotspot=in_hotspot,
        hotspot_name=spot["name"] if spot else None,
        hotspot_level=spot["level"] if spot else None,
        distance_m=dist,
        precip_next_6h_mm=precip,
        precip_observed_24h_mm=nasa.precip_last_24h_mm,
        precip_observed_3d_mm=nasa.precip_last_3d_mm,
        heavy_rain_likely=bool(heavy),
        wet_ground_signal=observed_wet,
        priority_alert=bool(priority),
        messages=messages,
        nasa=nasa if nasa.available else None,
    )


def neighborhood_hint_coords(label: str) -> tuple[float, float] | None:
    """Resolve 'Borough · Neighborhood' labels from the picker."""
    if " · " not in label:
        return None
    borough, name = label.split(" · ", 1)
    pin = NYC_BOROUGHS.get(borough, {}).get(name)
    if not pin:
        return None
    return pin["latitude"], pin["longitude"]
