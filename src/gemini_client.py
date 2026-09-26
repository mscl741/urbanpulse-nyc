"""Gemini vision client for hazard photo classification (swap with Grok)."""

from __future__ import annotations

import base64
import json
import os

import requests
from pydantic import ValidationError

from models import (
    DUPLICATE_PROMPT,
    SYSTEM_PROMPT,
    DispatchTicket,
    DuplicateVerdict,
)
from grok_client import mock_analyze


def _gemini_key() -> str:
    key = (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()
    if not key or key.startswith("your_"):
        raise RuntimeError("Photo review is temporarily unavailable. Please try again later.")
    return key


def _model() -> str:
    return os.getenv("GEMINI_VISION_MODEL", "gemini-2.0-flash")


def _generate(parts: list[dict], *, system: str) -> str:
    key = _gemini_key()
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{_model()}:generateContent?key={key}"
    )
    payload = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json",
        },
    }
    resp = requests.post(url, json=payload, timeout=90)
    resp.raise_for_status()
    data = resp.json()
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"Unexpected Gemini response: {data}") from exc


def analyze_hazard_gemini(
    image_bytes: bytes,
    location: str,
    *,
    mime: str = "image/jpeg",
    use_mock: bool = False,
    filename: str | None = None,
    weather_context: str | None = None,
) -> DispatchTicket:
    if use_mock:
        return mock_analyze(location, filename)
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    weather_block = f"\n\n{weather_context.strip()}" if weather_context and weather_context.strip() else ""
    raw = _generate(
        [
            {
                "text": (
                    f"Intersection / location: {location}\n"
                    "Classify this urban hazard photo into the required JSON. "
                    "Any civic hazard type is valid, including curb cuts."
                    f"{weather_block}"
                )
            },
            {"inline_data": {"mime_type": mime, "data": b64}},
        ],
        system=SYSTEM_PROMPT,
    )
    try:
        return DispatchTicket.model_validate(json.loads(raw))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise ValueError(f"Gemini returned invalid ticket JSON: {exc}\nRaw: {raw}") from exc


def check_duplicate_gemini(
    new_image: bytes,
    existing_image: bytes,
    location: str,
    existing_summary: str,
    *,
    mime: str = "image/jpeg",
    existing_mime: str = "image/jpeg",
    use_mock: bool = False,
    new_hash: str | None = None,
    existing_hash: str | None = None,
) -> DuplicateVerdict:
    if use_mock:
        from grok_client import check_duplicate_issue

        return check_duplicate_issue(
            new_image,
            existing_image,
            location,
            existing_summary,
            use_mock=True,
            new_hash=new_hash,
            existing_hash=existing_hash,
        )
    raw = _generate(
        [
            {
                "text": (
                    f"Location context: {location}\n"
                    f"Existing open report summary: {existing_summary}\n"
                    "Image 1 = NEW submission. Image 2 = EXISTING open report."
                )
            },
            {
                "inline_data": {
                    "mime_type": mime,
                    "data": base64.b64encode(new_image).decode("utf-8"),
                }
            },
            {
                "inline_data": {
                    "mime_type": existing_mime,
                    "data": base64.b64encode(existing_image).decode("utf-8"),
                }
            },
        ],
        system=DUPLICATE_PROMPT,
    )
    try:
        return DuplicateVerdict.model_validate(json.loads(raw))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise ValueError(f"Gemini duplicate check failed: {exc}\nRaw: {raw}") from exc


def chat_gemini(messages: list[dict[str, str]], *, system: str) -> str:
    key = _gemini_key()
    model = os.getenv("GEMINI_CHAT_MODEL", "gemini-2.0-flash")
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={key}"
    )
    contents = []
    for m in messages[-16:]:
        role = "user" if m["role"] == "user" else "model"
        contents.append({"role": role, "parts": [{"text": m["content"]}]})
    payload = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": contents,
        "generationConfig": {"temperature": 0.4},
    }
    resp = requests.post(url, json=payload, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    return data["candidates"][0]["content"]["parts"][0]["text"]
