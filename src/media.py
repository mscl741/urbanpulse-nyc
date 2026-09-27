"""Image storage + perceptual helpers for UrbanPulse reports.

Local files under data/uploads are a cache for local/dev. On Render the disk is
ephemeral, so durable photos must live in Tiger Data (see db.attach_image).
"""

from __future__ import annotations

import hashlib
import io
from pathlib import Path

UPLOAD_DIR = Path(__file__).resolve().parent.parent / "data" / "uploads"

# Soft cap so Postgres BYTEA stays reasonable for street photos.
_MAX_STORE_BYTES = 1_800_000


def ensure_upload_dir() -> Path:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    return UPLOAD_DIR


def image_sha256(image_bytes: bytes) -> str:
    return hashlib.sha256(image_bytes).hexdigest()


def prepare_image_for_storage(
    image_bytes: bytes, *, mime: str = "image/jpeg"
) -> tuple[bytes, str]:
    """Normalize / lightly compress for durable DB storage."""
    normalized = (mime or "image/jpeg").split(";", 1)[0].strip().lower()
    if normalized == "image/jpg":
        normalized = "image/jpeg"
    if len(image_bytes) <= _MAX_STORE_BYTES and normalized in {
        "image/jpeg",
        "image/png",
        "image/webp",
    }:
        return image_bytes, normalized

    try:
        from PIL import Image
    except Exception:
        return image_bytes, normalized if normalized.startswith("image/") else "image/jpeg"

    with Image.open(io.BytesIO(image_bytes)) as img:
        rgb = img.convert("RGB")
        rgb.thumbnail((1600, 1600))
        quality = 85
        buf = io.BytesIO()
        rgb.save(buf, format="JPEG", quality=quality, optimize=True)
        out = buf.getvalue()
        while len(out) > _MAX_STORE_BYTES and quality > 55:
            quality -= 10
            buf = io.BytesIO()
            rgb.save(buf, format="JPEG", quality=quality, optimize=True)
            out = buf.getvalue()
    return out, "image/jpeg"


def save_report_image(report_id: int, image_bytes: bytes, *, mime: str = "image/jpeg") -> str:
    """Write a local cache file (ephemeral on Render). Prefer DB blob for durability."""
    ensure_upload_dir()
    stored, stored_mime = prepare_image_for_storage(image_bytes, mime=mime)
    ext = ".png" if "png" in stored_mime else ".webp" if "webp" in stored_mime else ".jpg"
    path = UPLOAD_DIR / f"report_{report_id}{ext}"
    path.write_bytes(stored)
    return str(path)


def read_image_bytes(path: str | None) -> bytes | None:
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        return None
    return p.read_bytes()
