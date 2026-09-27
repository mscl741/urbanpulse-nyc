"""Small HTTP bridge so Photon Spectrum can call the existing hazard system.

Does not change the Streamlit website. Reuses scan_nearby_hazards and Hazard Helper chat.
"""

from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT.parent / ".env")

from ai_provider import get_provider  # noqa: E402
from db import ensure_db, get_ticket, save_ticket  # noqa: E402
from flood_risk import neighborhood_hint_coords  # noqa: E402
from geo_alerts import scan_nearby_hazards  # noqa: E402
from geo_services import forward_geocode  # noqa: E402
from grok_client import classify_text_report  # noqa: E402
from nasa_weather import weather_context_for_point  # noqa: E402
from nyc_areas import NYC_BOROUGHS  # noqa: E402
from safety_profile import load_profile  # noqa: E402
from vision_router import chat_routed  # noqa: E402

HOST = os.getenv("URBANPULSE_BRIDGE_HOST", "127.0.0.1")
PORT = int(os.getenv("URBANPULSE_BRIDGE_PORT", "8766"))

# When a text names only a borough, scan from a central neighborhood in that borough.
BOROUGH_DEFAULTS = {
    "manhattan": "Midtown / Times Square",
    "brooklyn": "Downtown Brooklyn",
    "queens": "Long Island City",
    "bronx": "South Bronx / Mott Haven",
    "staten island": "St. George",
}


def plain(text: str) -> str:
    cleaned = text.replace("**", "").replace("`", "").strip()
    if len(cleaned) > 1600:
        return cleaned[:1597] + "..."
    return cleaned


def _has_live_key() -> bool:
    key = (os.getenv("XAI_API_KEY") or "").strip()
    return bool(key) and key != "your_xai_api_key_here"


def resolve_pin(text: str) -> tuple[str, float, float] | None:
    """Match an NYC neighborhood already defined in nyc_areas. No second gazetteer."""
    hint = neighborhood_hint_coords(text)
    if hint:
        return text.strip(), hint[0], hint[1]

    low = text.lower()
    best: tuple[int, str, float, float] | None = None
    for borough, hoods in NYC_BOROUGHS.items():
        for name, pin in hoods.items():
            parts = [name.lower(), *[p.strip().lower() for p in name.split("/")]]
            for part in parts:
                part = part.strip()
                if len(part) < 4 or part not in low:
                    continue
                if best is None or len(part) > best[0]:
                    best = (len(part), f"{borough} · {name}", pin["latitude"], pin["longitude"])
    if best:
        return best[1], best[2], best[3]

    for borough, hoods in NYC_BOROUGHS.items():
        if borough.lower() not in low:
            continue
        name = BOROUGH_DEFAULTS.get(borough.lower())
        pin = hoods.get(name) if name else None
        if pin:
            return f"{borough} · {name}", pin["latitude"], pin["longitude"]
    return None


def _wants_report(text: str) -> bool:
    low = text.lower().strip()
    return (
        low.startswith("report ")
        or low.startswith("report:")
        or low.startswith("file a ")
        or low.startswith("file ")
    )


def extract_report_location(text: str) -> str | None:
    low = text.lower()
    for sep in (" at ", " on ", " near ", " by ", " around "):
        idx = low.rfind(sep)
        if idx == -1:
            continue
        loc = text[idx + len(sep) :].strip(" .")
        if len(loc) >= 3:
            return loc
    return None


def file_text_report(text: str) -> str:
    """Classify with Grok and insert through save_ticket so the live map can see it."""
    location = extract_report_location(text)
    if not location:
        return (
            "Tell me the hazard and where it is. "
            "For example: Report a large pothole at Broadway and W 116th St."
        )

    point = forward_geocode(location)
    lat = lon = None
    if point:
        lat = float(point["latitude"])
        lon = float(point["longitude"])
    else:
        pin = resolve_pin(location)
        if pin:
            lat, lon = pin[1], pin[2]
    if lat is None or lon is None:
        return (
            f'I couldn\'t place "{location}" on the NYC map. '
            "Include a street or neighborhood, like Broadway and W 116th St."
        )

    try:
        ticket = classify_text_report(
            text,
            location,
            model=os.getenv("GROK_MODEL"),
            use_mock=not _has_live_key(),
        )
    except Exception:
        return "I couldn't classify that report just now. Please try again in a moment."

    if not ticket.is_recognized_hazard():
        return (
            "I didn't recognize a civic hazard in that message, so nothing was filed. "
            f"{ticket.summary}"
        )

    report_id = save_ticket(
        ticket,
        location,
        latitude=lat,
        longitude=lon,
        source="mock" if not _has_live_key() else "imessage",
        status="open",
    )
    saved = get_ticket(report_id)
    if not saved:
        return "The report was classified but could not be read back from the database."

    return (
        f"Filed report #{report_id}: {ticket.hazard_type} at {location}. "
        f"Severity {ticket.severity.value}, routed to {ticket.agency}."
    )


def _wants_nearby(text: str) -> bool:
    low = f" {text.lower()} "
    markers = (
        " near ",
        " nearby ",
        " around me ",
        " around here ",
        " near me ",
        " scan ",
        " hazard ",
        " hazards ",
    )
    return any(marker in low for marker in markers)


def handle_text(text: str) -> str:
    ensure_db()
    question = text.strip()
    if not question:
        return "Ask about hazards near a neighborhood, for example: What hazards are near Harlem?"

    if _wants_report(question):
        return file_text_report(question)

    pin = resolve_pin(question)
    if pin and (_wants_nearby(question) or question.lower() == pin[0].split(" · ", 1)[-1].lower()):
        label, lat, lon = pin
        result = scan_nearby_hazards(lat, lon, load_profile(), radius_m=300.0)
        spoken = result.get("spoken") or "No nearby hazard details."
        return plain(f"Near {label}. {spoken}")

    if _wants_nearby(question):
        return (
            "Name a New York neighborhood and I will scan open hazards there. "
            "For example: What hazards are near Times Square?"
        )

    content = question
    if pin and any(k in question.lower() for k in ("flood", "rain", "storm", "basement", "weather", "wet")):
        wx = weather_context_for_point(pin[1], pin[2])
        if wx:
            content = f"{question}\n\n{wx}"

    try:
        reply = chat_routed(
            [{"role": "user", "content": content}],
            provider=get_provider(),
            use_mock=not _has_live_key(),
            model=os.getenv("GROK_MODEL"),
        )
    except Exception:
        return (
            "Hazard Helper is unavailable right now. "
            "You can still ask: What hazards are near Harlem?"
        )
    return plain(reply or "I don't have an answer for that yet.")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/health":
            self.send_error(404)
            return
        body = b'{"ok":true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802
        if self.path.split("?", 1)[0] != "/message":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8"))
            text = str(payload.get("text") or "")
        except Exception:
            self.send_error(400)
            return
        reply = handle_text(text)
        data = json.dumps({"reply": reply}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))


def main() -> None:
    ensure_db()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"UrbanPulse iMessage bridge listening on http://{HOST}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
