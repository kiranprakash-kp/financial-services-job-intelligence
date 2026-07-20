"""Closure reconciliation: grace period, and never closing on a bad crawl."""

from __future__ import annotations

from job_intelligence.persistence import orm_models as m
from job_intelligence.persistence.database import get_sessionmaker
from job_intelligence.processing.lifecycle import (
    CLOSURE_GRACE_MISSES,
    is_degraded,
    reconcile_closures,
)


def test_is_degraded_thresholds() -> None:
    assert is_degraded(current_discovered=100, previous_discovered=None) is False
    assert is_degraded(current_discovered=65, previous_discovered=100) is False  # 35% drop
    assert is_degraded(current_discovered=55, previous_discovered=100) is True  # 45% drop
    assert is_degraded(current_discovered=0, previous_discovered=0) is False


def _make_company_and_job(session, source_job_id: str) -> int:
    company = m.Company(code="WELLS_FARGO", name="Wells Fargo", career_site_url="https://x")
    session.add(company)
    session.flush()
    job = m.Job(
        company_id=company.id,
        source_job_id=source_job_id,
        canonical_key=f"WELLS_FARGO:{source_job_id}",
        title="Engineer",
        posting_url="https://example.com/1",
        is_active=True,
        missed_crawls=0,
        content_hash="abc",
    )
    session.add(job)
    session.flush()
    session.commit()
    return company.id


def test_job_absent_once_increments_but_does_not_close(isolated_db) -> None:
    Session = get_sessionmaker()
    with Session() as session:
        company_id = _make_company_and_job(session, "R-1")

    closed = reconcile_closures(company_id, seen_source_job_ids=set())
    assert closed == 0

    with Session() as session:
        job = session.query(m.Job).filter_by(source_job_id="R-1").one()
        assert job.missed_crawls == 1
        assert job.is_active is True


def test_job_absent_for_grace_period_closes_and_snapshots(isolated_db) -> None:
    Session = get_sessionmaker()
    with Session() as session:
        company_id = _make_company_and_job(session, "R-2")

    for _ in range(CLOSURE_GRACE_MISSES - 1):
        assert reconcile_closures(company_id, seen_source_job_ids=set()) == 0

    closed = reconcile_closures(company_id, seen_source_job_ids=set())
    assert closed == 1

    with Session() as session:
        job = session.query(m.Job).filter_by(source_job_id="R-2").one()
        assert job.is_active is False
        assert job.closed_at is not None
        snapshots = session.query(m.JobSnapshot).filter_by(job_id=job.id).all()
        assert any(s.change_type == "CLOSED" for s in snapshots)


def test_job_present_resets_missed_crawls(isolated_db) -> None:
    Session = get_sessionmaker()
    with Session() as session:
        company_id = _make_company_and_job(session, "R-3")

    reconcile_closures(company_id, seen_source_job_ids=set())  # miss once
    reconcile_closures(company_id, seen_source_job_ids={"R-3"})  # seen again

    with Session() as session:
        job = session.query(m.Job).filter_by(source_job_id="R-3").one()
        assert job.missed_crawls == 0
        assert job.is_active is True
