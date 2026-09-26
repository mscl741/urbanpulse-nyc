"""UrbanPulse theme entrypoint — delegates to styles.load_css()."""

from __future__ import annotations

from styles import load_css


def apply_theme() -> None:
    load_css()
