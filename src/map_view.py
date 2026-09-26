"""Street-level incident map — Google Maps when keyed, else OpenStreetMap Folium."""

from __future__ import annotations

import json
from typing import Any

import folium
import streamlit as st
import streamlit.components.v1 as components
from streamlit_folium import st_folium

from geo_services import google_maps_api_key

SEVERITY_COLOR = {
    "low": "#2ecc71",
    "medium": "#e8a317",
    "high": "#e67e22",
    "critical": "#c0392b",
    "resolved": "#95a5a6",
}


def _center(rows: list[dict[str, Any]]) -> tuple[float, float]:
    if not rows:
        return 40.7580, -73.9855
    return (
        sum(float(r["latitude"]) for r in rows) / len(rows),
        sum(float(r["longitude"]) for r in rows) / len(rows),
    )


def render_incident_map(rows: list[dict[str, Any]], *, height: int = 560) -> None:
    """Draw a Google-Maps-like street basemap with hazard markers."""
    if not rows:
        st.info("No pins to show.")
        return

    key = google_maps_api_key()
    if key:
        _google_maps(rows, key, height=height)
    else:
        st.caption(
            "Street map via OpenStreetMap. Add `GOOGLE_MAPS_API_KEY` to `.env` "
            "for the full Google Maps experience (streets, satellite, Street View)."
        )
        _folium_streets(rows, height=height)


def _folium_streets(rows: list[dict[str, Any]], *, height: int) -> None:
    lat, lon = _center(rows)
    m = folium.Map(location=[lat, lon], zoom_start=13, control_scale=True)

    # Familiar street basemap (OSM) + optional satellite
    folium.TileLayer("OpenStreetMap", name="Streets").add_to(m)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri",
        name="Satellite",
        overlay=False,
        control=True,
    ).add_to(m)

    for r in rows:
        color = (
            SEVERITY_COLOR["resolved"]
            if r.get("status") == "resolved"
            else SEVERITY_COLOR.get(str(r.get("severity", "medium")), "#e8a317")
        )
        popup = (
            f"<b>#{r['id']} · {r.get('hazard_type', '')}</b><br/>"
            f"{r.get('severity', '')} · {r.get('status', '')}<br/>"
            f"{r.get('location', '')}<br/>"
            f"<small>{r.get('created_at', '')}</small>"
        )
        folium.CircleMarker(
            location=[float(r["latitude"]), float(r["longitude"])],
            radius=9,
            color="#12141a",
            weight=1,
            fill=True,
            fill_color=color,
            fill_opacity=0.92,
            popup=folium.Popup(popup, max_width=280),
            tooltip=f"#{r['id']} {r.get('hazard_type', '')}",
        ).add_to(m)

    folium.LayerControl(collapsed=False).add_to(m)
    st_folium(m, width=None, height=height, returned_objects=[])


def _google_maps(rows: list[dict[str, Any]], api_key: str, *, height: int) -> None:
    lat, lon = _center(rows)
    markers = []
    for r in rows:
        color = (
            SEVERITY_COLOR["resolved"]
            if r.get("status") == "resolved"
            else SEVERITY_COLOR.get(str(r.get("severity", "medium")), "#e8a317")
        )
        markers.append(
            {
                "id": r["id"],
                "lat": float(r["latitude"]),
                "lng": float(r["longitude"]),
                "title": f"#{r['id']} {r.get('hazard_type', '')}",
                "body": (
                    f"{r.get('severity', '')} · {r.get('status', '')}\\n"
                    f"{r.get('location', '')}\\n"
                    f"{r.get('created_at', '')}"
                ),
                "color": color,
            }
        )

    markers_json = json.dumps(markers)
    html = f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <style>
    html, body, #map {{ margin: 0; padding: 0; height: 100%; width: 100%; }}
    .gm-style .gm-style-iw-c {{ border-radius: 2px; }}
  </style>
</head>
<body>
  <div id="map" style="height:{height}px;width:100%;"></div>
  <script>
    const MARKERS = {markers_json};
    function initMap() {{
      const map = new google.maps.Map(document.getElementById("map"), {{
        center: {{ lat: {lat}, lng: {lon} }},
        zoom: 13,
        mapTypeControl: true,
        streetViewControl: true,
        fullscreenControl: true,
        zoomControl: true,
        gestureHandling: "greedy",
      }});
      const bounds = new google.maps.LatLngBounds();
      MARKERS.forEach((m) => {{
        const pos = {{ lat: m.lat, lng: m.lng }};
        bounds.extend(pos);
        const marker = new google.maps.Marker({{
          position: pos,
          map,
          title: m.title,
          icon: {{
            path: google.maps.SymbolPath.CIRCLE,
            scale: 10,
            fillColor: m.color,
            fillOpacity: 0.95,
            strokeColor: "#12141a",
            strokeWeight: 1.5,
          }},
        }});
        const info = new google.maps.InfoWindow({{
          content: `<div style="font-family:system-ui,sans-serif;max-width:240px">
            <strong>${{m.title}}</strong><br/>
            <span style="white-space:pre-line">${{m.body}}</span></div>`,
        }});
        marker.addListener("click", () => info.open({{ map, anchor: marker }}));
      }});
      if (MARKERS.length > 1) map.fitBounds(bounds, 48);
    }}
  </script>
  <script async defer
    src="https://maps.googleapis.com/maps/api/js?key={api_key}&callback=initMap">
  </script>
</body>
</html>
"""
    components.html(html, height=height + 8, scrolling=False)
