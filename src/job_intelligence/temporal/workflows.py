"""Temporal workflows: deterministic orchestration only.

    JobIntelligenceIngestionWorkflow
        |-- CompanyJobIngestionWorkflow(wells_fargo)
        |-- CompanyJobIngestionWorkflow(goldman_sachs)
        +-- CompanyJobIngestionWorkflow(bny)

Every network call, database write, and Playwright operation happens inside an
Activity (activities.py) — nothing here touches I/O directly. Companies fan out
concurrently and a single company's failure never fails the others: each child
workflow catches its own activity failure and returns a `status="failed"`
CompanyRunResult instead of raising, so the parent always gets a complete
per-company picture (partial-company failure reporting).
"""

from __future__ import annotations

import asyncio
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError, ChildWorkflowError

with workflow.unsafe.imports_passed_through():
    from ..domain.enums import CompanyCode
    from ..domain.models import (
        CompanyIngestionParams,
        CompanyRunResult,
        ExtractionActivityParams,
        IngestionRequest,
    )
    from . import TASK_QUEUE, activities

# Matched against the raised exception's class name (domain/exceptions.py).
# Retryable errors (TransientSourceError, RateLimitedError) are deliberately
# absent here — they fall through to the retry policy's normal backoff.
_NON_RETRYABLE_ERROR_TYPES = [
    "AccessDeniedError",
    "ParsingError",
    "ValidationError",
    "ConfigurationError",
    "DatabaseError",
    "DisallowedDomainError",
]


@workflow.defn
class CompanyJobIngestionWorkflow:
    """Runs one company's full ingestion: create run record, then extract+persist."""

    @workflow.run
    async def run(self, params: CompanyIngestionParams) -> CompanyRunResult:
        info = workflow.info()

        run_id = await workflow.execute_activity(
            activities.create_ingestion_run_activity,
            params,
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )

        # A full run (dev_job_limit=None) fetches one detail request per job at
        # our deliberately conservative ~1 req/sec/domain rate limit -- for
        # Goldman Sachs (~1,250 jobs) or BNY (~1,700 jobs) that's 20-30+
        # minutes, all inside a single activity attempt (heartbeats prove the
        # worker is alive, but do not extend start_to_close_timeout). A dev/
        # limited run (e.g. --limit 20) finishes in seconds either way.
        is_full_run = params.dev_job_limit is None
        start_to_close = timedelta(minutes=90) if is_full_run else timedelta(minutes=10)
        schedule_to_close = timedelta(minutes=120) if is_full_run else timedelta(minutes=20)
        max_attempts = 2 if is_full_run else 4  # avoid hours of wasted re-crawls on real failures

        try:
            return await workflow.execute_activity(
                activities.run_extraction_activity,
                ExtractionActivityParams(
                    company_key=params.company_key,
                    dev_job_limit=params.dev_job_limit,
                    ingestion_run_id=run_id,
                    workflow_id=info.workflow_id,
                ),
                start_to_close_timeout=start_to_close,
                schedule_to_close_timeout=schedule_to_close,
                heartbeat_timeout=timedelta(seconds=30),
                retry_policy=RetryPolicy(
                    initial_interval=timedelta(seconds=2),
                    backoff_coefficient=2.0,
                    maximum_interval=timedelta(seconds=30),
                    maximum_attempts=max_attempts,
                    non_retryable_error_types=_NON_RETRYABLE_ERROR_TYPES,
                ),
            )
        except ActivityError as exc:
            workflow.logger.warning(f"{params.company_key} extraction failed: {exc}")
            return CompanyRunResult(
                company_code=CompanyCode(params.company_key.upper()),
                status="failed",
                error_summary=str(exc),
            )


@workflow.defn
class JobIntelligenceIngestionWorkflow:
    """Parent workflow: fans out one CompanyJobIngestionWorkflow per company."""

    @workflow.run
    async def run(self, request: IngestionRequest) -> dict[str, CompanyRunResult]:
        info = workflow.info()

        async def run_one(company_key: str) -> CompanyRunResult:
            try:
                return await workflow.execute_child_workflow(
                    CompanyJobIngestionWorkflow.run,
                    CompanyIngestionParams(
                        company_key=company_key,
                        triggered_by=request.triggered_by,
                        trigger_type=request.trigger_type,
                        dev_job_limit=request.dev_job_limit,
                    ),
                    id=f"{info.workflow_id}-{company_key}",
                    task_queue=TASK_QUEUE,
                )
            except ChildWorkflowError as exc:
                # Should be rare — CompanyJobIngestionWorkflow catches its own
                # failures — but a company's problem must never take down the
                # rest of the run.
                workflow.logger.warning(f"{company_key} child workflow failed: {exc}")
                return CompanyRunResult(
                    company_code=CompanyCode(company_key.upper()),
                    status="failed",
                    error_summary=str(exc),
                )

        results = await asyncio.gather(*(run_one(c) for c in request.companies))
        return dict(zip(request.companies, results, strict=True))
