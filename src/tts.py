"""Text-to-speech: Grok Voice API, Gemini TTS, or browser speechSynthesis fallback.

Only one voice engine plays at a time. Duplicate utterances are suppressed so
Streamlit reruns do not stack overlapping speech.
"""

from __future__ import annotations

import base64
import hashlib
import html
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


def _utterance_id(text: str) -> str:
    return hashlib.sha1(text.strip().encode("utf-8")).hexdigest()[:16]


def grok_tts(text: str, *, voice_id: str = "eve") -> bytes:
    """xAI Grok TTS → MP3 bytes. Docs: POST https://api.x.ai/v1/tts"""
    key = _xai_key()
    if not key:
        raise RuntimeError("XAI_API_KEY required for Grok voice")
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
    """Single browser speechSynthesis utterance (cancels any prior speech)."""
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
          try {{
            window.speechSynthesis.cancel();
            const u = new SpeechSynthesisUtterance({repr(safe)});
            u.rate = 1.0;
            u.lang = "en-US";
            window.speechSynthesis.speak(u);
          }} catch (e) {{}}
        </script>
        """,
        height=0,
    )


def _play_audio_once(audio: bytes, mime: str) -> None:
    """Play cloud audio once via HTML — avoids st.audio autoplay on every rerun."""
    b64 = base64.b64encode(audio).decode("ascii")
    safe_mime = html.escape(mime)
    components.html(
        f"""
        <audio id="up-tts" autoplay style="display:none">
          <source src="data:{safe_mime};base64,{b64}" type="{safe_mime}">
        </audio>
        <script>
          try {{ window.speechSynthesis && window.speechSynthesis.cancel(); }} catch (e) {{}}
          const a = document.getElementById("up-tts");
          if (a) {{ a.play().catch(function(){{}}); }}
        </script>
        """,
        height=0,
    )


def synthesize(text: str, *, provider: Provider, use_mock: bool = False) -> tuple[bytes | None, str]:
    """
    Returns (audio_bytes, mime). Prefer cloud TTS; fall back to browser-only.
    Never stacks cloud + browser in the same call — caller plays one path.
    """
    if not text.strip():
        return None, "empty"
    if use_mock:
        return None, "browser"

    try:
        if provider == "gemini":
            return gemini_tts(text), "audio/wav"
        return grok_tts(text), "audio/mp3"
    except Exception:
        return None, "browser"


def speak_and_play(
    text: str,
    *,
    provider: Provider,
    use_mock: bool = False,
    key: str | None = None,
) -> None:
    """Synthesize and play exactly once per unique utterance (no overlapping voices)."""
    clipped = (text or "").strip()
    if not clipped:
        return

    uid = key or _utterance_id(clipped)
    spoken = list(st.session_state.get("_tts_spoken_ids") or [])
    if uid in spoken:
        return
    spoken.append(uid)
    st.session_state["_tts_spoken_ids"] = spoken[-40:]

    # Prefer a single engine: cloud if available, else browser — never both.
    if use_mock or bool(st.session_state.get("a11y_browser_backup", False)):
        browser_speak(clipped)
        return

    audio, mime = synthesize(clipped, provider=provider, use_mock=False)
    if audio and mime.startswith("audio/"):
        _play_audio_once(audio, mime)
        return
    # Cloud failed — one browser voice only
    browser_speak(clipped)
