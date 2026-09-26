"""Structured municipal dispatch ticket returned by the vision engine."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


Agency = Literal[
    "DOT",
    "NYPD",
    "FDNY",
    "DEP",
    "DSNY",
    "Parks",
    "HPD",
    "Other",
]


# Weather / flood-like conditions — map pin + public alerts, NOT agency email.
# Do NOT treat hydrant leak / icy sidewalk alone as weather (reportable infrastructure).
WEATHER_TOKENS = (
    "flood",
    "flooding",
    "street flooding",
    "standing water",
    "ponding",
    "flash flood",
    "storm surge",
    "heavy rain",
    "rainwater",
    "inundation",
    "water accumulation",
)

_WEATHER_RADIUS_M: dict[str, float] = {
    "low": 100.0,
    "medium": 200.0,
    "high": 350.0,
    "critical": 500.0,
}


def is_weather_hazard_type(hazard_type: str) -> bool:
    """True for flood / standing-water style weather hazards (not infrastructure leaks)."""
    ht = (hazard_type or "").strip().lower()
    if not ht:
        return False
    # Explicit infrastructure exclusions even if "water" appears nearby in prose.
    if any(x in ht for x in ("hydrant", "icy", "ice", "leak", "pipe", "broken water main")):
        if not any(tok in ht for tok in ("flood", "flooding", "standing water", "ponding", "inundation")):
            return False
    return any(tok in ht for tok in WEATHER_TOKENS)


def weather_affected_radius_m(severity: str | Severity) -> float:
    """Affected-area radius (meters) for a weather hazard pin by severity."""
    key = severity.value if isinstance(severity, Severity) else str(severity).strip().lower()
    return _WEATHER_RADIUS_M.get(key, 200.0)


class DispatchTicket(BaseModel):
    """JSON contract Grok must satisfy so tickets are machine-routable."""

    hazard_type: str = Field(
        ...,
        min_length=2,
        max_length=80,
        description="Any urban hazard: pothole, scaffolding failure, flooding, graffiti on signal box, etc.",
    )
    severity: Severity
    agency: Agency
    confidence: float = Field(..., ge=0.0, le=1.0)
    summary: str = Field(..., min_length=10, max_length=500)
    council_email_subject: str = Field(..., min_length=5, max_length=120)
    council_email_body: str = Field(..., min_length=20, max_length=2000)
    recommended_priority: Literal["routine", "expedited", "emergency"]

    @field_validator("hazard_type")
    @classmethod
    def normalize_hazard(cls, value: str) -> str:
        return value.strip().lower()

    def is_recognized_hazard(self) -> bool:
        """False when the model found nothing actionable — skip filing / email."""
        ht = self.hazard_type.lower()
        no_hit = (
            "no hazard",
            "not a hazard",
            "no_hazard",
            "none detected",
            "unrecognized",
            "no issue",
            "not applicable",
            "n/a",
        )
        if any(token in ht for token in no_hit) or ht in {"none", "unknown", "n/a"}:
            return False
        if self.confidence < 0.35:
            return False
        return True

    def is_weather_hazard(self) -> bool:
        """Weather / flood conditions — map + alerts only; no agency email."""
        return is_weather_hazard_type(self.hazard_type)


class DuplicateVerdict(BaseModel):
    is_same_issue: bool
    confidence: float = Field(..., ge=0.0, le=1.0)
    reason: str = Field(..., min_length=5, max_length=400)


SYSTEM_PROMPT = """You are UrbanPulse NYC, a civic hazard classifier for New York City reports.

Any street / sidewalk / building-exterior hazard is in scope — not only potholes. Examples:
potholes, cracked pavement, sinkholes, broken curb, **defective pedestrian ramps / curb cuts**,
missing curb cuts, blocked accessible path, scaffolding issues, leaning tree, fallen branch,
flooded street, hydrant leak, illegal dumping, overflowing trash, broken traffic signal,
missing street sign, damaged bike lane, graffiti on signal cabinets, exposed wiring,
damaged bus shelter, icy sidewalk, construction debris, etc.

Accessibility infrastructure is a first-class category:
- Use hazard_type phrases like "defective pedestrian ramp", "missing curb cut",
  "blocked curb cut", "uneven accessible path" when the photo shows those failures.
- Route curb-cut / pedestrian-ramp defects to **DOT** (NYC Department of Transportation).

Return ONLY valid JSON:
{
  "hazard_type": string,
  "severity": "low" | "medium" | "high" | "critical",
  "agency": "DOT" | "NYPD" | "FDNY" | "DEP" | "DSNY" | "Parks" | "HPD" | "Other",
  "confidence": number between 0 and 1,
  "summary": string,
  "council_email_subject": string,
  "council_email_body": string,
  "recommended_priority": "routine" | "expedited" | "emergency"
}

Rules:
- Route to the NYC agency that owns the hazard.
- Draft a polite resident email including the location string for constructional /
  infrastructure hazards (potholes, scaffolding, signals, curb cuts, hydrant leaks, etc.).
- Weather hazards (flooding, standing water, ponding, flash flood, storm surge, heavy rain,
  rainwater, inundation, water accumulation): these are for map pins + public near-me alerts,
  NOT agency emails — the city cannot "fix" weather. Prefer hazard_type like
  "street flooding" or "standing water" when water + rain are evident. Still fill
  council_email_subject / council_email_body with short placeholders (schema requires them);
  the app will not send email for weather hazards.
- If weather-aid context is provided (recent rain / humidity), use it only as supporting
  evidence for flooding or wet pavement — never invent flooding that is not visible in the photo.
  When water on the street is visible AND recent rain is elevated, prefer hazard_type like
  "street flooding" or "standing water", agency DEP, and raise severity appropriately.
- Do NOT classify hydrant leaks or icy sidewalks alone as weather — those remain reportable
  infrastructure (agency email path).
- If the photo does NOT show a clear civic street / sidewalk / building-exterior hazard
  (e.g. selfie, indoor room, food, unrelated object, blank sky), set:
  hazard_type to "no hazard detected", confidence <= 0.25, severity "low", agency "Other",
  recommended_priority "routine", summarize why in summary, and put short placeholders in
  council_email_subject / council_email_body (the app will not send email for these).
- If unclear but possibly a hazard, lower confidence; prefer "Other" / "routine" over guessing.
- Raw JSON only — no markdown fences.
"""

DUPLICATE_PROMPT = """You are UrbanPulse NYC duplicate detection.

You receive TWO street photos from the same neighborhood / nearby coordinates, plus location text.
Decide if they show the SAME physical hazard instance (same hole, same pile, same broken signal),
not merely the same category of problem elsewhere.

Return ONLY JSON:
{
  "is_same_issue": boolean,
  "confidence": number between 0 and 1,
  "reason": string
}
"""
