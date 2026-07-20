"""Ask the Data — a safe catalog of parameterized questions.

Not a free-form SQL agent. Every question maps to a tested analytics function;
the analytics result is always the source of truth and no LLM is involved.
"""

from __future__ import annotations

import streamlit as st

from job_intelligence.analytics import metrics, questions

st.set_page_config(page_title="Ask the Data", layout="wide")
st.title("Ask the Data")
st.caption(
    "Deterministic template summaries built from database queries — no LLM is "
    "used or required. Every figure is traceable to a query."
)

companies = metrics.list_companies()
if not companies:
    st.warning("No companies found. Run an ingestion first.")
    st.stop()

names = {c["name"]: c["code"] for c in companies}
selected_name = st.selectbox("Company", list(names.keys()))
company_code = names[selected_name]

question_labels = {q.template.format(company=selected_name): q.key for q in questions.QUESTIONS}
chosen_label = st.selectbox("Question", list(question_labels.keys()))

if st.button("Get answer"):
    answer = questions.answer(question_labels[chosen_label], company_code)
    st.success(answer)
