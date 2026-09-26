"""Route vision / chat / TTS to the active provider (Grok or Gemini)."""

from __future__ import annotations

from typing import Literal

from gemini_client import (
    analyze_hazard_gemini,
    chat_gemini,
    check_duplicate_gemini,
)
from grok_client import analyze_hazard as analyze_hazard_grok
from grok_client import check_duplicate_issue as check_duplicate_grok
from grokbot import GROKBOT_SYSTEM, chat_once as chat_grok, mock_reply
from models import DispatchTicket, DuplicateVerdict

Provider = Literal["grok", "gemini"]


def analyze_hazard_routed(
    image_bytes: bytes,
    location: str,
    *,
    provider: Provider,
    mime: str = "image/jpeg",
    model: str | None = None,
    use_mock: bool = False,
    filename: str | None = None,
    weather_context: str | None = None,
) -> DispatchTicket:
    if provider == "gemini":
        return analyze_hazard_gemini(
            image_bytes,
            location,
            mime=mime,
            use_mock=use_mock,
            filename=filename,
            weather_context=weather_context,
        )
    return analyze_hazard_grok(
        image_bytes,
        location,
        mime=mime,
        model=model,
        use_mock=use_mock,
        filename=filename,
        weather_context=weather_context,
    )


def check_duplicate_routed(
    new_image: bytes,
    existing_image: bytes,
    location: str,
    existing_summary: str,
    *,
    provider: Provider,
    mime: str = "image/jpeg",
    existing_mime: str = "image/jpeg",
    model: str | None = None,
    use_mock: bool = False,
    new_hash: str | None = None,
    existing_hash: str | None = None,
) -> DuplicateVerdict:
    if provider == "gemini":
        return check_duplicate_gemini(
            new_image,
            existing_image,
            location,
            existing_summary,
            mime=mime,
            existing_mime=existing_mime,
            use_mock=use_mock,
            new_hash=new_hash,
            existing_hash=existing_hash,
        )
    return check_duplicate_grok(
        new_image,
        existing_image,
        location,
        existing_summary,
        mime=mime,
        existing_mime=existing_mime,
        model=model,
        use_mock=use_mock,
        new_hash=new_hash,
        existing_hash=existing_hash,
    )


def chat_routed(
    messages: list[dict[str, str]],
    *,
    provider: Provider,
    use_mock: bool = False,
    model: str | None = None,
) -> str:
    if not messages:
        return "Ask me anything about UrbanPulse NYC."
    if use_mock:
        return mock_reply(messages[-1]["content"])
    if provider == "gemini":
        return chat_gemini(messages, system=GROKBOT_SYSTEM)
    return chat_grok(messages, use_mock=False, model=model)
