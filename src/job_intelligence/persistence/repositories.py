"""Repositories: the only place that touches ORM sessions directly.

Idempotent upsert: re-running the same job never duplicates a row (unique
`(company_id, source_job_id)`), and a snapshot is only appended when the
content hash actually changes — never on an UNCHANGED re-crawl.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..domain.enums import JobChangeType
from ..domain.models import NormalizedJob
from . import orm_models as m


class CompanyRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def ensure(self, code: str, name: str, career_site_url: str) -> m.Company:
        existing = self._session.scalar(select(m.Company).where(m.Company.code == code))
        if existing is not None:
            return existing
        company = m.Company(code=code, name=name, career_site_url=career_site_url)
        self._session.add(company)
        self._session.flush()
        return company


class JobRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, company_id: int, source_job_id: str) -> m.Job | None:
        return self._session.scalar(
            select(m.Job).where(
                m.Job.company_id == company_id, m.Job.source_job_id == source_job_id
            )
        )

    def upsert(
        self, normalized: NormalizedJob, company: m.Company, ingestion_run_id: int | None = None
    ) -> tuple[m.Job, JobChangeType]:
        now = datetime.utcnow()
        existing = self.get(company.id, normalized.source_job_id)
        primary = normalized.primary_location

        if existing is None:
            job = m.Job(
                company_id=company.id,
                source_job_id=normalized.source_job_id,
                canonical_key=normalized.canonical_key,
                key_source=normalized.key_source.value,
                title=normalized.title,
                normalized_title=normalized.normalized_title,
                role_family=normalized.role_family,
                role_subfamily=normalized.role_subfamily,
                classification_confidence=normalized.classification_confidence,
                employment_type=normalized.employment_type,
                experience_level=normalized.experience_level,
                business_unit=normalized.business_unit,
                department=normalized.department,
                location_text=primary.location_text if primary else None,
                city=primary.city if primary else None,
                state=primary.state if primary else None,
                country=primary.country if primary else None,
                workplace_type=normalized.workplace_type.value,
                salary_min=normalized.salary_min,
                salary_max=normalized.salary_max,
                salary_currency=normalized.salary_currency,
                salary_period=normalized.salary_period,
                description_text=normalized.description_text,
                qualifications_text=normalized.qualifications_text,
                responsibilities_text=normalized.responsibilities_text,
                posting_url=normalized.posting_url,
                source_posted_at=normalized.source_posted_at,
                first_seen_at=now,
                last_seen_at=now,
                is_active=True,
                missed_crawls=0,
                content_hash=normalized.content_hash,
                raw_payload_json=normalized.raw_payload,
                data_source=normalized.data_source.value,
            )
            self._session.add(job)
            self._session.flush()
            self._add_locations(job, normalized)
            self._add_snapshot(job, normalized, ingestion_run_id, JobChangeType.NEW)
            return job, JobChangeType.NEW

        change_type = (
            JobChangeType.UNCHANGED
            if existing.content_hash == normalized.content_hash
            else JobChangeType.UPDATED
        )
        was_closed = not existing.is_active

        existing.title = normalized.title
        existing.employment_type = normalized.employment_type
        existing.business_unit = normalized.business_unit
        existing.location_text = primary.location_text if primary else existing.location_text
        existing.city = primary.city if primary else existing.city
        existing.state = primary.state if primary else existing.state
        existing.country = primary.country if primary else existing.country
        existing.workplace_type = normalized.workplace_type.value
        existing.description_text = normalized.description_text
        existing.posting_url = normalized.posting_url
        existing.source_posted_at = normalized.source_posted_at
        existing.last_seen_at = now
        existing.is_active = True
        existing.missed_crawls = 0
        existing.content_hash = normalized.content_hash
        existing.raw_payload_json = normalized.raw_payload

        if was_closed:
            existing.closed_at = None
            change_type = JobChangeType.REOPENED

        if change_type in (JobChangeType.UPDATED, JobChangeType.REOPENED):
            self._replace_locations(existing, normalized)
            self._add_snapshot(existing, normalized, ingestion_run_id, change_type)

        return existing, change_type

    def _add_locations(self, job: m.Job, normalized: NormalizedJob) -> None:
        for loc in normalized.locations:
            self._session.add(
                m.JobLocation(
                    job_id=job.id,
                    location_text=loc.location_text,
                    city=loc.city,
                    state=loc.state,
                    country=loc.country,
                    is_primary=loc.is_primary,
                )
            )

    def _replace_locations(self, job: m.Job, normalized: NormalizedJob) -> None:
        for loc in list(job.locations):
            self._session.delete(loc)
        self._session.flush()
        self._add_locations(job, normalized)

    def _add_snapshot(
        self,
        job: m.Job,
        normalized: NormalizedJob,
        ingestion_run_id: int | None,
        change_type: JobChangeType,
    ) -> None:
        self._session.add(
            m.JobSnapshot(
                job_id=job.id,
                ingestion_run_id=ingestion_run_id,
                title=normalized.title,
                location_text=normalized.primary_location.location_text
                if normalized.primary_location
                else None,
                description_text=normalized.description_text,
                content_hash=normalized.content_hash,
                change_type=change_type.value,
            )
        )
