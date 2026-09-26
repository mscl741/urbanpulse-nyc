"""Find nearby NYC streets / areas within ~1 mile of a GPS point."""

from __future__ import annotations

import math
from dataclasses import dataclass

import requests

from nyc_areas import neighborhoods_near

OVERPASS_ENDPOINTS = [
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
]
NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
USER_AGENT = "UrbanPulseNYC/0.1 (DivHacks civic reporting; student project)"
MILES_TO_METERS = 1609.34


@dataclass(frozen=True)
class NearbyPlace:
    label: str
    kind: str  # "area" | "street" | "intersection" | "neighborhood"
    distance_m: float


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def reverse_area(lat: float, lon: float) -> NearbyPlace | None:
    """Human-readable neighborhood / borough from OpenStreetMap Nominatim."""
    try:
        resp = requests.get(
            NOMINATIM_URL,
            params={
                "lat": lat,
                "lon": lon,
                "format": "json",
                "zoom": 16,
                "addressdetails": 1,
            },
            headers={"User-Agent": USER_AGENT},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return None

    addr = data.get("address") or {}
    neighborhood = (
        addr.get("neighbourhood")
        or addr.get("suburb")
        or addr.get("quarter")
        or addr.get("city_district")
    )
    borough = addr.get("borough") or addr.get("city") or addr.get("town") or "New York"
    road = addr.get("road")
    parts = [p for p in (road, neighborhood, borough) if p]
    if not parts:
        display = data.get("display_name")
        if not display:
            return None
        return NearbyPlace(label=display.split(",")[0], kind="area", distance_m=0.0)
    return NearbyPlace(label=", ".join(parts[:3]), kind="area", distance_m=0.0)


def _parse_overpass_streets(
    elements: list[dict], lat: float, lon: float
) -> list[NearbyPlace]:
    best_by_name: dict[str, NearbyPlace] = {}
    for el in elements:
        tags = el.get("tags") or {}
        name = (tags.get("name") or "").strip()
        center = el.get("center") or {}
        clat, clon = center.get("lat"), center.get("lon")
        if not name or clat is None or clon is None:
            continue
        dist = haversine_m(lat, lon, float(clat), float(clon))
        place = NearbyPlace(label=name, kind="street", distance_m=dist)
        prev = best_by_name.get(name)
        if prev is None or place.distance_m < prev.distance_m:
            best_by_name[name] = place
    return sorted(best_by_name.values(), key=lambda p: p.distance_m)


def nearby_streets(lat: float, lon: float, radius_m: float = MILES_TO_METERS) -> list[NearbyPlace]:
    """
    Query Overpass mirrors for named roads.
    Returns [] if every mirror times out / errors (caller should use fallbacks).
    """
    # Keep the query lighter so public Overpass mirrors don't 504 as often
    query = f"""
    [out:json][timeout:8];
    (
      way["highway"~"^(primary|secondary|tertiary|residential)$"]
        ["name"]
        (around:{int(radius_m)},{lat},{lon});
    );
    out tags center 60;
    """
    last_error: Exception | None = None
    for url in OVERPASS_ENDPOINTS:
        try:
            resp = requests.post(
                url,
                data={"data": query},
                headers={"User-Agent": USER_AGENT},
                timeout=10,
            )
            resp.raise_for_status()
            elements = resp.json().get("elements") or []
            return _parse_overpass_streets(elements, lat, lon)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            continue
    if last_error:
        # Surface soft failure via empty list; build_location_choices adds fallbacks
        return []
    return []


def build_location_choices(
    lat: float,
    lon: float,
    *,
    radius_miles: float = 1.0,
    max_streets: int = 20,
) -> tuple[list[str], str | None]:
    """
    Dropdown options: current area, nearby streets, intersections, NYC neighborhoods.
    Always returns something useful even when Overpass is down.
    Second value is a soft warning string (e.g. Overpass timeout).
    """
    radius_m = radius_miles * MILES_TO_METERS
    choices: list[str] = []
    warning: str | None = None

    # Instant local fallback first so the UI never depends only on Overpass
    for label, dist in neighborhoods_near(lat, lon, radius_miles=max(radius_miles, 2.0), limit=15):
        miles = dist / MILES_TO_METERS
        choices.append(f"{label}  ({miles:.2f} mi)")

    area = reverse_area(lat, lon)
    if area:
        choices.insert(0, f"Near me - {area.label}")

    streets = nearby_streets(lat, lon, radius_m=radius_m)
    if not streets:
        warning = (
            "Live street map is busy right now - showing NYC neighborhoods near you instead. "
            "You can still type an exact intersection below."
        )
    else:
        street_choices: list[str] = []
        for s in streets[:max_streets]:
            miles = s.distance_m / MILES_TO_METERS
            street_choices.append(f"{s.label}  ({miles:.2f} mi)")

        names = [s.label for s in streets[:8]]
        for i in range(min(5, len(names) - 1)):
            a, b = names[i], names[i + 1]
            if a != b:
                label = f"{a} & {b}"
                street_choices.append(label)

        # Prefer live streets at the top (after "Near me")
        near = [choices[0]] if choices and choices[0].startswith("Near me") else []
        rest_hoods = choices[len(near) :]
        choices = near + street_choices + rest_hoods

    if not choices:
        choices.append(f"Near me - {lat:.5f}, {lon:.5f}")
        warning = warning or "Could not resolve nearby names - use the text box to describe the spot."

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
    """Turn 'Broadway  (0.12 mi)' / 'Near me - X' into a clean location string."""
    text = choice.replace("Near me - ", "").strip()
    if "  (" in text:
        text = text.split("  (", 1)[0].strip()
    return text
