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


def list_companies() -> list[dict]:
    Session = get_sessionmaker()
    with Session() as session:
        rows = session.scalars(select(m.Company).order_by(m.Company.name)).all()
        return [{"code": c.code, "name": c.name} for c in rows]


def total_active_jobs() -> int:
    Session = get_sessionmaker()
    with Session() as session:
        return session.scalar(select(func.count(m.Job.id)).where(m.Job.is_active.is_(True))) or 0


def snapshot_change_count_this_month(change_type: str, company_code: str | None = None) -> int:
    Session = get_sessionmaker()
    with Session() as session:
        conditions = [
            m.JobSnapshot.change_type == change_type,
            func.strftime("%Y-%m", m.JobSnapshot.captured_at) == func.strftime("%Y-%m", "now"),
        ]
        query = select(func.count(m.JobSnapshot.id)).join(m.Job, m.Job.id == m.JobSnapshot.job_id)
        if company_code is not None:
            company_id = _company_id(session, company_code)
            if company_id is None:
                return 0
            conditions.append(m.Job.company_id == company_id)
        return session.scalar(query.where(*conditions)) or 0


def last_successful_run(company_code: str | None = None) -> dict | None:
    Session = get_sessionmaker()
    with Session() as session:
        query = select(m.IngestionRun).where(m.IngestionRun.status == "success")
        if company_code is not None:
            company_id = _company_id(session, company_code)
            if company_id is None:
                return None
            query = query.where(m.IngestionRun.company_id == company_id)
        row = session.scalar(query.order_by(m.IngestionRun.completed_at.desc()))
        if row is None:
            return None
        return {
            "workflow_id": row.workflow_id,
            "completed_at": row.completed_at,
            "jobs_discovered": row.jobs_discovered,
            "jobs_inserted": row.jobs_inserted,
            "jobs_updated": row.jobs_updated,
            "jobs_closed": row.jobs_closed,
        }


def recent_ingestion_runs(limit: int = 20) -> list[dict]:
    Session = get_sessionmaker()
    with Session() as session:
        rows = session.execute(
            select(m.IngestionRun, m.Company.code)
            .join(m.Company, m.Company.id == m.IngestionRun.company_id, isouter=True)
            .order_by(m.IngestionRun.started_at.desc())
            .limit(limit)
        ).all()
        return [
            {
                "company": code or "unknown",
                "workflow_id": run.workflow_id,
                "status": run.status,
                "started_at": run.started_at,
                "completed_at": run.completed_at,
                "jobs_discovered": run.jobs_discovered,
                "jobs_inserted": run.jobs_inserted,
                "jobs_updated": run.jobs_updated,
                "jobs_unchanged": run.jobs_unchanged,
                "jobs_closed": run.jobs_closed,
                "jobs_failed": run.jobs_failed,
                "error_summary": run.error_summary,
            }
            for run, code in rows
        ]


def search_jobs(
    company_code: str | None = None,
    active: bool | None = True,
    role_family: str | None = None,
    skill: str | None = None,
    state: str | None = None,
    city: str | None = None,
    workplace_type: str | None = None,
    keyword: str | None = None,
    limit: int = 200,
) -> list[dict]:
    Session = get_sessionmaker()
    with Session() as session:
        query = select(m.Job, m.Company.code).join(m.Company, m.Company.id == m.Job.company_id)
        if company_code is not None:
            query = query.where(m.Company.code == company_code)
        if active is not None:
            query = query.where(m.Job.is_active.is_(active))
        if role_family is not None:
            query = query.where(m.Job.role_family == role_family)
        if state is not None:
            query = query.where(m.Job.state == state)
        if city is not None:
            query = query.where(m.Job.city == city)
        if workplace_type is not None:
            query = query.where(m.Job.workplace_type == workplace_type)
        if keyword:
            like = f"%{keyword}%"
            query = query.where(m.Job.title.ilike(like))
        if skill is not None:
            query = (
                query.join(m.JobSkill, m.JobSkill.job_id == m.Job.id)
                .join(m.Skill, m.Skill.id == m.JobSkill.skill_id)
                .where(m.Skill.canonical_name == skill)
            )

        rows = session.execute(query.order_by(m.Job.last_seen_at.desc()).limit(limit)).all()
        return [
            {
                "company": code,
                "title": job.title,
                "role_family": job.role_family,
                "city": job.city,
                "state": job.state,
                "workplace_type": job.workplace_type,
                "is_active": job.is_active,
                "first_seen_at": job.first_seen_at,
                "source_posted_at": job.source_posted_at,
                "posting_url": job.posting_url,
            }
            for job, code in rows
        ]


def skill_frequency_by_company(limit: int = 15) -> list[dict]:
    """Top skills per company, for a company x skill breakdown table."""
    Session = get_sessionmaker()
    with Session() as session:
        rows = session.execute(
            select(m.Company.code, m.Skill.canonical_name, func.count(m.JobSkill.job_id))
            .join(m.Job, m.Job.id == m.JobSkill.job_id)
            .join(m.Company, m.Company.id == m.Job.company_id)
            .join(m.Skill, m.Skill.id == m.JobSkill.skill_id)
            .where(m.Job.is_active.is_(True))
            .group_by(m.Company.code, m.Skill.canonical_name)
            .order_by(func.count(m.JobSkill.job_id).desc())
            .limit(limit * 5)
        ).all()
        by_company: dict[str, list[dict]] = {}
        for company_code, skill_name, count in rows:
            by_company.setdefault(company_code, [])
            if len(by_company[company_code]) < limit:
                by_company[company_code].append({"skill": skill_name, "count": count})
        return [{"company": code, "skills": skills} for code, skills in by_company.items()]


def common_vs_specific_skills() -> dict:
    """Skills present at every active company vs. only some of them."""
    Session = get_sessionmaker()
    with Session() as session:
        num_companies = session.scalar(select(func.count(m.Company.id))) or 0
        rows = session.execute(
            select(m.Skill.canonical_name, func.count(func.distinct(m.Job.company_id)))
            .join(m.JobSkill, m.JobSkill.skill_id == m.Skill.id)
            .join(m.Job, m.Job.id == m.JobSkill.job_id)
            .where(m.Job.is_active.is_(True))
            .group_by(m.Skill.canonical_name)
        ).all()
        common = [name for name, company_count in rows if company_count == num_companies]
        specific = [name for name, company_count in rows if company_count == 1]
        return {"common": sorted(common), "company_specific": sorted(specific)}
