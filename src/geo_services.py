"""Fast geocoding for UrbanPulse — Google when available, otherwise quick local fallbacks."""

from __future__ import annotations

import os
import re
import time
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


def _in_nyc(lat: float, lon: float) -> bool:
    return 40.49 <= lat <= 40.92 and -74.27 <= lon <= -73.68


def _nominatim_search_one(query: str) -> dict[str, Any] | None:
    try:
        resp = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": query, "format": "json", "limit": 1},
            headers={"User-Agent": USER_AGENT},
            timeout=8,
        )
        resp.raise_for_status()
        rows = resp.json()
    except Exception:
        return None
    if not rows:
        return None
    top = rows[0]
    try:
        lat = float(top["lat"])
        lon = float(top["lon"])
    except (KeyError, TypeError, ValueError):
        return None
    if not _in_nyc(lat, lon):
        return None
    return {
        "latitude": lat,
        "longitude": lon,
        "label": top.get("display_name") or query,
        "provider": "nominatim",
    }


_OVERPASS_ENDPOINTS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)
_NYC_BBOX = (40.49, -74.27, 40.92, -73.68)  # south, west, north, east
_STREET_DIRS = {"w": "West", "e": "East", "n": "North", "s": "South"}
_STREET_SUFFIXES = {
    "st": "Street",
    "street": "Street",
    "ave": "Avenue",
    "av": "Avenue",
    "avenue": "Avenue",
    "blvd": "Boulevard",
    "rd": "Road",
    "dr": "Drive",
    "pl": "Place",
    "pkwy": "Parkway",
    "ln": "Lane",
    "ct": "Court",
    "ter": "Terrace",
}


def _split_intersection(text: str) -> tuple[str, str] | None:
    parts = re.split(r"\s+&\s+|\s+and\s+", text, maxsplit=1, flags=re.IGNORECASE)
    if len(parts) != 2:
        return None
    left, right = parts[0].strip(" .,"), parts[1].strip(" .,")
    if len(left) < 2 or len(right) < 2:
        return None
    return left, right


def _osm_street_names(piece: str) -> list[str]:
    raw = " ".join(piece.replace(".", " ").split())
    names = [raw]
    parts = raw.split(" ")
    if not parts:
        return names
    expanded = parts[:]
    lead = expanded[0].lower()
    if lead in _STREET_DIRS:
        expanded[0] = _STREET_DIRS[lead]
    last = expanded[-1].lower()
    if last in _STREET_SUFFIXES:
        expanded[-1] = _STREET_SUFFIXES[last]
    full = " ".join(expanded)
    if full not in names:
        names.append(full)
    return names


def _bbox_of(geoms: list[list[tuple[float, float]]], pad_deg: float) -> tuple[float, float, float, float]:
    pts = [p for line in geoms for p in line]
    lats = [p[0] for p in pts]
    lons = [p[1] for p in pts]
    return (
        min(lats) - pad_deg,
        min(lons) - pad_deg,
        max(lats) + pad_deg,
        max(lons) + pad_deg,
    )


def _overpass_street_ways(
    names: list[str],
    bbox: tuple[float, float, float, float] | None = None,
) -> list[list[tuple[float, float]]]:
    south, west, north, east = bbox or _NYC_BBOX
    pattern = "^(" + "|".join(re.escape(name) for name in names) + ")$"
    query = (
        f"[out:json][timeout:25];"
        f'way["highway"]["name"~"{pattern}",i]'
        f"({south},{west},{north},{east});"
        "out geom;"
    )
    for endpoint in _OVERPASS_ENDPOINTS:
        for attempt in range(3):
            try:
                resp = requests.post(
                    endpoint,
                    data={"data": query},
                    headers={"User-Agent": USER_AGENT},
                    timeout=30,
                )
            except Exception:
                time.sleep(1.5 * (attempt + 1))
                continue
            if resp.status_code in (429, 502, 503, 504):
                time.sleep(1.5 * (attempt + 1))
                continue
            if resp.status_code != 200:
                break
            try:
                payload = resp.json()
            except Exception:
                break
            elements = payload.get("elements") or []
            ways: list[list[tuple[float, float]]] = []
            for el in elements:
                if el.get("type") != "way":
                    continue
                line = [
                    (float(pt["lat"]), float(pt["lon"]))
                    for pt in (el.get("geometry") or [])
                    if "lat" in pt and "lon" in pt
                ]
                if len(line) >= 2:
                    ways.append(line)
            if ways:
                return ways
            # Empty 200s are often a busy mirror; try the next endpoint.
            break
    return []


def _shared_crossing(
    left: list[list[tuple[float, float]]],
    right: list[list[tuple[float, float]]],
) -> tuple[float, float] | None:
    left_pts = {(round(lat, 5), round(lon, 5)) for line in left for lat, lon in line}
    for line in right:
        for lat, lon in line:
            key = (round(lat, 5), round(lon, 5))
            if key in left_pts:
                return key
    return None


def _meters(a: tuple[float, float], b: tuple[float, float]) -> float:
    return (((b[0] - a[0]) * 111_000.0) ** 2 + ((b[1] - a[1]) * 85_000.0) ** 2) ** 0.5


def _segment_hit(
    a: tuple[float, float],
    b: tuple[float, float],
    c: tuple[float, float],
    d: tuple[float, float],
    *,
    max_past_b_m: float,
) -> tuple[float, float, float] | None:
    """Where segment c–d meets the line a→b.

    t=0 at a and t=1 at b. Hits past b are kept only within max_past_b_m.
    The third value is meters past b (0 when the hit lies on a–b).
    """
    ay, ax = a
    by, bx = b
    cy, cx = c
    dy, dx = d
    rlat, rlon = by - ay, bx - ax
    slat, slon = dy - cy, dx - cx
    denom = rlon * slat - rlat * slon
    if abs(denom) < 1e-14:
        return None
    qlat, qlon = cy - ay, cx - ax
    t = (qlon * slat - qlat * slon) / denom
    u = (qlon * rlat - qlat * rlon) / denom
    if u < -1e-8 or u > 1 + 1e-8 or t < -1e-8:
        return None
    ab_m = _meters(a, b) or 1.0
    extra = max(0.0, t - 1.0) * ab_m
    if extra > max_past_b_m:
        return None
    return ay + t * rlat, ax + t * rlon, extra


def _nearest_crossing(
    left: list[list[tuple[float, float]]],
    right: list[list[tuple[float, float]]],
    *,
    max_gap_m: float = 500.0,
) -> tuple[float, float] | None:
    """Crossing of two street centerlines, extending a short gap when needed.

    Manhattan cross streets run on a diagonal, and some named ways stop
    short of an avenue (a campus block with no mapped street). A due-east
    extension lands on the wrong block; follow the street's own bearing.
    """
    best: tuple[float, float, float] | None = None

    def consider(hit: tuple[float, float, float] | None, *, require_gap: bool) -> None:
        nonlocal best
        if hit is None:
            return
        if require_gap and hit[2] < 1.0:
            return
        if best is None or hit[2] < best[2]:
            best = hit

    for line in left:
        for a, b in zip(line, line[1:]):
            for other in right:
                for c, d in zip(other, other[1:]):
                    consider(_segment_hit(a, b, c, d, max_past_b_m=0.0), require_gap=False)
    if best is not None:
        return best[0], best[1]

    def terminals(geoms: list[list[tuple[float, float]]]):
        for line in geoms:
            if len(line) >= 2:
                yield line[1], line[0]
                yield line[-2], line[-1]

    for inner, end in terminals(left):
        for other in right:
            for c, d in zip(other, other[1:]):
                consider(_segment_hit(inner, end, c, d, max_past_b_m=max_gap_m), require_gap=True)
    for inner, end in terminals(right):
        for other in left:
            for c, d in zip(other, other[1:]):
                consider(_segment_hit(inner, end, c, d, max_past_b_m=max_gap_m), require_gap=True)
    if best is None:
        return None
    return best[0], best[1]


def _intersection_point(left_name: str, right_name: str) -> tuple[float, float] | None:
    left_names = _osm_street_names(left_name)
    right_names = _osm_street_names(right_name)
    # Numbered cross streets are short; use them to bound the avenue query.
    left_numbered = bool(re.search(r"\d", left_name))
    specific_names, avenue_names = (
        (left_names, right_names) if left_numbered else (right_names, left_names)
    )
    specific = _overpass_street_ways(specific_names)
    if not specific:
        return None
    avenue = _overpass_street_ways(avenue_names, _bbox_of(specific, 0.008))
    if not avenue:
        avenue = _overpass_street_ways(avenue_names)
    if not avenue:
        return None
    shared = _shared_crossing(specific, avenue)
    if shared:
        return shared
    return _nearest_crossing(specific, avenue)


def forward_geocode(query: str) -> dict[str, Any] | None:
    """Point for a street or intersection so a text report can be pinned.

    Intersections use the OpenStreetMap crossing of the two streets. A single
    street still uses Google when keyed, otherwise Nominatim.
    """
    text = " ".join(query.replace("&", " and ").split())
    if not text:
        return None

    key = google_maps_api_key()
    if key:
        try:
            resp = requests.get(
                GOOGLE_GEOCODE_URL,
                params={"address": f"{text}, New York, NY", "key": key},
                timeout=4,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("status") == "OK" and data.get("results"):
                loc = data["results"][0]["geometry"]["location"]
                lat, lon = float(loc["lat"]), float(loc["lng"])
                if _in_nyc(lat, lon):
                    return {
                        "latitude": lat,
                        "longitude": lon,
                        "label": data["results"][0].get("formatted_address") or text,
                        "provider": "google",
                    }
        except Exception:
            pass

    crossing = _split_intersection(text)
    if crossing:
        point = _intersection_point(crossing[0], crossing[1])
        if point and _in_nyc(point[0], point[1]):
            return {
                "latitude": point[0],
                "longitude": point[1],
                "label": f"{crossing[0]} & {crossing[1]}",
                "provider": "intersection",
            }
        return None

    expanded = (
        text.replace(" W ", " West ")
        .replace(" E ", " East ")
        .replace(" St", " Street")
        .replace(" Ave", " Avenue")
        .replace(" Blvd", " Boulevard")
    )
    for variant in (f"{text}, New York, NY", f"{expanded}, New York, NY"):
        hit = _nominatim_search_one(variant)
        if hit:
            return hit
    return None


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
