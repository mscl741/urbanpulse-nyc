"""Text-to-speech: Grok Voice API, Gemini TTS, or browser speechSynthesis fallback."""

from __future__ import annotations

import base64
import io
import os
import wave
from typing import Literal

import requests
import streamlit as st
import streamlit.components.v1 as components

Provider = Literal["grok", "gemini"]


def _xai_key() -> str | None:
    key = (os.getenv("XAI_API_KEY") or "").strip()
    if not key or key.startswith("your_"):
        return None
    return key


def _gemini_key() -> str | None:
    key = (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()
    if not key or key.startswith("your_"):
        return None
    return key


def grok_tts(text: str, *, voice_id: str = "eve") -> bytes:
    """xAI Grok TTS → MP3 bytes. Docs: POST https://api.x.ai/v1/tts"""
    key = _xai_key()
    if not key:
        raise RuntimeError("XAI_API_KEY required for Grok voice")
    # Keep utterances short for alerts / accessibility
    clipped = text.strip()[:1500]
    resp = requests.post(
        "https://api.x.ai/v1/tts",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        json={
            "text": clipped,
            "voice_id": voice_id or os.getenv("GROK_TTS_VOICE", "eve"),
            "language": "en",
        },
        timeout=60,
    )
    resp.raise_for_status()
    return resp.content


def gemini_tts(text: str, *, voice_name: str = "Kore") -> bytes:
    """Gemini TTS → WAV bytes (PCM wrapped)."""
    key = _gemini_key()
    if not key:
        raise RuntimeError("GEMINI_API_KEY required for Gemini voice")
    clipped = text.strip()[:1500]
    model = os.getenv("GEMINI_TTS_MODEL", "gemini-2.5-flash-preview-tts")
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={key}"
    )
    payload = {
        "contents": [{"parts": [{"text": clipped}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {
                    "prebuiltVoiceConfig": {
                        "voiceName": voice_name or os.getenv("GEMINI_TTS_VOICE", "Kore")
                    }
                }
            },
        },
    }
    resp = requests.post(url, json=payload, timeout=90)
    resp.raise_for_status()
    data = resp.json()
    try:
        b64 = data["candidates"][0]["content"]["parts"][0]["inlineData"]["data"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"Unexpected Gemini TTS response: {data}") from exc
    pcm = base64.b64decode(b64)
    return _pcm16_to_wav(pcm)


def _pcm16_to_wav(pcm: bytes, *, rate: int = 24000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(pcm)
    return buf.getvalue()


def browser_speak(text: str) -> None:
    """Always-available accessibility fallback using the phone/browser voice engine."""
    safe = (
        text.replace("\\", "\\\\")
        .replace("`", "'")
        .replace('"', "'")
        .replace("\n", " ")
        [:800]
    )
    components.html(
        f"""
        <script>
          const u = new SpeechSynthesisUtterance({repr(safe)});
          u.rate = 1.0;
          u.lang = "en-US";
          window.speechSynthesis.cancel();
          window.speechSynthesis.speak(u);
        </script>
        """,
        height=0,
    )


def synthesize(text: str, *, provider: Provider, use_mock: bool = False) -> tuple[bytes | None, str]:
    """
    Returns (audio_bytes, mime). audio_bytes may be None if only browser TTS was used.
    mime is 'audio/mp3' or 'audio/wav'.
    """
    if use_mock or not text.strip():
        browser_speak(text)
        return None, "browser"

    try:
        if provider == "gemini":
            return gemini_tts(text), "audio/wav"
        return grok_tts(text), "audio/mp3"
    except Exception as exc:
        # Fall back so visually impaired users still hear something
        browser_speak(f"{text}. (Cloud voice unavailable: {exc})")
        return None, "browser"


def speak_and_play(
    text: str,
    *,
    provider: Provider,
    use_mock: bool = False,
    key: str | None = None,
) -> None:
    """Synthesize and play in the Streamlit UI."""
    audio, mime = synthesize(text, provider=provider, use_mock=use_mock)
    if audio and mime.startswith("audio/"):
        st.audio(audio, format=mime, autoplay=True)
        # Also kick browser voice as redundancy on mobile autoplay blocks
        if st.session_state.get("a11y_browser_backup", True):
            browser_speak(text)
