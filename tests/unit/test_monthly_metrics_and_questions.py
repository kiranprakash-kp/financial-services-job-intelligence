"""Monthly metrics calculation, the Ask-the-Data question catalog, and CSV
exports (exports redirected to a tmp dir so tests never write into the real
repo's data/exports/).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from job_intelligence.analytics import exports, monthly_metrics, questions
from job_intelligence.persistence import orm_models as m
from job_intelligence.persistence.database import get_sessionmaker


def _seed(session) -> m.Company:
    company = m.Company(code="WELLS_FARGO", name="Wells Fargo", career_site_url="https://x")
    session.add(company)
    session.flush()

    active_job = m.Job(
        company_id=company.id,
        source_job_id="R-1",
        canonical_key="WELLS_FARGO:R-1",
        title="Software Engineer",
        posting_url="https://example.com/1",
        role_family="Software Engineering",
        city="Charlotte",
        is_active=True,
        content_hash="h1",
    )
    session.add(active_job)
    session.flush()

    session.add(
        m.JobSnapshot(
            job_id=active_job.id,
            captured_at=datetime(2026, 7, 5),
            title="Software Engineer",
            change_type="NEW",
            content_hash="h1",
        )
    )
    session.commit()
    return company


def test_calculate_monthly_metrics_from_real_data(isolated_db) -> None:
    Session = get_sessionmaker()
    with Session() as session:
        _seed(session)

    monthly_metrics.calculate_monthly_metrics("WELLS_FARGO", "2026-07")

    data = monthly_metrics.get_monthly_metrics("WELLS_FARGO", "2026-07")
    assert data is not None
    assert data["active_jobs"] == 1
    assert data["new_jobs"] == 1
    assert data["data_source"] == "live"


def test_questions_catalog_answers_are_traceable(isolated_db) -> None:
    Session = get_sessionmaker()
    with Session() as session:
        _seed(session)

    answer = questions.answer("top_role_families", "WELLS_FARGO")
    assert "Software Engineering" in answer

    answer = questions.answer("new_jobs_this_month", "WELLS_FARGO")
    assert "Wells Fargo" in answer


def test_export_active_jobs_writes_csv(isolated_db, monkeypatch, tmp_path) -> None:
    Session = get_sessionmaker()
    with Session() as session:
        _seed(session)

    monkeypatch.setattr(exports, "_exports_dir", lambda: tmp_path)
    path = exports.export_active_jobs()

    assert path.parent == tmp_path
    content = Path(path).read_text(encoding="utf-8")
    assert "Software Engineer" in content
    assert "WELLS_FARGO" in content
