"""Pipeline Operations dashboard flags: catch the exact failure mode found
live -- a run interrupted mid-processing (worker killed) that quietly wrote
partial data and looked like a normal completed run.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from job_intelligence.analytics import metrics
from job_intelligence.persistence import orm_models as m
from job_intelligence.persistence.database import get_sessionmaker


def _company(session) -> m.Company:
    company = m.Company(code="WELLS_FARGO", name="Wells Fargo", career_site_url="https://x")
    session.add(company)
    session.flush()
    return company


def test_stale_running_run_is_flagged(isolated_db) -> None:
    Session = get_sessionmaker()
    with Session() as session:
        company = _company(session)
        session.add(
            m.IngestionRun(
                workflow_id="wf-stuck",
                company_id=company.id,
                trigger_type="manual",
                status="running",
                started_at=datetime.utcnow() - timedelta(hours=5),
                jobs_discovered=1001,
            )
        )
        session.commit()

    runs = metrics.recent_ingestion_runs(limit=10)
    assert len(runs) == 1
    assert "Stuck?" in runs[0]["flags"]


def test_recent_running_run_is_not_flagged(isolated_db) -> None:
    Session = get_sessionmaker()
    with Session() as session:
        company = _company(session)
        session.add(
            m.IngestionRun(
                workflow_id="wf-in-progress",
                company_id=company.id,
                trigger_type="manual",
                status="running",
                started_at=datetime.utcnow() - timedelta(minutes=5),
                jobs_discovered=100,
            )
        )
        session.commit()

    runs = metrics.recent_ingestion_runs(limit=10)
    assert runs[0]["flags"] == ""


def test_low_count_vs_previous_run_is_flagged(isolated_db) -> None:
    Session = get_sessionmaker()
    with Session() as session:
        company = _company(session)
        session.add(
            m.IngestionRun(
                workflow_id="wf-full",
                company_id=company.id,
                trigger_type="manual",
                status="success",
                started_at=datetime.utcnow() - timedelta(hours=2),
                completed_at=datetime.utcnow() - timedelta(hours=1, minutes=58),
                jobs_discovered=1502,
            )
        )
        session.add(
            m.IngestionRun(
                workflow_id="wf-partial",
                company_id=company.id,
                trigger_type="manual",
                status="success",
                started_at=datetime.utcnow() - timedelta(minutes=10),
                completed_at=datetime.utcnow() - timedelta(minutes=8),
                jobs_discovered=1001,
            )
        )
        session.commit()

    runs = metrics.recent_ingestion_runs(limit=10)
    partial_run = next(r for r in runs if r["workflow_id"] == "wf-partial")
    assert "possibly incomplete" in partial_run["flags"]

    full_run = next(r for r in runs if r["workflow_id"] == "wf-full")
    assert full_run["flags"] == ""


def test_normal_run_with_no_history_is_not_flagged(isolated_db) -> None:
    Session = get_sessionmaker()
    with Session() as session:
        company = _company(session)
        session.add(
            m.IngestionRun(
                workflow_id="wf-first-run",
                company_id=company.id,
                trigger_type="manual",
                status="success",
                started_at=datetime.utcnow() - timedelta(minutes=5),
                completed_at=datetime.utcnow() - timedelta(minutes=4),
                jobs_discovered=20,
            )
        )
        session.commit()

    runs = metrics.recent_ingestion_runs(limit=10)
    assert runs[0]["flags"] == ""
