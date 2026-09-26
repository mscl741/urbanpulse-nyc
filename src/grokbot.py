"""GrokBot — conversational assistant for UrbanPulse NYC users."""

from __future__ import annotations

import os
from typing import Any

from openai import OpenAI

GROKBOT_SYSTEM = """You are GrokBot, the in-app assistant for UrbanPulse NYC — a DivHacks
"Hack the City" civic app that turns hazard photos into municipal dispatch tickets,
maps open issues, catches duplicates, and helps vulnerable New Yorkers during floods.

You help residents and teammates with:
- How to report hazards (any type: potholes, floods, curb cuts / pedestrian ramps, signals, etc.)
- Filing from chat when a photo + location are provided (the app runs vision and may create a ticket)
- Near-me hazard scans and opt-in voice services (TTS / Speak mic) — voice is OFF unless the user enables it
- Using location sharing (opt-in), the live map, and duplicate "issue already logged" messages
- Accessibility: basement flood early warnings, limited mobility, Access-A-Ride / 311 evacuation help
- Pointing to official NYC resources: 311, Know Your Zone, OEM, FloodNet, Access-A-Ride

When discussing a photo the app already classified:
- If no civic hazard (sunset, selfie, food, indoor unrelated scene), clearly say there are
  NO visible street/sidewalk hazards, explain briefly, and ask if they have another issue to log.
- Never invent a hazard that is not in the photo.

Tone: clear, calm, practical. Short paragraphs. If unsure about live city status,
send people to 311 / OEM. Never claim you already called 311. Do not invent API keys.
"""


def _client() -> OpenAI:
    api_key = os.getenv("XAI_API_KEY")
    if not api_key or api_key.startswith("your_"):
        raise RuntimeError("XAI_API_KEY is missing. Add it to .env or use Mock replies.")
    return OpenAI(api_key=api_key.strip(), base_url="https://api.x.ai/v1")


def mock_reply(user_text: str) -> str:
    q = user_text.lower()
    if "curb" in q or "ramp" in q:
        return (
            "**Curb cuts / pedestrian ramps:** On **Report**, upload a photo of the broken "
            "or missing ramp. With Mock AI off, Grok labels it for **DOT**. In Mock mode, "
            "name the file something like `curb_ramp.jpg` to demo the category.\n\n"
            "*(Mock GrokBot — turn Mock AI off for live answers.)*"
        )
    if "flood" in q or "basement" in q:
        return (
            "**Flood / basement safety:** Open **Safety & alerts**, turn on basement or "
            "limited-mobility flags, set your home neighborhood, and Save. UrbanPulse checks "
            "nearby flood hotspots + short-range rain forecast and can raise a priority alert "
            "so you can move early. Also use [Know Your Zone](https://www.nyc.gov/knowyourzone) "
            "and call **311** in a real emergency.\n\n"
            "*(Mock GrokBot — enable live Grok for fuller help.)*"
        )
    if "map" in q or "pin" in q:
        return (
            "**Live map:** Open issues show as pins on a street map. Select a pin below the map "
            "to see the photo. **Mark resolved** removes it from the open view. "
            "Add `GOOGLE_MAPS_API_KEY` for the full Google Maps experience.\n\n"
            "*(Mock GrokBot.)*"
        )
    if "voice" in q or "speak" in q or "tts" in q or "blind" in q or "visually" in q:
        return (
            "**Voice & accessibility:** In the sidebar, turn on **Voice guidance** and "
            "**Spoken hazard-area alerts**. Choose **Grok** or **Gemini** as the dominant AI "
            "for photo scanning and text-to-speech. On **Report** / **Safety**, opt into "
            "**location sharing** so we can announce when you enter a flood or open-hazard zone. "
            "GrokBot replies are also spoken aloud when Voice guidance is on.\n\n"
            "*(Mock GrokBot.)*"
        )
    if "error" in q or "broken" in q or "work" in q or "fix" in q:
        return (
            "**Troubleshooting:**\n"
            "1. Hard refresh the page (Ctrl+Shift+R).\n"
            "2. Sidebar → if you have no xAI key, leave **Mock AI** on.\n"
            "3. For live vision/chat, set `XAI_API_KEY` in `.env` and turn Mock AI off.\n"
            "4. Location: tap the GPS button and **Allow** in the browser, or pick a borough.\n"
            "5. Restart with `streamlit run src/app.py` if the server crashed.\n\n"
            "*(Mock GrokBot.)*"
        )
    if "311" in q or "evacuat" in q or "access-a-ride" in q or "access a ride" in q:
        return (
            "**Evacuation / Access-A-Ride:** Transit including Access-A-Ride may shut down "
            "**hours before** a storm. If there is an evacuation order and you have no safe way "
            "out, call **311** (VRS 212-639-9675 / TTY 212-504-4115) for accessible transport. "
            "See **Safety & alerts** and [OEM AFN guidance](https://www.nyc.gov/site/em/ready/"
            "disabilities-access-functional-needs.page).\n\n"
            "*(Mock GrokBot.)*"
        )
    return (
        "I'm **GrokBot** (mock mode). Ask about reporting hazards, the live map, flood/basement "
        "alerts, curb cuts, Access-A-Ride / 311 evacuation help, or app errors.\n\n"
        "For live Grok answers: add `XAI_API_KEY` to `.env` and turn **Mock AI** off in the sidebar."
    )


def chat_once(
    messages: list[dict[str, str]],
    *,
    use_mock: bool = False,
    model: str | None = None,
) -> str:
    """
    messages: prior turns as {role: user|assistant, content: str}, NOT including system.
    Returns assistant text.
    """
    if not messages:
        return "Ask me anything about UrbanPulse NYC."

    if use_mock:
        return mock_reply(messages[-1]["content"])

    model_name = model or os.getenv("GROK_MODEL", "grok-4.7")
    client = _client()
    api_messages: list[dict[str, Any]] = [{"role": "system", "content": GROKBOT_SYSTEM}]
    # Keep last N turns to control cost/context
    for m in messages[-16:]:
        api_messages.append({"role": m["role"], "content": m["content"]})

    response = client.chat.completions.create(
        model=model_name,
        temperature=0.4,
        messages=api_messages,
    )
    return (response.choices[0].message.content or "").strip() or "(No reply — try again.)"
