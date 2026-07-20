"""Deterministic, taxonomy-based skill extraction (config/skills.yml).

Word-boundary matching avoids the classic false positives: "Go" must not match
"going", and "SQL" must not match inside "MySQL"/"PostgreSQL" (those are their
own canonical entries). No LLM is used or required.
"""

from __future__ import annotations

import re
from typing import Protocol

from ..config import load_yaml_config
from ..domain.models import ExtractedSkill, NormalizedJob

_CONTEXT_CHARS = 40


class SkillExtractor(Protocol):
    def extract(self, job: NormalizedJob) -> list[ExtractedSkill]: ...


class TaxonomySkillExtractor:
    def __init__(self) -> None:
        taxonomy = load_yaml_config("skills.yml")
        self._entries: list[tuple[re.Pattern[str], str, str]] = []
        for category, skills in taxonomy.items():
            for canonical, meta in (skills or {}).items():
                names = [canonical, *((meta or {}).get("aliases") or [])]
                for name in names:
                    pattern = re.compile(rf"(?<!\w){re.escape(name)}(?!\w)", re.IGNORECASE)
                    self._entries.append((pattern, canonical, category))

    def extract(self, job: NormalizedJob) -> list[ExtractedSkill]:
        fields = [
            job.title,
            job.description_text,
            job.qualifications_text,
            job.responsibilities_text,
        ]
        text = " ".join(filter(None, fields))
        if not text:
            return []

        found: dict[str, ExtractedSkill] = {}
        for pattern, canonical, category in self._entries:
            if canonical in found:
                continue
            match = pattern.search(text)
            if not match:
                continue
            start = max(0, match.start() - _CONTEXT_CHARS)
            end = min(len(text), match.end() + _CONTEXT_CHARS)
            found[canonical] = ExtractedSkill(
                canonical_name=canonical,
                category=category,
                source="taxonomy",
                confidence=1.0,
                evidence_text=text[start:end].strip(),
            )
        return list(found.values())
