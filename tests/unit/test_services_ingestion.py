"""Regression test for the create_ingestion_run / run_company_ingestion split.

Uses an isolated in-memory DB (never data/app.db) and the same respx-mocked
Wells Fargo feed fixture as the adapter tests — no live network.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import respx

from job_intelligence.app.services import create_ingestion_run, run_company_ingestion
from job_intelligence.config import load_companies_config
from job_intelligence.persistence import orm_models as m
from job_intelligence.persistence.database import get_sessionmaker

FIXTURE = (Path(__file__).parent.parent / "fixtures" / "wells_fargo_feed_sample.xml").read_text(
    encoding="utf-8"
)
FEED_URL = load_companies_config().get("wells_fargo").settings["feed_url"]


@respx.mock
async def test_run_company_ingestion_creates_its_own_run_when_none_given(isolated_db) -> None:
    respx.get(FEED_URL).mock(return_value=httpx.Response(200, text=FIXTURE))

    result = await run_company_ingestion("wells_fargo", dev_job_limit=None)

    assert result.status == "success"
    assert result.jobs_inserted == 3  # 3 US, valid jobs in the fixture

    Session = get_sessionmaker()
    with Session() as session:
        run_row = session.query(m.IngestionRun).one()
        assert run_row.status == "success"
        assert run_row.jobs_inserted == 3
        assert run_row.completed_at is not None


@respx.mock
async def test_run_company_ingestion_uses_precreated_run_record(isolated_db) -> None:
    respx.get(FEED_URL).mock(return_value=httpx.Response(200, text=FIXTURE))

    run_id = create_ingestion_run("wells_fargo", workflow_id="wf-test-123", trigger_type="schedule")
    result = await run_company_ingestion(
        "wells_fargo", dev_job_limit=None, ingestion_run_id=run_id, workflow_id="wf-test-123"
    )

    assert result.jobs_inserted == 3

    Session = get_sessionmaker()
    with Session() as session:
        run_row = session.get(m.IngestionRun, run_id)
        assert run_row is not None
        assert run_row.workflow_id == "wf-test-123"
        assert run_row.trigger_type == "schedule"
        assert run_row.status == "success"


@respx.mock
async def test_rerun_is_idempotent_and_creates_second_run_record(isolated_db) -> None:
    respx.get(FEED_URL).mock(return_value=httpx.Response(200, text=FIXTURE))

    first = await run_company_ingestion("wells_fargo", dev_job_limit=None)
    second = await run_company_ingestion("wells_fargo", dev_job_limit=None)

    assert first.jobs_inserted == 3
    assert second.jobs_inserted == 0
    assert second.jobs_unchanged == 3

    Session = get_sessionmaker()
    with Session() as session:
        assert session.query(m.Job).count() == 3  # no duplicates
        assert session.query(m.IngestionRun).count() == 2  # one row per run
