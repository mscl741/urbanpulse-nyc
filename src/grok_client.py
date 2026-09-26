"""Grok vision client via the OpenAI-compatible xAI API."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path

from openai import OpenAI
from pydantic import ValidationError

from models import SYSTEM_PROMPT, DispatchTicket, Severity


def _client() -> OpenAI:
    api_key = os.getenv("XAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "XAI_API_KEY is not set. Add it to .env or enable Mock mode in the sidebar."
        )
    return OpenAI(api_key=api_key, base_url="https://api.x.ai/v1")


def image_to_data_url(image_bytes: bytes, mime: str = "image/jpeg") -> str:
    encoded = base64.b64encode(image_bytes).decode("utf-8")
    return f"data:{mime};base64,{encoded}"


def mock_analyze(location: str, filename: str | None = None) -> DispatchTicket:
    """Deterministic fallback so you can learn the UI without burning API credits."""
    hint = (filename or "").lower()
    if "signal" in hint or "light" in hint:
        hazard, agency, severity = "broken traffic signal", "DOT", Severity.HIGH
        priority = "expedited"
    elif "flood" in hint or "water" in hint:
        hazard, agency, severity = "street flooding", "DEP", Severity.HIGH
        priority = "expedited"
    elif "trash" in hint or "dump" in hint:
        hazard, agency, severity = "illegal dumping", "DSNY", Severity.MEDIUM
        priority = "routine"
    else:
        hazard, agency, severity = "pothole", "DOT", Severity.MEDIUM
        priority = "routine"

    return DispatchTicket(
        hazard_type=hazard,
        severity=severity,
        agency=agency,  # type: ignore[arg-type]
        confidence=0.72,
        summary=(
            f"Mock analysis for learning mode: likely {hazard} near {location}. "
            "Replace with a live Grok call once XAI_API_KEY is configured."
        ),
        council_email_subject=f"Resident report: {hazard} at {location}",
        council_email_body=(
            f"Dear Council Member,\n\n"
            f"I am writing to report a {hazard} at {location}. "
            f"Please route this to {agency} for inspection.\n\n"
            f"Thank you,\nA concerned resident"
        ),
        recommended_priority=priority,  # type: ignore[arg-type]
    )


def analyze_hazard(
    image_bytes: bytes,
    location: str,
    *,
    mime: str = "image/jpeg",
    model: str | None = None,
    use_mock: bool = False,
    filename: str | None = None,
) -> DispatchTicket:
    if use_mock:
        return mock_analyze(location, filename)

    model_name = model or os.getenv("GROK_MODEL", "grok-4.6")
    client = _client()
    data_url = image_to_data_url(image_bytes, mime=mime)

    response = client.chat.completions.create(
        model=model_name,
        temperature=0.2,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            f"Intersection / location: {location}\n"
                            "Classify this urban hazard photo into the required JSON."
                        ),
                    },
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            },
        ],
    )

    raw = response.choices[0].message.content or "{}"
    try:
        payload = json.loads(raw)
        return DispatchTicket.model_validate(payload)
    except (json.JSONDecodeError, ValidationError) as exc:
        raise ValueError(f"Grok returned invalid ticket JSON: {exc}\nRaw: {raw}") from exc


def analyze_image_path(path: Path, location: str, **kwargs) -> DispatchTicket:
    mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    return analyze_hazard(path.read_bytes(), location, mime=mime, filename=path.name, **kwargs)
