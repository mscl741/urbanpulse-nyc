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
- Draft a polite resident email including the location string.
- If unclear, lower confidence; prefer "Other" / "routine" over guessing wildly.
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
