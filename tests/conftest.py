"""Shared pytest fixtures."""

from __future__ import annotations

import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from job_intelligence.config import get_settings
from job_intelligence.persistence import database as db_module
from job_intelligence.persistence.orm_models import Base


@pytest.fixture
def isolated_db() -> Iterator[None]:
    """Point the persistence layer at a throwaway in-memory SQLite DB.

    Never touches the real data/app.db. Restores prior engine/sessionmaker
    state afterward so this fixture's effects don't leak between tests.
    """
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    prev_engine, prev_session = db_module._engine, db_module._Session
    db_module._engine, db_module._Session = engine, session_factory
    try:
        yield
    finally:
        db_module._engine, db_module._Session = prev_engine, prev_session
        engine.dispose()


@pytest.fixture
def isolated_file_db() -> Iterator[None]:
    """Point the persistence layer at a throwaway file-based SQLite DB.

    Unlike `isolated_db` (`:memory:`, one DB per connection), this is a real
    file on disk shared across connections — the only way to reproduce SQLite's
    single-writer locking behavior (and verify the WAL + busy_timeout fix for
    it). Goes through the real `get_engine()` code path so the actual pragmas
    apply, not a hand-rolled engine. Never touches the real data/app.db.
    """
    settings = get_settings()
    prev_url = settings.database_url
    prev_engine, prev_session = db_module._engine, db_module._Session

    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test.db"
        settings.database_url = f"sqlite:///{db_path}"
        db_module._engine, db_module._Session = None, None
        try:
            engine = db_module.get_engine()
            Base.metadata.create_all(engine)
            yield
        finally:
            if db_module._engine is not None:
                db_module._engine.dispose()
            settings.database_url = prev_url
            db_module._engine, db_module._Session = prev_engine, prev_session
