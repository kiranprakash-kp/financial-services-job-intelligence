"""Synthetic demo history: creates rows, never overwrites live data, marked distinctly."""

from __future__ import annotations

from sqlalchemy import select

from job_intelligence.persistence import orm_models as m
from job_intelligence.persistence.database import get_sessionmaker
from job_intelligence.processing.synthetic_demo import generate_synthetic_history


def test_generates_rows_marked_synthetic(isolated_db) -> None:
    created = generate_synthetic_history(months=3, seed=1)
    assert created > 0

    Session = get_sessionmaker()
    with Session() as session:
        rows = session.scalars(select(m.MonthlyCompanyMetrics)).all()
        assert len(rows) == created
        assert all(r.data_source == "synthetic" for r in rows)


def test_never_overwrites_a_live_month(isolated_db) -> None:
    Session = get_sessionmaker()
    with Session() as session:
        company = m.Company(code="WELLS_FARGO", name="Wells Fargo", career_site_url="https://x")
        session.add(company)
        session.flush()
        live_row = m.MonthlyCompanyMetrics(
            company_id=company.id, year_month="2026-07", active_jobs=999, data_source="live"
        )
        session.add(live_row)
        session.commit()

    generate_synthetic_history(months=6, seed=1)

    with Session() as session:
        row = session.scalar(
            select(m.MonthlyCompanyMetrics).where(m.MonthlyCompanyMetrics.year_month == "2026-07")
        )
        assert row is not None
        assert row.data_source == "live"
        assert row.active_jobs == 999  # untouched


def test_deterministic_given_same_seed(isolated_db) -> None:
    generate_synthetic_history(months=3, seed=7)
    Session = get_sessionmaker()
    with Session() as session:
        first = {
            (r.company_id, r.year_month): r.active_jobs
            for r in session.scalars(select(m.MonthlyCompanyMetrics)).all()
        }

    generate_synthetic_history(months=3, seed=7)
    with Session() as session:
        second = {
            (r.company_id, r.year_month): r.active_jobs
            for r in session.scalars(select(m.MonthlyCompanyMetrics)).all()
        }
    assert first == second
