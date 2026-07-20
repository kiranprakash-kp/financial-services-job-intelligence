"""Normalized content hashing for change detection.

Computed only from stable, meaningful fields — never timestamps or raw HTML —
after whitespace/formatting normalization, so cosmetic re-crawls don't create
spurious UPDATED transitions or duplicate snapshots.
"""

from __future__ import annotations

import hashlib
import re

from ..domain.models import NormalizedJob

_WHITESPACE = re.compile(r"\s+")
_FIELD_SEP = "\x1f"  # unit separator; extremely unlikely to appear in source text


def normalize_whitespace(text: str | None) -> str:
    if not text:
        return ""
    return _WHITESPACE.sub(" ", text).strip()


def compute_content_hash(job: NormalizedJob) -> str:
    location_texts = sorted(normalize_whitespace(loc.location_text) for loc in job.locations)
    fields = [
        normalize_whitespace(job.title),
        "|".join(location_texts),
        normalize_whitespace(job.employment_type),
        normalize_whitespace(job.business_unit),
        normalize_whitespace(job.description_text),
        normalize_whitespace(job.responsibilities_text),
        normalize_whitespace(job.qualifications_text),
        f"{job.salary_min}-{job.salary_max}-{job.salary_currency}-{job.salary_period}",
    ]
    digest_input = _FIELD_SEP.join(fields)
    return hashlib.sha256(digest_input.encode("utf-8")).hexdigest()
