"""Accessibility / vulnerability profile for targeted safety alerts."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

PROFILE_PATH = Path(__file__).resolve().parent.parent / "data" / "safety_profile.json"


@dataclass
class SafetyProfile:
    lives_in_basement: bool = False
    limited_mobility: bool = False
    needs_accessible_transit: bool = False
    depends_on_medical_power: bool = False
    medical_notes: str = ""
    notify_early_flood: bool = True
    notify_power_risk: bool = True
    # Optional home pin used for risk checks when GPS not active
    home_latitude: float | None = None
    home_longitude: float | None = None
    home_label: str = ""

    def risk_tags(self) -> list[str]:
        tags: list[str] = []
        if self.lives_in_basement:
            tags.append("basement / low-lying residence")
        if self.limited_mobility:
            tags.append("limited mobility")
        if self.needs_accessible_transit:
            tags.append("needs accessible transit")
        if self.depends_on_medical_power:
            tags.append("electric medical equipment")
        return tags

    def is_high_priority(self) -> bool:
        return any(
            [
                self.lives_in_basement,
                self.limited_mobility,
                self.depends_on_medical_power,
            ]
        )


def load_profile() -> SafetyProfile:
    if not PROFILE_PATH.exists():
        return SafetyProfile()
    try:
        data = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
        return SafetyProfile(**{k: v for k, v in data.items() if k in SafetyProfile.__dataclass_fields__})
    except Exception:
        return SafetyProfile()


def save_profile(profile: SafetyProfile) -> None:
    PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROFILE_PATH.write_text(json.dumps(asdict(profile), indent=2), encoding="utf-8")
