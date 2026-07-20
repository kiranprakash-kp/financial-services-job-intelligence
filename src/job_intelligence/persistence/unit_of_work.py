"""Unit of work: one transactional scope exposing all repositories together."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from sqlalchemy.orm import Session

from .database import session_scope
from .repositories import CompanyRepository, JobRepository


@dataclass(slots=True)
class UnitOfWork:
    session: Session
    companies: CompanyRepository
    jobs: JobRepository


@contextmanager
def unit_of_work() -> Iterator[UnitOfWork]:
    with session_scope() as session:
        yield UnitOfWork(
            session=session,
            companies=CompanyRepository(session),
            jobs=JobRepository(session),
        )
