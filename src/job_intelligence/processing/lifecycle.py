"""Job lifecycle: closure reconciliation with a grace period.

A job is only ever closed after a *complete, successful* crawl — never after a
partial/dev-limited or failed one — and only after `CLOSURE_GRACE_MISSES`
consecutive crawls in which it was absent, to avoid false closures caused by a
transient source hiccup. A big sudden drop in discovered-job count (more than
`DEGRADED_DROP_THRESHOLD`) marks the run DEGRADED and skips closure entirely
until reviewed.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from ..domain.enums import JobChangeType
from ..persistence import orm_models as m
from ..persistence.unit_of_work import unit_of_work

CLOSURE_GRACE_MISSES = 2
DEGRADED_DROP_THRESHOLD = 0.4


def previous_successful_discovered_count(company_id: int, exclude_run_id: int) -> int | None:
    """The `jobs_discovered` count of the most recent prior successful run."""
    with unit_of_work() as uow:
        row = uow.session.scalars(
            select(m.IngestionRun)
            .where(
                m.IngestionRun.company_id == company_id,
                m.IngestionRun.status == "success",
                m.IngestionRun.id != exclude_run_id,
            )
            .order_by(m.IngestionRun.completed_at.desc())
        ).first()
        return row.jobs_discovered if row else None


def is_degraded(current_discovered: int, previous_discovered: int | None) -> bool:
    """True if this run's count dropped more than the threshold vs. the last success."""
    if not previous_discovered:
        return False
    drop_ratio = (previous_discovered - current_discovered) / previous_discovered
    return drop_ratio > DEGRADED_DROP_THRESHOLD


def reconcile_closures(company_id: int, seen_source_job_ids: set[str]) -> int:
    """Increment the miss counter for active jobs absent from this crawl; close
    those that have now missed `CLOSURE_GRACE_MISSES` crawls in a row. Returns
    the number of jobs closed. Callers must only invoke this after confirming
    the crawl was complete and not degraded.
    """
    closed = 0
    with unit_of_work() as uow:
        active_jobs = uow.session.scalars(
            select(m.Job).where(m.Job.company_id == company_id, m.Job.is_active.is_(True))
        ).all()
        for job in active_jobs:
            if job.source_job_id in seen_source_job_ids:
                if job.missed_crawls:
                    job.missed_crawls = 0
                continue

            job.missed_crawls += 1
            if job.missed_crawls >= CLOSURE_GRACE_MISSES:
                job.is_active = False
                job.closed_at = datetime.utcnow()
                uow.session.add(
                    m.JobSnapshot(
                        job_id=job.id,
                        ingestion_run_id=None,
                        title=job.title,
                        location_text=job.location_text,
                        description_text=job.description_text,
                        content_hash=job.content_hash,
                        change_type=JobChangeType.CLOSED.value,
                    )
                )
                closed += 1
    return closed
