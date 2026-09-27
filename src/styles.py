"""
UrbanPulse visual system — look & feel only.

Call `load_css()` once per page (via `apply_theme()` / `_boot()`).
No page logic, data, or navigation changes live here.
"""

from __future__ import annotations

import streamlit as st

# Shared with maps / status charts — mostly neutrals; accent reserved for identity
ACCENT = "#4F46E5"
STATUS_GREEN = "#10B981"
STATUS_AMBER = "#D97706"
STATUS_CORAL = "#DC2626"
STATUS_MUTED = "#94A3B8"

CSS = """
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@500;600;700;800&family=Plus+Jakarta+Sans:ital,wght@0,400;0,500;0,600;0,700;1,400;1,500&family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@24,400,0,0&display=swap');

:root {
  /* ~75% neutral · ~18% primary · ~7% accent */
  --up-bg: #F8FAFC;
  --up-surface: #FFFFFF;
  --up-ink: #0F172A;
  --up-muted: #475569;
  --up-faint: #64748B;
  --up-line: rgba(15, 23, 42, 0.08);
  --up-accent: #4F46E5;
  --up-accent-soft: #EEF2FF;
  --up-accent-2: #7C3AED;
  --up-green: #10B981;
  --up-amber: #D97706;
  --up-coral: #DC2626;
  --up-radius: 16px;
  --up-radius-sm: 12px;
  --up-shadow: 0 1px 2px rgba(15, 23, 42, 0.04), 0 6px 18px rgba(15, 23, 42, 0.05);
  --up-font: "Plus Jakarta Sans", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  --up-font-display: "Outfit", "Plus Jakarta Sans", sans-serif;
}

html, body, [class*="css"], .stApp, [data-testid="stAppViewContainer"] {
  font-family: var(--up-font) !important;
  color: var(--up-ink);
}

.stApp {
  /* Quiet off-white — light navy wash only, no rainbow floods */
  background:
    radial-gradient(1000px 420px at 8% -8%, rgba(79, 70, 229, 0.06), transparent 55%),
    radial-gradient(800px 360px at 100% 0%, rgba(124, 58, 237, 0.04), transparent 50%),
    var(--up-bg) !important;
}

/* —— Hide unpolished Streamlit chrome (keep sidebar reopen) —— */
#MainMenu { visibility: hidden; }
footer { visibility: hidden; }
[data-testid="stDecoration"] { display: none !important; }
div[data-testid="stStatusWidget"] { display: none !important; }
.stDeployButton, [data-testid="stAppDeployButton"] { display: none !important; }

/* Top brand + nav bar — roomy so tabs don't clip page brand */
header[data-testid="stHeader"] {
  background: rgba(248, 250, 252, 0.92) !important;
  backdrop-filter: blur(10px);
  height: auto !important;
  min-height: 3.75rem !important;
  visibility: visible !important;
  opacity: 1 !important;
  z-index: 999990 !important;
  border-bottom: 1px solid var(--up-line) !important;
  padding-left: 0.35rem !important;
  padding-right: 0.75rem !important;
}
[data-testid="stToolbar"] {
  visibility: visible !important;
  height: auto !important;
  min-height: 3.25rem !important;
  display: flex !important;
  opacity: 1 !important;
  pointer-events: auto !important;
  align-items: center !important;
  gap: 0.35rem !important;
  padding-left: 0.25rem !important;
}

/* Give top nav links breathing room (Home shouldn't sit under the sidebar arrow) */
[data-testid="stHeader"] nav,
header[data-testid="stHeader"] [data-testid="stToolbar"] > div {
  margin-left: 0.15rem !important;
}
[data-testid="stHeader"] a,
[data-testid="stHeader"] [data-testid="stPageLink-NavLink"],
header[data-testid="stHeader"] button[kind="headerNoPadding"] {
  margin-left: 0.1rem !important;
}

/* Fix Material icon names showing as raw text (e.g. keyboard_double_arrow_left) */
span[data-testid="stIconMaterial"],
.material-symbols-outlined,
[data-testid="stHeader"] span[data-testid="stIconMaterial"],
[data-testid="stToolbar"] span[data-testid="stIconMaterial"],
[data-testid="collapsedControl"] span,
[data-testid="stSidebarCollapsedControl"] span {
  font-family: "Material Symbols Outlined" !important;
  font-weight: normal !important;
  font-style: normal !important;
  font-size: 1.35rem !important;
  line-height: 1 !important;
  letter-spacing: normal !important;
  text-transform: none !important;
  display: inline-block !important;
  white-space: nowrap !important;
  word-wrap: normal !important;
  direction: ltr !important;
  -webkit-font-smoothing: antialiased !important;
  font-variation-settings: "FILL" 0, "wght" 400, "GRAD" 0, "opsz" 24 !important;
  max-width: 1.6rem !important;
  overflow: hidden !important;
  color: var(--up-ink) !important;
}

/* Sidebar reopen: below top tabs and on the RIGHT so Home + brand stay clear */
[data-testid="collapsedControl"],
[data-testid="stExpandSidebarButton"],
[data-testid="stSidebarCollapsedControl"] {
  visibility: visible !important;
  display: flex !important;
  opacity: 1 !important;
  pointer-events: auto !important;
  position: fixed !important;
  left: auto !important;
  right: 0.85rem !important;
  top: 4.75rem !important;
  z-index: 1000001 !important;
  width: 2.35rem !important;
  height: 2.35rem !important;
  align-items: center !important;
  justify-content: center !important;
  background: #ffffff !important;
  border: 1px solid var(--up-line) !important;
  border-radius: 12px !important;
  box-shadow: var(--up-shadow) !important;
  font-size: 0 !important; /* hide any leftover raw icon-name text */
  color: transparent !important;
}
[data-testid="collapsedControl"] span[data-testid="stIconMaterial"],
[data-testid="stSidebarCollapsedControl"] span[data-testid="stIconMaterial"],
[data-testid="collapsedControl"] svg,
[data-testid="stSidebarCollapsedControl"] svg {
  font-size: 1.35rem !important;
  color: var(--up-ink) !important;
  visibility: visible !important;
}
/* Fallback chevron if the icon font still fails */
[data-testid="collapsedControl"]::after,
[data-testid="stSidebarCollapsedControl"]::after {
  content: "‹";
  position: absolute;
  font-size: 1.6rem !important;
  line-height: 1;
  color: var(--up-ink);
  font-family: var(--up-font);
  pointer-events: none;
}
[data-testid="collapsedControl"]:has(span[data-testid="stIconMaterial"])::after,
[data-testid="stSidebarCollapsedControl"]:has(span[data-testid="stIconMaterial"])::after,
[data-testid="collapsedControl"]:has(svg)::after,
[data-testid="stSidebarCollapsedControl"]:has(svg)::after {
  content: none;
}

[data-testid="stHeader"] button[kind="header"],
[data-testid="stHeader"] [data-testid="baseButton-header"],
[data-testid="stHeader"] [data-testid="stBaseButton-header"],
[data-testid="stToolbar"] button[kind="headerNoPadding"],
[data-testid="stToolbar"] [data-testid="stBaseButton-headerNoPadding"] {
  visibility: visible !important;
  display: inline-flex !important;
  opacity: 1 !important;
  pointer-events: auto !important;
  z-index: 1000001 !important;
  font-size: 0 !important;
  color: transparent !important;
}
[data-testid="stHeader"] button[kind="header"] span[data-testid="stIconMaterial"],
[data-testid="stToolbar"] button[kind="headerNoPadding"] span[data-testid="stIconMaterial"],
[data-testid="stHeader"] button[kind="header"] svg,
[data-testid="stToolbar"] button[kind="headerNoPadding"] svg {
  font-size: 1.35rem !important;
  color: var(--up-ink) !important;
}

.block-container {
  /* Clear sticky top nav so UrbanPulse NYC brand is never clipped */
  padding-top: 3.25rem !important;
  padding-bottom: 3rem !important;
  padding-left: 1.75rem !important;
  padding-right: 1.75rem !important;
  max-width: 1080px;
}
section.main > div {
  padding-top: 0.5rem !important;
}

/* —— Top navigation —— */
[data-testid="stSidebarNav"] { display: none !important; }
[data-testid="stHeader"] [data-testid="stToolbarActions"],
header [data-testid="stLogoSpacer"] { display: none !important; }

/* Sidebar = accessibility controls only */
[data-testid="stSidebar"] {
  background: var(--up-surface) !important;
  border-right: 1px solid var(--up-line) !important;
}
[data-testid="stSidebar"] > div:first-child {
  padding-top: 1.25rem;
}
[data-testid="stSidebar"] * {
  font-family: var(--up-font) !important;
}

/* —— Typography —— */
h1, h2, h3, .up-brand {
  font-family: var(--up-font-display) !important;
  font-weight: 700 !important;
  letter-spacing: -0.025em;
  color: var(--up-ink) !important;
}
h1 { font-size: clamp(1.85rem, 4vw, 2.35rem) !important; line-height: 1.15 !important; }
h2 { font-size: 1.45rem !important; margin-top: 0.25rem !important; }
h3 { font-size: 1.15rem !important; }
p, li, label, .stMarkdown, [data-testid="stCaption"] {
  font-size: 1rem;
  line-height: 1.6;
}
[data-testid="stCaption"], .stCaption {
  color: var(--up-muted) !important;
}

/* —— Hero / brand —— */
.up-topbrand {
  display: flex;
  align-items: baseline;
  gap: 0.55rem;
  flex-wrap: wrap;
  margin: 0.35rem 0 1.1rem 0;
  padding-top: 0.35rem;
  position: relative;
  z-index: 1;
}
.up-topbrand .name {
  font-family: var(--up-font-display);
  font-weight: 750;
  font-size: clamp(1.65rem, 3.8vw, 2.15rem);
  letter-spacing: -0.03em;
  color: var(--up-ink);
  line-height: 1.15;
}
.up-topbrand .name span {
  color: var(--up-accent);
}
.up-topbrand .tag {
  font-size: 0.72rem;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--up-accent);
  background: var(--up-accent-soft);
  border-radius: 999px;
  padding: 0.22rem 0.55rem;
}
.up-hero {
  padding: 0.5rem 0 1.4rem 0;
  max-width: 780px;
}
.up-brand {
  font-size: clamp(2.5rem, 6.5vw, 3.75rem) !important;
  line-height: 1.02 !important;
  margin: 0 0 1rem 0 !important;
  font-weight: 750 !important;
}
.up-brand span {
  color: var(--up-accent);
}
.up-lede {
  font-size: 1.18rem;
  line-height: 1.65;
  color: var(--up-ink);
  font-weight: 600;
  max-width: 42rem;
  margin: 0 0 0.75rem 0;
}
.up-lede-sub {
  font-size: 1.02rem;
  line-height: 1.6;
  color: var(--up-muted);
  font-weight: 500;
  max-width: 42rem;
  margin: 0 0 1.35rem 0;
}
.up-kicker {
  text-transform: uppercase;
  letter-spacing: 0.1em;
  font-size: 0.72rem;
  font-weight: 600;
  color: var(--up-accent-2);
  margin-bottom: 0.55rem;
}

/* —— Photon / iMessage howto (home) —— */
.up-photon {
  margin: 2.1rem 0 1.1rem 0;
  padding: 1.35rem 0 0.35rem 0;
  border-top: 1px solid var(--up-line);
}
.up-photon-title {
  font-family: var(--up-font-display) !important;
  font-size: clamp(1.45rem, 2.4vw, 1.85rem) !important;
  font-weight: 700 !important;
  letter-spacing: -0.02em;
  margin: 0 0 0.55rem 0 !important;
  color: var(--up-ink) !important;
}
.up-photon-lede {
  font-size: 1.02rem;
  line-height: 1.55;
  color: var(--up-muted);
  max-width: 42rem;
  margin: 0 0 1rem 0;
}
.up-photon-number {
  margin: 0.35rem 0 0.45rem 0;
  font-family: var(--up-font-display);
  font-size: clamp(1.85rem, 4.2vw, 2.55rem);
  font-weight: 700;
  letter-spacing: -0.03em;
  line-height: 1.15;
}
.up-photon-number a {
  color: var(--up-accent) !important;
  text-decoration: none !important;
  border-bottom: 2px solid rgba(79, 70, 229, 0.22);
}
.up-photon-number a:hover {
  border-bottom-color: var(--up-accent);
}
.up-photon-hint {
  font-size: 0.92rem;
  color: var(--up-faint);
  margin: 0 0 0.85rem 0;
}

/* —— Cards / panels —— */
.up-panel {
  border: 1px solid var(--up-line);
  background: var(--up-surface);
  border-radius: var(--up-radius);
  box-shadow: var(--up-shadow);
  padding: 1.15rem 1.35rem;
}
.up-dup {
  border: 1px solid rgba(217, 119, 6, 0.28);
  border-left: 4px solid var(--up-amber);
  background: #FFFBEB;
  border-radius: var(--up-radius-sm);
  padding: 1rem 1.15rem;
  margin: 0.75rem 0 1.25rem;
  box-shadow: none;
}
.up-dup strong { color: var(--up-ink); }

[data-testid="stVerticalBlockBorderWrapper"] {
  border: 1px solid var(--up-line) !important;
  border-radius: var(--up-radius) !important;
  background: var(--up-surface) !important;
  box-shadow: var(--up-shadow);
  padding: 0.35rem 0.15rem;
}

/* —— Buttons: neutrals by default; saturated indigo only on primary CTAs —— */
div.stButton > button,
div.stDownloadButton > button,
[data-testid="stBaseButton-secondary"],
[data-testid="baseButton-secondary"],
[data-testid="stBaseButton-primary"],
[data-testid="baseButton-primary"],
[data-testid="stLinkButton"] a,
[data-testid="stPageLink-NavLink"],
a[data-testid="stPageLink-NavLink"] {
  border-radius: 999px !important;
  font-weight: 600 !important;
  font-family: var(--up-font) !important;
  transition: transform 160ms ease, box-shadow 160ms ease, background 160ms ease !important;
  padding: 0.55rem 1.2rem !important;
}
div.stButton > button,
div.stDownloadButton > button,
[data-testid="stBaseButton-secondary"],
[data-testid="baseButton-secondary"] {
  border: 1px solid var(--up-line) !important;
  background: var(--up-surface) !important;
  color: var(--up-ink) !important;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04) !important;
}
div.stButton > button:hover {
  transform: translateY(-1px);
  background: #F1F5F9 !important;
  border-color: rgba(15, 23, 42, 0.14) !important;
  box-shadow: 0 4px 12px rgba(15, 23, 42, 0.08) !important;
}
/* Strong saturated color reserved for primary actions */
div.stButton > button[kind="primary"],
div.stButton > button[data-testid="baseButton-primary"],
[data-testid="stBaseButton-primary"] {
  background: var(--up-accent) !important;
  color: #fff !important;
  border: none !important;
  box-shadow: 0 6px 16px rgba(79, 70, 229, 0.28) !important;
}
div.stButton > button[kind="primary"]:hover,
div.stButton > button[data-testid="baseButton-primary"]:hover {
  background: #4338CA !important;
  color: #fff !important;
  box-shadow: 0 8px 20px rgba(79, 70, 229, 0.34) !important;
}
[data-testid="stLinkButton"] a {
  background: var(--up-surface) !important;
  color: var(--up-ink) !important;
  border: 1px solid var(--up-line) !important;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04) !important;
}

/* Home action page links — quiet neutrals, light primary tint only */
[data-testid="stPageLink-NavLink"],
a[data-testid="stPageLink-NavLink"] {
  background: var(--up-surface) !important;
  border: 1px solid var(--up-line) !important;
  margin: 0.25rem 0 !important;
  color: var(--up-ink) !important;
  box-shadow: var(--up-shadow) !important;
}
div[data-testid="column"]:nth-child(1) [data-testid="stPageLink-NavLink"],
div[data-testid="column"]:nth-child(2) [data-testid="stPageLink-NavLink"],
div[data-testid="column"]:nth-child(3) [data-testid="stPageLink-NavLink"],
div[data-testid="column"]:nth-child(4) [data-testid="stPageLink-NavLink"] {
  background: var(--up-surface) !important;
  box-shadow: var(--up-shadow) !important;
}
div[data-testid="column"]:nth-child(1) [data-testid="stPageLink-NavLink"]:hover,
div[data-testid="column"]:nth-child(2) [data-testid="stPageLink-NavLink"]:hover,
div[data-testid="column"]:nth-child(3) [data-testid="stPageLink-NavLink"]:hover,
div[data-testid="column"]:nth-child(4) [data-testid="stPageLink-NavLink"]:hover {
  border-color: rgba(79, 70, 229, 0.35) !important;
  box-shadow: 0 0 0 3px rgba(79, 70, 229, 0.1), var(--up-shadow) !important;
}

/* —— Inputs —— */
[data-testid="stTextInput"] input,
[data-testid="stTextArea"] textarea,
[data-testid="stNumberInput"] input,
[data-baseweb="select"] > div,
[data-baseweb="input"] {
  border-radius: var(--up-radius-sm) !important;
  border-color: var(--up-line) !important;
  font-family: var(--up-font) !important;
  transition: border-color 160ms ease, box-shadow 160ms ease !important;
}
[data-testid="stTextInput"] input:focus,
[data-testid="stTextArea"] textarea:focus,
[data-testid="stNumberInput"] input:focus {
  border-color: var(--up-accent) !important;
  box-shadow: 0 0 0 3px rgba(79, 70, 229, 0.18) !important;
}
[data-testid="stFileUploader"] section {
  border-radius: var(--up-radius) !important;
  border: 1px dashed rgba(15, 23, 42, 0.18) !important;
  background: var(--up-surface) !important;
}
[data-testid="stSlider"] [data-baseweb="slider"] div[role="slider"] {
  background: var(--up-accent) !important;
}

/* —— Metrics —— */
[data-testid="stMetric"] {
  background: var(--up-surface);
  border: 1px solid var(--up-line);
  border-radius: var(--up-radius);
  box-shadow: var(--up-shadow);
  padding: 0.85rem 1rem;
}
[data-testid="stMetricValue"] {
  font-family: var(--up-font-display) !important;
  font-weight: 700 !important;
  color: var(--up-ink) !important;
}
[data-testid="stMetricLabel"] {
  color: var(--up-muted) !important;
  font-weight: 500 !important;
}

/* —— Alerts / chat —— */
[data-testid="stAlert"] {
  border-radius: var(--up-radius-sm) !important;
  border: 1px solid var(--up-line) !important;
}
[data-testid="stChatMessage"] {
  border-radius: var(--up-radius) !important;
  background: var(--up-surface);
  border: 1px solid var(--up-line);
  box-shadow: var(--up-shadow);
  padding: 0.35rem 0.5rem;
  margin-bottom: 0.5rem;
}

/* —— Tabs / radio / toggle —— */
[data-baseweb="tab-list"] {
  gap: 0.35rem;
}
[data-baseweb="tab"] {
  border-radius: 999px !important;
  font-weight: 600 !important;
}
div[role="radiogroup"] label {
  border-radius: 999px !important;
}

/* —— Dataframe / charts —— */
[data-testid="stDataFrame"],
[data-testid="stDataFrameResizable"] {
  border-radius: var(--up-radius) !important;
  overflow: hidden;
  border: 1px solid var(--up-line);
  box-shadow: var(--up-shadow);
}
[data-testid="stArrowVegaLiteChart"],
[data-testid="stVegaLiteChart"] {
  border-radius: var(--up-radius);
  background: var(--up-surface);
  border: 1px solid var(--up-line);
  box-shadow: var(--up-shadow);
  padding: 0.75rem;
}

/* —— Expander —— */
[data-testid="stExpander"] {
  border: 1px solid var(--up-line) !important;
  border-radius: var(--up-radius-sm) !important;
  background: var(--up-surface) !important;
  box-shadow: none !important;
}

/* —— Dividers —— */
hr {
  border: none !important;
  border-top: 1px solid var(--up-line) !important;
  margin: 1.5rem 0 !important;
}

/* —— Map iframe soften —— */
iframe {
  border-radius: var(--up-radius) !important;
}

/* —— Mobile —— */
@media (max-width: 768px) {
  .block-container {
    padding-top: 3rem !important;
    padding-left: 1rem !important;
    padding-right: 1rem !important;
  }
  .up-brand {
    font-size: 2.2rem !important;
  }
  [data-testid="collapsedControl"],
  [data-testid="stExpandSidebarButton"],
  [data-testid="stSidebarCollapsedControl"] {
    top: 5.25rem !important;
    right: 0.65rem !important;
    left: auto !important;
  }
  [data-testid="stMetric"] {
    margin-bottom: 0.5rem;
  }
}
"""


def load_css() -> None:
    """Inject the single global CSS block."""
    st.markdown(f"<style>{CSS}</style>", unsafe_allow_html=True)


def chart_colors() -> dict[str, str]:
    """Shared status / series colors for charts and maps."""
    return {
        "accent": ACCENT,
        "green": STATUS_GREEN,
        "amber": STATUS_AMBER,
        "coral": STATUS_CORAL,
        "muted": STATUS_MUTED,
        "low": STATUS_GREEN,
        "medium": STATUS_AMBER,
        "high": "#EA580C",
        "critical": STATUS_CORAL,
        "resolved": STATUS_MUTED,
    }
