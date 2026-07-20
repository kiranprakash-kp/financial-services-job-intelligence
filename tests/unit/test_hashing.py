"""Content hashing: stable across cosmetic changes, sensitive to real ones."""

from __future__ import annotations

from job_intelligence.domain.enums import CompanyCode
from job_intelligence.domain.models import NormalizedJob, NormalizedLocation
from job_intelligence.processing.hashing import compute_content_hash, normalize_whitespace


def _job(**overrides) -> NormalizedJob:
    base = dict(
        company_code=CompanyCode.WELLS_FARGO,
        source_job_id="R-1",
        canonical_key="WELLS_FARGO:R-1",
        title="Software Engineer",
        posting_url="https://www.wellsfargojobs.com/en/jobs/r-1/",
        description_text="Build things with Python.",
        locations=[NormalizedLocation(location_text="Charlotte, NC", is_us=True)],
    )
    base.update(overrides)
    return NormalizedJob(**base)


def test_whitespace_normalization() -> None:
    assert normalize_whitespace("  a\n\tb   c ") == "a b c"
    assert normalize_whitespace(None) == ""


def test_hash_stable_across_whitespace_only_changes() -> None:
    a = compute_content_hash(_job(description_text="Build  things   with Python."))
    b = compute_content_hash(_job(description_text="Build things with Python."))
    assert a == b


def test_hash_changes_when_title_changes() -> None:
    a = compute_content_hash(_job(title="Software Engineer"))
    b = compute_content_hash(_job(title="Senior Software Engineer"))
    assert a != b


def test_hash_changes_when_location_changes() -> None:
    a = compute_content_hash(_job())
    b = compute_content_hash(
        _job(locations=[NormalizedLocation(location_text="Dallas, TX", is_us=True)])
    )
    assert a != b


def test_hash_ignores_location_order() -> None:
    locs_a = [
        NormalizedLocation(location_text="A", is_us=True),
        NormalizedLocation(location_text="B", is_us=True),
    ]
    locs_b = list(reversed(locs_a))
    assert compute_content_hash(_job(locations=locs_a)) == compute_content_hash(
        _job(locations=locs_b)
    )
