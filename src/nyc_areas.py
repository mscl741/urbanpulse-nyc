"""NYC borough → neighborhood pins for visitors and residents."""

from __future__ import annotations

import math

MILES_TO_METERS = 1609.34


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


# Approx centers — good enough to load a 1-mile street list / nearby areas.
NYC_BOROUGHS: dict[str, dict[str, dict[str, float]]] = {
    "Manhattan": {
        "Financial District": {"latitude": 40.7075, "longitude": -74.0113},
        "Battery Park City": {"latitude": 40.7115, "longitude": -74.0155},
        "Tribeca": {"latitude": 40.7163, "longitude": -74.0086},
        "Chinatown": {"latitude": 40.7158, "longitude": -73.9970},
        "Little Italy": {"latitude": 40.7191, "longitude": -73.9973},
        "SoHo": {"latitude": 40.7233, "longitude": -74.0030},
        "Nolita": {"latitude": 40.7229, "longitude": -73.9954},
        "Lower East Side": {"latitude": 40.7150, "longitude": -73.9843},
        "East Village": {"latitude": 40.7265, "longitude": -73.9815},
        "Greenwich Village": {"latitude": 40.7336, "longitude": -74.0027},
        "West Village": {"latitude": 40.7358, "longitude": -74.0036},
        "Meatpacking District": {"latitude": 40.7400, "longitude": -74.0080},
        "Chelsea": {"latitude": 40.7465, "longitude": -74.0014},
        "Flatiron District": {"latitude": 40.7411, "longitude": -73.9897},
        "Union Square": {"latitude": 40.7359, "longitude": -73.9911},
        "Gramercy": {"latitude": 40.7368, "longitude": -73.9845},
        "Murray Hill": {"latitude": 40.7479, "longitude": -73.9757},
        "Kips Bay": {"latitude": 40.7423, "longitude": -73.9801},
        "Midtown East": {"latitude": 40.7549, "longitude": -73.9680},
        "Midtown / Times Square": {"latitude": 40.7580, "longitude": -73.9855},
        "Theater District": {"latitude": 40.7590, "longitude": -73.9845},
        "Hell's Kitchen": {"latitude": 40.7638, "longitude": -73.9918},
        "Hudson Yards": {"latitude": 40.7537, "longitude": -74.0010},
        "Upper East Side": {"latitude": 40.7736, "longitude": -73.9566},
        "Yorkville": {"latitude": 40.7762, "longitude": -73.9492},
        "Upper West Side": {"latitude": 40.7870, "longitude": -73.9754},
        "Lincoln Square": {"latitude": 40.7736, "longitude": -73.9824},
        "Morningside Heights": {"latitude": 40.8100, "longitude": -73.9625},
        "Harlem": {"latitude": 40.8116, "longitude": -73.9465},
        "East Harlem / El Barrio": {"latitude": 40.7947, "longitude": -73.9425},
        "Hamilton Heights": {"latitude": 40.8245, "longitude": -73.9490},
        "Washington Heights": {"latitude": 40.8417, "longitude": -73.9394},
        "Inwood": {"latitude": 40.8677, "longitude": -73.9212},
        "Central Park": {"latitude": 40.7829, "longitude": -73.9654},
        "Roosevelt Island": {"latitude": 40.7605, "longitude": -73.9500},
    },
    "Brooklyn": {
        "Downtown Brooklyn": {"latitude": 40.6930, "longitude": -73.9870},
        "Brooklyn Heights": {"latitude": 40.6960, "longitude": -73.9936},
        "DUMBO": {"latitude": 40.7033, "longitude": -73.9881},
        "Williamsburg": {"latitude": 40.7081, "longitude": -73.9571},
        "Greenpoint": {"latitude": 40.7300, "longitude": -73.9540},
        "Bushwick": {"latitude": 40.6944, "longitude": -73.9210},
        "Bedford-Stuyvesant": {"latitude": 40.6872, "longitude": -73.9418},
        "Crown Heights": {"latitude": 40.6681, "longitude": -73.9442},
        "Prospect Heights": {"latitude": 40.6770, "longitude": -73.9680},
        "Park Slope": {"latitude": 40.6710, "longitude": -73.9814},
        "Gowanus": {"latitude": 40.6730, "longitude": -73.9900},
        "Carroll Gardens": {"latitude": 40.6795, "longitude": -73.9990},
        "Cobble Hill": {"latitude": 40.6870, "longitude": -73.9960},
        "Red Hook": {"latitude": 40.6740, "longitude": -74.0100},
        "Sunset Park": {"latitude": 40.6455, "longitude": -74.0124},
        "Bay Ridge": {"latitude": 40.6330, "longitude": -74.0280},
        "Borough Park": {"latitude": 40.6330, "longitude": -73.9940},
        "Bensonhurst": {"latitude": 40.6110, "longitude": -73.9970},
        "Coney Island": {"latitude": 40.5755, "longitude": -73.9707},
        "Brighton Beach": {"latitude": 40.5776, "longitude": -73.9614},
        "Sheepshead Bay": {"latitude": 40.5860, "longitude": -73.9420},
        "Flatbush": {"latitude": 40.6520, "longitude": -73.9590},
        "East Flatbush": {"latitude": 40.6482, "longitude": -73.9300},
        "Canarsie": {"latitude": 40.6400, "longitude": -73.9020},
        "East New York": {"latitude": 40.6660, "longitude": -73.8820},
        "Bush Terminal / Industry City": {"latitude": 40.6560, "longitude": -74.0100},
        "Fort Greene": {"latitude": 40.6920, "longitude": -73.9740},
        "Clinton Hill": {"latitude": 40.6890, "longitude": -73.9660},
    },
    "Queens": {
        "Long Island City": {"latitude": 40.7440, "longitude": -73.9480},
        "Astoria": {"latitude": 40.7720, "longitude": -73.9300},
        "Sunnyside": {"latitude": 40.7430, "longitude": -73.9190},
        "Woodside": {"latitude": 40.7450, "longitude": -73.9060},
        "Jackson Heights": {"latitude": 40.7557, "longitude": -73.8831},
        "Elmhurst": {"latitude": 40.7420, "longitude": -73.8820},
        "Corona": {"latitude": 40.7460, "longitude": -73.8600},
        "Flushing": {"latitude": 40.7650, "longitude": -73.8300},
        "Forest Hills": {"latitude": 40.7180, "longitude": -73.8450},
        "Rego Park": {"latitude": 40.7250, "longitude": -73.8620},
        "Kew Gardens": {"latitude": 40.7080, "longitude": -73.8300},
        "Jamaica": {"latitude": 40.7020, "longitude": -73.7890},
        "Howard Beach": {"latitude": 40.6570, "longitude": -73.8430},
        "Rockaway Beach": {"latitude": 40.5860, "longitude": -73.8110},
        "Far Rockaway": {"latitude": 40.6050, "longitude": -73.7550},
        "Bayside": {"latitude": 40.7680, "longitude": -73.7770},
        "Fresh Meadows": {"latitude": 40.7330, "longitude": -73.7800},
        "Ridgewood": {"latitude": 40.7040, "longitude": -73.9100},
        "Maspeth": {"latitude": 40.7250, "longitude": -73.9120},
        "Middle Village": {"latitude": 40.7170, "longitude": -73.8800},
        "Ozone Park": {"latitude": 40.6800, "longitude": -73.8450},
        "South Ozone Park": {"latitude": 40.6760, "longitude": -73.8200},
        "Whitestone": {"latitude": 40.7940, "longitude": -73.8100},
        "College Point": {"latitude": 40.7870, "longitude": -73.8380},
    },
    "Bronx": {
        "South Bronx / Mott Haven": {"latitude": 40.8090, "longitude": -73.9220},
        "Port Morris": {"latitude": 40.8020, "longitude": -73.9100},
        "Melrose": {"latitude": 40.8250, "longitude": -73.9100},
        "Morrisania": {"latitude": 40.8290, "longitude": -73.9020},
        "Highbridge": {"latitude": 40.8420, "longitude": -73.9280},
        "Yankee Stadium / Concourse": {"latitude": 40.8296, "longitude": -73.9262},
        "Grand Concourse": {"latitude": 40.8270, "longitude": -73.9220},
        "Fordham": {"latitude": 40.8620, "longitude": -73.8980},
        "Belmont / Little Italy": {"latitude": 40.8550, "longitude": -73.8860},
        "Tremont": {"latitude": 40.8450, "longitude": -73.9000},
        "University Heights": {"latitude": 40.8580, "longitude": -73.9100},
        "Kingsbridge": {"latitude": 40.8800, "longitude": -73.9050},
        "Riverdale": {"latitude": 40.9000, "longitude": -73.9070},
        "Norwood": {"latitude": 40.8780, "longitude": -73.8780},
        "Williamsbridge": {"latitude": 40.8770, "longitude": -73.8560},
        "Baychester": {"latitude": 40.8700, "longitude": -73.8330},
        "Co-op City": {"latitude": 40.8740, "longitude": -73.8290},
        "Pelham Bay": {"latitude": 40.8500, "longitude": -73.8330},
        "Throgs Neck": {"latitude": 40.8200, "longitude": -73.8200},
        "Hunts Point": {"latitude": 40.8120, "longitude": -73.8840},
        "Parkchester": {"latitude": 40.8380, "longitude": -73.8600},
        "Castle Hill": {"latitude": 40.8180, "longitude": -73.8500},
    },
    "Staten Island": {
        "St. George": {"latitude": 40.6437, "longitude": -74.0776},
        "Tomkinsville": {"latitude": 40.6350, "longitude": -74.0760},
        "Stapleton": {"latitude": 40.6270, "longitude": -74.0770},
        "New Brighton": {"latitude": 40.6400, "longitude": -74.0900},
        "West Brighton": {"latitude": 40.6350, "longitude": -74.1100},
        "Port Richmond": {"latitude": 40.6350, "longitude": -74.1300},
        "Mariners Harbor": {"latitude": 40.6300, "longitude": -74.1550},
        "New Springville": {"latitude": 40.5800, "longitude": -74.1600},
        "Willowbrook": {"latitude": 40.6000, "longitude": -74.1450},
        "Todt Hill": {"latitude": 40.6000, "longitude": -74.1100},
        "Dongan Hills": {"latitude": 40.5850, "longitude": -74.0950},
        "New Dorp": {"latitude": 40.5700, "longitude": -74.1150},
        "Oakwood": {"latitude": 40.5600, "longitude": -74.1200},
        "Great Kills": {"latitude": 40.5500, "longitude": -74.1500},
        "Eltingville": {"latitude": 40.5400, "longitude": -74.1550},
        "Annadale": {"latitude": 40.5400, "longitude": -74.1750},
        "Huguenot": {"latitude": 40.5350, "longitude": -74.1900},
        "Prince's Bay": {"latitude": 40.5250, "longitude": -74.2000},
        "Tottenville": {"latitude": 40.5100, "longitude": -74.2450},
    },
}


def flat_area_labels() -> list[str]:
    labels: list[str] = []
    for borough, neighborhoods in NYC_BOROUGHS.items():
        for name in neighborhoods:
            labels.append(f"{borough} · {name}")
    return labels


def pin_for_label(label: str) -> dict[str, float] | None:
    if " · " not in label:
        return None
    borough, name = label.split(" · ", 1)
    return NYC_BOROUGHS.get(borough, {}).get(name)


def neighborhoods_near(
    lat: float, lon: float, *, radius_miles: float = 1.0, limit: int = 12
) -> list[tuple[str, float]]:
    """Static NYC neighborhood pins within radius (fallback when Overpass is down)."""
    radius_m = radius_miles * MILES_TO_METERS
    hits: list[tuple[str, float]] = []
    for borough, neighborhoods in NYC_BOROUGHS.items():
        for name, pin in neighborhoods.items():
            dist = haversine_m(lat, lon, pin["latitude"], pin["longitude"])
            if dist <= radius_m:
                hits.append((f"{borough} · {name}", dist))
    hits.sort(key=lambda x: x[1])
    return hits[:limit]


# Back-compat alias used by older app code
DEMO_AREAS: dict[str, dict[str, float]] = {
    f"{borough} · {name}": pin
    for borough, neighborhoods in NYC_BOROUGHS.items()
    for name, pin in neighborhoods.items()
}
