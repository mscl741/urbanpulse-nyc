"""Outbound notification helpers: mailto + safe mock send (never hits real agencies)."""

from __future__ import annotations

import os
import smtplib
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import quote

from models import DispatchTicket

# Intended public / agency contacts for mailto drafts (NOT used by mock SMTP by default)
AGENCY_INTENDED_EMAIL: dict[str, str] = {
    "DOT": "dot.comments@example.nyc.gov",
    "NYPD": "nypd.community@example.nyc.gov",
    "FDNY": "fdny.info@example.nyc.gov",
    "DEP": "dep.help@example.nyc.gov",
    "DSNY": "dsny@example.nyc.gov",
    "Parks": "parks@example.nyc.gov",
    "HPD": "hpd@example.nyc.gov",
    "Other": "311@example.nyc.gov",
}

LOG_DIR = Path(__file__).resolve().parent.parent / "data" / "outbound_mail"


@dataclass
class MailDraft:
    to_address: str
    subject: str
    body: str
    agency: str


def placeholder_inbox() -> str:
    return os.getenv("NOTIFY_PLACEHOLDER_TO", "urbanpulse-mock@example.com")


def intended_agency_email(agency: str) -> str:
    return AGENCY_INTENDED_EMAIL.get(agency, AGENCY_INTENDED_EMAIL["Other"])


def build_draft(
    ticket: DispatchTicket,
    location: str,
    *,
    report_id: int | None = None,
    use_placeholder: bool = True,
) -> MailDraft:
    to_addr = placeholder_inbox() if use_placeholder else intended_agency_email(ticket.agency)
    subject = ticket.council_email_subject
    if report_id is not None:
        subject = f"[UrbanPulse #{report_id}] {subject}"

    body = (
        f"{ticket.council_email_body}\n\n"
        f"---\n"
        f"UrbanPulse NYC dispatch metadata\n"
        f"Location: {location}\n"
        f"Hazard: {ticket.hazard_type}\n"
        f"Severity: {ticket.severity.value}\n"
        f"Agency route: {ticket.agency}\n"
        f"Priority: {ticket.recommended_priority}\n"
        f"Confidence: {ticket.confidence:.0%}\n"
        f"Intended agency inbox (for production later): {intended_agency_email(ticket.agency)}\n"
    )
    if use_placeholder:
        body += (
            f"\n[SAFE MODE] This message is addressed to the placeholder inbox "
            f"({placeholder_inbox()}), not a real city mailbox.\n"
        )
    return MailDraft(to_address=to_addr, subject=subject, body=body, agency=ticket.agency)


def mailto_url(draft: MailDraft) -> str:
    return (
        f"mailto:{quote(draft.to_address, safe='@.')}"
        f"?subject={quote(draft.subject)}"
        f"&body={quote(draft.body)}"
    )


def mock_send(draft: MailDraft) -> dict:
    """
    'Send' without contacting a real government inbox.
    Writes a .eml-style log file and optionally relays via SMTP to the placeholder only.
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_subj = "".join(c if c.isalnum() or c in "-_" else "_" for c in draft.subject)[:60]
    path = LOG_DIR / f"{stamp}_{safe_subj}.txt"
    path.write_text(
        f"To: {draft.to_address}\nSubject: {draft.subject}\n\n{draft.body}",
        encoding="utf-8",
    )

    result = {
        "ok": True,
        "method": "mock_log",
        "to": draft.to_address,
        "log_file": str(path),
        "sent_at": datetime.now(timezone.utc).isoformat(),
    }

    # Optional: real SMTP, but ONLY to the configured placeholder address
    smtp_host = os.getenv("SMTP_HOST", "").strip()
    if smtp_host:
        allowed = placeholder_inbox().lower()
        if draft.to_address.lower() != allowed:
            raise RuntimeError(
                f"Refusing SMTP send to {draft.to_address}; "
                f"mock mode may only send to {allowed}"
            )
        msg = EmailMessage()
        msg["From"] = os.getenv("SMTP_FROM", "urbanpulse@localhost")
        msg["To"] = draft.to_address
        msg["Subject"] = draft.subject
        msg.set_content(draft.body)
        with smtplib.SMTP(smtp_host, int(os.getenv("SMTP_PORT", "587"))) as smtp:
            if os.getenv("SMTP_STARTTLS", "1") == "1":
                smtp.starttls()
            user = os.getenv("SMTP_USER", "")
            password = os.getenv("SMTP_PASSWORD", "")
            if user:
                smtp.login(user, password)
            smtp.send_message(msg)
        result["method"] = "smtp_placeholder"
    return result
