"""Active AI provider: Grok (xAI) vs Gemini (Google).

Switch in `.env` by commenting / uncommenting ACTIVE_AI — not in the UI.
"""

from __future__ import annotations

import os
from typing import Literal

import streamlit as st

Provider = Literal["grok", "gemini"]


def get_provider() -> Provider:
    """
    Read ACTIVE_AI from .env (reloaded each call so edits apply after restart).

    In `.env`, leave exactly one line uncommented:
        ACTIVE_AI=grok
        # ACTIVE_AI=gemini
    or:
        # ACTIVE_AI=grok
        ACTIVE_AI=gemini
    """
    raw = (os.getenv("ACTIVE_AI") or "grok").strip().lower()
    return "gemini" if raw == "gemini" else "grok"


def set_provider(provider: Provider) -> None:
    """Kept for compatibility; UI no longer switches — edit ACTIVE_AI in .env."""
    st.session_state["ai_provider"] = provider


def voice_enabled() -> bool:
    return bool(st.session_state.get("a11y_voice", True))


def alert_voice_enabled() -> bool:
    return bool(st.session_state.get("a11y_alert_voice", True))


def location_consent() -> bool:
    return bool(st.session_state.get("location_consent", False))
