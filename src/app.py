"""
UrbanPulse NYC — civic hazard reporting (DivHacks Hack the City).

Flow: photo + location → Grok vision → Tiger Data insert → planner dashboard.
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

from db import (  # noqa: E402
    db_status,
    init_db,
    mark_email_sent,
    recent_tickets,
    save_ticket,
    severity_by_hour,
)
from grok_client import analyze_hazard  # noqa: E402
from models import DispatchTicket, Severity  # noqa: E402
from nearby_places import build_location_choices, strip_choice_meta  # noqa: E402
from nyc_areas import NYC_BOROUGHS  # noqa: E402
from notify import (  # noqa: E402
    build_draft,
    intended_agency_email,
    mailto_url,
    mock_send,
    placeholder_inbox,
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
)

SEVERITY_COLORS = {
    Severity.LOW: "#2ecc71",
    Severity.MEDIUM: "#f1c40f",
    Severity.HIGH: "#e67e22",
    Severity.CRITICAL: "#e74c3c",
}


def render_ticket(ticket: DispatchTicket, location: str, report_id: int | None = None) -> None:
    color = SEVERITY_COLORS[ticket.severity]
    saved = f" · saved as #{report_id}" if report_id is not None else ""
    st.markdown(
        f"""
        <div style="border-left: 6px solid {color}; padding: 0.75rem 1rem; background: #0f172a0d; border-radius: 4px;">
          <h3 style="margin:0;">Dispatch ticket · {ticket.hazard_type.title()}{saved}</h3>
          <p style="margin:0.35rem 0 0; opacity:0.85;">{location}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Severity", ticket.severity.value.upper())
    c2.metric("Agency", ticket.agency)
    c3.metric("Priority", ticket.recommended_priority)
    c4.metric("Confidence", f"{ticket.confidence:.0%}")

    st.subheader("Dispatcher summary")
    st.write(ticket.summary)

    st.subheader("Notify governing body")
    st.caption(
        f"Routed toward **{ticket.agency}** "
        f"(intended contact: `{intended_agency_email(ticket.agency)}`). "
        f"Safe default inbox: `{placeholder_inbox()}` — nothing goes to a real city mailbox unless you change that later."
    )

    use_placeholder = st.radio(
        "Email destination",
        options=[
            "Placeholder inbox (safe / demo)",
            "Intended agency address (for mailto preview only)",
        ],
        index=0,
        horizontal=True,
    )
    draft = build_draft(
        ticket,
        location,
        report_id=report_id,
        use_placeholder=use_placeholder.startswith("Placeholder"),
    )

    st.text_input("To", value=draft.to_address, disabled=True)
    st.text_input("Subject", value=draft.subject, disabled=True)
    st.text_area("Body", value=draft.body, height=200, disabled=True)

    mail_col, mock_col = st.columns(2)
    with mail_col:
        st.link_button(
            "Open in email app (mailto)",
            mailto_url(draft),
            use_container_width=True,
            help="Opens Outlook/Gmail/etc with this draft. You still choose Send.",
        )
    with mock_col:
        if st.button(
            "Mock send (log only)",
            use_container_width=True,
            type="primary",
            help="Writes the email to data/outbound_mail and records status in the DB. Never emails a real agency.",
        ):
            try:
                result = mock_send(draft)
                if report_id is not None:
                    mark_email_sent(
                        report_id,
                        to_address=result["to"],
                        method=result["method"],
                        status="sent_mock",
                    )
                st.success(
                    f"Mock send logged → `{result['log_file']}` "
                    f"(to {result['to']}, method={result['method']})"
                )
            except Exception as exc:  # noqa: BLE001
                st.error(f"Mock send failed: {exc}")

    with st.expander("Raw JSON stored in Tiger Data / SQLite"):
        st.json(ticket.model_dump())


def _load_nearby(lat: float, lon: float) -> None:
    cache_key = (round(lat, 4), round(lon, 4))
    if st.session_state.get("nearby_cache_key") == cache_key:
        return
    with st.spinner("Finding streets & neighborhoods near you…"):
        choices, warning = build_location_choices(lat, lon, radius_miles=1.0)
        st.session_state["nearby_choices"] = choices
        st.session_state["nearby_cache_key"] = cache_key
        if warning:
            st.session_state["nearby_warning"] = warning
        else:
            st.session_state.pop("nearby_warning", None)
        st.session_state.pop("nearby_error", None)


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


def location_picker() -> tuple[str, float | None, float | None]:
    st.subheader("Where is the hazard?")
    st.caption(
        "Visitors welcome — share your phone location, or pick any NYC borough & neighborhood. "
        "We'll suggest places within about 1 mile."
    )

    # --- 1) Device GPS (phones) ---
    st.markdown("#### 1. Use my phone / device location")
    st.write(
        "Tap the location button and **Allow** when your browser asks. "
        "UrbanPulse only uses this to list nearby streets — it is not sold or shared."
    )
    if streamlit_geolocation is not None:
        try:
            geo = streamlit_geolocation()
        except Exception as exc:  # noqa: BLE001
            geo = None
            st.warning(f"Location button unavailable ({exc}). Use borough picker below.")
        browser_coords = _coords_from_browser(geo)
        if browser_coords:
            st.session_state["gps"] = {
                "latitude": browser_coords[0],
                "longitude": browser_coords[1],
                "source": "device",
                "area": "device location",
            }
    else:
        st.info("Install `streamlit-geolocation` for one-tap GPS, or pick a neighborhood below.")

    # --- 2) Borough → neighborhood (all NYC) ---
    st.markdown("#### 2. Or pick your NYC area")
    boroughs = list(NYC_BOROUGHS.keys())
    bcol, ncol, lcol = st.columns([1, 1.4, 1])
    with bcol:
        borough = st.selectbox("Borough", options=boroughs, index=0)
    with ncol:
        hoods = list(NYC_BOROUGHS[borough].keys())
        neighborhood = st.selectbox("Neighborhood", options=hoods)
    with lcol:
        st.write("")
        st.write("")
        load_area = st.button("Load nearby places", type="secondary", use_container_width=True)

    if load_area:
        pin = NYC_BOROUGHS[borough][neighborhood]
        st.session_state["gps"] = {
            "latitude": pin["latitude"],
            "longitude": pin["longitude"],
            "source": "area",
            "area": f"{borough} · {neighborhood}",
        }

    # --- 3) Manual coordinates (advanced) ---
    with st.expander("Advanced: type exact GPS coordinates"):
        c1, c2, c3 = st.columns([1, 1, 1])
        with c1:
            lat = st.number_input("Latitude", value=40.7580, format="%.5f", key="manual_lat")
        with c2:
            lon = st.number_input("Longitude", value=-73.9855, format="%.5f", key="manual_lon")
        with c3:
            st.write("")
            st.write("")
            if st.button("Use typed coordinates", use_container_width=True):
                st.session_state["gps"] = {
                    "latitude": float(lat),
                    "longitude": float(lon),
                    "source": "manual_gps",
                    "area": "typed coordinates",
                }

    gps = st.session_state.get("gps")
    lat_out = lon_out = None
    if gps:
        lat_out = float(gps["latitude"])
        lon_out = float(gps["longitude"])
        source = gps.get("source", "pin")
        where = gps.get("area") or "your pin"
        label = {
            "device": "your device",
            "area": where,
            "manual_gps": "typed coordinates",
        }.get(source, where)
        st.success(f"Located via {label}: {lat_out:.5f}, {lon_out:.5f}")
        _load_nearby(lat_out, lon_out)

        if warn := st.session_state.get("nearby_warning"):
            st.info(warn)

        choices = st.session_state.get("nearby_choices") or []
        if choices:
            picked = st.selectbox(
                "Places near you (≈1 mile)",
                options=choices,
                help="Streets when the map service is up; otherwise nearby NYC neighborhoods.",
            )
            clean = strip_choice_meta(picked)
            if st.session_state.get("last_nearby_pick") != picked:
                st.session_state["location_manual"] = clean
                st.session_state["last_nearby_pick"] = picked
        else:
            st.info("No nearby names yet — type an intersection below.")
    else:
        st.info("Share device location or pick a borough/neighborhood to continue.")

    if "location_manual" not in st.session_state:
        st.session_state["location_manual"] = ""

    manual = st.text_input(
        "Intersection / landmark for the ticket",
        placeholder="e.g. Broadway & W 125th St, Manhattan",
        key="location_manual",
    )
    return manual.strip(), lat_out, lon_out


def render_settings_bar() -> tuple[bool, str]:
    """Mock / model controls on the main page (easier to find than a collapsed sidebar)."""
    has_key = bool(os.getenv("XAI_API_KEY") and os.getenv("XAI_API_KEY") != "your_xai_api_key_here")
    st.subheader("Settings")
    c1, c2, c3 = st.columns([1.2, 1.2, 1.6])
    with c1:
        use_mock = st.toggle(
            "Mock mode (skip live Grok)",
            value=not has_key,
            help="Turn OFF once XAI_API_KEY is in .env to call Grok for real.",
        )
    with c2:
        model = st.text_input(
            "Grok model",
            value=os.getenv("GROK_MODEL", "grok-4.6"),
            disabled=use_mock,
        )
    with c3:
        status = db_status()
        if status.get("ok"):
            st.caption(
                f"DB: {status.get('backend')} · {status.get('report_count', 0)} reports"
            )
        else:
            st.caption(f"DB error: {status.get('error')}")
        if not has_key:
            st.caption("No XAI_API_KEY in .env yet — keep Mock on, or add your key.")
        elif use_mock:
            st.caption("Key found — turn Mock OFF to use live Grok.")
        else:
            st.caption("Live Grok enabled.")

    with st.sidebar:
        st.header("Database")
        status = db_status()
        if status.get("ok"):
            st.success(
                f"{status.get('backend', '?')} · {status.get('report_count', 0)} reports"
            )
            st.caption(status.get("database", ""))
            if status.get("hypertable"):
                st.caption("Timescale hypertable: on")
        else:
            st.error(f"DB error: {status.get('error')}")

        if st.button("Initialize / repair database"):
            try:
                info = init_db()
                st.session_state.pop("_db_bootstrapped", None)
                st.success(f"Ready ({info.get('backend')})")
            except Exception as exc:  # noqa: BLE001
                st.error(str(exc))

        st.markdown(
            "Set `XAI_API_KEY` and optional Tiger Data `DATABASE_URL` in `.env`."
        )
    return use_mock, model


def page_report(use_mock: bool, model: str) -> None:
    st.header("File a hazard report")
    uploaded = st.file_uploader(
        "Hazard photo",
        type=["jpg", "jpeg", "png", "webp"],
    )
    location, lat, lon = location_picker()
    analyze = st.button("Generate dispatch ticket", type="primary", use_container_width=True)

    if uploaded:
        st.image(Image.open(uploaded), caption="Uploaded hazard photo", use_container_width=True)

    if not analyze:
        return
    if not uploaded:
        st.error("Upload a photo first.")
        return
    if not location:
        st.error("Pick a nearby street or type a location.")
        return

    mime = uploaded.type or "image/jpeg"
    image_bytes = uploaded.getvalue()
    label = "Calling Grok…" if not use_mock else "Running mock analyzer…"

    with st.spinner(label):
        try:
            ticket = analyze_hazard(
                image_bytes,
                location,
                mime=mime,
                model=model,
                use_mock=use_mock,
                filename=uploaded.name,
            )
        except Exception as exc:  # noqa: BLE001
            st.error(f"Analysis failed: {exc}")
            return

    report_id = None
    try:
        report_id = save_ticket(
            ticket,
            location,
            latitude=lat,
            longitude=lon,
            source="mock" if use_mock else "grok",
        )
        st.success(f"Ticket saved to database as report #{report_id}.")
    except Exception as exc:  # noqa: BLE001
        st.warning(f"Ticket generated but DB save failed: {exc}")

    render_ticket(ticket, location, report_id=report_id)


def page_planner() -> None:
    st.header("Planner dashboard")
    st.caption("Live view of ingested reports (Tiger Data `time_bucket` when available).")

    col_a, col_b = st.columns(2)
    with col_a:
        limit = st.slider("Recent reports", 5, 100, 25)
    with col_b:
        hours = st.slider("Severity chart window (hours)", 6, 168, 48)

    try:
        rows = recent_tickets(limit=limit)
        buckets = severity_by_hour(hours=hours)
    except Exception as exc:  # noqa: BLE001
        st.error(f"Could not query database: {exc}")
        return

    if not rows:
        st.info("No reports yet — file one on the Report tab.")
        return

    df = pd.DataFrame(rows)
    st.subheader("Recent incidents")
    st.dataframe(
        df[
            [
                "id",
                "created_at",
                "location",
                "hazard_type",
                "severity",
                "agency",
                "priority",
                "source",
                "email_status",
                "email_to",
            ]
        ],
        use_container_width=True,
        hide_index=True,
    )

    if buckets:
        bdf = pd.DataFrame(buckets)
        st.subheader("Severity over time")
        pivot = (
            bdf.pivot_table(index="bucket", columns="severity", values="count", fill_value=0)
            if not bdf.empty
            else bdf
        )
        st.bar_chart(pivot)

    map_df = df.dropna(subset=["latitude", "longitude"])
    if not map_df.empty:
        st.subheader("Incident map")
        st.map(map_df.rename(columns={"latitude": "lat", "longitude": "lon"})[["lat", "lon"]])


def main() -> None:
    st.title("UrbanPulse NYC")
    st.caption(
        "Photo → Grok classification → municipal ticket → Tiger Data (or local SQLite)."
    )

    try:
        if "_db_bootstrapped" not in st.session_state:
            init_db()
            st.session_state["_db_bootstrapped"] = True
    except Exception as exc:  # noqa: BLE001
        st.sidebar.error(f"DB init failed: {exc}")

    use_mock, model = render_settings_bar()
    st.divider()
    tab_report, tab_planner = st.tabs(["Report", "Planner dashboard"])
    with tab_report:
        page_report(use_mock, model)
    with tab_planner:
        page_planner()


if __name__ == "__main__":
    main()
