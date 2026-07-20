"""Regression test for the SQLite "database is locked" bug.

Milestone 5's whole point is running multiple companies' ingestion
concurrently. A first cut of run_company_ingestion held one DB transaction
open across the entire discover+fetch+normalize loop — including all the
network I/O — so three companies running concurrently against the same
SQLite file collided and timed out waiting for the write lock. Fixed by
(1) WAL mode + a longer busy_timeout, and (2) shrinking each transaction down
to just the write itself, opened only after network I/O for that job is done.

Uses `isolated_file_db` (a real file, not `:memory:`) because the bug is
specific to SQLite's cross-connection single-writer lock — `:memory:` is a
separate database per connection and can't reproduce it.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import respx

from job_intelligence.app.services import run_company_ingestion
from job_intelligence.config import load_companies_config

FIXTURES = Path(__file__).parent.parent / "fixtures"
WF_FEED = FIXTURES / "wells_fargo_feed_sample.xml"
GS_PAGE1 = FIXTURES / "goldman_sachs_roles_page1.json"
GS_DETAIL = FIXTURES / "goldman_sachs_role_detail_100001.html"
BNY_PAGE1 = FIXTURES / "bny_requisitions_page1.json"
BNY_DETAIL = FIXTURES / "bny_requisition_detail_900001.json"

WF_FEED_URL = load_companies_config().get("wells_fargo").settings["feed_url"]
GS_GRAPHQL_URL = load_companies_config().get("goldman_sachs").settings["graphql_url"]
_bny_cfg = load_companies_config().get("bny").settings
BNY_LIST_URL = f"{_bny_cfg['api_base']}/{_bny_cfg['requisitions_resource']}"
BNY_DETAIL_URL_900001 = f"{_bny_cfg['api_base']}/{_bny_cfg['detail_resource']}/900001"


@respx.mock
async def test_three_companies_ingest_concurrently_without_lock_errors(
    isolated_file_db,
) -> None:
    respx.get(WF_FEED_URL).mock(return_value=httpx.Response(200, text=WF_FEED.read_text()))
    respx.post(GS_GRAPHQL_URL).mock(return_value=httpx.Response(200, text=GS_PAGE1.read_text()))
    respx.get("https://higher.gs.com/roles/100001").mock(
        return_value=httpx.Response(200, text=GS_DETAIL.read_text())
    )
    respx.get(BNY_LIST_URL).mock(return_value=httpx.Response(200, text=BNY_PAGE1.read_text()))
    respx.get(BNY_DETAIL_URL_900001).mock(
        return_value=httpx.Response(200, text=BNY_DETAIL.read_text())
    )

    # This is the exact concurrency pattern JobIntelligenceIngestionWorkflow
    # uses (asyncio.gather over per-company execute_child_workflow calls).
    # GS/BNY use dev_job_limit=1 so only the one role/requisition with a
    # mocked detail response gets fetched (this test is about write-lock
    # safety under concurrency, not full adapter coverage — that's already
    # exercised in test_adapter_goldman_sachs.py / test_adapter_bny.py).
    results = await asyncio.gather(
        run_company_ingestion("wells_fargo", dev_job_limit=None),
        run_company_ingestion("goldman_sachs", dev_job_limit=1),
        run_company_ingestion("bny", dev_job_limit=1),
    )

    for result in results:
        assert result.status == "success"
    wf_result, gs_result, bny_result = results
    assert wf_result.jobs_inserted == 3
    assert gs_result.jobs_inserted == 1
    assert bny_result.jobs_inserted == 1
