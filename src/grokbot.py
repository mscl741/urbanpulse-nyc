"""Hazard Helper — conversational assistant for UrbanPulse NYC users."""

from __future__ import annotations

import os
from typing import Any

from openai import OpenAI

GROKBOT_SYSTEM = """You are Hazard Helper, the in-app assistant for UrbanPulse NYC — an
accessibility-focused civic app that helps New Yorkers report street hazards, map open issues,
catch duplicates, and get early flood / evacuation support when storms hit.

You help residents and teammates with:
- How to report hazards (any type: potholes, floods, curb cuts / pedestrian ramps, signals, etc.)
- Filing from chat when a photo + location are provided (the app runs vision and may create a ticket)
- Near-me hazard scans and opt-in voice services (TTS / Speak mic) — voice is OFF unless the user enables it
- Using location sharing (opt-in), the live map, and duplicate "issue already logged" messages
- Accessibility: basement flood early warnings, limited mobility, Access-A-Ride / 311 evacuation help
- Pointing to official NYC resources: 311, Know Your Zone, OEM, FloodNet, Access-A-Ride
- Explaining flood / rain heads-ups that blend neighborhood flood pins, short-range forecasts,
  and NASA satellite rain observations (describe this simply as "satellite weather" — never
  mention API keys, model names, or internal config)

When discussing a photo the app already classified:
- If no civic hazard (sunset, selfie, food, indoor unrelated scene), clearly say there are
  NO visible street/sidewalk hazards, explain briefly, and ask if they have another issue to log.
- Never invent a hazard that is not in the photo.

Tone: clear, calm, practical. Short paragraphs. If unsure about live city status,
send people to 311 / OEM. Never claim you already called 311. Do not invent credentials
or mention internal tools, model names, or configuration details.
"""


def _client() -> OpenAI:
    api_key = os.getenv("XAI_API_KEY")
    if not api_key or api_key.startswith("your_"):
        raise RuntimeError("Assistant is temporarily unavailable.")
    return OpenAI(api_key=api_key.strip(), base_url="https://api.x.ai/v1")


def mock_reply(user_text: str) -> str:
    q = user_text.lower()
    if "curb" in q or "ramp" in q:
        return (
            "**Curb cuts / pedestrian ramps:** On **Report**, upload a photo of the broken "
            "or missing ramp. We’ll label it for **DOT** when possible. Take a clear photo "
            "of the ramp from the sidewalk so the damage or missing cut is visible.\n\n"
            "Need more help? Ask me how to use the live map or near-me scan."
        )
    if "flood" in q or "basement" in q:
        return (
            "**Flood / basement safety:** Open **Near-me & safety**, turn on basement or "
            "limited-mobility flags, set your home neighborhood, and Save. UrbanPulse checks "
            "nearby flood hotspots, short-range rain forecast, and satellite rain observations, "
            "then can raise a priority alert so you can move early. Also use "
            "[Know Your Zone](https://www.nyc.gov/knowyourzone) and call **311** in a real emergency."
        )
    if "map" in q or "pin" in q:
        return (
            "**Live map:** Open issues show as pins on a street map. Select a pin below the map "
            "to see the photo. **Mark resolved** removes it from the open view."
        )
    if "voice" in q or "speak" in q or "tts" in q or "blind" in q or "visually" in q:
        return (
            "**Voice & accessibility:** In the sidebar, turn on **voice services**, then choose "
            "what to hear (report results, Hazard Helper replies, near-me scans). On **Report** "
            "or **Near-me & safety**, opt into **location sharing** so we can announce when you "
            "enter a flood or open-hazard zone. Hazard Helper replies are spoken when that "
            "option is enabled."
        )
    if "error" in q or "broken" in q or "work" in q or "fix" in q:
        return (
            "**Troubleshooting:**\n"
            "1. Hard refresh the page (Ctrl+Shift+R).\n"
            "2. Location: tap the GPS button and **Allow** in the browser, or pick a borough.\n"
            "3. If something still fails, try **Report** with a clear photo, or ask me again.\n"
            "4. In an emergency, call **311**."
        )
    if "311" in q or "evacuat" in q or "access-a-ride" in q or "access a ride" in q:
        return (
            "**Evacuation / Access-A-Ride:** Transit including Access-A-Ride may shut down "
            "**hours before** a storm. If there is an evacuation order and you have no safe way "
            "out, call **311** (VRS 212-639-9675 / TTY 212-504-4115) for accessible transport. "
            "See **Near-me & safety** and [OEM AFN guidance](https://www.nyc.gov/site/em/ready/"
            "disabilities-access-functional-needs.page)."
        )
    return (
        "I'm **Hazard Helper**. Ask about reporting hazards, the live map, flood/basement "
        "alerts, curb cuts, Access-A-Ride / 311 evacuation help, or how to use voice services."
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
