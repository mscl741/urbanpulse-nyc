"""Street-level incident map — Google Maps when keyed, else light Carto Positron Folium."""

from __future__ import annotations

import json
from typing import Any

import folium
import streamlit as st
import streamlit.components.v1 as components
from streamlit_folium import st_folium

from geo_services import google_maps_api_key
from models import is_weather_hazard_type, weather_affected_radius_m
from styles import chart_colors

_COLORS = chart_colors()
SEVERITY_COLOR = {
    "low": _COLORS["low"],
    "medium": _COLORS["medium"],
    "high": _COLORS["high"],
    "critical": _COLORS["critical"],
    "resolved": _COLORS["resolved"],
}


def _center(rows: list[dict[str, Any]]) -> tuple[float, float]:
    if not rows:
        return 40.7580, -73.9855
    return (
        sum(float(r["latitude"]) for r in rows) / len(rows),
        sum(float(r["longitude"]) for r in rows) / len(rows),
    )


def _affected_radius(r: dict[str, Any]) -> float:
    """Meters for weather-zone circle; infer from severity when DB radius missing."""
    try:
        val = float(r.get("affected_radius_m") or 0)
    except (TypeError, ValueError):
        val = 0.0
    if val > 0:
        return val
    if is_weather_hazard_type(str(r.get("hazard_type") or "")):
        return weather_affected_radius_m(str(r.get("severity") or "medium"))
    return 0.0


def _pin_offset(i: int) -> tuple[float, float]:
    """Tiny lat/lon nudge so stacked reports at the same block stay clickable."""
    # ~12–25 m offsets in a small spiral
    step = (i % 6) + 1
    return (0.00011 * step * ((-1) ** i), 0.00009 * step * ((-1) ** (i // 2)))


def render_incident_map(rows: list[dict[str, Any]], *, height: int = 560) -> None:
    """Draw a street basemap with hazard markers (same API as before)."""
    if not rows:
        st.info("No pins to show.")
        return

    key = google_maps_api_key()
    if key:
        _google_maps(rows, key, height=height)
    else:
        st.caption("Street map of open hazard reports across NYC — weather hazards show an affected-area ring.")
        _folium_streets(rows, height=height)


def _folium_streets(rows: list[dict[str, Any]], *, height: int) -> None:
    lat, lon = _center(rows)
    # Zoom tighter when a weather zone is present so the radius is obvious.
    has_zone = any(_affected_radius(r) > 0 for r in rows)
    m = folium.Map(
        location=[lat, lon],
        zoom_start=14 if has_zone else 13,
        control_scale=True,
        tiles=None,
    )

    # Light, minimal basemap (Carto Positron)
    folium.TileLayer(
        tiles="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
        attr='&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> '
        '&copy; <a href="https://carto.com/attributions">CARTO</a>',
        name="Light streets",
        max_zoom=20,
    ).add_to(m)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri",
        name="Satellite",
        overlay=False,
        control=True,
    ).add_to(m)

    accent = _COLORS["accent"]
    for i, r in enumerate(rows):
        color = (
            SEVERITY_COLOR["resolved"]
            if r.get("status") == "resolved"
            else SEVERITY_COLOR.get(str(r.get("severity", "medium")), _COLORS["medium"])
        )
        aff = _affected_radius(r)
        dlat, dlon = _pin_offset(i)
        plat = float(r["latitude"]) + dlat
        plon = float(r["longitude"]) + dlon
        zone_note = (
            f"<br/><em>Weather zone · ~{int(aff)} m affected radius</em>"
            if aff > 0
            else ""
        )
        popup = (
            f"<div style='font-family:Inter,system-ui,sans-serif;font-size:13px'>"
            f"<b>#{r['id']} · {r.get('hazard_type', '')}</b><br/>"
            f"{r.get('severity', '')} · {r.get('status', '')}<br/>"
            f"{r.get('location', '')}{zone_note}<br/>"
            f"<small style='color:#5F6368'>{r.get('created_at', '')}</small></div>"
        )
        tip = f"#{r['id']} {r.get('hazard_type', '')}"
        if aff > 0:
            tip += f" · weather zone {int(aff)} m"
            folium.Circle(
                location=[plat, plon],
                radius=aff,
                color=color,
                weight=3,
                fill=True,
                fill_color=color,
                fill_opacity=0.28,
                popup=folium.Popup(popup, max_width=280),
                tooltip=tip,
            ).add_to(m)
        folium.CircleMarker(
            location=[plat, plon],
            radius=11 if aff > 0 else 9,
            color="#FFFFFF" if aff > 0 else accent,
            weight=2.5 if aff > 0 else 1.5,
            fill=True,
            fill_color=color,
            fill_opacity=0.95,
            popup=folium.Popup(popup, max_width=280),
            tooltip=tip,
        ).add_to(m)

    folium.LayerControl(collapsed=True).add_to(m)
    st_folium(m, width=None, height=height, returned_objects=[])


def _google_maps(rows: list[dict[str, Any]], api_key: str, *, height: int) -> None:
    lat, lon = _center(rows)
    markers = []
    for i, r in enumerate(rows):
        color = (
            SEVERITY_COLOR["resolved"]
            if r.get("status") == "resolved"
            else SEVERITY_COLOR.get(str(r.get("severity", "medium")), _COLORS["medium"])
        )
        aff = _affected_radius(r)
        dlat, dlon = _pin_offset(i)
        body = (
            f"{r.get('severity', '')} · {r.get('status', '')}\\n"
            f"{r.get('location', '')}\\n"
            f"{r.get('created_at', '')}"
        )
        if aff > 0:
            body += f"\\nWeather zone · ~{int(aff)} m affected radius"
        markers.append(
            {
                "id": r["id"],
                "lat": float(r["latitude"]) + dlat,
                "lng": float(r["longitude"]) + dlon,
                "title": f"#{r['id']} {r.get('hazard_type', '')}",
                "body": body,
                "color": color,
                "radius_m": aff,
            }
        )

    markers_json = json.dumps(markers)
    accent = _COLORS["accent"]
    has_zone = any(m["radius_m"] > 0 for m in markers)
    start_zoom = 14 if has_zone else 13
    html = f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <style>
    html, body, #map {{ margin: 0; padding: 0; height: 100%; width: 100%; }}
    .gm-style .gm-style-iw-c {{ border-radius: 14px; }}
  </style>
</head>
<body>
  <div id="map" style="height:{height}px;width:100%;border-radius:18px;overflow:hidden;"></div>
  <script>
    const MARKERS = {markers_json};
    function initMap() {{
      const map = new google.maps.Map(document.getElementById("map"), {{
        center: {{ lat: {lat}, lng: {lon} }},
        zoom: {start_zoom},
        mapTypeControl: true,
        streetViewControl: true,
        fullscreenControl: true,
        zoomControl: true,
        gestureHandling: "greedy",
        styles: [
          {{ elementType: "geometry", stylers: [{{ color: "#f8f9fb" }}] }},
          {{ elementType: "labels.text.fill", stylers: [{{ color: "#5f6368" }}] }},
          {{ elementType: "labels.text.stroke", stylers: [{{ color: "#ffffff" }}] }},
          {{ featureType: "poi", stylers: [{{ visibility: "simplified" }}] }},
          {{ featureType: "road", elementType: "geometry", stylers: [{{ color: "#ffffff" }}] }},
          {{ featureType: "road", elementType: "geometry.stroke", stylers: [{{ color: "#e8eaed" }}] }},
          {{ featureType: "water", elementType: "geometry", stylers: [{{ color: "#e8f0fe" }}] }}
        ]
      }});
      const bounds = new google.maps.LatLngBounds();
      MARKERS.forEach((m) => {{
        const pos = {{ lat: m.lat, lng: m.lng }};
        bounds.extend(pos);
        if (m.radius_m && m.radius_m > 0) {{
          const circle = new google.maps.Circle({{
            map,
            center: pos,
            radius: m.radius_m,
            strokeColor: m.color,
            strokeOpacity: 0.85,
            strokeWeight: 2,
            fillColor: m.color,
            fillOpacity: 0.28,
          }});
          const cBounds = circle.getBounds();
          if (cBounds) bounds.union(cBounds);
        }}
        const marker = new google.maps.Marker({{
          position: pos,
          map,
          title: m.title,
          icon: {{
            path: google.maps.SymbolPath.CIRCLE,
            scale: m.radius_m > 0 ? 12 : 10,
            fillColor: m.color,
            fillOpacity: 0.95,
            strokeColor: m.radius_m > 0 ? "#ffffff" : "{accent}",
            strokeWeight: 2,
          }},
        }});
        const info = new google.maps.InfoWindow({{
          content: `<div style="font-family:Inter,system-ui,sans-serif;max-width:240px;font-size:13px">
            <strong>${{m.title}}</strong><br/>
            <span style="white-space:pre-line;color:#5f6368">${{m.body}}</span></div>`,
        }});
        marker.addListener("click", () => info.open({{ map, anchor: marker }}));
      }});
      if (MARKERS.length > 0) map.fitBounds(bounds, 56);
    }}
  </script>
  <script async defer
    src="https://maps.googleapis.com/maps/api/js?key={api_key}&callback=initMap">
  </script>
</body>
</html>
"""
    components.html(html, height=height + 8, scrolling=False)
