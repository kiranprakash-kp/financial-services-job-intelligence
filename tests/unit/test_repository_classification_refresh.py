"""Regression test: role classification and skill fields must be refreshed on
re-processing an *existing* job, not only set when a job is first inserted.

This reproduces the real scenario that surfaced the bug: jobs inserted before
Milestone 6 added skills/role classification had role_family=None forever,
because upsert()'s existing-job branch only copied title/location/description
fields onto the row — never role_family/role_subfamily/classification_confidence.
Content hash does not include role_family, so a re-run correctly reports
UNCHANGED, but the classification fields must still update.
"""

from __future__ import annotations

from job_intelligence.domain.enums import CompanyCode, JobChangeType, KeySource
from job_intelligence.domain.models import NormalizedJob
from job_intelligence.persistence.database import get_sessionmaker
from job_intelligence.persistence.repositories import CompanyRepository, JobRepository


def _job(**overrides) -> NormalizedJob:
    base = dict(
        company_code=CompanyCode.WELLS_FARGO,
        source_job_id="R-1",
        canonical_key="WELLS_FARGO:R-1",
        key_source=KeySource.SOURCE_ID,
        title="Software Engineer",
        posting_url="https://example.com/1",
        description_text="Build things.",
        content_hash="stable-hash",
    )
    base.update(overrides)
    return NormalizedJob(**base)


def test_role_classification_refreshes_on_unchanged_reprocess(isolated_db) -> None:
    Session = get_sessionmaker()
    with Session() as session:
        company = CompanyRepository(session).ensure("WELLS_FARGO", "Wells Fargo", "https://x")
        repo = JobRepository(session)

        # Simulate a job inserted before role classification existed.
        job, change_type = repo.upsert(_job(role_family=None), company.id)
        session.commit()
        assert change_type == JobChangeType.NEW
        assert job.role_family is None

        # Re-processing now computes a classification. Content hash is
        # identical (role_family isn't part of the hash), so this must
        # report UNCHANGED -- but the classification fields must still land.
        job, change_type = repo.upsert(
            _job(
                role_family="Software Engineering",
                role_subfamily="Backend",
                classification_confidence=0.8,
            ),
            company.id,
        )
        session.commit()

        assert change_type == JobChangeType.UNCHANGED
        assert job.role_family == "Software Engineering"
        assert job.role_subfamily == "Backend"
        assert job.classification_confidence == 0.8
