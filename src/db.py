"""Tiger Data / PostgreSQL persistence for UrbanPulse hazard tickets."""

from __future__ import annotations

import json
import math
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from sqlalchemy import (
    DateTime,
    Float,
    Integer,
    LargeBinary,
    MetaData,
    String,
    Text,
    create_engine,
    desc,
    func,
    select,
    text,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from models import DispatchTicket, is_weather_hazard_type, weather_affected_radius_m

metadata = MetaData()


class Base(DeclarativeBase):
    metadata = metadata


class HazardReport(Base):
    """One row per resident report — time-series friendly via created_at."""

    __tablename__ = "hazard_reports"

    # Composite PK (id, created_at) is required for Timescale hypertables.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        primary_key=True,
        nullable=False,
        index=True,
        default=lambda: datetime.now(timezone.utc),
    )
    location: Mapped[str] = mapped_column(String(255), nullable=False)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    hazard_type: Mapped[str] = mapped_column(String(80), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    agency: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    priority: Mapped[str] = mapped_column(String(20), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    council_email_subject: Mapped[str] = mapped_column(String(120), nullable=False)
    council_email_body: Mapped[str] = mapped_column(Text, nullable=False)
    ticket_json: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="live")
    email_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    email_to: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email_method: Mapped[str | None] = mapped_column(String(40), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open", index=True)
    image_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    image_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    # Durable photo bytes in Tiger — Render local disk is ephemeral across deploys.
    image_blob: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    image_mime: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Weather hazards: affected-area radius (meters) around the pin for near-me alerts.
    affected_radius_m: Mapped[float | None] = mapped_column(Float, nullable=True)


_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None
_initialized = False


def database_url() -> str:
    raw = (os.getenv("DATABASE_URL") or "sqlite:///./urbanpulse.db").strip()
    # Tiger / Timescale often hands out postgres:// — SQLAlchemy wants postgresql://
    if raw.startswith("postgres://"):
        raw = "postgresql://" + raw[len("postgres://") :]
    # Prefer psycopg2 (in requirements) over psycopg3 if none specified
    if raw.startswith("postgresql://") and "+psycopg" not in raw.split("://", 1)[0]:
        raw = "postgresql+psycopg2://" + raw[len("postgresql://") :]
    return raw


def is_postgres(url: str | None = None) -> bool:
    u = (url or database_url()).lower()
    return u.startswith("postgresql") or u.startswith("postgres")


def get_engine() -> Engine:
    global _engine, _SessionLocal
    if _engine is None:
        url = database_url()
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        _engine = create_engine(url, pool_pre_ping=True, connect_args=connect_args)
        _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)
    return _engine


@contextmanager
def session_scope() -> Iterator[Session]:
    get_engine()
    assert _SessionLocal is not None
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _row_dict(r: HazardReport) -> dict[str, Any]:
    return {
        "id": r.id,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "resolved_at": r.resolved_at.isoformat() if r.resolved_at else None,
        "location": r.location,
        "hazard_type": r.hazard_type,
        "severity": r.severity,
        "agency": r.agency,
        "priority": r.priority,
        "confidence": r.confidence,
        "summary": r.summary,
        "latitude": r.latitude,
        "longitude": r.longitude,
        "source": r.source,
        "status": r.status or "open",
        "image_path": r.image_path,
        "image_hash": r.image_hash,
        "has_image": bool(r.image_blob) or bool(r.image_path),
        "image_mime": r.image_mime,
        "email_status": r.email_status,
        "email_to": r.email_to,
        "email_method": r.email_method,
        "affected_radius_m": r.affected_radius_m,
    }


def init_db() -> dict[str, Any]:
    global _initialized
    engine = get_engine()
    Base.metadata.create_all(engine)
    _migrate_columns(engine)
    info: dict[str, Any] = {
        "url_scheme": database_url().split("://", 1)[0],
        "hypertable": False,
        "backend": "postgres" if is_postgres() else "sqlite",
    }

    if is_postgres():
        with engine.begin() as conn:
            try:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE"))
            except Exception as exc:  # noqa: BLE001
                info["timescale_extension_error"] = str(exc)
            # Ensure PK includes created_at (Timescale requirement)
            try:
                conn.execute(
                    text(
                        """
                        DO $$
                        BEGIN
                          IF EXISTS (
                            SELECT 1 FROM information_schema.table_constraints
                            WHERE table_name = 'hazard_reports'
                              AND constraint_type = 'PRIMARY KEY'
                              AND constraint_name = 'hazard_reports_pkey'
                          ) THEN
                            ALTER TABLE hazard_reports DROP CONSTRAINT hazard_reports_pkey;
                          END IF;
                          ALTER TABLE hazard_reports
                            ADD PRIMARY KEY (id, created_at);
                        EXCEPTION WHEN others THEN
                          NULL; -- already composite or not applicable
                        END $$;
                        """
                    )
                )
            except Exception as exc:  # noqa: BLE001
                info["pk_migrate_note"] = str(exc)
            try:
                conn.execute(
                    text(
                        "SELECT create_hypertable("
                        "'hazard_reports', 'created_at', "
                        "if_not_exists => TRUE, migrate_data => TRUE)"
                    )
                )
                info["hypertable"] = True
            except Exception as exc:  # noqa: BLE001
                info["hypertable_note"] = str(exc)

    _initialized = True
    try:
        _backfill_weather_radii(engine)
    except Exception:
        pass
    return info


def _migrate_columns(engine: Engine) -> None:
    """Add missing columns one statement / transaction at a time.

    Postgres aborts the whole transaction after the first failed ALTER (e.g. column
    already exists). Bundling all ALTERs in one begin() silently skipped newer
    columns like affected_radius_m — which crashed Live map.
    """
    stmts = [
        "ALTER TABLE hazard_reports ADD COLUMN email_status VARCHAR(40)",
        "ALTER TABLE hazard_reports ADD COLUMN email_to VARCHAR(255)",
        "ALTER TABLE hazard_reports ADD COLUMN email_method VARCHAR(40)",
        "ALTER TABLE hazard_reports ADD COLUMN status VARCHAR(20) DEFAULT 'open'",
        "ALTER TABLE hazard_reports ADD COLUMN image_path VARCHAR(512)",
        "ALTER TABLE hazard_reports ADD COLUMN image_hash VARCHAR(64)",
        "ALTER TABLE hazard_reports ADD COLUMN image_blob BYTEA",
        "ALTER TABLE hazard_reports ADD COLUMN image_mime VARCHAR(64)",
        "ALTER TABLE hazard_reports ADD COLUMN resolved_at TIMESTAMP",
        "ALTER TABLE hazard_reports ADD COLUMN affected_radius_m FLOAT",
    ]
    for sql in stmts:
        try:
            with engine.begin() as conn:
                conn.execute(text(sql))
        except Exception:
            pass
    try:
        with engine.begin() as conn:
            conn.execute(text("UPDATE hazard_reports SET status = 'open' WHERE status IS NULL"))
    except Exception:
        pass
    # Explicit Postgres guard — Timescale / older deploys may still lack the column.
    if is_postgres():
        try:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        """
                        DO $$
                        BEGIN
                          IF NOT EXISTS (
                            SELECT 1 FROM information_schema.columns
                            WHERE table_name = 'hazard_reports'
                              AND column_name = 'affected_radius_m'
                          ) THEN
                            ALTER TABLE hazard_reports
                              ADD COLUMN affected_radius_m DOUBLE PRECISION;
                          END IF;
                        END $$;
                        """
                    )
                )
        except Exception:
            pass


def ensure_db() -> dict[str, Any]:
    if not _initialized:
        return init_db()
    # Re-run cheap column migrations so new deploys heal live Postgres schemas.
    try:
        _migrate_columns(get_engine())
    except Exception:
        pass
    try:
        _backfill_weather_radii(get_engine())
    except Exception:
        pass
    return {
        "url_scheme": database_url().split("://", 1)[0],
        "backend": "postgres" if is_postgres() else "sqlite",
    }


def _backfill_weather_radii(engine: Engine) -> None:
    """Ensure open weather pins have a visible affected_radius_m."""
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                "SELECT id, hazard_type, severity, affected_radius_m "
                "FROM hazard_reports WHERE status = 'open'"
            )
        ).mappings().all()
        for row in rows:
            ht = str(row.get("hazard_type") or "")
            if not is_weather_hazard_type(ht):
                continue
            current = row.get("affected_radius_m")
            desired = weather_affected_radius_m(str(row.get("severity") or "medium"))
            try:
                cur_f = float(current) if current is not None else 0.0
            except (TypeError, ValueError):
                cur_f = 0.0
            # Refresh if missing or still on the old smaller demo radii.
            if cur_f <= 0 or cur_f < desired:
                conn.execute(
                    text(
                        "UPDATE hazard_reports SET affected_radius_m = :r "
                        "WHERE id = :id"
                    ),
                    {"r": desired, "id": int(row["id"])},
                )


def save_ticket(
    ticket: DispatchTicket,
    location: str,
    *,
    latitude: float | None = None,
    longitude: float | None = None,
    source: str = "live",
    image_path: str | None = None,
    image_hash: str | None = None,
    status: str = "open",
) -> int:
    ensure_db()
    aff_radius: float | None = None
    if ticket.is_weather_hazard():
        aff_radius = weather_affected_radius_m(ticket.severity)
    row = HazardReport(
        created_at=datetime.now(timezone.utc),
        location=location,
        latitude=latitude,
        longitude=longitude,
        hazard_type=ticket.hazard_type,
        severity=ticket.severity.value,
        agency=ticket.agency,
        confidence=ticket.confidence,
        priority=ticket.recommended_priority,
        summary=ticket.summary,
        council_email_subject=ticket.council_email_subject,
        council_email_body=ticket.council_email_body,
        ticket_json=json.dumps(ticket.model_dump(), default=str),
        source=source,
        status=status,
        image_path=image_path,
        image_hash=image_hash,
        affected_radius_m=aff_radius,
    )
    with session_scope() as session:
        session.add(row)
        session.flush()
        return int(row.id)


def _get_report_row(session, report_id: int) -> HazardReport | None:
    """Lookup by report id only — Timescale uses composite PK (id, created_at)."""
    return session.scalars(
        select(HazardReport)
        .where(HazardReport.id == report_id)
        .order_by(desc(HazardReport.created_at))
        .limit(1)
    ).first()


def attach_image(
    report_id: int,
    image_path: str,
    image_hash: str,
    *,
    image_bytes: bytes | None = None,
    mime: str | None = None,
) -> None:
    """Attach photo metadata + durable blob (Tiger) so pins keep images after redeploys."""
    ensure_db()
    stored: bytes | None = None
    stored_mime: str | None = mime
    if image_bytes:
        from media import prepare_image_for_storage

        stored, stored_mime = prepare_image_for_storage(image_bytes, mime=mime or "image/jpeg")
    with session_scope() as session:
        row = _get_report_row(session, report_id)
        if row is None:
            raise ValueError(f"No report #{report_id}")
        row.image_path = image_path
        row.image_hash = image_hash
        if stored is not None:
            row.image_blob = stored
            row.image_mime = stored_mime


def load_report_image(report_id: int) -> tuple[bytes, str] | None:
    """Load photo bytes for a report — Tiger blob first, then local path cache."""
    ensure_db()
    with session_scope() as session:
        row = _get_report_row(session, report_id)
        if row is None:
            return None
        if row.image_blob:
            mime = (row.image_mime or "image/jpeg").strip() or "image/jpeg"
            return bytes(row.image_blob), mime
        path = row.image_path
    if not path:
        return None
    from media import read_image_bytes

    data = read_image_bytes(path)
    if not data:
        return None
    lower = path.lower()
    mime = "image/png" if lower.endswith(".png") else "image/webp" if lower.endswith(".webp") else "image/jpeg"
    return data, mime


def resolve_ticket(report_id: int) -> None:
    ensure_db()
    with session_scope() as session:
        row = _get_report_row(session, report_id)
        if row is None:
            raise ValueError(f"No report #{report_id}")
        row.status = "resolved"
        row.resolved_at = datetime.now(timezone.utc)


def reopen_ticket(report_id: int) -> None:
    ensure_db()
    with session_scope() as session:
        row = _get_report_row(session, report_id)
        if row is None:
            raise ValueError(f"No report #{report_id}")
        row.status = "open"
        row.resolved_at = None


def get_ticket(report_id: int) -> dict[str, Any] | None:
    ensure_db()
    with session_scope() as session:
        row = _get_report_row(session, report_id)
        return _row_dict(row) if row else None


def recent_tickets(limit: int = 25, *, status: str | None = "open") -> list[dict[str, Any]]:
    ensure_db()
    with session_scope() as session:
        stmt = select(HazardReport).order_by(desc(HazardReport.created_at)).limit(limit)
        if status:
            stmt = (
                select(HazardReport)
                .where(HazardReport.status == status)
                .order_by(desc(HazardReport.created_at))
                .limit(limit)
            )
        rows = session.scalars(stmt).all()
        return [_row_dict(r) for r in rows]


def map_tickets(*, include_resolved: bool = False) -> list[dict[str, Any]]:
    """Reports with coordinates for the live map (open by default)."""
    ensure_db()
    with session_scope() as session:
        stmt = select(HazardReport).where(
            HazardReport.latitude.is_not(None),
            HazardReport.longitude.is_not(None),
        )
        if not include_resolved:
            stmt = stmt.where(HazardReport.status == "open")
        rows = session.scalars(stmt.order_by(desc(HazardReport.created_at))).all()
        return [_row_dict(r) for r in rows]


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def nearby_open_reports(
    lat: float,
    lon: float,
    *,
    radius_m: float = 120.0,
    limit: int = 8,
) -> list[dict[str, Any]]:
    """Open issues within radius_m of a point (same block / intersection)."""
    ensure_db()
    with session_scope() as session:
        rows = session.scalars(
            select(HazardReport).where(
                HazardReport.status == "open",
                HazardReport.latitude.is_not(None),
                HazardReport.longitude.is_not(None),
            )
        ).all()
        scored: list[tuple[float, HazardReport]] = []
        for r in rows:
            assert r.latitude is not None and r.longitude is not None
            d = _haversine_m(lat, lon, float(r.latitude), float(r.longitude))
            aff = 0.0
            if is_weather_hazard_type(r.hazard_type):
                aff = float(r.affected_radius_m or 0.0)
                if aff <= 0:
                    aff = weather_affected_radius_m(r.severity)
            # Include if within scan radius, or inside a weather affected zone.
            if d <= max(radius_m, aff):
                scored.append((d, r))
        scored.sort(key=lambda t: t[0])
        out = []
        for dist, r in scored[:limit]:
            item = _row_dict(r)
            item["distance_m"] = round(dist, 1)
            out.append(item)
        return out


def find_open_by_hash(image_hash: str) -> dict[str, Any] | None:
    ensure_db()
    with session_scope() as session:
        row = session.scalars(
            select(HazardReport)
            .where(
                HazardReport.status == "open",
                HazardReport.image_hash == image_hash,
            )
            .order_by(desc(HazardReport.created_at))
            .limit(1)
        ).first()
        return _row_dict(row) if row else None


def mark_email_sent(
    report_id: int,
    *,
    to_address: str,
    method: str,
    status: str = "sent_mock",
) -> None:
    ensure_db()
    with session_scope() as session:
        row = _get_report_row(session, report_id)
        if row is None:
            raise ValueError(f"No report #{report_id}")
        row.email_status = status
        row.email_to = to_address
        row.email_method = method


def severity_by_hour(hours: int = 48) -> list[dict[str, Any]]:
    ensure_db()
    engine = get_engine()

    if is_postgres():
        queries = [
            """
            SELECT time_bucket('1 hour', created_at) AS bucket,
                   severity,
                   COUNT(*)::int AS n
            FROM hazard_reports
            WHERE created_at >= NOW() - make_interval(hours => :hours)
              AND status = 'open'
            GROUP BY 1, 2
            ORDER BY 1 ASC
            """,
            """
            SELECT date_trunc('hour', created_at) AS bucket,
                   severity,
                   COUNT(*)::int AS n
            FROM hazard_reports
            WHERE created_at >= NOW() - make_interval(hours => :hours)
            GROUP BY 1, 2
            ORDER BY 1 ASC
            """,
        ]
        with engine.connect() as conn:
            for sql in queries:
                try:
                    result = conn.execute(text(sql), {"hours": hours})
                    return [
                        {
                            "bucket": row.bucket.isoformat() if row.bucket else None,
                            "severity": row.severity,
                            "count": row.n,
                        }
                        for row in result
                    ]
                except Exception:
                    continue

    with session_scope() as session:
        rows = session.scalars(select(HazardReport).order_by(HazardReport.created_at)).all()
        buckets: dict[tuple[str, str], int] = {}
        for r in rows:
            if not r.created_at or (r.status or "open") != "open":
                continue
            hour = r.created_at.astimezone(timezone.utc).replace(
                minute=0, second=0, microsecond=0
            )
            key = (hour.isoformat(), r.severity)
            buckets[key] = buckets.get(key, 0) + 1
        return [
            {"bucket": b, "severity": sev, "count": n}
            for (b, sev), n in sorted(buckets.items())
        ]


def db_status() -> dict[str, Any]:
    try:
        info = ensure_db()
        with session_scope() as session:
            total = session.scalar(select(func.count()).select_from(HazardReport)) or 0
            open_n = (
                session.scalar(
                    select(func.count()).select_from(HazardReport).where(HazardReport.status == "open")
                )
                or 0
            )
        info["ok"] = True
        info["report_count"] = int(total)
        info["open_count"] = int(open_n)
        raw = database_url()
        info["database"] = raw.split("@", 1)[-1] if "@" in raw else raw
        return info
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc), "database": database_url().split("://", 1)[0]}
