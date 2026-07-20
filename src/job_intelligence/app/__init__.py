"""Application services and the Streamlit UI.

Services are the single entry point the CLI and Streamlit both call — neither
scrapes directly. Before Temporal exists (Milestone 5), services run adapters
in-process; after Milestone 5, the same functions dispatch to Temporal instead,
with no change to their callers.
"""
