"""Executive Overview — the Streamlit entry point.

The UI never scrapes directly: every number here comes from analytics/metrics.py
querying the database that Temporal/CLI ingestion already populated.
"""

from __future__ import annotations

import streamlit as st

from job_intelligence.analytics import metrics

st.set_page_config(page_title="FS Job Intelligence — Executive Overview", layout="wide")

st.title("Financial Services Client Job Intelligence")
st.caption(
    "POC — public US job postings from Wells Fargo, Goldman Sachs, and BNY career sites. "
    "Decision-support only; see docs/limitations.md."
)

companies = metrics.list_companies()

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total active US jobs", metrics.total_active_jobs())
col2.metric("New this month", metrics.snapshot_change_count_this_month("NEW"))
col3.metric("Closed this month", metrics.snapshot_change_count_this_month("CLOSED"))
col4.metric("Companies tracked", len(companies))

st.divider()

last_run = metrics.last_successful_run()
if last_run:
    st.caption(
        f"Last successful refresh: {last_run['completed_at']} · "
        f"discovered {last_run['jobs_discovered']}, inserted {last_run['jobs_inserted']}, "
        f"updated {last_run['jobs_updated']}, closed {last_run['jobs_closed']}"
    )
else:
    st.warning(
        "No successful ingestion run recorded yet. Run `job-intel scrape --company all` "
        "or trigger the Temporal workflow, then refresh this page."
    )

left, right = st.columns(2)

with left:
    st.subheader("Most in-demand role families")
    families: dict[str, dict[str, float]] = {}
    for c in companies:
        for f in metrics.top_role_families(c["code"], limit=5):
            entry = families.setdefault(f["role_family"], {"count": 0})
            entry["count"] += f["count"]
    if families:
        ranked = sorted(families.items(), key=lambda kv: kv[1]["count"], reverse=True)[:8]
        st.bar_chart({name: data["count"] for name, data in ranked})
    else:
        st.info("No role classification data yet.")

with right:
    st.subheader("Most in-demand skills")
    technical_skills: dict[str, int] = {}
    domain_skills: dict[str, int] = {}
    for c in companies:
        groups = metrics.top_skills_by_group(c["code"], limit=10)
        for s in groups["technical"]:
            technical_skills[s["skill"]] = technical_skills.get(s["skill"], 0) + s["count"]
        for s in groups["domain"]:
            domain_skills[s["skill"]] = domain_skills.get(s["skill"], 0) + s["count"]
    if technical_skills:
        st.caption("Technical skills (Python, AWS, SQL, ...)")
        ranked = dict(sorted(technical_skills.items(), key=lambda kv: kv[1], reverse=True)[:8])
        st.bar_chart(ranked)
    if domain_skills:
        st.caption("Domain and process areas (Payments, Risk Management, Agile, ...)")
        ranked_domain = dict(sorted(domain_skills.items(), key=lambda kv: kv[1], reverse=True)[:8])
        st.bar_chart(ranked_domain)
    if not technical_skills and not domain_skills:
        st.info("No skill data yet.")

st.subheader("Top US locations")
locations: dict[str, int] = {}
for c in companies:
    for loc in metrics.top_locations(c["code"], limit=10):
        if loc["city"]:
            locations[loc["city"]] = locations.get(loc["city"], 0) + loc["count"]
if locations:
    ranked_locations = dict(sorted(locations.items(), key=lambda kv: kv[1], reverse=True)[:10])
    st.bar_chart(ranked_locations)
else:
    st.info("No location data yet.")

st.divider()
st.caption(
    "Data-quality status: a run is marked DEGRADED (and closure reconciliation is "
    "skipped) if the discovered job count drops more than 40% vs. the last "
    "successful run. See the Pipeline Operations page for run-level detail."
)
