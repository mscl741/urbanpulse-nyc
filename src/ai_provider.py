"""Active AI provider + opt-in voice services (default OFF)."""

from __future__ import annotations

import os
from typing import Literal

import streamlit as st

Provider = Literal["grok", "gemini"]


def get_provider() -> Provider:
    """
    Read ACTIVE_AI from .env.

    In `.env`, leave exactly one line uncommented:
        ACTIVE_AI=grok
        # ACTIVE_AI=gemini
    """
    raw = (os.getenv("ACTIVE_AI") or "grok").strip().lower()
    return "gemini" if raw == "gemini" else "grok"


def set_provider(provider: Provider) -> None:
    st.session_state["ai_provider"] = provider


def voice_services_enabled() -> bool:
    """Master switch — off by default so TTS never surprises users."""
    return bool(st.session_state.get("a11y_voice_master", False))


def voice_for_reports() -> bool:
    return voice_services_enabled() and bool(st.session_state.get("a11y_voice_reports", True))


def voice_for_chat() -> bool:
    return voice_services_enabled() and bool(st.session_state.get("a11y_voice_chat", True))


def voice_for_scan() -> bool:
    return voice_services_enabled() and bool(st.session_state.get("a11y_voice_scan", True))


def voice_enabled() -> bool:
    """Backward-compatible: any voice feature armed."""
    return voice_services_enabled()


def alert_voice_enabled() -> bool:
    return voice_for_scan()


def location_consent() -> bool:
    return bool(st.session_state.get("location_consent", False))
