"""Materializes one month's aggregate metrics for a company from real data.

Powers Monthly Comparison. Upserts `monthly_company_metrics` with
`data_source="live"` — never touches a row a synthetic generator wrote for a
period where no live data exists yet (synthetic never silently overwrites or
mixes with live, per spec).
"""

from __future__ import annotations

from sqlalchemy import func, select

from ..persistence import orm_models as m
from ..persistence.database import get_sessionmaker
from . import metrics

# Coarse category buckets used for the monthly_company_metrics summary columns.
_TECH_FAMILIES = {"Software Engineering", "Cloud and Infrastructure", "Cybersecurity"}
_OPERATIONS_FAMILIES = {"Operations"}
_RISK_FAMILIES = {"Risk and Compliance", "Audit"}
_DATA_AI_FAMILIES = {"Data and AI"}


def calculate_monthly_metrics(company_code: str, year_month: str) -> None:
    """Compute and upsert one company's real metrics for `year_month` (YYYY-MM)."""
    Session = get_sessionmaker()
    with Session() as session:
        company = session.scalar(select(m.Company).where(m.Company.code == company_code))
        if company is None:
            return

        active_jobs = metrics.count_active_jobs(company_code)

        snapshot_rows = session.execute(
            select(m.JobSnapshot.change_type, func.count(m.JobSnapshot.id))
            .join(m.Job, m.Job.id == m.JobSnapshot.job_id)
            .where(
                m.Job.company_id == company.id,
                func.strftime("%Y-%m", m.JobSnapshot.captured_at) == year_month,
            )
            .group_by(m.JobSnapshot.change_type)
        ).all()
        counts: dict[str, int] = {change_type: count for change_type, count in snapshot_rows}
        new_jobs = counts.get("NEW", 0)
        closed_jobs = counts.get("CLOSED", 0)
        updated_jobs = counts.get("UPDATED", 0)

        families = metrics.top_role_families(company_code, limit=100)
        family_counts = {f["role_family"]: f["count"] for f in families}
        technology_jobs = sum(v for k, v in family_counts.items() if k in _TECH_FAMILIES)
        operations_jobs = sum(v for k, v in family_counts.items() if k in _OPERATIONS_FAMILIES)
        risk_jobs = sum(v for k, v in family_counts.items() if k in _RISK_FAMILIES)
        data_ai_jobs = sum(v for k, v in family_counts.items() if k in _DATA_AI_FAMILIES)

        top_skills = [s["skill"] for s in metrics.top_skills(company_code, limit=10)]
        top_locations = [loc["city"] for loc in metrics.top_locations(company_code, limit=10)]

        row = session.scalar(
            select(m.MonthlyCompanyMetrics).where(
                m.MonthlyCompanyMetrics.company_id == company.id,
                m.MonthlyCompanyMetrics.year_month == year_month,
            )
        )
        if row is None:
            row = m.MonthlyCompanyMetrics(company_id=company.id, year_month=year_month)
            session.add(row)

        row.active_jobs = active_jobs
        row.new_jobs = new_jobs
        row.closed_jobs = closed_jobs
        row.updated_jobs = updated_jobs
        row.technology_jobs = technology_jobs
        row.operations_jobs = operations_jobs
        row.risk_jobs = risk_jobs
        row.data_ai_jobs = data_ai_jobs
        row.top_skills_json = top_skills
        row.top_locations_json = top_locations
        row.data_source = "live"
        session.commit()


def list_available_periods(company_code: str) -> list[str]:
    Session = get_sessionmaker()
    with Session() as session:
        company = session.scalar(select(m.Company).where(m.Company.code == company_code))
        if company is None:
            return []
        rows = session.scalars(
            select(m.MonthlyCompanyMetrics.year_month)
            .where(m.MonthlyCompanyMetrics.company_id == company.id)
            .order_by(m.MonthlyCompanyMetrics.year_month)
        ).all()
        return list(rows)


def get_monthly_metrics(company_code: str, year_month: str) -> dict | None:
    Session = get_sessionmaker()
    with Session() as session:
        company = session.scalar(select(m.Company).where(m.Company.code == company_code))
        if company is None:
            return None
        row = session.scalar(
            select(m.MonthlyCompanyMetrics).where(
                m.MonthlyCompanyMetrics.company_id == company.id,
                m.MonthlyCompanyMetrics.year_month == year_month,
            )
        )
        if row is None:
            return None
        return {
            "year_month": row.year_month,
            "active_jobs": row.active_jobs,
            "new_jobs": row.new_jobs,
            "closed_jobs": row.closed_jobs,
            "updated_jobs": row.updated_jobs,
            "technology_jobs": row.technology_jobs,
            "operations_jobs": row.operations_jobs,
            "risk_jobs": row.risk_jobs,
            "data_ai_jobs": row.data_ai_jobs,
            "top_skills": row.top_skills_json,
            "top_locations": row.top_locations_json,
            "data_source": row.data_source,
        }
