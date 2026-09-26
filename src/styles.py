"""
UrbanPulse visual system — Material 3 × Apple HIG (look & feel only).

Call `load_css()` once per page (via `apply_theme()` / `_boot()`).
No page logic, data, or navigation changes live here.
"""

from __future__ import annotations

import streamlit as st

# Friendly palette for maps / status (shared with map_view)
ACCENT = "#1A73E8"
STATUS_GREEN = "#34A853"
STATUS_AMBER = "#FBBC04"
STATUS_CORAL = "#EA4335"
STATUS_MUTED = "#9AA0A6"

CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

:root {
  --up-bg: #F8F9FB;
  --up-surface: #FFFFFF;
  --up-ink: #202124;
  --up-muted: #5F6368;
  --up-faint: #80868B;
  --up-line: rgba(32, 33, 36, 0.08);
  --up-accent: #1A73E8;
  --up-accent-soft: #E8F0FE;
  --up-green: #34A853;
  --up-amber: #FBBC04;
  --up-coral: #EA4335;
  --up-radius: 18px;
  --up-radius-sm: 12px;
  --up-shadow: 0 1px 2px rgba(32, 33, 36, 0.06), 0 4px 16px rgba(32, 33, 36, 0.04);
  --up-font: "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
}

html, body, [class*="css"], .stApp, [data-testid="stAppViewContainer"] {
  font-family: var(--up-font) !important;
  color: var(--up-ink);
}

.stApp {
  background: var(--up-bg) !important;
}

/* —— Hide unpolished Streamlit chrome —— */
#MainMenu { visibility: hidden; }
footer { visibility: hidden; }
header[data-testid="stHeader"] {
  background: transparent !important;
  height: 0 !important;
}
[data-testid="stToolbar"] { visibility: hidden; height: 0; }
[data-testid="stDecoration"] { display: none !important; }
div[data-testid="stStatusWidget"] { display: none !important; }
.stDeployButton, [data-testid="stAppDeployButton"] { display: none !important; }

.block-container {
  padding-top: 1.5rem !important;
  padding-bottom: 3rem !important;
  max-width: 1080px;
}

/* —— Sidebar nav —— */
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
[data-testid="stSidebarNav"] {
  padding-top: 0.25rem;
}
[data-testid="stSidebarNav"] a,
[data-testid="stSidebarNav"] span {
  font-size: 0.95rem !important;
  font-weight: 500 !important;
  border-radius: 10px !important;
  transition: background 160ms ease, color 160ms ease;
}
[data-testid="stSidebarNav"] a:hover {
  background: var(--up-accent-soft) !important;
}
[data-testid="stSidebarNav"] [aria-selected="true"],
[data-testid="stSidebarNav"] a[aria-current="page"] {
  background: var(--up-accent-soft) !important;
  color: var(--up-accent) !important;
  font-weight: 600 !important;
}

/* —— Typography —— */
h1, h2, h3, .up-brand {
  font-family: var(--up-font) !important;
  font-weight: 700 !important;
  letter-spacing: -0.025em;
  color: var(--up-ink) !important;
}
h1 { font-size: clamp(1.85rem, 4vw, 2.35rem) !important; line-height: 1.15 !important; }
h2 { font-size: 1.45rem !important; margin-top: 0.25rem !important; }
h3 { font-size: 1.15rem !important; }
p, li, label, .stMarkdown, [data-testid="stCaption"] {
  font-size: 0.98rem;
  line-height: 1.5;
}
[data-testid="stCaption"], .stCaption {
  color: var(--up-muted) !important;
}

/* —— Hero / brand —— */
.up-hero {
  padding: 1.75rem 0 1.25rem 0;
  max-width: 720px;
}
.up-brand {
  font-size: clamp(2.4rem, 6.5vw, 3.6rem) !important;
  line-height: 1.05 !important;
  margin: 0 0 0.85rem 0 !important;
  font-weight: 700 !important;
}
.up-brand span {
  color: var(--up-accent);
}
.up-lede {
  font-size: 1.05rem;
  line-height: 1.55;
  color: var(--up-muted);
  max-width: 36rem;
  margin: 0 0 1.25rem 0;
}
.up-kicker {
  text-transform: uppercase;
  letter-spacing: 0.12em;
  font-size: 0.7rem;
  font-weight: 600;
  color: var(--up-faint);
  margin-bottom: 0.65rem;
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
  border: 1px solid rgba(251, 188, 4, 0.35);
  border-left: 4px solid var(--up-amber);
  background: #FFF8E1;
  border-radius: var(--up-radius-sm);
  padding: 1rem 1.15rem;
  margin: 0.75rem 0 1.25rem;
  box-shadow: none;
}
.up-dup strong { color: var(--up-ink); }

/* Streamlit bordered containers ≈ cards */
[data-testid="stVerticalBlockBorderWrapper"] {
  border: 1px solid var(--up-line) !important;
  border-radius: var(--up-radius) !important;
  background: var(--up-surface) !important;
  box-shadow: var(--up-shadow);
  padding: 0.35rem 0.15rem;
}

/* —— Buttons —— */
div.stButton > button,
div.stDownloadButton > button,
[data-testid="stBaseButton-secondary"],
[data-testid="baseButton-secondary"] {
  border-radius: 999px !important;
  font-weight: 600 !important;
  font-family: var(--up-font) !important;
  border: 1px solid var(--up-line) !important;
  background: var(--up-accent-soft) !important;
  color: var(--up-accent) !important;
  transition: background 160ms ease, box-shadow 160ms ease, transform 160ms ease !important;
  padding: 0.4rem 1.1rem !important;
}
div.stButton > button:hover {
  background: #D2E3FC !important;
  border-color: transparent !important;
  box-shadow: 0 2px 8px rgba(26, 115, 232, 0.15) !important;
}
div.stButton > button[kind="primary"],
div.stButton > button[data-testid="baseButton-primary"],
[data-testid="stBaseButton-primary"] {
  background: var(--up-accent) !important;
  color: #fff !important;
  border: none !important;
  box-shadow: 0 1px 3px rgba(26, 115, 232, 0.35) !important;
}
div.stButton > button[kind="primary"]:hover,
div.stButton > button[data-testid="baseButton-primary"]:hover {
  background: #1557B0 !important;
  color: #fff !important;
}
[data-testid="stLinkButton"] a {
  border-radius: 999px !important;
  font-weight: 600 !important;
  transition: background 160ms ease !important;
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
  box-shadow: 0 0 0 3px rgba(26, 115, 232, 0.2) !important;
}
[data-testid="stFileUploader"] section {
  border-radius: var(--up-radius) !important;
  border: 1px dashed rgba(26, 115, 232, 0.35) !important;
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
  font-family: var(--up-font) !important;
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
    padding-left: 1rem !important;
    padding-right: 1rem !important;
  }
  .up-brand {
    font-size: 2.2rem !important;
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
        "high": "#F57C00",
        "critical": STATUS_CORAL,
        "resolved": STATUS_MUTED,
    }
