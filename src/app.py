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
    alert_voice_enabled,
    get_provider,
    location_consent,
    voice_enabled,
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
from geo_alerts import alert_fingerprint, build_area_alerts  # noqa: E402
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
    has_grok = bool(
        os.getenv("XAI_API_KEY") and not os.getenv("XAI_API_KEY", "").startswith("your_")
    )
    has_gemini = bool(
        (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()
        and not (os.getenv("GEMINI_API_KEY") or "").startswith("your_")
    )
    with st.sidebar:
        st.markdown("### UrbanPulse")
        st.caption("Hack the City · DivHacks")

        st.markdown("#### AI engine")
        provider = get_provider()
        st.caption(
            f"Active: **{provider.upper()}** · set in `.env` via `ACTIVE_AI` "
            f"(comment out the line you don’t want) · "
            f"Grok key {'✓' if has_grok else '✗'} · Gemini key {'✓' if has_gemini else '✗'}"
        )

        use_mock = st.toggle(
            "Mock AI (no cloud vision/chat)",
            value=not (has_grok or has_gemini),
            help="Offline demo replies. Turn off when API keys are set.",
        )
        model = st.text_input(
            "Grok chat/vision model",
            value=os.getenv("GROK_MODEL", "grok-4.7"),
            disabled=use_mock or provider != "grok",
        )

        st.markdown("#### Accessibility")
        st.toggle(
            "Voice guidance (TTS)",
            value=st.session_state.get("a11y_voice", True),
            key="a11y_voice",
            help="Speak GrokBot answers and key confirmations aloud.",
        )
        st.toggle(
            "Spoken hazard-area alerts",
            value=st.session_state.get("a11y_alert_voice", True),
            key="a11y_alert_voice",
            help="When location is shared, announce flood/open-hazard zones you enter.",
        )
        st.toggle(
            "Browser voice backup",
            value=st.session_state.get("a11y_browser_backup", True),
            key="a11y_browser_backup",
            help="Also use the phone’s built-in speech if cloud TTS is blocked.",
        )

        status = db_status()
        if status.get("ok"):
            st.caption(
                f"{status.get('backend')} · {status.get('open_count', 0)} open / "
                f"{status.get('report_count', 0)} total"
            )
        st.divider()
    return use_mock, model


def _maybe_speak(text: str, *, use_mock: bool, force_alert: bool = False) -> None:
    if force_alert:
        if not alert_voice_enabled():
            return
    elif not voice_enabled():
        return
    speak_and_play(text, provider=get_provider(), use_mock=use_mock)


def _run_geofence_alerts(lat: float, lon: float, *, use_mock: bool) -> None:
    """Speak when the user enters a flood / open-hazard zone (consent required)."""
    if not location_consent() or not alert_voice_enabled():
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
    _maybe_speak(spoken, use_mock=use_mock, force_alert=True)


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
        "We pull GPS once and resolve the address quickly "
        + ("(Google)" if google_maps_api_key() else "(add GOOGLE_MAPS_API_KEY for Google addresses)")
        + "."
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
        # Spoken geofence when user opted into location + hazard voice alerts
        if consented:
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


def render_ticket(ticket: DispatchTicket, location: str, report_id: int | None = None) -> None:
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
        if st.button("Mock send (log only)", type="primary", use_container_width=True, key=f"mock_{report_id}"):
            try:
                result = mock_send(draft)
                if report_id is not None:
                    mark_email_sent(
                        report_id,
                        to_address=result["to"],
                        method=result["method"],
                    )
                st.success(f"Logged → {result['log_file']}")
            except Exception as exc:  # noqa: BLE001
                st.error(str(exc))


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
        st.page_link(page_safety, label="Safety & alerts", icon="♿")
    with d:
        st.page_link(page_bot, label="Ask GrokBot", icon="🤖")

    st.markdown("### How it works")
    x, y, z = st.columns(3)
    x.markdown(
        "**1 · Capture**\n\nPhoto + optional GPS (you choose location sharing) or any NYC neighborhood."
    )
    y.markdown(
        "**2 · Classify + speak**\n\nGrok or Gemini scans the photo; TTS reads results aloud."
    )
    z.markdown(
        "**3 · Protect + chat**\n\nSpoken flood/hazard alerts when you enter a flagged area, plus GrokBot."
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
        "pedestrian ramps** — any street or accessibility issue counts. "
        f"Vision engine: **{provider.upper()}** (switch `ACTIVE_AI` in `.env`)."
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
        _maybe_speak("Please add a hazard photo first.", use_mock=use_mock)
        return
    if not location:
        st.error("Add a location.")
        _maybe_speak("Please add a location for the hazard report.", use_mock=use_mock)
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
        )
        st.page_link(page_map, label="Show on live map", icon="🗺️")
        return

    engine = provider.upper() if not use_mock else "Mock"
    with st.spinner(f"{engine} is classifying…" if not use_mock else "Mock classifier…"):
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
        except Exception as exc:  # noqa: BLE001
            st.error(f"Analysis failed: {exc}")
            _maybe_speak(f"Analysis failed. {exc}", use_mock=use_mock)
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
    except Exception as exc:  # noqa: BLE001
        st.error(f"Save failed: {exc}")
        return

    st.success(f"Filed as open report #{report_id} — pinned on the live map.")
    st.session_state["focus_report_id"] = report_id
    _maybe_speak(
        f"Hazard filed as report {report_id}. "
        f"{ticket.hazard_type}. Severity {ticket.severity.value}. "
        f"Routed to {ticket.agency}. {ticket.summary}",
        use_mock=use_mock,
    )
    render_ticket(ticket, location, report_id=report_id)


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

    st.markdown("### Voice hazard-area alerts")
    st.write(
        "If you opt into location sharing and enable **Spoken hazard-area alerts** in the sidebar, "
        "UrbanPulse can announce when you enter a flood-flagged zone or an open mapped hazard — "
        "for example: “You are in a hazard area flagged for flooding.”"
    )
    location_consent_controls(key_prefix="safety")
    st.caption(
        f"Spoken alerts: **{'on' if alert_voice_enabled() else 'off'}** · "
        f"TTS engine: **{get_provider().upper()}** (`.env` ACTIVE_AI)"
    )

    st.markdown("#### Check alerts at my location now")
    gps = st.session_state.get("gps")
    if st.button("Check hazard alerts here", type="primary", use_container_width=True):
        if not location_consent():
            st.warning("Turn on location sharing above first.")
        elif not gps:
            st.warning("No pin yet — share GPS on Report or set a home area below, then check again.")
        else:
            st.session_state.pop("last_alert_fp", None)
            _run_geofence_alerts(
                float(gps["latitude"]), float(gps["longitude"]), use_mock=use_mock
            )
            if not alert_voice_enabled():
                st.info("Enable **Spoken hazard-area alerts** in the sidebar to hear the announcement.")

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
        _maybe_speak(
            "Safety profile saved. Flood and power alerts will use your preferences.",
            use_mock=use_mock,
        )

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
                _maybe_speak(" ".join(assessment.messages), use_mock=use_mock, force_alert=True)
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
        "- Active AI (Grok or Gemini) labels **defective pedestrian ramp / curb cut** → **DOT**.  \n"
        "- Mock tip: name a file like `curb_ramp.jpg` to demo without an API key."
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


def render_grokbot() -> None:
    _boot()
    use_mock, model = settings_rail()
    provider = get_provider()
    st.markdown("## GrokBot")
    st.caption(
        f"Your smart AI guide for UrbanPulse — ask how to report hazards, read the map, "
        f"use Safety alerts, or troubleshoot errors. Active engine: **{provider.upper()}** "
        f"(`.env` ACTIVE_AI). Replies can be read aloud when Voice guidance is on."
    )

    if "grokbot_messages" not in st.session_state:
        st.session_state["grokbot_messages"] = [
            {
                "role": "assistant",
                "content": (
                    "Hi — I'm **GrokBot**. Ask me about reporting (including curb cuts), "
                    "the live map, flood/basement alerts, Access-A-Ride / 311 evacuation help, "
                    "voice alerts, or fixing app issues. I can also speak my answers aloud."
                ),
            }
        ]

    for msg in st.session_state["grokbot_messages"]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    suggestions = [
        "How do I report a broken curb cut?",
        "I live in a basement — what should I do before heavy rain?",
        "Why isn't my location loading?",
        "Where do I request accessible evacuation help?",
    ]
    tips = st.columns(4)
    for col, tip in zip(tips, suggestions):
        with col:
            if st.button(tip, use_container_width=True, key=f"tip_{abs(hash(tip)) % 10_000}"):
                st.session_state["grokbot_tip"] = tip
                st.rerun()

    speak_replies = voice_enabled()
    st.caption(
        f"Voice guidance: **{'on' if speak_replies else 'off'}** — toggle in the sidebar under Accessibility."
    )

    prompt = st.session_state.pop("grokbot_tip", None) or st.chat_input("Ask GrokBot…")

    if prompt:
        st.session_state["grokbot_messages"].append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            label = provider.upper() if not use_mock else "Mock"
            with st.spinner(f"{label} GrokBot is thinking…" if not use_mock else "Mock GrokBot…"):
                try:
                    reply = chat_routed(
                        [
                            m
                            for m in st.session_state["grokbot_messages"]
                            if m["role"] in ("user", "assistant")
                        ],
                        provider=provider,
                        use_mock=use_mock,
                        model=model,
                    )
                except Exception as exc:  # noqa: BLE001
                    reply = (
                        f"I hit an error talking to {provider}: `{exc}`\n\n"
                        "Check `XAI_API_KEY` / `GEMINI_API_KEY` in `.env`, "
                        "or turn **Mock AI** on in the sidebar."
                    )
                st.markdown(reply)
                _maybe_speak(reply, use_mock=use_mock)
        st.session_state["grokbot_messages"].append({"role": "assistant", "content": reply})

    if st.button("Clear chat"):
        st.session_state["grokbot_messages"] = [
            {
                "role": "assistant",
                "content": "Chat cleared. What do you want to know about UrbanPulse?",
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
page_safety = st.Page(render_safety, title="Safety & alerts", icon="♿")
page_bot = st.Page(render_grokbot, title="GrokBot", icon="🤖")
page_ops = st.Page(render_ops, title="Ops", icon="📊")


def main() -> None:
    nav = st.navigation(
        [page_home, page_report, page_map, page_safety, page_bot, page_ops]
    )
    nav.run()


if __name__ == "__main__":
    main()
