"""Metrics queries. Every function here is the single source of truth for the
number it returns — summaries.py and the future Streamlit pages both read
through these, never around them.
"""

from __future__ import annotations

from sqlalchemy import func, select

from ..persistence import orm_models as m
from ..persistence.database import get_sessionmaker


def _company_id(session, company_code: str) -> int | None:
    company = session.scalar(select(m.Company).where(m.Company.code == company_code))
    return company.id if company else None


def count_active_jobs(company_code: str) -> int:
    Session = get_sessionmaker()
    with Session() as session:
        company_id = _company_id(session, company_code)
        if company_id is None:
            return 0
        return (
            session.scalar(
                select(func.count(m.Job.id)).where(
                    m.Job.company_id == company_id, m.Job.is_active.is_(True)
                )
            )
            or 0
        )


def top_role_families(company_code: str, limit: int = 5) -> list[dict]:
    Session = get_sessionmaker()
    with Session() as session:
        company_id = _company_id(session, company_code)
        if company_id is None:
            return []
        total = count_active_jobs(company_code)
        if total == 0:
            return []
        rows = session.execute(
            select(m.Job.role_family, func.count(m.Job.id).label("cnt"))
            .where(m.Job.company_id == company_id, m.Job.is_active.is_(True))
            .group_by(m.Job.role_family)
            .order_by(func.count(m.Job.id).desc())
            .limit(limit)
        ).all()
        return [
            {
                "role_family": row.role_family or "Other",
                "count": row.cnt,
                "pct": round(100 * row.cnt / total, 1),
            }
            for row in rows
        ]


def top_skills(company_code: str, limit: int = 10) -> list[dict]:
    Session = get_sessionmaker()
    with Session() as session:
        company_id = _company_id(session, company_code)
        if company_id is None:
            return []
        rows = session.execute(
            select(m.Skill.canonical_name, func.count(m.JobSkill.job_id).label("cnt"))
            .join(m.JobSkill, m.JobSkill.skill_id == m.Skill.id)
            .join(m.Job, m.Job.id == m.JobSkill.job_id)
            .where(m.Job.company_id == company_id, m.Job.is_active.is_(True))
            .group_by(m.Skill.canonical_name)
            .order_by(func.count(m.JobSkill.job_id).desc())
            .limit(limit)
        ).all()
        return [{"skill": row.canonical_name, "count": row.cnt} for row in rows]


def top_locations(company_code: str, limit: int = 5) -> list[dict]:
    Session = get_sessionmaker()
    with Session() as session:
        company_id = _company_id(session, company_code)
        if company_id is None:
            return []
        rows = session.execute(
            select(m.Job.city, func.count(m.Job.id).label("cnt"))
            .where(
                m.Job.company_id == company_id,
                m.Job.is_active.is_(True),
                m.Job.city.is_not(None),
            )
            .group_by(m.Job.city)
            .order_by(func.count(m.Job.id).desc())
            .limit(limit)
        ).all()
        return [{"city": row.city, "count": row.cnt} for row in rows]


def counts_by_change_type(company_code: str, ingestion_run_id: int) -> dict[str, int]:
    """Snapshot change-type breakdown for one run (new/updated/unchanged/closed)."""
    Session = get_sessionmaker()
    with Session() as session:
        rows = session.execute(
            select(m.JobSnapshot.change_type, func.count(m.JobSnapshot.id))
            .where(m.JobSnapshot.ingestion_run_id == ingestion_run_id)
            .group_by(m.JobSnapshot.change_type)
        ).all()
        return {change_type: count for change_type, count in rows}
