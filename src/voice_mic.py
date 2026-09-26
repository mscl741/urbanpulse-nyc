"""Browser mic (SpeechRecognition) + optional Gemini audio transcription."""

from __future__ import annotations

import base64
import os
from typing import Literal

import requests
import streamlit as st
import streamlit.components.v1 as components

Provider = Literal["grok", "gemini"]


def browser_mic_panel(*, key: str = "mic") -> None:
    """
    On-page Speak button using the browser Web Speech API.
    Transcript appears in the HTML box — user copies into chat, or we mirror
    into session_state via a follow-up text field on the page.
    """
    components.html(
        f"""
        <div style="font-family: system-ui, sans-serif; padding: 0.25rem 0;">
          <button id="up-mic-{key}" style="
            padding: 0.5rem 1.15rem; border-radius: 999px; border: none;
            background: #1A73E8; color: #fff; font-weight: 600; cursor: pointer;
            font-family: Inter, system-ui, sans-serif; font-size: 0.95rem;
            box-shadow: 0 1px 3px rgba(26,115,232,0.35);
            transition: background 160ms ease;
          ">Speak</button>
          <span id="up-mic-status-{key}" style="margin-left:0.6rem;color:#5F6368;font-family:Inter,system-ui,sans-serif;font-size:0.9rem;"></span>
          <textarea id="up-mic-out-{key}" rows="2" style="
            width:100%; margin-top:0.65rem; padding:0.65rem 0.75rem; border-radius:12px;
            border:1px solid rgba(32,33,36,0.1); font-size: 0.95rem;
            font-family: Inter, system-ui, sans-serif; color: #202124;
            background: #fff; box-sizing: border-box;
          " placeholder="Your spoken words appear here — copy into the chat box below."></textarea>
        </div>
        <script>
          (function() {{
            const btn = document.getElementById("up-mic-{key}");
            const status = document.getElementById("up-mic-status-{key}");
            const out = document.getElementById("up-mic-out-{key}");
            const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
            if (!SR) {{
              status.textContent = "Voice input not supported in this browser — type instead.";
              btn.disabled = true;
              return;
            }}
            const rec = new SR();
            rec.lang = "en-US";
            rec.interimResults = false;
            rec.maxAlternatives = 1;
            let listening = false;
            btn.onclick = function() {{
              if (listening) {{ rec.stop(); return; }}
              try {{
                window.speechSynthesis && window.speechSynthesis.cancel();
                listening = true;
                status.textContent = "Listening… speak now";
                btn.textContent = "Stop";
                rec.start();
              }} catch (e) {{
                status.textContent = "Mic error: " + e;
                listening = false;
                btn.textContent = "Speak";
              }}
            }};
            rec.onresult = function(ev) {{
              const text = ev.results[0][0].transcript || "";
              out.value = text;
              status.textContent = "Got it — copy into chat, or paste below.";
              try {{
                localStorage.setItem("urbanpulse_voice_transcript", text);
              }} catch (e) {{}}
            }};
            rec.onerror = function(ev) {{
              status.textContent = "Mic: " + (ev.error || "error");
              listening = false;
              btn.textContent = "Speak";
            }};
            rec.onend = function() {{
              listening = false;
              btn.textContent = "Speak";
              if (status.textContent.indexOf("Listening") === 0) {{
                status.textContent = "Stopped";
              }}
            }};
          }})();
        </script>
        """,
        height=130,
    )


def pull_browser_transcript() -> str:
    """Best-effort: user may have used Speak; they paste into the field we provide."""
    return (st.session_state.get("voice_transcript_box") or "").strip()


def transcribe_audio_bytes(
    audio_bytes: bytes,
    *,
    mime: str = "audio/wav",
    provider: Provider = "gemini",
    use_mock: bool = False,
) -> str:
    """Transcribe a recorded clip. Gemini handles audio; mock/Grok fall back to empty."""
    if use_mock:
        return ""
    if provider != "gemini":
        # Grok path: rely on browser Speak panel; no cloud STT here.
        return ""
    key = (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()
    if not key or key.startswith("your_"):
        return ""
    model = os.getenv("GEMINI_CHAT_MODEL", "gemini-2.0-flash")
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={key}"
    )
    b64 = base64.b64encode(audio_bytes).decode("ascii")
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "text": (
                            "Transcribe this spoken English exactly. "
                            "Return only the transcript text, no quotes or commentary."
                        )
                    },
                    {"inline_data": {"mime_type": mime, "data": b64}},
                ],
            }
        ],
        "generationConfig": {"temperature": 0.1},
    }
    resp = requests.post(url, json=payload, timeout=90)
    resp.raise_for_status()
    data = resp.json()
    return (data["candidates"][0]["content"]["parts"][0]["text"] or "").strip()
