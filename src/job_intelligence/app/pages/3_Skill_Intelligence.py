"""Skill Intelligence — frequency by company, and common vs. company-specific skills."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from job_intelligence.analytics import metrics

st.set_page_config(page_title="Skill Intelligence", layout="wide")
st.title("Skill Intelligence")

st.subheader("Skill frequency by company")
by_company = metrics.skill_frequency_by_company(limit=10)
if by_company:
    rows = [
        {"company": entry["company"], "skill": s["skill"], "count": s["count"]}
        for entry in by_company
        for s in entry["skills"]
    ]
    pivot = pd.DataFrame(rows).pivot_table(
        index="skill", columns="company", values="count", fill_value=0
    )
    st.dataframe(pivot, width='stretch')
else:
    st.info("No skill data recorded yet.")

st.divider()
st.subheader("Common vs. company-specific skills")
result = metrics.common_vs_specific_skills()
col1, col2 = st.columns(2)
with col1:
    st.markdown("**Common across every active company**")
    st.write(", ".join(result["common"]) or "None yet.")
with col2:
    st.markdown("**Only at one company**")
    st.write(", ".join(result["company_specific"]) or "None yet.")

st.caption(
    "Skill extraction is deterministic taxonomy/alias matching (config/skills.yml) — "
    "no LLM is used. It can under- or over-match; see docs/limitations.md."
)
