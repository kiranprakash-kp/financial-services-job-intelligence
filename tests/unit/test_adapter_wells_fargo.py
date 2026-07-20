"""Wells Fargo adapter tests — fully offline via respx-mocked HTTP.

Never hits the live site (see docs/site_reconnaissance/wells_fargo.md for the
verified live behavior). Fixture covers: first page, a US job, a non-US job to
filter, a malformed job missing its reference number, a duplicate reference
number, and a job with missing optional fields.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx

from job_intelligence.adapters.wells_fargo import WellsFargoAdapter
from job_intelligence.config import get_settings, load_companies_config
from job_intelligence.domain.exceptions import AccessDeniedError, TransientSourceError
from job_intelligence.domain.models import RunContext
from job_intelligence.extraction.transport import TransportFactory

FIXTURE = (Path(__file__).parent.parent / "fixtures" / "wells_fargo_feed_sample.xml").read_text(
    encoding="utf-8"
)
FEED_URL = load_companies_config().get("wells_fargo").settings["feed_url"]


def _adapter() -> WellsFargoAdapter:
    return WellsFargoAdapter(TransportFactory(get_settings()))


def _run_context(dev_job_limit: int | None = None) -> RunContext:
    return RunContext(
        company_code="WELLS_FARGO",
        workflow_id="test-wf",
        run_id="test-run",
        triggered_by="test",
        dev_job_limit=dev_job_limit,
    )


async def _discover_all(adapter: WellsFargoAdapter, dev_job_limit: int | None = None) -> list:
    return [job async for job in adapter.discover_jobs(_run_context(dev_job_limit))]


@respx.mock
async def test_discover_filters_non_us_dedupes_and_skips_malformed() -> None:
    respx.get(FEED_URL).mock(return_value=httpx.Response(200, text=FIXTURE))
    adapter = _adapter()
    try:
        jobs = await _discover_all(adapter)
    finally:
        await adapter.aclose()

    ids = [j.source_job_id for j in jobs]
    # R-200001 (Philippines) filtered; missing-ref job skipped; duplicate R-100001 deduped.
    assert ids == ["R-100001", "R-100002", "R-300001"]


@respx.mock
async def test_dev_job_limit_stops_early() -> None:
    respx.get(FEED_URL).mock(return_value=httpx.Response(200, text=FIXTURE))
    adapter = _adapter()
    try:
        jobs = await _discover_all(adapter, dev_job_limit=1)
    finally:
        await adapter.aclose()
    assert [j.source_job_id for j in jobs] == ["R-100001"]


@respx.mock
async def test_empty_feed_yields_nothing() -> None:
    empty = '<?xml version="1.0"?><source></source>'
    respx.get(FEED_URL).mock(return_value=httpx.Response(200, text=empty))
    adapter = _adapter()
    try:
        jobs = await _discover_all(adapter)
    finally:
        await adapter.aclose()
    assert jobs == []


@respx.mock
async def test_transient_5xx_raises_transient_error() -> None:
    respx.get(FEED_URL).mock(return_value=httpx.Response(503))
    adapter = _adapter()
    try:
        with pytest.raises(TransientSourceError):
            await _discover_all(adapter)
    finally:
        await adapter.aclose()


@respx.mock
async def test_access_denied_raises_and_does_not_retry_silently() -> None:
    respx.get(FEED_URL).mock(return_value=httpx.Response(403))
    adapter = _adapter()
    try:
        with pytest.raises(AccessDeniedError):
            await _discover_all(adapter)
    finally:
        await adapter.aclose()


@respx.mock
async def test_normalize_strips_html_parses_date_and_handles_missing_fields() -> None:
    respx.get(FEED_URL).mock(return_value=httpx.Response(200, text=FIXTURE))
    adapter = _adapter()
    try:
        jobs = await _discover_all(adapter)
        # R-300001 has empty jobtype/category — must normalize without raising.
        dc_job = next(j for j in jobs if j.source_job_id == "R-300001")
        raw = await adapter.fetch_job_detail(dc_job, _run_context())
        normalized = adapter.normalize(raw)
    finally:
        await adapter.aclose()

    assert normalized.employment_type is None
    assert normalized.business_unit is None
    assert normalized.has_valid_us_location
    assert normalized.primary_location is not None
    assert normalized.primary_location.state == "DC"
    assert normalized.content_hash is not None
    assert normalized.source_posted_at is not None
    assert "<p>" not in (normalized.description_text or "")


@respx.mock
async def test_normalize_extracts_text_from_html_description() -> None:
    respx.get(FEED_URL).mock(return_value=httpx.Response(200, text=FIXTURE))
    adapter = _adapter()
    try:
        jobs = await _discover_all(adapter)
        se_job = next(j for j in jobs if j.source_job_id == "R-100001")
        raw = await adapter.fetch_job_detail(se_job, _run_context())
        normalized = adapter.normalize(raw)
    finally:
        await adapter.aclose()

    assert "Python" in normalized.description_text
    assert "AWS" in normalized.description_text
    assert normalized.employment_type == "Full time"
    assert normalized.business_unit == "Technology"
