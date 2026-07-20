"""Deterministic narrative summaries — string templates filled from
metrics.py's query results. No LLM is used or required; every number in the
sentence traces back to a database query, per the spec's "no statistic may be
invented by an LLM" requirement.

This is a lean first cut: it summarizes current active-job composition
(role families, skills, locations). Period-over-period growth and the full
recruiting-priority score (needs monthly_company_metrics populated across
several periods) are deferred to the Streamlit milestone, where synthetic
demo history gives the trend lines something to show.
"""

from __future__ import annotations

from . import metrics


def company_narrative(company_code: str, company_name: str) -> str:
    active = metrics.count_active_jobs(company_code)
    if active == 0:
        return (
            f"No active US openings are currently recorded for {company_name}. "
            "This may mean no ingestion run has completed yet, or the company "
            "has no open US roles at this time."
        )

    families = metrics.top_role_families(company_code, limit=2)
    skills = metrics.top_skills(company_code, limit=3)
    locations = metrics.top_locations(company_code, limit=3)

    sentences = [f"{company_name} has {active} observed active US openings."]

    if families:
        first = families[0]
        family_text = f"{first['role_family']} represents {first['pct']}% of openings"
        if len(families) > 1:
            second = families[1]
            family_text += f", followed by {second['role_family']} at {second['pct']}%"
        sentences.append(family_text + ".")

    if skills:
        names = ", ".join(s["skill"] for s in skills)
        sentences.append(f"{names} are the most frequently observed technical skills.")

    location_names = [loc["city"] for loc in locations if loc["city"]]
    if location_names:
        sentences.append(f"{', '.join(location_names)} are the leading locations.")

    sentences.append(
        "This is a POC Recruiting Priority Indicator data point, not a validated "
        "prediction — figures reflect currently recorded active postings only."
    )
    return " ".join(sentences)
