"""Shared pytest fixtures."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

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
