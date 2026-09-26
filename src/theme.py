"""UrbanPulse visual theme — asphalt daylight + signal amber (not generic purple/cream)."""

from __future__ import annotations

import streamlit as st

# Concrete, ink, signal amber, steel
CSS = """
@import url('https://fonts.googleapis.com/css2?family=Archivo+Black&family=DM+Sans:ital,opsz,wght@0,9..40,400;0,9..40,500;0,9..40,700;1,9..40,400&display=swap');

:root {
  --up-ink: #12141a;
  --up-slate: #3a4050;
  --up-fog: #e8eaef;
  --up-paper: #f4f5f7;
  --up-amber: #e8a317;
  --up-amber-deep: #c4840a;
  --up-steel: #5b6b7c;
  --up-line: rgba(18, 20, 26, 0.08);
}

html, body, [class*="css"] {
  font-family: "DM Sans", sans-serif;
}

.stApp {
  background:
    radial-gradient(1200px 600px at 10% -10%, rgba(232, 163, 23, 0.12), transparent 55%),
    radial-gradient(900px 500px at 100% 0%, rgba(91, 107, 124, 0.14), transparent 50%),
    linear-gradient(165deg, #f7f8fa 0%, #e9ecf1 48%, #dde3ea 100%);
  color: var(--up-ink);
}

[data-testid="stHeader"] {
  background: transparent;
}

[data-testid="stSidebar"] {
  background: rgba(244, 245, 247, 0.92);
  border-right: 1px solid var(--up-line);
}

[data-testid="stSidebar"] * {
  font-family: "DM Sans", sans-serif !important;
}

h1, h2, h3, .up-brand {
  font-family: "Archivo Black", sans-serif !important;
  letter-spacing: -0.02em;
  color: var(--up-ink) !important;
}

.up-hero {
  padding: 2.5rem 0 1.5rem 0;
  max-width: 920px;
}

.up-brand {
  font-size: clamp(2.8rem, 8vw, 5.2rem);
  line-height: 0.95;
  margin: 0 0 0.75rem 0;
}

.up-brand span {
  color: var(--up-amber-deep);
}

.up-lede {
  font-size: 1.15rem;
  line-height: 1.45;
  color: var(--up-slate);
  max-width: 34rem;
  margin: 0 0 1.5rem 0;
}

.up-kicker {
  text-transform: uppercase;
  letter-spacing: 0.14em;
  font-size: 0.72rem;
  font-weight: 700;
  color: var(--up-steel);
  margin-bottom: 0.75rem;
}

.up-panel {
  border: 1px solid var(--up-line);
  background: rgba(255,255,255,0.55);
  backdrop-filter: blur(8px);
  border-radius: 2px;
  padding: 1.1rem 1.25rem;
}

.up-dup {
  border-left: 5px solid var(--up-amber);
  background: rgba(232, 163, 23, 0.12);
  padding: 1rem 1.15rem;
  margin: 0.75rem 0 1.25rem;
}

.up-dup strong { color: var(--up-ink); }

div.stButton > button[kind="primary"],
div.stButton > button[data-testid="baseButton-primary"] {
  background: var(--up-ink) !important;
  color: #fff !important;
  border: none !important;
  border-radius: 2px !important;
  font-weight: 700 !important;
}

div.stButton > button:hover {
  border-color: var(--up-amber) !important;
}

[data-testid="stMetricValue"] {
  font-family: "Archivo Black", sans-serif;
}

.block-container {
  padding-top: 1.25rem;
  max-width: 1100px;
}
"""


def apply_theme() -> None:
    st.markdown(f"<style>{CSS}</style>", unsafe_allow_html=True)
