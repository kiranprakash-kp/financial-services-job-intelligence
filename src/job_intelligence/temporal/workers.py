"""Temporal worker entrypoint. A single task queue for the POC (see the
module docstring in temporal/__init__.py for the "fewer task queues, clean
module boundaries" tradeoff spec allows for a local POC).
"""

from __future__ import annotations

import asyncio

from temporalio.worker import Worker

from ..logging import configure_logging, get_logger
from . import TASK_QUEUE, activities
from .client import get_temporal_client
from .workflows import CompanyJobIngestionWorkflow, JobIntelligenceIngestionWorkflow

log = get_logger("temporal.worker")


async def run_worker() -> None:
    configure_logging()
    client = await get_temporal_client()
    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[JobIntelligenceIngestionWorkflow, CompanyJobIngestionWorkflow],
        activities=[
            activities.create_ingestion_run_activity,
            activities.run_extraction_activity,
        ],
    )
    log.info("temporal.worker.starting", task_queue=TASK_QUEUE)
    await worker.run()


def main() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
