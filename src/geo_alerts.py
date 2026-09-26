"""Geofenced / near-me hazard scans for accessibility."""

from __future__ import annotations

from typing import Any

from db import nearby_open_reports
from evacuation import nearest_centers
from flood_risk import assess_flood_risk
from models import is_weather_hazard_type
from safety_profile import SafetyProfile


def _needs_safety_directions(profile: SafetyProfile) -> bool:
    return (
        profile.notify_early_flood
        or profile.is_high_priority()
        or profile.limited_mobility
        or profile.needs_accessible_transit
    )


def _safety_direction_lines(lat: float, lon: float, *, limit: int = 2) -> list[str]:
    lines: list[str] = []
    centers = nearest_centers(lat, lon, limit=limit)
    if not centers:
        return lines
    lines.append(
        "Safety directions: move toward higher ground or a verified accessible center. "
        "Confirm open status with 311 or Know Your Zone before you travel."
    )
    for sug in centers:
        c = sug.center
        name = c.get("name") or "accessible center"
        dist_m = int(sug.distance_m)
        clat, clon = c.get("latitude"), c.get("longitude")
        maps = (
            f"https://www.google.com/maps/dir/?api=1&destination={clat},{clon}"
            if clat is not None and clon is not None
            else None
        )
        if maps:
            lines.append(
                f"Suggested safety area: {name}, about {dist_m} meters away. "
                f"Open Google Maps directions: {maps}."
            )
        else:
            lines.append(f"Suggested safety area: {name}, about {dist_m} meters away.")
    return lines


def build_area_alerts(
    lat: float,
    lon: float,
    profile: SafetyProfile,
    *,
    hazard_radius_m: float = 180.0,
) -> list[str]:
    """Short spoken-friendly alert lines for the current pin."""
    lines: list[str] = []
    assessment = assess_flood_risk(lat, lon, profile)
    if assessment.priority_alert or (assessment.in_hotspot and assessment.heavy_rain_likely):
        where = assessment.hotspot_name or "this area"
        lines.append(
            f"Attention. You are in or near a flood-flagged zone: {where}. "
            "If you live in a basement or have limited mobility, move to higher ground early."
        )
    elif assessment.in_hotspot and profile.notify_early_flood:
        lines.append(
            f"Notice. You are near a historically flood-exposed area: {assessment.hotspot_name}."
        )

    if profile.depends_on_medical_power and (
        assessment.priority_alert or assessment.heavy_rain_likely
    ):
        lines.append(
            "Power risk warning. Charge electric medical equipment and prepare a backup plan."
        )

    opens = nearby_open_reports(lat, lon, radius_m=hazard_radius_m, limit=5)
    weather_hit = False
    for h in opens:
        hazard = h.get("hazard_type") or "hazard"
        sev = h.get("severity") or "unknown"
        dist = h.get("distance_m")
        dist_txt = f" about {int(dist)} meters away" if dist is not None else ""
        if is_weather_hazard_type(str(hazard)):
            weather_hit = True
            aff = h.get("affected_radius_m")
            zone = f" Mapped weather zone about {int(aff)} meters." if aff else ""
            lines.append(
                f"WARNING. Weather hazard nearby{dist_txt}: {hazard}, severity {sev}. "
                f"You are in or near a mapped flood / standing-water zone at "
                f"{h.get('location') or 'this block'}.{zone}"
            )
        else:
            lines.append(
                f"Open city hazard nearby{dist_txt}: {hazard}, severity {sev}. "
                f"Reported at {h.get('location') or 'this block'}."
            )
    if weather_hit and _needs_safety_directions(profile):
        lines.extend(_safety_direction_lines(lat, lon, limit=2))
    return lines


def scan_nearby_hazards(
    lat: float,
    lon: float,
    profile: SafetyProfile,
    *,
    radius_m: float = 300.0,
) -> dict[str, Any]:
    """
    Full near-me scan for the UI + TTS.

    Returns:
      hazards: list of open report dicts
      flood_lines: flood-related spoken lines
      weather_warnings: weather-hazard warning lines
      safety_directions: directions toward nearby safety areas
      spoken: one paragraph suitable for text-to-speech
      count: number of open mapped hazards
    """
    opens = nearby_open_reports(lat, lon, radius_m=radius_m, limit=8)
    assessment = assess_flood_risk(lat, lon, profile)
    flood_only: list[str] = []
    if assessment.priority_alert or (assessment.in_hotspot and assessment.heavy_rain_likely):
        where = assessment.hotspot_name or "this area"
        flood_only.append(
            f"You are in or near a flood-flagged zone: {where}."
        )
    elif assessment.in_hotspot:
        flood_only.append(
            f"You are near a historically flood-exposed area: {assessment.hotspot_name}."
        )
    if profile.depends_on_medical_power and (
        assessment.priority_alert or assessment.heavy_rain_likely
    ):
        flood_only.append(
            "Power risk: charge electric medical equipment and prepare a backup plan."
        )

    weather_warnings: list[str] = []
    weather_hazards = [h for h in opens if is_weather_hazard_type(str(h.get("hazard_type") or ""))]
    for h in weather_hazards:
        dist = h.get("distance_m")
        dist_txt = f", about {int(dist)} meters away" if dist is not None else ""
        aff = h.get("affected_radius_m")
        zone = f" Affected area radius about {int(aff)} meters." if aff else ""
        weather_warnings.append(
            f"WARNING: weather hazard — {h.get('hazard_type')}, severity "
            f"{h.get('severity') or 'unknown'}{dist_txt}. "
            f"You are in or near a mapped flood / standing-water zone at "
            f"{h.get('location') or 'nearby'}.{zone}"
        )

    safety_directions: list[str] = []
    if weather_hazards and _needs_safety_directions(profile):
        safety_directions = _safety_direction_lines(lat, lon, limit=2)

    parts: list[str] = [
        f"Near-me hazard scan complete within about {int(radius_m)} meters."
    ]
    if not opens and not flood_only:
        parts.append(
            "No open mapped hazards and no flood flags were found near you right now."
        )
    else:
        if weather_warnings:
            parts.extend(weather_warnings)
        if flood_only:
            parts.extend(flood_only)
        if opens:
            parts.append(f"Found {len(opens)} open reported hazard{'s' if len(opens) != 1 else ''}.")
            for i, h in enumerate(opens, start=1):
                dist = h.get("distance_m")
                dist_txt = f", about {int(dist)} meters away" if dist is not None else ""
                label = h.get("hazard_type") or "hazard"
                prefix = "Weather warning — " if is_weather_hazard_type(str(label)) else ""
                parts.append(
                    f"Number {i}: {prefix}{label}, "
                    f"severity {h.get('severity') or 'unknown'}{dist_txt}, "
                    f"at {h.get('location') or 'nearby'}."
                )
        else:
            parts.append("No open mapped hazard reports in this radius.")
        if safety_directions:
            parts.extend(safety_directions)

    spoken = " ".join(parts)
    return {
        "hazards": opens,
        "flood_lines": flood_only,
        "weather_warnings": weather_warnings,
        "safety_directions": safety_directions,
        "spoken": spoken,
        "count": len(opens),
        "radius_m": radius_m,
        "assessment": assessment,
    }


def alert_fingerprint(lines: list[str], lat: float, lon: float) -> str:
    return f"{round(lat, 4)}:{round(lon, 4)}:" + "|".join(lines[:3])
