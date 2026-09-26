"""Fast geocoding for UrbanPulse — Google when available, otherwise quick local fallbacks."""

from __future__ import annotations

import os
from typing import Any

import requests

from nyc_areas import neighborhoods_near

USER_AGENT = "UrbanPulseNYC/1.0 (accessibility civic reporting; contact: urbanpulse)"

NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
GOOGLE_GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"


def google_maps_api_key() -> str | None:
    key = (os.getenv("GOOGLE_MAPS_API_KEY") or "").strip()
    if not key or key.startswith("your_"):
        return None
    return key


_GEOCODE_CACHE: dict[tuple[float, float], dict[str, Any]] = {}


def reverse_geocode(lat: float, lon: float) -> dict[str, Any]:
    """
    Human address for a coordinate.
    Prefers Google Geocoding (fast/accurate); falls back to Nominatim (short timeout).
    """
    cache_key = (round(lat, 5), round(lon, 5))
    if cache_key in _GEOCODE_CACHE:
        return _GEOCODE_CACHE[cache_key]

    result: dict[str, Any]
    key = google_maps_api_key()
    if key:
        try:
            resp = requests.get(
                GOOGLE_GEOCODE_URL,
                params={"latlng": f"{lat},{lon}", "key": key},
                timeout=4,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("status") == "OK" and data.get("results"):
                top = data["results"][0]
                result = {
                    "label": top.get("formatted_address") or f"{lat:.5f}, {lon:.5f}",
                    "provider": "google",
                    "place_id": top.get("place_id"),
                }
                _GEOCODE_CACHE[cache_key] = result
                return result
        except Exception:
            pass

    try:
        resp = requests.get(
            NOMINATIM_URL,
            params={
                "lat": lat,
                "lon": lon,
                "format": "json",
                "zoom": 17,
                "addressdetails": 1,
            },
            headers={"User-Agent": USER_AGENT},
            timeout=3,
        )
        resp.raise_for_status()
        data = resp.json()
        label = data.get("display_name") or f"{lat:.5f}, {lon:.5f}"
        parts = [p.strip() for p in label.split(",")]
        short = ", ".join(parts[:3]) if parts else label
        result = {"label": short, "provider": "nominatim", "place_id": None}
    except Exception:
        result = {
            "label": f"{lat:.5f}, {lon:.5f}",
            "provider": "coords",
            "place_id": None,
        }
    _GEOCODE_CACHE[cache_key] = result
    return result


def fast_location_choices(lat: float, lon: float) -> tuple[list[str], str | None]:
    """
    Instant nearby options — no Overpass wait.
    Uses static NYC neighborhoods + one reverse-geocode call.
    """
    choices: list[str] = []
    warning: str | None = None

    geo = reverse_geocode(lat, lon)
    choices.append(f"Near me - {geo['label']}")

    for label, dist in neighborhoods_near(lat, lon, radius_miles=1.5, limit=18):
        miles = dist / 1609.34
        choices.append(f"{label}  ({miles:.2f} mi)")

    if geo["provider"] == "coords":
        warning = "Could not resolve a street address quickly — pick a neighborhood or type one."
    elif geo["provider"] == "nominatim" and not google_maps_api_key():
        warning = None  # fine; optional tip in UI elsewhere

    seen: set[str] = set()
    unique: list[str] = []
    for c in choices:
        key = c.split("  (")[0].strip()
        if key in seen:
            continue
        seen.add(key)
        unique.append(c)
    return unique, warning


def strip_choice_meta(choice: str) -> str:
    text = choice.replace("Near me - ", "").strip()
    if "  (" in text:
        text = text.split("  (", 1)[0].strip()
    return text
