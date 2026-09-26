"""Image storage + perceptual helpers for UrbanPulse reports."""

from __future__ import annotations

import hashlib
from pathlib import Path

UPLOAD_DIR = Path(__file__).resolve().parent.parent / "data" / "uploads"


def ensure_upload_dir() -> Path:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    return UPLOAD_DIR


def image_sha256(image_bytes: bytes) -> str:
    return hashlib.sha256(image_bytes).hexdigest()


def save_report_image(report_id: int, image_bytes: bytes, *, mime: str = "image/jpeg") -> str:
    ensure_upload_dir()
    ext = ".png" if "png" in mime else ".webp" if "webp" in mime else ".jpg"
    path = UPLOAD_DIR / f"report_{report_id}{ext}"
    path.write_bytes(image_bytes)
    return str(path)


def read_image_bytes(path: str | None) -> bytes | None:
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        return None
    return p.read_bytes()
