"""Domain-model behavior at the boundaries."""

from __future__ import annotations

from job_intelligence.domain.enums import CompanyCode
from job_intelligence.domain.models import NormalizedJob, NormalizedLocation


def _job(**overrides) -> NormalizedJob:
    base = dict(
        company_code=CompanyCode.WELLS_FARGO,
        source_job_id="R-1",
        canonical_key="WELLS_FARGO:R-1",
        title="Software Engineer",
        posting_url="https://www.wellsfargojobs.com/en/jobs/r-1/",
    )
    base.update(overrides)
    return NormalizedJob(**base)


def test_primary_location_prefers_flagged_primary() -> None:
    job = _job(
        locations=[
            NormalizedLocation(location_text="London", is_us=False),
            NormalizedLocation(
                location_text="Dallas, TX",
                city="Dallas",
                state="TX",
                is_us=True,
                is_primary=True,
            ),
        ]
    )
    assert job.primary_location is not None
    assert job.primary_location.city == "Dallas"


def test_primary_location_falls_back_to_first() -> None:
    job = _job(locations=[NormalizedLocation(location_text="Remote - US", is_remote=True)])
    assert job.primary_location is not None
    assert job.primary_location.is_remote


def test_has_valid_us_location() -> None:
    us_job = _job(locations=[NormalizedLocation(location_text="NYC", is_us=True)])
    remote_job = _job(locations=[NormalizedLocation(location_text="Remote - US", is_remote=True)])
    intl_job = _job(locations=[NormalizedLocation(location_text="London", is_us=False)])

    assert us_job.has_valid_us_location
    assert remote_job.has_valid_us_location
    assert not intl_job.has_valid_us_location
    assert not _job().has_valid_us_location
