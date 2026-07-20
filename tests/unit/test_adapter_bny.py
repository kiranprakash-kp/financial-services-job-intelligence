"""BNY adapter tests — fully offline via respx-mocked HTTP.

Never hits the live site (see docs/site_reconnaissance/bny.md). Fixture page1
covers: two US requisitions, one non-US (India) requisition that must be
filtered at discovery, and a Hybrid workplace-type example.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx

from job_intelligence.adapters.bny import BNYAdapter
from job_intelligence.config import get_settings, load_companies_config
from job_intelligence.domain.exceptions import AccessDeniedError, ParsingError, TransientSourceError
from job_intelligence.domain.models import RunContext
from job_intelligence.extraction.transport import TransportFactory

FIXTURES = Path(__file__).parent.parent / "fixtures"
PAGE1 = (FIXTURES / "bny_requisitions_page1.json").read_text(encoding="utf-8")
DETAIL_900001 = (FIXTURES / "bny_requisition_detail_900001.json").read_text(encoding="utf-8")

_CFG = load_companies_config().get("bny").settings
LIST_URL = f"{_CFG['api_base']}/{_CFG['requisitions_resource']}"
DETAIL_URL_900001 = f"{_CFG['api_base']}/{_CFG['detail_resource']}/900001"


def _adapter() -> BNYAdapter:
    return BNYAdapter(TransportFactory(get_settings()))


def _run_context(dev_job_limit: int | None = None) -> RunContext:
    return RunContext(
        company_code="BNY",
        workflow_id="test-bny",
        run_id="test-run",
        triggered_by="test",
        dev_job_limit=dev_job_limit,
    )


async def _discover_all(adapter: BNYAdapter, dev_job_limit: int | None = None) -> list:
    return [job async for job in adapter.discover_jobs(_run_context(dev_job_limit))]


@respx.mock
async def test_discover_filters_non_us() -> None:
    respx.get(LIST_URL).mock(return_value=httpx.Response(200, text=PAGE1))
    adapter = _adapter()
    try:
        jobs = await _discover_all(adapter)
    finally:
        await adapter.aclose()

    ids = [j.source_job_id for j in jobs]
    assert ids == ["900001", "900003"]  # 900002 (India) filtered


@respx.mock
async def test_dev_job_limit_stops_early() -> None:
    respx.get(LIST_URL).mock(return_value=httpx.Response(200, text=PAGE1))
    adapter = _adapter()
    try:
        jobs = await _discover_all(adapter, dev_job_limit=1)
    finally:
        await adapter.aclose()
    assert [j.source_job_id for j in jobs] == ["900001"]


@respx.mock
async def test_empty_response_yields_nothing() -> None:
    respx.get(LIST_URL).mock(return_value=httpx.Response(200, json={"items": []}))
    adapter = _adapter()
    try:
        jobs = await _discover_all(adapter)
    finally:
        await adapter.aclose()
    assert jobs == []


@respx.mock
async def test_transient_5xx_raises_transient_error() -> None:
    respx.get(LIST_URL).mock(return_value=httpx.Response(503))
    adapter = _adapter()
    try:
        with pytest.raises(TransientSourceError):
            await _discover_all(adapter)
    finally:
        await adapter.aclose()


@respx.mock
async def test_access_denied_raises() -> None:
    respx.get(LIST_URL).mock(return_value=httpx.Response(403))
    adapter = _adapter()
    try:
        with pytest.raises(AccessDeniedError):
            await _discover_all(adapter)
    finally:
        await adapter.aclose()


@respx.mock
async def test_fetch_detail_and_normalize_hybrid_workplace() -> None:
    respx.get(LIST_URL).mock(return_value=httpx.Response(200, text=PAGE1))
    respx.get(DETAIL_URL_900001).mock(return_value=httpx.Response(200, text=DETAIL_900001))
    adapter = _adapter()
    try:
        jobs = await _discover_all(adapter)
        discovered = next(j for j in jobs if j.source_job_id == "900001")
        raw = await adapter.fetch_job_detail(discovered, _run_context())
        normalized = adapter.normalize(raw)
    finally:
        await adapter.aclose()

    assert normalized.has_valid_us_location
    assert normalized.primary_location is not None
    assert normalized.primary_location.state == "FL"
    assert "Process client transactions" in normalized.description_text
    assert "Bachelor's degree" in normalized.qualifications_text
    assert "Reconcile accounts" in normalized.responsibilities_text
    assert normalized.workplace_type.value == "onsite"  # detail's WorkplaceType == "Office"
    assert normalized.business_unit == "Operations"
    assert normalized.department == "Client Processing"
    assert normalized.content_hash is not None


@respx.mock
async def test_detail_missing_id_raises_parsing_error() -> None:
    respx.get(LIST_URL).mock(return_value=httpx.Response(200, text=PAGE1))
    respx.get(DETAIL_URL_900001).mock(return_value=httpx.Response(200, json={"Title": "no id"}))
    adapter = _adapter()
    try:
        jobs = await _discover_all(adapter)
        discovered = next(j for j in jobs if j.source_job_id == "900001")
        with pytest.raises(ParsingError):
            await adapter.fetch_job_detail(discovered, _run_context())
    finally:
        await adapter.aclose()
