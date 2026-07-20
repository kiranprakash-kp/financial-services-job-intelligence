"""Top skills split into technical vs. domain/process areas.

Found live: "Top skills for Wells Fargo: Securities, Payments, Risk
Management" reads oddly when technical skills (Python, AWS) and financial
domain/process keywords (Payments, Risk Management, Agile) are shown as one
undifferentiated "skills" list -- they're different kinds of things.
"""

from __future__ import annotations

from job_intelligence.analytics import metrics, questions
from job_intelligence.persistence import orm_models as m
from job_intelligence.persistence.database import get_sessionmaker


def _seed(session) -> None:
    company = m.Company(code="WELLS_FARGO", name="Wells Fargo", career_site_url="https://x")
    session.add(company)
    session.flush()

    job = m.Job(
        company_id=company.id,
        source_job_id="R-1",
        canonical_key="WELLS_FARGO:R-1",
        title="Risk Technology Analyst",
        posting_url="https://example.com/1",
        is_active=True,
        content_hash="h1",
    )
    session.add(job)
    session.flush()

    python_skill = m.Skill(canonical_name="Python", category="Programming")
    risk_skill = m.Skill(canonical_name="Risk Management", category="Financial-services domain")
    agile_skill = m.Skill(canonical_name="Agile", category="Enterprise and delivery")
    session.add_all([python_skill, risk_skill, agile_skill])
    session.flush()
    session.add_all(
        [
            m.JobSkill(job_id=job.id, skill_id=python_skill.id, confidence=1.0),
            m.JobSkill(job_id=job.id, skill_id=risk_skill.id, confidence=1.0),
            m.JobSkill(job_id=job.id, skill_id=agile_skill.id, confidence=1.0),
        ]
    )
    session.commit()


def test_top_skills_by_group_separates_technical_from_domain(isolated_db) -> None:
    Session = get_sessionmaker()
    with Session() as session:
        _seed(session)

    groups = metrics.top_skills_by_group("WELLS_FARGO")
    technical_names = {s["skill"] for s in groups["technical"]}
    domain_names = {s["skill"] for s in groups["domain"]}

    assert technical_names == {"Python"}
    assert domain_names == {"Risk Management", "Agile"}


def test_ask_the_data_top_skills_answer_labels_both_groups(isolated_db) -> None:
    Session = get_sessionmaker()
    with Session() as session:
        _seed(session)

    answer = questions.answer("top_skills", "WELLS_FARGO")
    assert "technical skills" in answer
    assert "Python" in answer
    assert "domain and process areas" in answer
    assert "Risk Management" in answer


def test_no_skills_yields_friendly_message(isolated_db) -> None:
    Session = get_sessionmaker()
    with Session() as session:
        session.add(m.Company(code="WELLS_FARGO", name="Wells Fargo", career_site_url="https://x"))
        session.commit()

    groups = metrics.top_skills_by_group("WELLS_FARGO")
    assert groups == {"technical": [], "domain": []}
    assert "No skill data" in questions.answer("top_skills", "WELLS_FARGO")
