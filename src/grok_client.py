"""Grok vision client via the OpenAI-compatible xAI API."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path

from openai import OpenAI
from pydantic import ValidationError

from models import (
    DUPLICATE_PROMPT,
    SYSTEM_PROMPT,
    DispatchTicket,
    DuplicateVerdict,
    Severity,
)


def _client() -> OpenAI:
    api_key = os.getenv("XAI_API_KEY")
    if not api_key:
        raise RuntimeError("Photo review is temporarily unavailable. Please try again later.")
    return OpenAI(api_key=api_key, base_url="https://api.x.ai/v1")


def image_to_data_url(image_bytes: bytes, mime: str = "image/jpeg") -> str:
    encoded = base64.b64encode(image_bytes).decode("utf-8")
    return f"data:{mime};base64,{encoded}"


def mock_analyze(location: str, filename: str | None = None) -> DispatchTicket:
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
    elif "scaffold" in hint:
        hazard, agency, severity = "unsafe scaffolding", "Other", Severity.HIGH
        priority = "expedited"
    elif "tree" in hint or "branch" in hint:
        hazard, agency, severity = "fallen tree / limb", "Parks", Severity.MEDIUM
        priority = "expedited"
    elif "curb" in hint or "ramp" in hint or "accessib" in hint:
        hazard, agency, severity = "defective pedestrian ramp / curb cut", "DOT", Severity.HIGH
        priority = "expedited"
    elif any(x in hint for x in ("clear", "none", "selfie", "food", "indoor", "blank")):
        return DispatchTicket(
            hazard_type="no hazard detected",
            severity=Severity.LOW,
            agency="Other",
            confidence=0.15,
            summary=(
                f"Mock analysis: no civic street hazard recognized near {location}. "
                "Photo does not appear to show a reportable NYC hazard."
            ),
            council_email_subject="No hazard — do not send",
            council_email_body="No municipal hazard recognized. This draft should not be sent.",
            recommended_priority="routine",
        )
    else:
        hazard, agency, severity = "street surface hazard", "DOT", Severity.MEDIUM
        priority = "routine"

    return DispatchTicket(
        hazard_type=hazard,
        severity=severity,
        agency=agency,  # type: ignore[arg-type]
        confidence=0.72,
        summary=(
            f"Mock analysis: likely {hazard} near {location}. "
            "Supports all urban hazards including accessibility infrastructure (curb cuts)."
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

    model_name = model or os.getenv("GROK_MODEL", "grok-4.7")
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
                            "Classify this urban hazard photo into the required JSON. "
                            "Any civic hazard type is valid."
                        ),
                    },
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            },
        ],
    )

    raw = response.choices[0].message.content or "{}"
    try:
        return DispatchTicket.model_validate(json.loads(raw))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise ValueError(f"Grok returned invalid ticket JSON: {exc}\nRaw: {raw}") from exc


def check_duplicate_issue(
    new_image: bytes,
    existing_image: bytes,
    location: str,
    existing_summary: str,
    *,
    mime: str = "image/jpeg",
    existing_mime: str = "image/jpeg",
    model: str | None = None,
    use_mock: bool = False,
    new_hash: str | None = None,
    existing_hash: str | None = None,
) -> DuplicateVerdict:
    """Compare a new photo to an existing nearby open report."""
    if use_mock:
        if new_hash and existing_hash and new_hash == existing_hash:
            return DuplicateVerdict(
                is_same_issue=True,
                confidence=0.99,
                reason="Mock mode: identical image fingerprint to an open report nearby.",
            )
        return DuplicateVerdict(
            is_same_issue=False,
            confidence=0.55,
            reason="Mock mode: nearby open report exists but image fingerprint differs.",
        )

    model_name = model or os.getenv("GROK_MODEL", "grok-4.7")
    client = _client()
    response = client.chat.completions.create(
        model=model_name,
        temperature=0.1,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": DUPLICATE_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            f"Location context: {location}\n"
                            f"Existing open report summary: {existing_summary}\n"
                            "Image 1 = NEW submission. Image 2 = EXISTING open report."
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": image_to_data_url(new_image, mime=mime)},
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": image_to_data_url(existing_image, mime=existing_mime)
                        },
                    },
                ],
            },
        ],
    )
    raw = response.choices[0].message.content or "{}"
    try:
        return DuplicateVerdict.model_validate(json.loads(raw))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise ValueError(f"Grok duplicate check failed: {exc}\nRaw: {raw}") from exc


def analyze_image_path(path: Path, location: str, **kwargs) -> DispatchTicket:
    mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    return analyze_hazard(path.read_bytes(), location, mime=mime, filename=path.name, **kwargs)
