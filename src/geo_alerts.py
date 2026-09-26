"""Geofenced spoken hazard alerts for accessibility (location sharing required)."""

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
    """
    Return short spoken-friendly alert lines for the current pin.
    Combines open mapped hazards + flood hotspot / rain assessment.
    """
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


def alert_fingerprint(lines: list[str], lat: float, lon: float) -> str:
    return f"{round(lat, 4)}:{round(lon, 4)}:" + "|".join(lines[:3])
