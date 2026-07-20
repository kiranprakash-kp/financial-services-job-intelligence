"""Ask the Data: a safe, fixed catalog of parameterized questions.

Deliberately NOT a free-form SQL agent (the spec forbids one for this POC).
Each question maps to a specific, already-tested analytics function. The
analytics result is always the source of truth; no statistic is ever invented.
An LLM could optionally rephrase the deterministic answer later, but every
question here already has one without needing an LLM or API key.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from . import metrics, summaries


@dataclass(slots=True)
class Question:
    key: str
    template: str  # human-readable, with {company} placeholder
    run: Callable[[str], str]


def _top_skills_answer(company_code: str) -> str:
    company_name = next(
        (c["name"] for c in metrics.list_companies() if c["code"] == company_code), company_code
    )
    groups = metrics.top_skills_by_group(company_code, limit=5)
    technical, domain = groups["technical"], groups["domain"]
    if not technical and not domain:
        return f"No skill data recorded yet for {company_name}."

    parts = [f"Top skills for {company_name}:"]
    if technical:
        names = ", ".join(f"{s['skill']} ({s['count']})" for s in technical)
        parts.append(f"technical skills — {names}.")
    if domain:
        names = ", ".join(f"{s['skill']} ({s['count']})" for s in domain)
        parts.append(f"domain and process areas — {names}.")
    return " ".join(parts)


def _top_role_families_answer(company_code: str) -> str:
    company_name = next(
        (c["name"] for c in metrics.list_companies() if c["code"] == company_code), company_code
    )
    families = metrics.top_role_families(company_code, limit=5)
    if not families:
        return f"No role classification data recorded yet for {company_name}."
    names = ", ".join(f"{f['role_family']} ({f['pct']}%)" for f in families)
    return f"Top role families for {company_name}: {names}."


def _new_jobs_this_month_answer(company_code: str) -> str:
    company_name = next(
        (c["name"] for c in metrics.list_companies() if c["code"] == company_code), company_code
    )
    count = metrics.snapshot_change_count_this_month("NEW", company_code)
    return f"{company_name} had {count} newly opened US roles observed this month."


def _recruiting_focus_answer(company_code: str) -> str:
    return summaries.company_narrative(
        company_code,
        next(
            (c["name"] for c in metrics.list_companies() if c["code"] == company_code),
            company_code,
        ),
    )


def _common_skills_answer(_company_code: str) -> str:
    result = metrics.common_vs_specific_skills()
    common = result["common"]
    if not common:
        return "No skill is currently observed across every active company."
    return f"Skills observed across all companies: {', '.join(common)}."


QUESTIONS: list[Question] = [
    Question("top_skills", "What are the top skills for {company}?", _top_skills_answer),
    Question(
        "top_role_families",
        "Which role families are largest at {company}?",
        _top_role_families_answer,
    ),
    Question(
        "new_jobs_this_month",
        "What jobs were newly opened for {company} this month?",
        _new_jobs_this_month_answer,
    ),
    Question(
        "recruiting_focus",
        "What recruiting areas should be reviewed for {company}?",
        _recruiting_focus_answer,
    ),
    Question("common_skills", "Which skills occur across all companies?", _common_skills_answer),
]


def answer(question_key: str, company_code: str) -> str:
    for question in QUESTIONS:
        if question.key == question_key:
            return question.run(company_code)
    raise ValueError(f"Unknown question: {question_key!r}")
