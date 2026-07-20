"""Job Explorer — keyword search and filters over normalized jobs."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from job_intelligence.analytics import metrics

st.set_page_config(page_title="Job Explorer", layout="wide")
st.title("Job Explorer")

companies = metrics.list_companies()
company_names = {"All": None} | {c["name"]: c["code"] for c in companies}

col1, col2, col3 = st.columns(3)
with col1:
    company_choice = st.selectbox("Company", list(company_names.keys()))
with col2:
    status_choice = st.selectbox("Status", ["Active", "Closed", "All"])
with col3:
    keyword = st.text_input("Keyword (title)")

active_filter = {"Active": True, "Closed": False, "All": None}[status_choice]

results = metrics.search_jobs(
    company_code=company_names[company_choice],
    active=active_filter,
    keyword=keyword or None,
    limit=200,
)

st.caption(f"{len(results)} result(s)")
if results:
    df = pd.DataFrame(results)
    st.dataframe(
        df,
        column_config={"posting_url": st.column_config.LinkColumn("Source link")},
        width='stretch',
    )
else:
    st.info("No jobs match these filters.")
