"""Company Intelligence — pick one company, see its dashboard."""

from __future__ import annotations

import streamlit as st

from job_intelligence.analytics import metrics, summaries

st.set_page_config(page_title="Company Intelligence", layout="wide")
st.title("Company Intelligence")

companies = metrics.list_companies()
if not companies:
    st.warning("No companies found. Run an ingestion first.")
    st.stop()

names = {c["name"]: c["code"] for c in companies}
selected_name = st.selectbox("Company", list(names.keys())) or next(iter(names))
company_code = names[selected_name]

st.metric("Active US jobs", metrics.count_active_jobs(company_code))

col1, col2 = st.columns(2)
with col1:
    st.subheader("Top role families")
    families = metrics.top_role_families(company_code, limit=8)
    if families:
        st.bar_chart({f["role_family"]: f["count"] for f in families})
    else:
        st.info("No role classification data yet for this company.")

with col2:
    st.subheader("Top skills")
    skill_groups = metrics.top_skills_by_group(company_code, limit=8)
    technical, domain = skill_groups["technical"], skill_groups["domain"]
    if technical:
        st.caption("Technical skills (Python, AWS, SQL, ...)")
        st.bar_chart({s["skill"]: s["count"] for s in technical})
    if domain:
        st.caption("Domain and process areas (Payments, Risk Management, Agile, ...)")
        st.bar_chart({s["skill"]: s["count"] for s in domain})
    if not technical and not domain:
        st.info("No skill data yet for this company.")

st.subheader("Top locations")
locations = metrics.top_locations(company_code, limit=8)
if locations:
    st.bar_chart({loc["city"]: loc["count"] for loc in locations if loc["city"]})
else:
    st.info("No location data yet for this company.")

st.divider()
st.subheader("Narrative summary")
st.caption("Deterministic — every figure below comes from a database query, not a model.")
st.write(summaries.company_narrative(company_code, selected_name))
