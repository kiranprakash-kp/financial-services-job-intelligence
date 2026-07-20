"""CSV exports of normalized jobs and aggregated insights.

Never exports raw payloads by default — only normalized, already-public fields.
"""

from __future__ import annotations

import csv
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

from ..config import get_settings
from ..persistence import orm_models as m
from ..persistence.database import get_sessionmaker
from . import metrics

_TIMESTAMP_FMT = "%Y%m%dT%H%M%S"


def _exports_dir() -> Path:
    directory = get_settings().project_root / "data" / "exports"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _write_csv(path: Path, rows: list[dict]) -> Path:
    if not rows:
        path.write_text("", encoding="utf-8")
        return path
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return path


def export_active_jobs() -> Path:
    Session = get_sessionmaker()
    with Session() as session:
        rows = session.execute(
            select(m.Job, m.Company.code)
            .join(m.Company, m.Company.id == m.Job.company_id)
            .where(m.Job.is_active.is_(True))
        ).all()
        data = [
            {
                "company": code,
                "source_job_id": job.source_job_id,
                "title": job.title,
                "role_family": job.role_family,
                "city": job.city,
                "state": job.state,
                "country": job.country,
                "workplace_type": job.workplace_type,
                "employment_type": job.employment_type,
                "first_seen_at": job.first_seen_at,
                "source_posted_at": job.source_posted_at,
                "posting_url": job.posting_url,
            }
            for job, code in rows
        ]
    stamp = datetime.now(UTC).strftime(_TIMESTAMP_FMT)
    return _write_csv(_exports_dir() / f"active_jobs_{stamp}.csv", data)


def export_company_skill_summary() -> Path:
    rows = []
    for entry in metrics.skill_frequency_by_company(limit=20):
        for skill in entry["skills"]:
            rows.append(
                {"company": entry["company"], "skill": skill["skill"], "count": skill["count"]}
            )
    stamp = datetime.now(UTC).strftime(_TIMESTAMP_FMT)
    return _write_csv(_exports_dir() / f"company_skill_summary_{stamp}.csv", rows)


def export_monthly_role_summary() -> Path:
    Session = get_sessionmaker()
    with Session() as session:
        rows = session.execute(
            select(m.MonthlyCompanyMetrics, m.Company.code).join(
                m.Company, m.Company.id == m.MonthlyCompanyMetrics.company_id
            )
        ).all()
        data = [
            {
                "company": code,
                "year_month": row.year_month,
                "active_jobs": row.active_jobs,
                "new_jobs": row.new_jobs,
                "closed_jobs": row.closed_jobs,
                "technology_jobs": row.technology_jobs,
                "risk_jobs": row.risk_jobs,
                "operations_jobs": row.operations_jobs,
                "data_ai_jobs": row.data_ai_jobs,
                "data_source": row.data_source,
            }
            for row, code in rows
        ]
    stamp = datetime.now(UTC).strftime(_TIMESTAMP_FMT)
    return _write_csv(_exports_dir() / f"monthly_role_summary_{stamp}.csv", data)
