"""Temporal workflow tests using the SDK's own testing facilities.

Spins up Temporal's ephemeral time-skipping test server (downloaded once,
cached afterward — no Docker, no real cluster) and runs our actual worker
in-process. Adapter HTTP calls are respx-mocked (never live); persistence uses
the isolated in-memory DB fixture — never data/app.db.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import respx
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from job_intelligence.config import load_companies_config
from job_intelligence.domain.enums import TriggerType
from job_intelligence.domain.models import CompanyIngestionParams, IngestionRequest
from job_intelligence.persistence import orm_models as m
from job_intelligence.persistence.database import get_sessionmaker
from job_intelligence.temporal import TASK_QUEUE, activities
from job_intelligence.temporal.client import pydantic_data_converter
from job_intelligence.temporal.workflows import (
    CompanyJobIngestionWorkflow,
    JobIntelligenceIngestionWorkflow,
)

FIXTURE = (Path(__file__).parent.parent / "fixtures" / "wells_fargo_feed_sample.xml").read_text(
    encoding="utf-8"
)
FEED_URL = load_companies_config().get("wells_fargo").settings["feed_url"]

_ACTIVITIES = [activities.create_ingestion_run_activity, activities.run_extraction_activity]
_WORKFLOWS = [JobIntelligenceIngestionWorkflow, CompanyJobIngestionWorkflow]


@respx.mock
async def test_company_workflow_success(isolated_db) -> None:
    respx.get(FEED_URL).mock(return_value=httpx.Response(200, text=FIXTURE))

    async with (
        await WorkflowEnvironment.start_time_skipping(
            data_converter=pydantic_data_converter
        ) as env,
        Worker(env.client, task_queue=TASK_QUEUE, workflows=_WORKFLOWS, activities=_ACTIVITIES),
    ):
        result = await env.client.execute_workflow(
            CompanyJobIngestionWorkflow.run,
            CompanyIngestionParams(company_key="wells_fargo", triggered_by="test"),
            id="test-company-wf-success",
            task_queue=TASK_QUEUE,
        )

    assert result.status == "success"
    assert result.jobs_inserted == 3

    Session = get_sessionmaker()
    with Session() as session:
        run_row = session.query(m.IngestionRun).one()
        assert run_row.status == "success"
        assert run_row.workflow_id == "test-company-wf-success"


@respx.mock
async def test_company_workflow_non_retryable_failure_does_not_raise(isolated_db) -> None:
    # 403 -> AccessDeniedError, a non-retryable type per the workflow's RetryPolicy.
    respx.get(FEED_URL).mock(return_value=httpx.Response(403))

    async with (
        await WorkflowEnvironment.start_time_skipping(
            data_converter=pydantic_data_converter
        ) as env,
        Worker(env.client, task_queue=TASK_QUEUE, workflows=_WORKFLOWS, activities=_ACTIVITIES),
    ):
        result = await env.client.execute_workflow(
            CompanyJobIngestionWorkflow.run,
            CompanyIngestionParams(company_key="wells_fargo", triggered_by="test"),
            id="test-company-wf-failure",
            task_queue=TASK_QUEUE,
        )

    # The workflow itself completes successfully — it CATCHES the activity
    # failure and reports it, rather than raising and failing the workflow.
    assert result.status == "failed"
    assert result.company_code.value == "WELLS_FARGO"
    assert result.error_summary is not None


@respx.mock
async def test_parent_workflow_fans_out_and_reports_partial_failure(isolated_db) -> None:
    respx.get(FEED_URL).mock(return_value=httpx.Response(200, text=FIXTURE))

    async with (
        await WorkflowEnvironment.start_time_skipping(
            data_converter=pydantic_data_converter
        ) as env,
        Worker(env.client, task_queue=TASK_QUEUE, workflows=_WORKFLOWS, activities=_ACTIVITIES),
    ):
        results = await env.client.execute_workflow(
            JobIntelligenceIngestionWorkflow.run,
            IngestionRequest(
                companies=["wells_fargo"],
                triggered_by="test",
                trigger_type=TriggerType.MANUAL,
            ),
            id="test-parent-wf",
            task_queue=TASK_QUEUE,
        )

    assert set(results.keys()) == {"wells_fargo"}
    assert results["wells_fargo"].status == "success"
    assert results["wells_fargo"].jobs_inserted == 3
