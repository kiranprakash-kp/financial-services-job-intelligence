"""Analytics metrics and the deterministic narrative summary."""

from __future__ import annotations

from job_intelligence.analytics import metrics, summaries
from job_intelligence.persistence import orm_models as m
from job_intelligence.persistence.database import get_sessionmaker


def _seed(session) -> None:
    company = m.Company(code="WELLS_FARGO", name="Wells Fargo", career_site_url="https://x")
    session.add(company)
    session.flush()

    jobs = [
        m.Job(
            company_id=company.id,
            source_job_id="R-1",
            canonical_key="WELLS_FARGO:R-1",
            title="Software Engineer",
            posting_url="https://example.com/1",
            role_family="Software Engineering",
            city="Charlotte",
            is_active=True,
            content_hash="h1",
        ),
        m.Job(
            company_id=company.id,
            source_job_id="R-2",
            canonical_key="WELLS_FARGO:R-2",
            title="Backend Engineer",
            posting_url="https://example.com/2",
            role_family="Software Engineering",
            city="Charlotte",
            is_active=True,
            content_hash="h2",
        ),
        m.Job(
            company_id=company.id,
            source_job_id="R-3",
            canonical_key="WELLS_FARGO:R-3",
            title="Risk Analyst",
            posting_url="https://example.com/3",
            role_family="Risk and Compliance",
            city="Dallas",
            is_active=True,
            content_hash="h3",
        ),
        m.Job(
            company_id=company.id,
            source_job_id="R-4",
            canonical_key="WELLS_FARGO:R-4",
            title="Closed Role",
            posting_url="https://example.com/4",
            role_family="Operations",
            city="Dallas",
            is_active=False,  # must not count toward active metrics
            content_hash="h4",
        ),
    ]
    session.add_all(jobs)
    session.flush()

    python_skill = m.Skill(canonical_name="Python", category="Programming")
    session.add(python_skill)
    session.flush()
    session.add_all(
        [
            m.JobSkill(job_id=jobs[0].id, skill_id=python_skill.id, confidence=1.0),
            m.JobSkill(job_id=jobs[1].id, skill_id=python_skill.id, confidence=1.0),
        ]
    )
    session.commit()


def test_metrics_reflect_only_active_jobs(isolated_db) -> None:
    Session = get_sessionmaker()
    with Session() as session:
        _seed(session)

    assert metrics.count_active_jobs("WELLS_FARGO") == 3  # excludes the closed one

    families = metrics.top_role_families("WELLS_FARGO")
    assert families[0]["role_family"] == "Software Engineering"
    assert families[0]["count"] == 2
    assert families[0]["pct"] == round(100 * 2 / 3, 1)

    skills = metrics.top_skills("WELLS_FARGO")
    assert skills[0] == {"skill": "Python", "count": 2}

    locations = metrics.top_locations("WELLS_FARGO")
    cities = {loc["city"] for loc in locations}
    assert cities == {"Charlotte", "Dallas"}


def test_narrative_uses_only_queried_values(isolated_db) -> None:
    Session = get_sessionmaker()
    with Session() as session:
        _seed(session)

    text = summaries.company_narrative("WELLS_FARGO", "Wells Fargo")
    assert "3 observed active US openings" in text
    assert "Software Engineering" in text
    assert "Python" in text
    assert "Charlotte" in text


def test_narrative_handles_zero_active_jobs(isolated_db) -> None:
    text = summaries.company_narrative("WELLS_FARGO", "Wells Fargo")
    assert "No active US openings" in text
