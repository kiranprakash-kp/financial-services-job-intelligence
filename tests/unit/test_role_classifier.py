"""Rule-based role classification — title-weighted keyword matching."""

from __future__ import annotations

from job_intelligence.domain.enums import CompanyCode
from job_intelligence.domain.models import NormalizedJob
from job_intelligence.processing.role_classifier import FALLBACK_FAMILY, RuleBasedRoleClassifier


def _job(title: str, description: str = "") -> NormalizedJob:
    return NormalizedJob(
        company_code=CompanyCode.WELLS_FARGO,
        source_job_id="R-1",
        canonical_key="WELLS_FARGO:R-1",
        title=title,
        posting_url="https://example.com/1",
        description_text=description,
    )


def test_title_match_classifies_software_engineering() -> None:
    classifier = RuleBasedRoleClassifier()
    result = classifier.classify(_job("Senior Software Engineer", "Work with Python and AWS."))
    assert result.role_family == "Software Engineering"
    assert result.confidence > 0
    assert result.matched_evidence


def test_aml_kyc_classifies_risk_and_compliance_with_subfamily() -> None:
    classifier = RuleBasedRoleClassifier()
    result = classifier.classify(_job("AML Compliance Analyst", "Investigate KYC alerts."))
    assert result.role_family == "Risk and Compliance"
    assert result.role_subfamily == "Financial Crime"


def test_title_weighted_over_description() -> None:
    classifier = RuleBasedRoleClassifier()
    # Title says Business Analyst; description mentions "audit" once — title
    # keyword weight (2x) should still win over a single description hit.
    result = classifier.classify(_job("Business Analyst", "Supports the annual audit process."))
    assert result.role_family == "Business Analysis"


def test_no_matching_keywords_falls_back_to_other() -> None:
    classifier = RuleBasedRoleClassifier()
    result = classifier.classify(_job("Mystery Role Title", ""))
    assert result.role_family == FALLBACK_FAMILY
    assert result.confidence == 0.0
    assert result.matched_evidence == []
