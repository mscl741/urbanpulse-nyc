"""Accessible evacuation + transit assistance resources (NYC OEM / 311)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from nyc_areas import haversine_m

# Representative accessible-leaning public facilities used as demo pins.
# Official open/closed status changes during storms — always verify via Know Your Zone / 311.
EVACUATION_CENTERS: list[dict[str, Any]] = [
    {
        "name": "Brooklyn Tech HS area (demo pin)",
        "borough": "Brooklyn",
        "latitude": 40.6890,
        "longitude": -73.9650,
        "notes": "Verify accessibility + open status with 311 / Know Your Zone during an event.",
    },
    {
        "name": "Hunter College area (demo pin)",
        "borough": "Manhattan",
        "latitude": 40.7678,
        "longitude": -73.9645,
        "notes": "Verify before travel — centers open only when OEM activates them.",
    },
    {
        "name": "Queens College area (demo pin)",
        "borough": "Queens",
        "latitude": 40.7360,
        "longitude": -73.8200,
        "notes": "Confirm Access-A-Ride / accessible drop-off with 311.",
    },
    {
        "name": "Lehman College area (demo pin)",
        "borough": "Bronx",
        "latitude": 40.8720,
        "longitude": -73.8950,
        "notes": "Confirm facility accessibility features via 311.",
    },
    {
        "name": "CSI / South Shore area (demo pin)",
        "borough": "Staten Island",
        "latitude": 40.5800,
        "longitude": -74.1500,
        "notes": "North Shore vs South Shore openings vary by storm — check OEM.",
    },
]

LINKS = {
    "know_your_zone": "https://www.nyc.gov/knowyourzone",
    "request_help_311": "https://portal.311.nyc.gov/",
    "oem_afn": "https://www.nyc.gov/site/em/ready/disabilities-access-functional-needs.page",
    "oem_evacuation": "https://www.nyc.gov/site/em/ready/hurricane-evacuation.page",
    "access_a_ride": "https://new.mta.info/accessibility/paratransit",
    "mopd": "https://www.nyc.gov/site/mopd/index.page",
}


@dataclass
class EvacSuggestion:
    center: dict[str, Any]
    distance_m: float


def nearest_centers(lat: float, lon: float, *, limit: int = 3) -> list[EvacSuggestion]:
    scored: list[EvacSuggestion] = []
    for c in EVACUATION_CENTERS:
        d = haversine_m(lat, lon, c["latitude"], c["longitude"])
        scored.append(EvacSuggestion(center=c, distance_m=d))
    scored.sort(key=lambda s: s.distance_m)
    return scored[:limit]


def assistance_blurb() -> str:
    return (
        "If the Mayor issues an evacuation order and you have a disability or access/functional "
        "need with **no other safe way out**, call **311** (or 212-639-9675 VRS / TTY 212-504-4115) "
        "to request transportation assistance to an accessible evacuation center or hospital. "
        "Access-A-Ride and other transit may shut down **hours before** a storm arrives — "
        "plan early. Sources: NYC Emergency Management."
    )
