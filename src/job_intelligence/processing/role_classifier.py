"""Explainable, rule-based role classification (config/roles.yml).

Title keyword hits are weighted 2x over description hits — a title match is a
much stronger signal. Returns matched evidence so classifications can be
reviewed later. No LLM is used or required.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..config import load_yaml_config
from ..domain.models import NormalizedJob

_TITLE_WEIGHT = 2
_DESC_WEIGHT = 1
_CONFIDENCE_DIVISOR = 4.0  # score at/above this saturates confidence to 1.0
FALLBACK_FAMILY = "Other"


@dataclass(slots=True)
class RoleFamilyRule:
    name: str
    keywords: list[str] = field(default_factory=list)
    subfamilies: dict[str, list[str]] = field(default_factory=dict)


@dataclass(slots=True)
class ClassificationResult:
    role_family: str
    role_subfamily: str | None
    confidence: float
    matched_evidence: list[str]


class RuleBasedRoleClassifier:
    def __init__(self) -> None:
        data = load_yaml_config("roles.yml")
        self._families = [
            RoleFamilyRule(
                name=f["role_family"],
                keywords=f.get("keywords") or [],
                subfamilies=f.get("subfamilies") or {},
            )
            for f in data.get("families", [])
        ]

    def classify(self, job: NormalizedJob) -> ClassificationResult:
        title = (job.title or "").lower()
        description = (job.description_text or "").lower()

        best: RoleFamilyRule | None = None
        best_score = 0
        best_evidence: list[str] = []

        for family in self._families:
            if not family.keywords:
                continue  # the "Other" fallback has no keywords to match on
            title_hits = [kw for kw in family.keywords if kw in title]
            desc_hits = [kw for kw in family.keywords if kw in description]
            score = len(title_hits) * _TITLE_WEIGHT + len(desc_hits) * _DESC_WEIGHT
            if score > best_score:
                best_score = score
                best = family
                best_evidence = title_hits + desc_hits

        if best is None:
            return ClassificationResult(FALLBACK_FAMILY, None, 0.0, [])

        subfamily = None
        for sub_name, sub_keywords in best.subfamilies.items():
            if any(kw in title or kw in description for kw in sub_keywords):
                subfamily = sub_name
                break

        confidence = min(1.0, best_score / _CONFIDENCE_DIVISOR)
        return ClassificationResult(best.name, subfamily, confidence, best_evidence)
