"""Geofenced / near-me hazard scans for accessibility."""

from __future__ import annotations

from typing import Any

from db import nearby_open_reports
from flood_risk import assess_flood_risk
from safety_profile import SafetyProfile


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
    for h in opens:
        hazard = h.get("hazard_type") or "hazard"
        sev = h.get("severity") or "unknown"
        dist = h.get("distance_m")
        dist_txt = f" about {int(dist)} meters away" if dist is not None else ""
        lines.append(
            f"Open city hazard nearby{dist_txt}: {hazard}, severity {sev}. "
            f"Reported at {h.get('location') or 'this block'}."
        )
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

    parts: list[str] = [
        f"Near-me hazard scan complete within about {int(radius_m)} meters."
    ]
    if not opens and not flood_only:
        parts.append(
            "No open mapped hazards and no flood flags were found near you right now."
        )
    else:
        if flood_only:
            parts.extend(flood_only)
        if opens:
            parts.append(f"Found {len(opens)} open reported hazard{'s' if len(opens) != 1 else ''}.")
            for i, h in enumerate(opens, start=1):
                dist = h.get("distance_m")
                dist_txt = f", about {int(dist)} meters away" if dist is not None else ""
                parts.append(
                    f"Number {i}: {h.get('hazard_type') or 'hazard'}, "
                    f"severity {h.get('severity') or 'unknown'}{dist_txt}, "
                    f"at {h.get('location') or 'nearby'}."
                )
        else:
            parts.append("No open mapped hazard reports in this radius.")

    spoken = " ".join(parts)
    return {
        "hazards": opens,
        "flood_lines": flood_only,
        "spoken": spoken,
        "count": len(opens),
        "radius_m": radius_m,
        "assessment": assessment,
    }


def alert_fingerprint(lines: list[str], lat: float, lon: float) -> str:
    return f"{round(lat, 4)}:{round(lon, 4)}:" + "|".join(lines[:3])
