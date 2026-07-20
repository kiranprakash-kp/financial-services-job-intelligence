"""Engine and session management (sync SQLAlchemy 2.x).

The DATABASE_URL drives the backend: SQLite for the POC, PostgreSQL later with no
model changes. `create_all` exists for quick local bootstrapping; Alembic owns
schema evolution.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from ..config import get_settings
from .orm_models import Base

_engine: Engine | None = None
_Session: sessionmaker[Session] | None = None


def _ensure_sqlite_dir(url: str) -> None:
    prefix = "sqlite:///"
    if url.startswith(prefix):
        db_path = Path(url[len(prefix):])
        if not db_path.is_absolute():
            db_path = get_settings().project_root / db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)


def get_engine() -> Engine:
    global _engine, _Session
    if _engine is None:
        settings = get_settings()
        _ensure_sqlite_dir(settings.database_url)
        _engine = create_engine(settings.database_url, future=True)
        if settings.database_url.startswith("sqlite"):
            # Enforce foreign keys on SQLite (off by default).
            @event.listens_for(_engine, "connect")
            def _fk_on(dbapi_conn, _rec):
                dbapi_conn.execute("PRAGMA foreign_keys=ON")

        _Session = sessionmaker(bind=_engine, expire_on_commit=False, future=True)
    return _engine


def get_sessionmaker() -> sessionmaker[Session]:
    if _Session is None:
        get_engine()
    assert _Session is not None
    return _Session


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional session: commit on success, rollback on error."""
    session = get_sessionmaker()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def create_all() -> None:
    """Create every table. Convenience for tests/local bootstrap only."""
    Base.metadata.create_all(get_engine())
