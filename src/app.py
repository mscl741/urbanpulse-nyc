"""
UrbanPulse NYC — civic hazard reporting.

Pages: Home · Report · Live map · Ops
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from PIL import Image

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ai_provider import (  # noqa: E402
    get_provider,
    location_consent,
    voice_for_chat,
    voice_for_reports,
    voice_for_scan,
    voice_services_enabled,
)
from db import (  # noqa: E402
    attach_image,
    db_status,
    find_open_by_hash,
    get_ticket,
    init_db,
    map_tickets,
    mark_email_sent,
    nearby_open_reports,
    recent_tickets,
    resolve_ticket,
    save_ticket,
    severity_by_hour,
)
from evacuation import (  # noqa: E402
    LINKS as EVAC_LINKS,
    assistance_blurb,
    nearest_centers,
)
from flood_risk import RESOURCES as FLOOD_LINKS, assess_flood_risk  # noqa: E402
from geo_alerts import alert_fingerprint, build_area_alerts, scan_nearby_hazards  # noqa: E402
from geo_services import (  # noqa: E402
    fast_location_choices,
    google_maps_api_key,
    reverse_geocode,
    strip_choice_meta,
)
from map_view import render_incident_map  # noqa: E402
from media import image_sha256, read_image_bytes, save_report_image  # noqa: E402
from models import DispatchTicket  # noqa: E402
from notify import (  # noqa: E402
    build_draft,
    intended_agency_email,
    mailto_url,
    mock_send,
    placeholder_inbox,
)
from nyc_areas import NYC_BOROUGHS  # noqa: E402
from safety_profile import SafetyProfile, load_profile, save_profile  # noqa: E402
from theme import apply_theme  # noqa: E402
from tts import speak_and_play  # noqa: E402
from vision_router import (  # noqa: E402
    analyze_hazard_routed,
    chat_routed,
    check_duplicate_routed,
)
from voice_mic import browser_mic_panel, transcribe_audio_bytes  # noqa: E402

try:
    from streamlit_geolocation import streamlit_geolocation
except Exception:  # noqa: BLE001
    streamlit_geolocation = None  # type: ignore[assignment,misc]

load_dotenv(ROOT.parent / ".env")

st.set_page_config(
    page_title="UrbanPulse NYC",
    page_icon="🗽",
    layout="wide",
    initial_sidebar_state="expanded",
)

def _boot() -> None:
    apply_theme()
    try:
        if "_db_bootstrapped" not in st.session_state:
            init_db()
            st.session_state["_db_bootstrapped"] = True
    except Exception as exc:  # noqa: BLE001
        st.sidebar.error(f"DB init failed: {exc}")


def settings_rail() -> tuple[bool, str]:
    """Sidebar: public-friendly controls only (no API/vendor jargon)."""
    has_cloud = bool(
        (
            os.getenv("XAI_API_KEY")
            and not os.getenv("XAI_API_KEY", "").startswith("your_")
        )
        or (
            (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()
            and not (os.getenv("GEMINI_API_KEY") or "").startswith("your_")
        )
    )
    # Demo mode is automatic when no cloud keys are configured — never shown in UI.
    use_mock = not has_cloud
    model = os.getenv("GROK_MODEL", "grok-4.7")

    with st.sidebar:
        st.markdown("### UrbanPulse")
        st.caption("Civic reporting for New York")

        st.markdown("#### Accessibility")
        st.toggle(
            "Enable voice services",
            value=st.session_state.get("a11y_voice_master", False),
            key="a11y_voice_master",
            help="When on, the app can read report results, Hazard Helper replies, and near-me scans aloud.",
        )
        voice_on = bool(st.session_state.get("a11y_voice_master", False))
        st.toggle(
            "Speak report results",
            value=st.session_state.get("a11y_voice_reports", True),
            key="a11y_voice_reports",
            disabled=not voice_on,
        )
        st.toggle(
            "Speak Hazard Helper replies",
            value=st.session_state.get("a11y_voice_chat", True),
            key="a11y_voice_chat",
            disabled=not voice_on,
        )
        st.toggle(
            "Speak near-me scans & area alerts",
            value=st.session_state.get("a11y_voice_scan", True),
            key="a11y_voice_scan",
            disabled=not voice_on,
            help="Also used for spoken flood / open-hazard zone alerts.",
        )
        st.toggle(
            "Use phone voice only",
            value=st.session_state.get("a11y_browser_backup", False),
            key="a11y_browser_backup",
            disabled=not voice_on,
            help="Prefer your device’s built-in speech.",
        )
        if not voice_on:
            st.caption("Voice is off — nothing will be read aloud until you enable it.")

        status = db_status()
        if status.get("ok"):
            st.caption(
                f"{status.get('open_count', 0)} open hazards · "
                f"{status.get('report_count', 0)} total reports"
            )
        st.divider()
    return use_mock, model


def _maybe_speak(
    text: str,
    *,
    use_mock: bool,
    feature: str = "reports",
) -> None:
    """Speak only when master voice is on AND the feature flag matches."""
    allowed = {
        "reports": voice_for_reports,
        "chat": voice_for_chat,
        "scan": voice_for_scan,
    }.get(feature, voice_services_enabled)
    if not allowed():
        return
    speak_and_play(text, provider=get_provider(), use_mock=use_mock)


def _run_geofence_alerts(lat: float, lon: float, *, use_mock: bool) -> None:
    """Speak when the user enters a flood / open-hazard zone (consent + voice scan)."""
    if not location_consent() or not voice_for_scan():
        return
    profile = load_profile()
    lines = build_area_alerts(lat, lon, profile)
    if not lines:
        return
    fp = alert_fingerprint(lines, lat, lon)
    if st.session_state.get("last_alert_fp") == fp:
        return
    st.session_state["last_alert_fp"] = fp
    spoken = " ".join(lines)
    st.warning("Hazard-area alert (spoken)")
    for line in lines:
        st.markdown(f"- {line}")
    _maybe_speak(spoken, use_mock=use_mock, feature="scan")


# ---------- location picker (shared) ----------


def _load_nearby(lat: float, lon: float) -> None:
    """Fast path: static NYC neighborhoods + one reverse-geocode (Google if keyed)."""
    cache_key = (round(lat, 4), round(lon, 4))
    if st.session_state.get("nearby_cache_key") == cache_key:
        return
    # Neighborhoods are instant; reverse geocode is a short network call
    with st.spinner("Resolving your address…"):
        choices, warning = fast_location_choices(lat, lon)
        st.session_state["nearby_choices"] = choices
        st.session_state["nearby_cache_key"] = cache_key
        if warning:
            st.session_state["nearby_warning"] = warning
        else:
            st.session_state.pop("nearby_warning", None)
        # Prefer the reverse-geocoded "Near me" line as the ticket location
        if choices and choices[0].startswith("Near me - "):
            if not st.session_state.get("location_manual"):
                st.session_state["location_manual"] = strip_choice_meta(choices[0])


def _coords_from_browser(geo: object) -> tuple[float, float] | None:
    if not geo or not isinstance(geo, dict):
        return None
    lat, lon = geo.get("latitude"), geo.get("longitude")
    if lat in (None, "Null", "null") or lon in (None, "Null", "null"):
        return None
    try:
        return float(lat), float(lon)
    except (TypeError, ValueError):
        return None


def location_consent_controls(*, key_prefix: str = "report") -> bool:
    """Opt-in location sharing for filing + spoken geofence alerts."""
    del key_prefix  # reserved for future per-page labels
    st.markdown("#### Location sharing")
    if "location_consent" not in st.session_state:
        st.session_state["location_consent"] = False
    consented = st.toggle(
        "I allow UrbanPulse to use my location",
        key="location_consent",
        help=(
            "Required for GPS filing, nearby duplicate checks, and spoken hazard-area alerts "
            "(flood / open hazards). You can turn this off anytime."
        ),
    )
    if not consented:
        st.caption(
            "Location is off. You can still type an intersection or pick a neighborhood "
            "without sharing live GPS. Spoken area alerts stay disabled until you opt in."
        )
    return bool(consented)


def location_picker(*, use_mock: bool = False, key_prefix: str = "report") -> tuple[str, float | None, float | None]:
    st.markdown("#### Where is it?")
    consented = location_consent_controls(key_prefix=key_prefix)
    st.caption(
        "On your phone: allow location below, then tap **Share my location**. "
        "We pull GPS once and resolve a nearby address for your report."
    )

    st.markdown("**1 · Share my exact location**")
    if not consented:
        st.info("Turn on **I allow UrbanPulse to use my location** to enable GPS sharing.")
    elif streamlit_geolocation is not None:
        try:
            geo = streamlit_geolocation()
            browser_coords = _coords_from_browser(geo)
            if browser_coords:
                # Only refresh when coords actually change
                prev = st.session_state.get("gps") or {}
                moved = (
                    abs(float(prev.get("latitude", 0)) - browser_coords[0]) > 1e-5
                    or abs(float(prev.get("longitude", 0)) - browser_coords[1]) > 1e-5
                    or prev.get("source") != "device"
                )
                if moved:
                    st.session_state.pop("nearby_cache_key", None)
                    addr = reverse_geocode(browser_coords[0], browser_coords[1])
                    st.session_state["gps"] = {
                        "latitude": browser_coords[0],
                        "longitude": browser_coords[1],
                        "source": "device",
                        "area": addr.get("label") or "device location",
                    }
                    st.session_state["location_manual"] = addr.get("label") or ""
                    st.session_state["gps_just_updated"] = True
        except Exception as exc:  # noqa: BLE001
            st.warning(f"Location button unavailable ({exc}). Use borough picker below.")
    else:
        st.info("Location component missing — use borough picker or typed GPS.")

    st.markdown("**2 · Or pick a NYC area**")
    boroughs = list(NYC_BOROUGHS.keys())
    bcol, ncol, lcol = st.columns([1, 1.4, 1])
    with bcol:
        borough = st.selectbox("Borough", options=boroughs, index=0, key=f"{key_prefix}_boro")
    with ncol:
        hoods = list(NYC_BOROUGHS[borough].keys())
        neighborhood = st.selectbox(
            "Neighborhood", options=hoods, key=f"{key_prefix}_hood"
        )
    with lcol:
        st.write("")
        st.write("")
        if st.button("Use this area", use_container_width=True, key=f"{key_prefix}_use_area"):
            pin = NYC_BOROUGHS[borough][neighborhood]
            st.session_state.pop("nearby_cache_key", None)
            label = f"{borough} · {neighborhood}"
            st.session_state["gps"] = {
                "latitude": pin["latitude"],
                "longitude": pin["longitude"],
                "source": "area",
                "area": label,
            }
            st.session_state["location_manual"] = label
            st.session_state["gps_just_updated"] = True

    with st.expander("Advanced: type GPS"):
        c1, c2, c3 = st.columns(3)
        with c1:
            lat = st.number_input(
                "Latitude", value=40.7580, format="%.5f", key=f"{key_prefix}_manual_lat"
            )
        with c2:
            lon = st.number_input(
                "Longitude", value=-73.9855, format="%.5f", key=f"{key_prefix}_manual_lon"
            )
        with c3:
            st.write("")
            st.write("")
            if st.button(
                "Use typed coordinates",
                use_container_width=True,
                key=f"{key_prefix}_use_gps",
            ):
                st.session_state.pop("nearby_cache_key", None)
                addr = reverse_geocode(float(lat), float(lon))
                st.session_state["gps"] = {
                    "latitude": float(lat),
                    "longitude": float(lon),
                    "source": "manual_gps",
                    "area": addr.get("label") or "typed coordinates",
                }
                st.session_state["location_manual"] = addr.get("label") or ""
                st.session_state["gps_just_updated"] = True

    gps = st.session_state.get("gps")
    lat_out = lon_out = None
    if gps:
        lat_out = float(gps["latitude"])
        lon_out = float(gps["longitude"])
        st.success(f"Located · {gps.get('area', 'pin')}")
        _load_nearby(lat_out, lon_out)
        if warn := st.session_state.get("nearby_warning"):
            st.info(warn)
        choices = st.session_state.get("nearby_choices") or []
        if choices:
            picked = st.selectbox(
                "Confirm place near you",
                options=choices,
                key=f"{key_prefix}_nearby_pick",
            )
            clean = strip_choice_meta(picked)
            if st.session_state.get("last_nearby_pick") != picked:
                st.session_state["location_manual"] = clean
                st.session_state["last_nearby_pick"] = picked
        # Only announce on a fresh pin change — not on every Streamlit rerun
        if consented and st.session_state.pop("gps_just_updated", False):
            _run_geofence_alerts(lat_out, lon_out, use_mock=use_mock)

    if "location_manual" not in st.session_state:
        st.session_state["location_manual"] = ""
    manual = st.text_input(
        "Intersection / landmark on the ticket",
        placeholder="e.g. Broadway & W 125th St, Manhattan",
        key="location_manual",
    )
    return manual.strip(), lat_out, lon_out


# ---------- ticket UI ----------


def render_ticket(
    ticket: DispatchTicket,
    location: str,
    report_id: int | None = None,
    *,
    include_email: bool = True,
) -> None:
    saved = f" · #{report_id}" if report_id is not None else ""
    st.markdown(
        f"<div class='up-panel'><h3 style='margin:0'>Dispatch · "
        f"{ticket.hazard_type.title()}{saved}</h3>"
        f"<p style='margin:0.4rem 0 0;color:#3a4050'>{location}</p></div>",
        unsafe_allow_html=True,
    )
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Severity", ticket.severity.value.upper())
    c2.metric("Agency", ticket.agency)
    c3.metric("Priority", ticket.recommended_priority)
    c4.metric("Confidence", f"{ticket.confidence:.0%}")
    st.write(ticket.summary)

    if not include_email or not ticket.is_recognized_hazard():
        st.info("No agency email draft — no clear civic hazard was recognized.")
        return

    st.markdown("#### Notify")
    st.caption(
        f"Route: **{ticket.agency}** · safe inbox `{placeholder_inbox()}` "
        f"(intended `{intended_agency_email(ticket.agency)}`)"
    )
    use_placeholder = st.radio(
        "Destination",
        ["Placeholder inbox (safe)", "Intended agency (mailto preview)"],
        horizontal=True,
        key=f"mail_dest_{report_id}",
    )
    draft = build_draft(
        ticket,
        location,
        report_id=report_id,
        use_placeholder=use_placeholder.startswith("Placeholder"),
    )
    st.text_input("To", value=draft.to_address, disabled=True, key=f"to_{report_id}")
    st.text_input("Subject", value=draft.subject, disabled=True, key=f"sub_{report_id}")
    st.text_area("Body", value=draft.body, height=160, disabled=True, key=f"body_{report_id}")
    m1, m2 = st.columns(2)
    with m1:
        st.link_button("Open in email app", mailto_url(draft), use_container_width=True)
    with m2:
        if st.button("Send notification (demo)", type="primary", use_container_width=True, key=f"mock_{report_id}"):
            try:
                result = mock_send(draft)
                if report_id is not None:
                    mark_email_sent(
                        report_id,
                        to_address=result["to"],
                        method=result["method"],
                    )
                st.success(f"Logged → {result['log_file']}")
            except Exception:  # noqa: BLE001
                st.error("Couldn’t send that notification right now. The report is still saved.")


def find_duplicate(
    image_bytes: bytes,
    location: str,
    lat: float | None,
    lon: float | None,
    *,
    mime: str,
    use_mock: bool,
    model: str,
) -> dict | None:
    """Return matching open report dict if active AI (or hash) says same issue."""
    digest = image_sha256(image_bytes)
    by_hash = find_open_by_hash(digest)
    if by_hash:
        return by_hash

    candidates: list[dict] = []
    if lat is not None and lon is not None:
        candidates = nearby_open_reports(lat, lon, radius_m=120.0, limit=6)
    if not candidates:
        return None

    provider = get_provider()
    for cand in candidates:
        existing_bytes = read_image_bytes(cand.get("image_path"))
        if not existing_bytes:
            continue
        try:
            verdict = check_duplicate_routed(
                image_bytes,
                existing_bytes,
                location,
                cand.get("summary") or cand.get("hazard_type") or "",
                provider=provider,
                mime=mime,
                use_mock=use_mock,
                model=model,
                new_hash=digest,
                existing_hash=cand.get("image_hash"),
            )
        except Exception:
            continue
        if verdict.is_same_issue and verdict.confidence >= 0.65:
            cand = dict(cand)
            cand["dup_reason"] = verdict.reason
            cand["dup_confidence"] = verdict.confidence
            return cand
    return None


# ---------- pages ----------


def render_home() -> None:
    _boot()
    settings_rail()
    st.markdown(
        """
        <div class="up-hero">
          <div class="up-kicker">Civic reporting for New York</div>
          <h1 class="up-brand">UrbanPulse<br/><span>NYC</span></h1>
          <p class="up-lede">
            Snap a street hazard — any kind — and we classify it, route it to the
            right city agency, and pin it on a live map so New Yorkers don’t file
            the same issue twice. Built for accessibility: voice guidance, spoken
            hazard-area alerts, flood early-warnings, curb-cut reporting, and
            evacuation help when storms hit.
          </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    a, b, c, d = st.columns(4)
    with a:
        st.page_link(page_report, label="Report a hazard", icon="📷")
    with b:
        st.page_link(page_map, label="Open live map", icon="🗺️")
    with c:
        st.page_link(page_safety, label="Near-me scan & safety", icon="♿")
    with d:
        st.page_link(page_bot, label="Ask Hazard Helper", icon="💬")

    st.markdown("### How it works")
    x, y, z = st.columns(3)
    x.markdown(
        "**1 · Capture**\n\nPhoto + optional GPS (you choose location sharing) or any NYC neighborhood."
    )
    y.markdown(
        "**2 · Classify + optional voice**\n\nWe review the photo and help route it. Enable voice if you want results read aloud."
    )
    z.markdown(
        "**3 · Scan + chat**\n\nNear-me hazard scan, Hazard Helper with Speak + photo filing, flood alerts."
    )

    status = db_status()
    if status.get("ok"):
        st.caption(
            f"Live pulse · {status.get('open_count', 0)} open hazards on the map right now."
        )


def render_report() -> None:
    _boot()
    use_mock, model = settings_rail()
    provider = get_provider()
    st.markdown("## Report a hazard")
    st.caption(
        "Potholes, flooding, signals, dumping, scaffolding, trees, **defective curb cuts / "
        "pedestrian ramps** — any street or accessibility issue counts."
    )

    uploaded = st.file_uploader("Hazard photo", type=["jpg", "jpeg", "png", "webp"])
    location, lat, lon = location_picker(use_mock=use_mock, key_prefix="report")
    go = st.button("Analyze & file", type="primary", use_container_width=True)

    if uploaded:
        st.image(Image.open(uploaded), use_container_width=True)

    if not go:
        return
    if not uploaded:
        st.error("Add a photo first.")
        return
    if not location:
        st.error("Add a location.")
        return
    if lat is None or lon is None:
        st.warning(
            "No map pin yet — pick a neighborhood or share GPS so we can check duplicates + show it on the map."
        )

    mime = uploaded.type or "image/jpeg"
    image_bytes = uploaded.getvalue()

    with st.spinner("Checking for an existing open issue nearby…"):
        dup = find_duplicate(
            image_bytes,
            location,
            lat,
            lon,
            mime=mime,
            use_mock=use_mock,
            model=model,
        )

    if dup:
        st.markdown(
            f"""
            <div class="up-dup">
              <strong>Issue already logged</strong><br/>
              Report #{dup['id']} · {dup.get('hazard_type','').title()} ·
              filed {dup.get('created_at')}<br/>
              {dup.get('location')}<br/>
              <span style="opacity:0.85">{dup.get('dup_reason', 'Matched an open report in this area.')}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if dup.get("image_path") and Path(dup["image_path"]).exists():
            st.image(dup["image_path"], caption=f"Existing report #{dup['id']}")
        st.info("Open the Live map to see this pin. No duplicate ticket was created.")
        st.session_state["focus_report_id"] = dup["id"]
        _maybe_speak(
            f"This issue is already logged as report {dup['id']}, "
            f"{dup.get('hazard_type') or 'hazard'}. No duplicate ticket was created.",
            use_mock=use_mock,
            feature="reports",
        )
        st.page_link(page_map, label="Show on live map", icon="🗺️")
        return

    with st.spinner("Reviewing your photo…" if not use_mock else "Preparing a demo classification…"):
        try:
            ticket = analyze_hazard_routed(
                image_bytes,
                location,
                provider=provider,
                mime=mime,
                model=model,
                use_mock=use_mock,
                filename=uploaded.name,
            )
        except Exception:  # noqa: BLE001
            st.error(
                "We couldn’t review that photo right now. Please try again in a moment."
            )
            return

    if not ticket.is_recognized_hazard():
        st.warning("No civic hazard recognized — nothing was filed and no email was drafted.")
        st.write(ticket.summary)
        st.caption(f"Confidence {ticket.confidence:.0%} · type: {ticket.hazard_type}")
        _maybe_speak(
            f"No civic hazard recognized in this photo. {ticket.summary} "
            "Do you have another issue to log?",
            use_mock=use_mock,
            feature="reports",
        )
        return

    digest = image_sha256(image_bytes)
    source = "mock" if use_mock else provider
    try:
        report_id = save_ticket(
            ticket,
            location,
            latitude=lat,
            longitude=lon,
            source=source,
            image_hash=digest,
            status="open",
        )
        path = save_report_image(report_id, image_bytes, mime=mime)
        attach_image(report_id, path, digest)
    except Exception:  # noqa: BLE001
        st.error("Couldn’t save that report right now. Please try again in a moment.")
        return

    st.success(f"Filed as open report #{report_id} — pinned on the live map.")
    st.session_state["focus_report_id"] = report_id
    _maybe_speak(
        f"Hazard filed as report {report_id}. "
        f"{ticket.hazard_type}. Severity {ticket.severity.value}. "
        f"Routed to {ticket.agency}. {ticket.summary}",
        use_mock=use_mock,
        feature="reports",
    )
    render_ticket(ticket, location, report_id=report_id, include_email=True)


def render_map() -> None:
    _boot()
    settings_rail()
    st.markdown("## Live hazard map")
    st.caption(
        "Street-level map of open hazards — zoom like Google Maps, click a pin for details. "
        "Resolved pins disappear from the default view."
    )

    show_resolved = st.toggle("Include resolved (ghost pins)", value=False)
    rows = map_tickets(include_resolved=show_resolved)
    if not rows:
        st.info("No pinned reports yet. File one from Report (with a location pin).")
        return

    render_incident_map(rows, height=560)

    focus = st.session_state.get("focus_report_id")
    labels = [
        f"#{r['id']} · {r['hazard_type']} · {r['status']} · {r['location']}"
        for r in rows
    ]
    default_ix = 0
    if focus is not None:
        for i, r in enumerate(rows):
            if r["id"] == focus:
                default_ix = i
                break
    pick = st.selectbox("Inspect pin", options=labels, index=min(default_ix, len(labels) - 1))
    selected = rows[labels.index(pick)]
    detail = get_ticket(int(selected["id"])) or selected

    left, right = st.columns([1.1, 1])
    with left:
        st.markdown(f"### #{detail['id']} · {str(detail.get('hazard_type','')).title()}")
        st.write(
            f"**{detail.get('severity','').upper()}** · {detail.get('agency')} · "
            f"{detail.get('status')} · filed {detail.get('created_at')}"
        )
        st.write(detail.get("summary") or "")
        st.caption(detail.get("location"))
        maps_link = (
            f"https://www.google.com/maps?q={detail.get('latitude')},{detail.get('longitude')}"
            if detail.get("latitude") is not None
            else None
        )
        if maps_link:
            st.link_button("Open in Google Maps", maps_link, use_container_width=True)
        if detail.get("status") == "open":
            if st.button("Mark resolved (remove pin)", type="primary"):
                resolve_ticket(int(detail["id"]))
                st.success("Resolved — pin dropped from the open map.")
                st.rerun()
        else:
            st.caption(f"Resolved at {detail.get('resolved_at')}")
    with right:
        img = detail.get("image_path")
        if img and Path(img).exists():
            st.image(img, use_container_width=True)
        else:
            st.info("No photo on file for this pin.")


def render_safety() -> None:
    _boot()
    use_mock, _model = settings_rail()
    st.markdown("## Safety & accessibility alerts")
    st.caption(
        "Hackathon focus: turn UrbanPulse from “report a pothole” into early protection for "
        "basement residents, limited-mobility New Yorkers, and people on electric medical devices. "
        "Official guidance: NYC Emergency Management + 311."
    )

    st.markdown("### Scan for hazards near me")
    st.write(
        "Share location, optionally enable **voice services** in the sidebar, then run a scan. "
        "We’ll list open mapped hazards and flood flags nearby — and read them aloud only if voice is on."
    )
    location_consent_controls(key_prefix="safety")
    st.caption(
        f"Voice services: **{'on' if voice_services_enabled() else 'off'}** · "
        f"Near-me speech: **{'on' if voice_for_scan() else 'off'}**"
    )

    gps = st.session_state.get("gps")
    scan_cols = st.columns([1.4, 1])
    with scan_cols[0]:
        radius = st.slider("Scan radius (meters)", 100, 800, 300, 50, key="near_scan_radius")
    with scan_cols[1]:
        st.write("")
        st.write("")
        run_scan = st.button("Run near-me scan", type="primary", use_container_width=True)

    if run_scan:
        if not location_consent():
            st.warning("Turn on location sharing above first.")
        elif not gps:
            st.warning("No pin yet — share GPS on Report, pick an area below, or set a home pin.")
        else:
            profile = load_profile()
            result = scan_nearby_hazards(
                float(gps["latitude"]),
                float(gps["longitude"]),
                profile,
                radius_m=float(radius),
            )
            st.session_state["last_near_scan"] = result
            st.session_state.pop("_tts_spoken_ids", None)
            st.success(
                result["spoken"]
                if result["count"] or result["flood_lines"]
                else "Scan complete — all clear nearby."
            )
            for line in result["flood_lines"]:
                st.warning(line)
            if result["hazards"]:
                for h in result["hazards"]:
                    dist = h.get("distance_m")
                    dist_txt = f" · ~{int(dist)} m" if dist is not None else ""
                    st.markdown(
                        f"- **#{h['id']}** {h.get('hazard_type')} · {h.get('severity')}{dist_txt}  \n"
                        f"  {h.get('location')}"
                    )
            else:
                st.info("No open mapped hazard reports in this radius.")
            _maybe_speak(result["spoken"], use_mock=use_mock, feature="scan")
            if not voice_for_scan():
                st.caption(
                    "Enable **voice services** + **Speak near-me scans** in the sidebar to hear this."
                )

    elif st.session_state.get("last_near_scan"):
        prev = st.session_state["last_near_scan"]
        with st.expander("Last scan results", expanded=False):
            st.write(prev.get("spoken"))
            if st.button("Read last scan aloud"):
                st.session_state.pop("_tts_spoken_ids", None)
                _maybe_speak(prev.get("spoken") or "", use_mock=use_mock, feature="scan")

    st.divider()
    st.markdown("### Voice area alerts (when you move)")
    st.write(
        "With location sharing + near-me speech enabled, UrbanPulse can announce when your pin "
        "enters a flood-flagged zone or open hazard — for example: "
        "“You are in a hazard area flagged for flooding.”"
    )
    if st.button("Check area alerts at current pin", use_container_width=True):
        if not location_consent():
            st.warning("Turn on location sharing first.")
        elif not gps:
            st.warning("No pin yet.")
        else:
            st.session_state.pop("last_alert_fp", None)
            st.session_state.pop("_tts_spoken_ids", None)
            _run_geofence_alerts(
                float(gps["latitude"]), float(gps["longitude"]), use_mock=use_mock
            )
            if not voice_for_scan():
                st.info("Enable voice services → Speak near-me scans to hear alerts.")

    profile = load_profile()
    st.markdown("### Your safety profile")
    st.write(
        "Stored only on this device’s app data folder for the demo — not sold. "
        "Use it to personalize flood / power warnings."
    )
    c1, c2 = st.columns(2)
    with c1:
        basement = st.toggle("I live in a basement / low-lying unit", value=profile.lives_in_basement)
        mobility = st.toggle("I have limited mobility / need extra exit time", value=profile.limited_mobility)
        transit = st.toggle("I rely on Access-A-Ride or accessible transit", value=profile.needs_accessible_transit)
    with c2:
        medical = st.toggle(
            "I depend on electric medical equipment (e.g. nebulizer)",
            value=profile.depends_on_medical_power,
        )
        early = st.toggle("Send me early flood / storm heads-ups", value=profile.notify_early_flood)
        power = st.toggle("Warn me about flood-related power risk", value=profile.notify_power_risk)
        notes = st.text_input("Optional medical / access notes", value=profile.medical_notes)

    st.markdown("#### Home pin for alerts")
    boroughs = list(NYC_BOROUGHS.keys())
    bc, nc, sc = st.columns([1, 1.3, 1])
    with bc:
        b = st.selectbox("Borough", boroughs, key="safety_boro")
    with nc:
        n = st.selectbox("Neighborhood", list(NYC_BOROUGHS[b].keys()), key="safety_hood")
    with sc:
        st.write("")
        st.write("")
        use_home = st.button("Set as home area", use_container_width=True)

    gps = st.session_state.get("gps")
    home_lat = profile.home_latitude
    home_lon = profile.home_longitude
    home_label = profile.home_label
    if use_home:
        pin = NYC_BOROUGHS[b][n]
        home_lat, home_lon = pin["latitude"], pin["longitude"]
        home_label = f"{b} · {n}"
        st.session_state["gps"] = {
            "latitude": home_lat,
            "longitude": home_lon,
            "source": "area",
            "area": home_label,
        }
        st.session_state["gps_just_updated"] = True
    elif gps and home_lat is None:
        home_lat = float(gps["latitude"])
        home_lon = float(gps["longitude"])
        home_label = gps.get("area") or "last shared location"

    if st.button("Save profile", type="primary"):
        updated = SafetyProfile(
            lives_in_basement=basement,
            limited_mobility=mobility,
            needs_accessible_transit=transit,
            depends_on_medical_power=medical,
            medical_notes=notes,
            notify_early_flood=early,
            notify_power_risk=power,
            home_latitude=home_lat,
            home_longitude=home_lon,
            home_label=home_label or "",
        )
        save_profile(updated)
        profile = updated
        st.success("Profile saved.")

    st.divider()
    st.markdown("### 1 · Early flood / basement warnings")
    st.write(
        "People in basement apartments or with limited mobility are among those most at risk "
        "in flash floods. If heavy rain is building, it is safer to move early rather than wait "
        "for a last-minute official alert."
    )
    if home_lat is not None and home_lon is not None:
        st.caption(f"Checking risk near: **{home_label or f'{home_lat:.4f}, {home_lon:.4f}'}**")
        assessment = assess_flood_risk(home_lat, home_lon, profile)
        if assessment.priority_alert:
            st.error("Priority alert for your profile — review the messages below and plan early.")
        elif assessment.heavy_rain_likely or assessment.in_hotspot:
            st.warning("Elevated flood attention for this area.")
        else:
            st.info("No urgent flood signal from the demo sensors right now.")
        for msg in assessment.messages:
            st.markdown(f"- {msg}")
        if assessment.messages and (
            assessment.priority_alert or profile.notify_early_flood
        ):
            if st.button("Read flood assessment aloud"):
                st.session_state.pop("_tts_spoken_ids", None)
                _maybe_speak(" ".join(assessment.messages), use_mock=use_mock, feature="scan")
        st.markdown(
            f"Cross-check official tools: "
            f"[Know Your Zone]({FLOOD_LINKS['know_your_zone']}) · "
            f"[FloodNet NYC]({FLOOD_LINKS['floodnet']}) · "
            f"[OEM coastal storms]({FLOOD_LINKS['oem_hurricane']})"
        )
    else:
        st.info("Set a home neighborhood above (or share GPS on Report) to run a localized check.")

    st.divider()
    st.markdown("### 2 · Accessible evacuation & transit")
    st.write(assistance_blurb())
    st.markdown(
        f"- [Know Your Zone / evacuation centers]({EVAC_LINKS['know_your_zone']})  \n"
        f"- [Request help via NYC 311]({EVAC_LINKS['request_help_311']})  \n"
        f"- [OEM: Disabilities, Access & Functional Needs]({EVAC_LINKS['oem_afn']})  \n"
        f"- [MTA Access-A-Ride]({EVAC_LINKS['access_a_ride']})"
    )
    if home_lat is not None and home_lon is not None:
        st.markdown("#### Nearby demo evacuation pins")
        st.caption(
            "These are illustrative campus/area pins for the hackathon map — "
            "**always confirm open/accessible status with 311 or Know Your Zone during a real event.**"
        )
        for sug in nearest_centers(home_lat, home_lon, limit=3):
            c = sug.center
            miles = sug.distance_m / 1609.34
            st.markdown(
                f"**{c['name']}** ({c['borough']}) · {miles:.1f} mi  \n"
                f"{c['notes']}  \n"
                f"[Google Maps](https://www.google.com/maps?q={c['latitude']},{c['longitude']})"
            )

    st.divider()
    st.markdown("### 3 · Everyday accessibility: curb cuts & ramps")
    st.write(
        "Pedestrian ramps (curb cuts) are how wheelchair users, strollers, and many elders "
        "get on and off the street. Missing or broken ones are DOT-repair issues — and they "
        "belong in UrbanPulse, not only potholes."
    )
    st.markdown(
        "- On **Report**, upload a photo of a damaged / missing curb cut.  \n"
        "- UrbanPulse labels **defective pedestrian ramp / curb cut** and routes it to **DOT**.  \n"
        "- Tip: in demo mode, name a file like `curb_ramp.jpg` to try the category."
    )
    st.page_link(page_report, label="Report a curb cut or other hazard", icon="📷")

    st.divider()
    st.markdown("### 4 · Medical equipment power risk")
    st.write(
        "If you depend on electric medical equipment, flooding and storms raise outage risk. "
        "When your profile flags medical power needs and your area looks wet / flood-exposed, "
        "UrbanPulse elevates a power-prep warning above."
    )
    if profile.depends_on_medical_power:
        st.success(
            "Medical-power flag is ON — keep devices charged, pack backups, and identify a "
            "powered destination (hospital / accessible center) before travel gets hard."
        )


def _grokbot_file_from_image(
    image_bytes: bytes,
    *,
    mime: str,
    location: str,
    lat: float | None,
    lon: float | None,
    filename: str | None,
    use_mock: bool,
    model: str,
    provider: str,
    user_text: str,
) -> str:
    """Analyze photo; file only when a real hazard is recognized."""
    ticket = analyze_hazard_routed(
        image_bytes,
        location,
        provider=provider,  # type: ignore[arg-type]
        mime=mime,
        model=model,
        use_mock=use_mock,
        filename=filename,
    )
    if not ticket.is_recognized_hazard():
        return (
            f"I looked at your photo carefully. **No visible civic hazard** was recognized "
            f"(type: {ticket.hazard_type}, confidence {ticket.confidence:.0%}).\n\n"
            f"{ticket.summary}\n\n"
            "Nothing was filed and no agency email was drafted. "
            "**Do you have another issue to log?** You can attach a different photo or describe it."
        )

    digest = image_sha256(image_bytes)
    report_id = save_ticket(
        ticket,
        location,
        latitude=lat,
        longitude=lon,
        source="mock" if use_mock else provider,
        image_hash=digest,
        status="open",
    )
    path = save_report_image(report_id, image_bytes, mime=mime)
    attach_image(report_id, path, digest)
    st.session_state["focus_report_id"] = report_id
    note = f" (You said: {user_text[:120]})" if user_text.strip() else ""
    return (
        f"Filed **open report #{report_id}**{note}.\n\n"
        f"- **Hazard:** {ticket.hazard_type}\n"
        f"- **Severity:** {ticket.severity.value}\n"
        f"- **Agency:** {ticket.agency}\n"
        f"- **Where:** {location}\n\n"
        f"{ticket.summary}\n\n"
        "It’s pinned on the **Live map**. Want to log another issue?"
    )


def render_grokbot() -> None:
    _boot()
    use_mock, model = settings_rail()
    provider = get_provider()
    st.markdown("## Hazard Helper")
    st.caption(
        "Ask questions, attach a hazard photo to file an issue, or use **Speak** for voice input. "
        "Replies are spoken only if you enable voice services in the sidebar."
    )

    helper_hello = (
        "Hi — I'm **Hazard Helper**. Ask about reporting, the map, flood alerts, or "
        "attach a photo and say something like "
        "“Log this issue at Broadway & 125th in Manhattan.” "
        "If the photo isn’t a street hazard (sunset, selfie, etc.), I’ll say so "
        "and ask if you have another issue. Voice is **opt-in** in the sidebar."
    )

    if "grokbot_messages" not in st.session_state:
        st.session_state["grokbot_messages"] = [
            {"role": "assistant", "content": helper_hello}
        ]
    else:
        # Migrate older greetings that still say GrokBot
        msgs = st.session_state["grokbot_messages"]
        if msgs and "GrokBot" in (msgs[0].get("content") or ""):
            msgs[0]["content"] = helper_hello

    for msg in st.session_state["grokbot_messages"]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg.get("image_bytes"):
                st.image(msg["image_bytes"], width=280)

    st.markdown("#### Attach photo + location (optional — for filing)")
    bot_img = st.file_uploader(
        "Hazard photo",
        type=["jpg", "jpeg", "png", "webp"],
        key="grokbot_image",
    )
    gps = st.session_state.get("gps") or {}
    default_loc = st.session_state.get("location_manual") or gps.get("area") or ""
    bot_location = st.text_input(
        "Location for this photo (street / neighborhood)",
        value=default_loc,
        key="grokbot_location",
        placeholder="e.g. Broadway & W 125th St, Manhattan",
    )

    st.markdown("#### Speak to Hazard Helper")
    st.caption(
        "Tap **Speak**, allow the mic, then paste/copy the transcript into the box "
        "(or type). On phones you can also use the keyboard mic in chat."
    )
    browser_mic_panel(key="grokbot")
    voice_box = st.text_input(
        "Voice / typed instruction (sent with chat)",
        key="voice_transcript_box",
        placeholder="Paste spoken text here, or type: Log the pothole at …",
    )

    audio_clip = None
    if hasattr(st, "audio_input"):
        audio_clip = st.audio_input("Or record a short voice note")

    suggestions = [
        "How do I report a broken curb cut?",
        "Scan: what hazards are near me?",
        "I live in a basement — what before heavy rain?",
        "Where do I request accessible evacuation help?",
    ]
    tips = st.columns(4)
    for col, tip in zip(tips, suggestions):
        with col:
            if st.button(tip, use_container_width=True, key=f"tip_{abs(hash(tip)) % 10_000}"):
                st.session_state["grokbot_tip"] = tip
                st.rerun()

    st.caption(
        f"Voice services: **{'on' if voice_services_enabled() else 'off'}** · "
        f"Speak replies: **{'on' if voice_for_chat() else 'off'}**"
    )

    prompt = st.session_state.pop("grokbot_tip", None) or st.chat_input("Ask Hazard Helper…")
    if voice_box and st.button("Send voice / typed instruction", type="primary"):
        prompt = voice_box

    if audio_clip is not None and st.button("Transcribe recording & send"):
        raw = audio_clip.getvalue()
        mime = getattr(audio_clip, "type", None) or "audio/wav"
        with st.spinner("Transcribing…"):
            transcript = transcribe_audio_bytes(
                raw, mime=mime, provider=provider, use_mock=use_mock
            )
        if transcript:
            prompt = transcript
            st.session_state["voice_transcript_box"] = transcript
        else:
            st.warning(
                "Could not transcribe that recording. Try **Speak** and paste the text, or type your message."
            )

    if prompt:
        user_display = prompt
        image_bytes = bot_img.getvalue() if bot_img else None
        mime = (bot_img.type if bot_img else None) or "image/jpeg"
        lat = float(gps["latitude"]) if gps.get("latitude") is not None else None
        lon = float(gps["longitude"]) if gps.get("longitude") is not None else None

        st.session_state["grokbot_messages"].append(
            {
                "role": "user",
                "content": user_display
                + (f"\n\n*(photo attached · location: {bot_location or 'not set'})*" if image_bytes else ""),
                "image_bytes": image_bytes,
            }
        )
        with st.chat_message("user"):
            st.markdown(user_display)
            if image_bytes:
                st.image(image_bytes, width=280)

        with st.chat_message("assistant"):
            with st.spinner("Hazard Helper is thinking…"):
                try:
                    if image_bytes:
                        loc = (bot_location or "").strip() or "NYC (location not specified)"
                        reply = _grokbot_file_from_image(
                            image_bytes,
                            mime=mime,
                            location=loc,
                            lat=lat,
                            lon=lon,
                            filename=bot_img.name if bot_img else None,
                            use_mock=use_mock,
                            model=model,
                            provider=provider,
                            user_text=prompt,
                        )
                    elif "near me" in prompt.lower() or "nearby" in prompt.lower() or "scan" in prompt.lower():
                        if not gps.get("latitude"):
                            reply = (
                                "I can scan nearby hazards once you share a location pin "
                                "(Report or Safety → location sharing / home area). "
                                "Or open **Near-me & safety** and tap **Run near-me scan**."
                            )
                        else:
                            result = scan_nearby_hazards(
                                float(gps["latitude"]),
                                float(gps["longitude"]),
                                load_profile(),
                                radius_m=300.0,
                            )
                            reply = result["spoken"]
                    else:
                        history = [
                            {"role": m["role"], "content": m["content"]}
                            for m in st.session_state["grokbot_messages"]
                            if m["role"] in ("user", "assistant")
                        ]
                        reply = chat_routed(
                            history,
                            provider=provider,
                            use_mock=use_mock,
                            model=model,
                        )
                except Exception:  # noqa: BLE001
                    reply = (
                        "Sorry — I couldn’t finish that just now. "
                        "Please try again in a moment, or use **Report** to file a photo directly."
                    )
                st.markdown(reply)
                st.session_state.pop("_tts_spoken_ids", None)
                _maybe_speak(reply, use_mock=use_mock, feature="chat")
                if voice_services_enabled() and not voice_for_chat():
                    st.caption("Enable **Speak Hazard Helper replies** under voice services to hear answers.")
                elif not voice_services_enabled():
                    if st.button("Read this reply aloud once"):
                        st.session_state["a11y_voice_master"] = True
                        st.session_state["a11y_voice_chat"] = True
                        st.session_state.pop("_tts_spoken_ids", None)
                        speak_and_play(reply, provider=provider, use_mock=use_mock)
        st.session_state["grokbot_messages"].append({"role": "assistant", "content": reply})

    if st.button("Clear chat"):
        st.session_state["grokbot_messages"] = [
            {
                "role": "assistant",
                "content": "Chat cleared. Attach a photo or ask me anything about UrbanPulse.",
            }
        ]
        st.rerun()


def render_ops() -> None:
    _boot()
    settings_rail()
    st.markdown("## Ops dashboard")
    open_rows = recent_tickets(limit=40, status="open")
    st.dataframe(pd.DataFrame(open_rows), use_container_width=True, hide_index=True)
    buckets = severity_by_hour(48)
    if buckets:
        bdf = pd.DataFrame(buckets)
        st.bar_chart(
            bdf.pivot_table(index="bucket", columns="severity", values="count", fill_value=0)
        )


page_home = st.Page(render_home, title="Home", icon="🏠", default=True)
page_report = st.Page(render_report, title="Report", icon="📷")
page_map = st.Page(render_map, title="Live map", icon="🗺️")
page_safety = st.Page(render_safety, title="Near-me & safety", icon="♿")
page_bot = st.Page(render_grokbot, title="Hazard Helper", icon="🛟")
page_ops = st.Page(render_ops, title="Ops", icon="📊")


def main() -> None:
    nav = st.navigation(
        [page_home, page_report, page_map, page_safety, page_bot, page_ops]
    )
    nav.run()


if __name__ == "__main__":
    main()
