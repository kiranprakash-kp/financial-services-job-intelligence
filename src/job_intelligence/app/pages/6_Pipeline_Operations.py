"""Pipeline Operations — recent Temporal ingestion runs and a manual refresh.

The refresh button triggers a Temporal workflow through the application
service layer (temporal/schedules.py) — it never calls a scraper directly.
Requires `docker compose up -d` and a running `job-intel temporal-worker`.
"""

from __future__ import annotations

import asyncio

import pandas as pd
import streamlit as st

from job_intelligence.analytics import metrics

st.set_page_config(page_title="Pipeline Operations", layout="wide")
st.title("Pipeline Operations")

if st.button("Trigger manual refresh (all companies, dev limit 20)"):
    try:
        from job_intelligence.temporal.schedules import run_once

        workflow_id = asyncio.run(run_once(dev_job_limit=20, triggered_by="streamlit-manual"))
        st.success(
            f"Started workflow {workflow_id!r}. Refresh this page shortly to see its "
            "progress — requires Temporal running (`docker compose up -d`) and a "
            "worker (`job-intel temporal-worker`)."
        )
    except Exception as exc:
        st.error(f"Could not start the workflow: {exc}")

st.divider()
st.subheader("Recent ingestion runs")
runs = metrics.recent_ingestion_runs(limit=30)
if runs:
    flagged = [r for r in runs if r["flags"]]
    if flagged:
        st.warning(
            f"⚠️ {len(flagged)} run(s) below look suspicious — see the **flags** "
            "column for why (e.g. stuck at 'running', or a job count much lower "
            "than a previous run for that company)."
        )
    st.dataframe(pd.DataFrame(runs), width="stretch")
else:
    st.info("No ingestion runs recorded yet.")

st.divider()
st.subheader("Last successful run per company")
for company in metrics.list_companies():
    last = metrics.last_successful_run(company["code"])
    if last:
        st.write(
            f"**{company['name']}** — {last['completed_at']} · "
            f"inserted {last['jobs_inserted']}, updated {last['jobs_updated']}, "
            f"closed {last['jobs_closed']}"
        )
    else:
        st.write(f"**{company['name']}** — no successful run yet.")

st.caption("Full workflow history and retry detail are in the Temporal UI (http://localhost:8080).")
