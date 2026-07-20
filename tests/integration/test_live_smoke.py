"""Opt-in live smoke test — hits the real Wells Fargo, Goldman Sachs, and BNY
career sites with `dev_job_limit=1` (one job each, conservative traffic).

Skipped by default; set `RUN_LIVE_SCRAPER_TESTS=true` to run it (see the
`pytest_collection_modifyitems` hook in tests/conftest.py). Uses an isolated
DB fixture so a live run never writes into the real data/app.db.
"""

from __future__ import annotations

import pytest

from job_intelligence.app.services import run_company_ingestion

pytestmark = pytest.mark.live


async def test_wells_fargo_live_smoke(isolated_db) -> None:
    result = await run_company_ingestion("wells_fargo", dev_job_limit=1)
    assert result.status == "success"
    assert result.jobs_discovered >= 1


async def test_goldman_sachs_live_smoke(isolated_db) -> None:
    result = await run_company_ingestion("goldman_sachs", dev_job_limit=1)
    assert result.status == "success"
    assert result.jobs_discovered >= 1


async def test_bny_live_smoke(isolated_db) -> None:
    result = await run_company_ingestion("bny", dev_job_limit=1)
    assert result.status == "success"
    assert result.jobs_discovered >= 1
