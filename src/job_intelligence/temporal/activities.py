"""Temporal Activities: the only place in the Temporal layer allowed to do I/O.

Two activities per company, matching the two-step service split in
app/services.py:

- `create_ingestion_run_activity` — cheap; creates the run record, returns its id.
- `run_extraction_activity` — the extraction/normalize/persist loop; heartbeats
  as jobs are discovered so Temporal can detect a stalled worker during a long
  crawl, and always leaves the run record in a terminal status.

Exception classification for retries lives on the workflow's RetryPolicy
(`non_retryable_error_types`), matched against these activities' exception
class names — see domain/exceptions.py for the Retryable/NonRetryable split.
"""

from __future__ import annotations

from temporalio import activity

from ..app.services import create_ingestion_run, run_company_ingestion
from ..domain.models import CompanyIngestionParams, CompanyRunResult, ExtractionActivityParams


@activity.defn
async def create_ingestion_run_activity(params: CompanyIngestionParams) -> int:
    info = activity.info()
    return create_ingestion_run(
        params.company_key,
        workflow_id=str(info.workflow_id),
        trigger_type=params.trigger_type.value,
    )


@activity.defn
async def run_extraction_activity(params: ExtractionActivityParams) -> CompanyRunResult:
    def _on_progress(discovered_count: int) -> None:
        activity.heartbeat(discovered_count)

    return await run_company_ingestion(
        params.company_key,
        params.dev_job_limit,
        ingestion_run_id=params.ingestion_run_id,
        workflow_id=params.workflow_id,
        on_progress=_on_progress,
    )
