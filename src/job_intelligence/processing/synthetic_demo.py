"""Synthetic demo-data generator.

Generates several months of plausible `monthly_company_metrics` history
(`data_source="synthetic"`) so Monthly Comparison and trend views have
something to show before enough live history accumulates. Never touches a
month that already has a `data_source="live"` row — synthetic never silently
overwrites or mixes with live data. The UI must always show which rows are
LIVE vs SYNTHETIC.
"""

from __future__ import annotations

import random
from datetime import date

from sqlalchemy import select

from ..config import load_companies_config
from ..persistence import orm_models as m
from ..persistence.database import get_sessionmaker

_SAMPLE_SKILLS = ["Python", "SQL", "AWS", "Java", "Kubernetes", "Risk Management", "AML"]
_SAMPLE_LOCATIONS = ["Charlotte", "New York", "Dallas", "Pittsburgh", "Phoenix"]


def _previous_year_months(count: int, from_year_month: str | None = None) -> list[str]:
    if from_year_month:
        year, month = (int(p) for p in from_year_month.split("-"))
    else:
        today = date.today()
        year, month = today.year, today.month

    months = []
    for _ in range(count):
        months.append(f"{year:04d}-{month:02d}")
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    return list(reversed(months))


def generate_synthetic_history(months: int = 6, seed: int = 42) -> int:
    """Backfill `months` of synthetic monthly_company_metrics per active company.

    Returns the number of rows created. Deterministic given the same seed, so
    demos are reproducible.
    """
    rng = random.Random(seed)
    companies_cfg = load_companies_config()
    Session = get_sessionmaker()
    created = 0

    with Session() as session:
        for key in companies_cfg.active_keys():
            cfg = companies_cfg.get(key)
            company = session.scalar(select(m.Company).where(m.Company.code == cfg.code))
            if company is None:
                company = m.Company(
                    code=cfg.code, name=cfg.name, career_site_url=cfg.career_site_url
                )
                session.add(company)
                session.flush()

            base_active = rng.randint(150, 500)
            for year_month in _previous_year_months(months):
                existing = session.scalar(
                    select(m.MonthlyCompanyMetrics).where(
                        m.MonthlyCompanyMetrics.company_id == company.id,
                        m.MonthlyCompanyMetrics.year_month == year_month,
                    )
                )
                if existing is not None and existing.data_source == "live":
                    continue  # never overwrite real data

                drift = rng.randint(-15, 25)
                base_active = max(20, base_active + drift)
                new_jobs = max(0, rng.randint(5, 40))
                closed_jobs = max(0, rng.randint(5, 35))
                updated_jobs = rng.randint(10, 60)
                technology_jobs = int(base_active * rng.uniform(0.2, 0.35))
                risk_jobs = int(base_active * rng.uniform(0.1, 0.2))
                operations_jobs = int(base_active * rng.uniform(0.15, 0.25))
                data_ai_jobs = int(base_active * rng.uniform(0.05, 0.15))
                top_skills = rng.sample(_SAMPLE_SKILLS, k=3)
                top_locations = rng.sample(_SAMPLE_LOCATIONS, k=3)

                if existing is None:
                    existing = m.MonthlyCompanyMetrics(company_id=company.id, year_month=year_month)
                    session.add(existing)

                existing.active_jobs = base_active
                existing.new_jobs = new_jobs
                existing.closed_jobs = closed_jobs
                existing.updated_jobs = updated_jobs
                existing.technology_jobs = technology_jobs
                existing.operations_jobs = operations_jobs
                existing.risk_jobs = risk_jobs
                existing.data_ai_jobs = data_ai_jobs
                existing.top_skills_json = top_skills
                existing.top_locations_json = top_locations
                existing.data_source = "synthetic"
                created += 1

        session.commit()

    return created
