"""Regression test: a cancelled run (e.g. Temporal timing out the activity)
must still leave the run record in a terminal "failed" state, not stuck at
"running" forever. Reproduces the real bug found live: `asyncio.CancelledError`
subclasses `BaseException`, not `Exception`, so it skipped the
`except JobIntelError` handler entirely.
"""

from __future__ import annotations

import asyncio

import pytest

from job_intelligence.app import services
from job_intelligence.persistence import orm_models as m
from job_intelligence.persistence.database import get_sessionmaker


class _CancellingAdapter:
    """A fake adapter whose discovery is cancelled mid-run, like a real
    adapter would be if Temporal forcibly times out its activity."""

    async def discover_jobs(self, run_context):
        if False:  # pragma: no cover - keeps this an async generator
            yield
        raise asyncio.CancelledError()

    async def fetch_job_detail(self, discovered_job, run_context):
        raise AssertionError("should never be reached")

    def normalize(self, raw_job):
        raise AssertionError("should never be reached")

    async def aclose(self) -> None:
        return None


async def test_cancellation_marks_run_failed_not_stuck_running(isolated_db, monkeypatch) -> None:
    monkeypatch.setitem(
        services._ADAPTER_BUILDERS,
        "wells_fargo",
        lambda transport_factory: _CancellingAdapter(),
    )

    with pytest.raises(asyncio.CancelledError):
        await services.run_company_ingestion("wells_fargo", dev_job_limit=None)

    Session = get_sessionmaker()
    with Session() as session:
        run_row = session.query(m.IngestionRun).one()
        assert run_row.status == "failed"
        assert run_row.completed_at is not None
        assert run_row.error_summary is not None
        assert "CancelledError" in run_row.error_summary
