"""Temporal Schedule management: create/trigger/pause/unpause/inspect/delete,
plus a one-time manual workflow start. `ScheduleOverlapPolicy.SKIP` prevents two
full ingestion runs from overlapping.
"""

from __future__ import annotations

from datetime import UTC, datetime

from temporalio.client import (
    Schedule,
    ScheduleActionStartWorkflow,
    ScheduleOverlapPolicy,
    SchedulePolicy,
    ScheduleSpec,
)

from ..domain.enums import TriggerType
from ..domain.models import IngestionRequest
from . import TASK_QUEUE
from .client import get_temporal_client
from .workflows import JobIntelligenceIngestionWorkflow

SCHEDULE_ID = "job-intelligence-daily"
DEFAULT_COMPANIES = ["wells_fargo", "goldman_sachs", "bny"]
DEFAULT_CRON = "0 6 * * *"  # 06:00 UTC daily


async def create_schedule(cron: str = DEFAULT_CRON, companies: list[str] | None = None) -> None:
    client = await get_temporal_client()
    await client.create_schedule(
        SCHEDULE_ID,
        Schedule(
            action=ScheduleActionStartWorkflow(
                JobIntelligenceIngestionWorkflow.run,
                IngestionRequest(
                    companies=companies or DEFAULT_COMPANIES,
                    triggered_by="schedule",
                    trigger_type=TriggerType.SCHEDULE,
                ),
                id="job-intelligence-scheduled-run",
                task_queue=TASK_QUEUE,
            ),
            spec=ScheduleSpec(cron_expressions=[cron]),
            policy=SchedulePolicy(overlap=ScheduleOverlapPolicy.SKIP),
        ),
    )


async def trigger_schedule() -> None:
    client = await get_temporal_client()
    await client.get_schedule_handle(SCHEDULE_ID).trigger()


async def pause_schedule(note: str = "paused via CLI") -> None:
    client = await get_temporal_client()
    await client.get_schedule_handle(SCHEDULE_ID).pause(note=note)


async def unpause_schedule(note: str = "unpaused via CLI") -> None:
    client = await get_temporal_client()
    await client.get_schedule_handle(SCHEDULE_ID).unpause(note=note)


async def delete_schedule() -> None:
    client = await get_temporal_client()
    await client.get_schedule_handle(SCHEDULE_ID).delete()


async def describe_schedule() -> dict:
    client = await get_temporal_client()
    desc = await client.get_schedule_handle(SCHEDULE_ID).describe()
    return {
        "schedule_id": SCHEDULE_ID,
        "paused": desc.schedule.state.paused,
        "note": desc.schedule.state.note,
        "num_actions": desc.info.num_actions,
        "num_actions_skipped_overlap": desc.info.num_actions_skipped_overlap,
        "recent_actions": [str(a.scheduled_at) for a in desc.info.recent_actions[-5:]],
        "next_action_times": [str(t) for t in desc.info.next_action_times[:3]],
    }


async def run_once(
    companies: list[str] | None = None,
    dev_job_limit: int | None = None,
    triggered_by: str = "cli-manual",
) -> str:
    """Start a one-time manual workflow execution; returns its workflow id."""
    client = await get_temporal_client()
    workflow_id = f"job-intelligence-manual-{datetime.now(UTC):%Y%m%dT%H%M%S}"
    await client.start_workflow(
        JobIntelligenceIngestionWorkflow.run,
        IngestionRequest(
            companies=companies or DEFAULT_COMPANIES,
            triggered_by=triggered_by,
            trigger_type=TriggerType.MANUAL,
            dev_job_limit=dev_job_limit,
        ),
        id=workflow_id,
        task_queue=TASK_QUEUE,
    )
    return workflow_id
