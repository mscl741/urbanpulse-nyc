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


# Common NYC agency routes for 311-style civic reports
Agency = Literal[
    "DOT",  # Department of Transportation
    "NYPD",
    "FDNY",
    "DEP",  # Environmental Protection
    "DSNY",  # Sanitation
    "Parks",
    "HPD",  # Housing Preservation & Development
    "Other",
]


class DispatchTicket(BaseModel):
    """JSON contract Grok must satisfy so tickets are machine-routable."""

    hazard_type: str = Field(
        ...,
        min_length=2,
        max_length=80,
        description="Short hazard label, e.g. 'pothole' or 'broken traffic signal'",
    )
    severity: Severity
    agency: Agency
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Model confidence that the classification is correct",
    )
    summary: str = Field(
        ...,
        min_length=10,
        max_length=500,
        description="One-paragraph description for dispatchers",
    )
    council_email_subject: str = Field(..., min_length=5, max_length=120)
    council_email_body: str = Field(..., min_length=20, max_length=2000)
    recommended_priority: Literal["routine", "expedited", "emergency"]

    @field_validator("hazard_type")
    @classmethod
    def normalize_hazard(cls, value: str) -> str:
        return value.strip().lower()


SYSTEM_PROMPT = """You are UrbanPulse NYC, a civic hazard classifier for New York City 311-style reports.

Given a street-level photo and an intersection/location string, return ONLY valid JSON matching this schema:
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
- Route to the NYC agency that owns the hazard (e.g. potholes/signals → DOT, flooding → DEP).
- Draft the council email as a polite resident report with the intersection included.
- If the image is unclear, lower confidence and prefer "Other" / "routine" rather than guessing wildly.
- Do not wrap the JSON in markdown fences. Return raw JSON only.
"""
