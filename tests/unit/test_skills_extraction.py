"""Deterministic skill extraction — matching, aliases, and false-positive avoidance."""

from __future__ import annotations

from job_intelligence.domain.enums import CompanyCode
from job_intelligence.domain.models import NormalizedJob
from job_intelligence.processing.skills import TaxonomySkillExtractor


def _job(description: str, title: str = "Engineer") -> NormalizedJob:
    return NormalizedJob(
        company_code=CompanyCode.WELLS_FARGO,
        source_job_id="R-1",
        canonical_key="WELLS_FARGO:R-1",
        title=title,
        posting_url="https://example.com/1",
        description_text=description,
    )


def test_matches_canonical_names() -> None:
    extractor = TaxonomySkillExtractor()
    skills = extractor.extract(_job("Experience with Python, SQL, and AWS required."))
    names = {s.canonical_name for s in skills}
    assert {"Python", "SQL", "AWS"} <= names


def test_matches_aliases_to_canonical_name() -> None:
    extractor = TaxonomySkillExtractor()
    skills = extractor.extract(_job("Experience with K8s and Anti-Money Laundering controls."))
    names = {s.canonical_name for s in skills}
    assert "Kubernetes" in names
    assert "AML" in names


def test_go_does_not_match_going() -> None:
    extractor = TaxonomySkillExtractor()
    skills = extractor.extract(_job("The candidate is going to be a great fit."))
    assert "Go" not in {s.canonical_name for s in skills}


def test_sql_does_not_match_inside_mysql() -> None:
    extractor = TaxonomySkillExtractor()
    skills = extractor.extract(_job("Experience with MySQL required."))
    names = {s.canonical_name for s in skills}
    assert "MySQL" in names
    assert "SQL" not in names


def test_evidence_text_present() -> None:
    extractor = TaxonomySkillExtractor()
    [skill] = extractor.extract(_job("Strong Python skills are required for this role."))
    assert skill.evidence_text and "Python" in skill.evidence_text
    assert skill.source == "taxonomy"
    assert skill.confidence == 1.0


def test_no_text_returns_empty() -> None:
    extractor = TaxonomySkillExtractor()
    assert extractor.extract(_job("", title="Untitled")) == []
