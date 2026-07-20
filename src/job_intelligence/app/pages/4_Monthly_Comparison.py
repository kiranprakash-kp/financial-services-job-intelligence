"""Monthly Comparison — pick two periods, see the delta.

Requires monthly_company_metrics rows to compare. If your live history is too
short, seed synthetic demo history: `job-intel seed-demo`. Synthetic rows are
always visibly labeled — never mixed silently with live data.
"""

from __future__ import annotations

import streamlit as st

from job_intelligence.analytics import metrics, monthly_metrics

st.set_page_config(page_title="Monthly Comparison", layout="wide")
st.title("Monthly Comparison")

companies = metrics.list_companies()
if not companies:
    st.warning("No companies found. Run an ingestion first.")
    st.stop()

names = {c["name"]: c["code"] for c in companies}
selected_name = st.selectbox("Company", list(names.keys()))
company_code = names[selected_name]

periods = monthly_metrics.list_available_periods(company_code)
if len(periods) < 2:
    st.info(
        "Fewer than two periods of history are available for this company. "
        "Run `job-intel seed-demo` to backfill synthetic demo history, or wait "
        "for more monthly ingestion runs to accumulate."
    )
    st.stop()

col1, col2 = st.columns(2)
with col1:
    period_a = st.selectbox("Period A (earlier)", periods, index=0)
with col2:
    period_b = st.selectbox("Period B (later)", periods, index=len(periods) - 1)

data_a = monthly_metrics.get_monthly_metrics(company_code, period_a)
data_b = monthly_metrics.get_monthly_metrics(company_code, period_b)

if not data_a or not data_b:
    st.warning("Could not load metrics for one of the selected periods.")
    st.stop()


def _source_badge(data: dict) -> str:
    return "🟢 LIVE" if data["data_source"] == "live" else "🟡 SYNTHETIC DEMO DATA"


st.caption(f"{period_a}: {_source_badge(data_a)}  ·  {period_b}: {_source_badge(data_b)}")

col1, col2, col3, col4 = st.columns(4)
col1.metric("Active jobs", data_b["active_jobs"], data_b["active_jobs"] - data_a["active_jobs"])
col2.metric("New roles", data_b["new_jobs"], data_b["new_jobs"] - data_a["new_jobs"])
col3.metric("Closed roles", data_b["closed_jobs"], data_b["closed_jobs"] - data_a["closed_jobs"])
col4.metric(
    "Net change",
    data_b["active_jobs"] - data_a["active_jobs"],
)

st.subheader("Role-family change")
st.bar_chart(
    {
        "Technology": [data_a["technology_jobs"], data_b["technology_jobs"]],
        "Risk": [data_a["risk_jobs"], data_b["risk_jobs"]],
        "Operations": [data_a["operations_jobs"], data_b["operations_jobs"]],
        "Data and AI": [data_a["data_ai_jobs"], data_b["data_ai_jobs"]],
    }
)

col1, col2 = st.columns(2)
with col1:
    st.subheader(f"Top skills — {period_a}")
    st.write(", ".join(data_a["top_skills"]) or "None recorded.")
    st.subheader(f"Top skills — {period_b}")
    st.write(", ".join(data_b["top_skills"]) or "None recorded.")
with col2:
    st.subheader(f"Top locations — {period_a}")
    st.write(", ".join(data_a["top_locations"]) or "None recorded.")
    st.subheader(f"Top locations — {period_b}")
    st.write(", ".join(data_b["top_locations"]) or "None recorded.")
