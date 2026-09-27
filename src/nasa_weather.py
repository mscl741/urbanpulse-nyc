"""NASA POWER weather aid — observed rain / humidity / wind for flood context.

NASA POWER (Langley) is free and requires no API key:
https://power.larc.nasa.gov/docs/services/api/

Used as a satellite weather aid alongside Open-Meteo forecasts — never shown as
vendor/API jargon in the public UI.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import requests

POWER_DAILY_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
# Corrected precipitation (mm/day), humidity (%), wind (m/s), temperature (°C)
POWER_PARAMS = "PRECTOTCORR,RH2M,WS10M,T2M"


@dataclass
class NasaWeatherAid:
    """Recent NASA MERRA-2 / POWER observations for a point."""

    latitude: float
    longitude: float
    precip_last_24h_mm: float | None
    precip_last_3d_mm: float | None
    precip_last_7d_mm: float | None
    humidity_pct: float | None
    wind_ms: float | None
    temp_c: float | None
    wet_signal: bool
    source_label: str = "NASA satellite weather"
    available: bool = False

    def brief_for_model(self) -> str:
        """Compact context string for vision / chat models (internal)."""
        if not self.available:
            return ""
        parts = [
            "Weather aid (NASA POWER satellite observations near this location):",
        ]
        if self.precip_last_24h_mm is not None:
            parts.append(f"- Rain last ~24h: {self.precip_last_24h_mm:.1f} mm")
        if self.precip_last_3d_mm is not None:
            parts.append(f"- Rain last ~3 days: {self.precip_last_3d_mm:.1f} mm")
        if self.precip_last_7d_mm is not None:
            parts.append(f"- Rain last ~7 days: {self.precip_last_7d_mm:.1f} mm")
        if self.humidity_pct is not None:
            parts.append(f"- Humidity: {self.humidity_pct:.0f}%")
        if self.wind_ms is not None:
            parts.append(f"- Wind: {self.wind_ms:.1f} m/s")
        if self.temp_c is not None:
            parts.append(f"- Temp: {self.temp_c:.1f} °C")
        if self.wet_signal:
            parts.append(
                "- Wet-ground signal: YES — weigh street flooding / standing water "
                "more carefully if the photo could show water on pavement."
            )
        else:
            parts.append("- Wet-ground signal: low recent rain.")
        parts.append(
            "Use this only as supporting context. Trust the photo for whether a "
            "civic hazard is actually visible. Prefer DEP for clear street flooding."
        )
        return "\n".join(parts)

    def public_lines(self) -> list[str]:
        """Friendly lines for Safety / near-me UI (no API jargon)."""
        if not self.available:
            return []
        lines: list[str] = []
        if self.precip_last_24h_mm is not None:
            lines.append(
                f"Satellite rain near you (last ~24h): **{self.precip_last_24h_mm:.1f} mm**."
            )
        if self.precip_last_3d_mm is not None:
            lines.append(
                f"Rain over the last ~3 days: **{self.precip_last_3d_mm:.1f} mm**."
            )
        if self.wet_signal:
            lines.append(
                "Recent rainfall looks elevated — basement and limited-mobility "
                "neighbors should treat standing water reports seriously."
            )
        return lines


def _sum_series(series: dict[str, Any] | None, *, last_n: int) -> float | None:
    if not series:
        return None
    # Keys are YYYYMMDD strings; ignore fill values
    items: list[tuple[str, float]] = []
    for k, v in series.items():
        try:
            val = float(v)
        except (TypeError, ValueError):
            continue
        if val < -900:  # POWER fill_value often -999
            continue
        items.append((str(k), val))
    if not items:
        return None
    items.sort(key=lambda x: x[0])
    window = items[-last_n:]
    return float(sum(v for _, v in window))


def _latest(series: dict[str, Any] | None) -> float | None:
    if not series:
        return None
    items: list[tuple[str, float]] = []
    for k, v in series.items():
        try:
            val = float(v)
        except (TypeError, ValueError):
            continue
        if val < -900:
            continue
        items.append((str(k), val))
    if not items:
        return None
    items.sort(key=lambda x: x[0])
    return items[-1][1]


def fetch_nasa_weather(lat: float, lon: float, *, days: int = 7) -> NasaWeatherAid:
    """
    Pull recent daily NASA POWER meteorology for a lat/lon.

    No API key required. Failures return available=False so callers can fall back.
    """
    empty = NasaWeatherAid(
        latitude=lat,
        longitude=lon,
        precip_last_24h_mm=None,
        precip_last_3d_mm=None,
        precip_last_7d_mm=None,
        humidity_pct=None,
        wind_ms=None,
        temp_c=None,
        wet_signal=False,
        available=False,
    )
    end = date.today()
    start = end - timedelta(days=max(days, 3))
    try:
        resp = requests.get(
            POWER_DAILY_URL,
            params={
                "parameters": POWER_PARAMS,
                "community": "AG",
                "longitude": f"{lon:.4f}",
                "latitude": f"{lat:.4f}",
                "start": start.strftime("%Y%m%d"),
                "end": end.strftime("%Y%m%d"),
                "format": "JSON",
            },
            timeout=12,
        )
        resp.raise_for_status()
        props = (resp.json().get("properties") or {}).get("parameter") or {}
        precip = props.get("PRECTOTCORR") or {}
        rh = props.get("RH2M") or {}
        wind = props.get("WS10M") or {}
        temp = props.get("T2M") or {}

        p1 = _sum_series(precip, last_n=1)
        p3 = _sum_series(precip, last_n=3)
        p7 = _sum_series(precip, last_n=7)
        # Wet if ~24h >= 10 mm or 3-day >= 25 mm (NYC flash-flood early attention)
        wet = bool(
            (p1 is not None and p1 >= 10.0)
            or (p3 is not None and p3 >= 25.0)
        )
        return NasaWeatherAid(
            latitude=lat,
            longitude=lon,
            precip_last_24h_mm=p1,
            precip_last_3d_mm=p3,
            precip_last_7d_mm=p7,
            humidity_pct=_latest(rh),
            wind_ms=_latest(wind),
            temp_c=_latest(temp),
            wet_signal=wet,
            available=p1 is not None or p3 is not None,
        )
    except Exception:
        return empty


def weather_context_for_point(lat: float | None, lon: float | None) -> str:
    """Helper used by vision / chat — empty string if coords or NASA unavailable."""
    if lat is None or lon is None:
        return ""
    return fetch_nasa_weather(float(lat), float(lon)).brief_for_model()
