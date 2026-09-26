"""Tiger Data / PostgreSQL persistence for UrbanPulse hazard tickets."""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from sqlalchemy import (
    DateTime,
    Float,
    Integer,
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

from models import DispatchTicket

metadata = MetaData()


class Base(DeclarativeBase):
    metadata = metadata


class HazardReport(Base):
    """One row per resident report — time-series friendly via created_at."""

    __tablename__ = "hazard_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
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


_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None
_initialized = False


def database_url() -> str:
    """Tiger Data connection string, or local SQLite so the app still runs."""
    return os.getenv("DATABASE_URL", "sqlite:///./urbanpulse.db")


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


def init_db() -> dict[str, Any]:
    """Create table; promote to TimescaleDB hypertable when available (Tiger Data)."""
    global _initialized
    engine = get_engine()
    Base.metadata.create_all(engine)
    _ensure_email_columns(engine)
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
    return info


def _ensure_email_columns(engine: Engine) -> None:
    """Add email_* columns on older DBs created before notify shipped."""
    stmts = [
        "ALTER TABLE hazard_reports ADD COLUMN email_status VARCHAR(40)",
        "ALTER TABLE hazard_reports ADD COLUMN email_to VARCHAR(255)",
        "ALTER TABLE hazard_reports ADD COLUMN email_method VARCHAR(40)",
    ]
    with engine.begin() as conn:
        for sql in stmts:
            try:
                conn.execute(text(sql))
            except Exception:
                pass


def ensure_db() -> dict[str, Any]:
    if not _initialized:
        return init_db()
    return {
        "url_scheme": database_url().split("://", 1)[0],
        "backend": "postgres" if is_postgres() else "sqlite",
    }


def save_ticket(
    ticket: DispatchTicket,
    location: str,
    *,
    latitude: float | None = None,
    longitude: float | None = None,
    source: str = "live",
) -> int:
    ensure_db()
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
    )
    with session_scope() as session:
        session.add(row)
        session.flush()
        return int(row.id)


def recent_tickets(limit: int = 25) -> list[dict[str, Any]]:
    ensure_db()
    with session_scope() as session:
        rows = session.scalars(
            select(HazardReport).order_by(desc(HazardReport.created_at)).limit(limit)
        ).all()
        return [
            {
                "id": r.id,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "location": r.location,
                "hazard_type": r.hazard_type,
                "severity": r.severity,
                "agency": r.agency,
                "priority": r.priority,
                "confidence": r.confidence,
                "latitude": r.latitude,
                "longitude": r.longitude,
                "source": r.source,
                "email_status": r.email_status,
                "email_to": r.email_to,
                "email_method": r.email_method,
            }
            for r in rows
        ]


def mark_email_sent(
    report_id: int,
    *,
    to_address: str,
    method: str,
    status: str = "sent_mock",
) -> None:
    ensure_db()
    with session_scope() as session:
        row = session.get(HazardReport, report_id)
        if row is None:
            raise ValueError(f"No report #{report_id}")
        row.email_status = status
        row.email_to = to_address
        row.email_method = method


def severity_by_hour(hours: int = 48) -> list[dict[str, Any]]:
    """
    Aggregate counts by hour + severity.
    Uses Tiger Data time_bucket when available; falls back to date_trunc / Python.
    """
    ensure_db()
    engine = get_engine()

    if is_postgres():
        # Prefer Timescale time_bucket; fall back to date_trunc
        queries = [
            """
            SELECT time_bucket('1 hour', created_at) AS bucket,
                   severity,
                   COUNT(*)::int AS n
            FROM hazard_reports
            WHERE created_at >= NOW() - make_interval(hours => :hours)
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

    # SQLite / generic fallback
    with session_scope() as session:
        rows = session.scalars(
            select(HazardReport).order_by(HazardReport.created_at)
        ).all()
        buckets: dict[tuple[str, str], int] = {}
        for r in rows:
            if not r.created_at:
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
            count = session.scalar(select(func.count()).select_from(HazardReport)) or 0
        info["ok"] = True
        info["report_count"] = int(count)
        # Redact password if present in URL display
        raw = database_url()
        if "@" in raw:
            info["database"] = raw.split("@", 1)[-1]
        else:
            info["database"] = raw
        return info
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc), "database": database_url().split("://", 1)[0]}
