"""Goldman Sachs adapter tests — fully offline via respx-mocked HTTP.

Never hits the live site (see docs/site_reconnaissance/goldman_sachs.md).
Fixture page1 covers: a US role, a non-US (London) role — GS discovery does not
pre-filter by country, that validation happens downstream — and a duplicate
roleId to exercise dedup.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx

from job_intelligence.adapters.goldman_sachs import GoldmanSachsAdapter
from job_intelligence.config import get_settings, load_companies_config
from job_intelligence.domain.exceptions import AccessDeniedError, ParsingError, TransientSourceError
from job_intelligence.domain.models import RunContext
from job_intelligence.extraction.transport import TransportFactory

FIXTURES = Path(__file__).parent.parent / "fixtures"
PAGE1 = (FIXTURES / "goldman_sachs_roles_page1.json").read_text(encoding="utf-8")
DETAIL_OK = (FIXTURES / "goldman_sachs_role_detail_100001.html").read_text(encoding="utf-8")
DETAIL_ERROR = (FIXTURES / "goldman_sachs_role_detail_error.html").read_text(encoding="utf-8")
GRAPHQL_URL = load_companies_config().get("goldman_sachs").settings["graphql_url"]


def _adapter() -> GoldmanSachsAdapter:
    return GoldmanSachsAdapter(TransportFactory(get_settings()))


def _run_context(dev_job_limit: int | None = None, dev_page_limit: int | None = None) -> RunContext:
    return RunContext(
        company_code="GOLDMAN_SACHS",
        workflow_id="test-gs",
        run_id="test-run",
        triggered_by="test",
        dev_job_limit=dev_job_limit,
        dev_page_limit=dev_page_limit,
    )


async def _discover_all(adapter: GoldmanSachsAdapter, **kwargs) -> list:
    return [job async for job in adapter.discover_jobs(_run_context(**kwargs))]


@respx.mock
async def test_discover_yields_all_including_non_us_and_dedupes() -> None:
    respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(200, text=PAGE1))
    adapter = _adapter()
    try:
        jobs = await _discover_all(adapter)
    finally:
        await adapter.aclose()

    ids = [j.source_job_id for j in jobs]
    assert ids == ["100001", "100002"]  # duplicate roleId deduped


@respx.mock
async def test_dev_job_limit_stops_early() -> None:
    respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(200, text=PAGE1))
    adapter = _adapter()
    try:
        jobs = await _discover_all(adapter, dev_job_limit=1)
    finally:
        await adapter.aclose()
    assert [j.source_job_id for j in jobs] == ["100001"]


@respx.mock
async def test_pagination_across_pages() -> None:
    page0 = {
        "data": {
            "roleSearch": {
                "totalCount": 4,
                "items": [
                    {
                        "roleId": "1",
                        "jobTitle": "Role 1",
                        "locations": [],
                        "division": "Ops",
                        "skills": [],
                        "externalSource": {"sourceId": "1"},
                    },
                    {
                        "roleId": "2",
                        "jobTitle": "Role 2",
                        "locations": [],
                        "division": "Ops",
                        "skills": [],
                        "externalSource": {"sourceId": "2"},
                    },
                ],
            }
        }
    }
    page1 = {
        "data": {
            "roleSearch": {
                "totalCount": 4,
                "items": [
                    {
                        "roleId": "3",
                        "jobTitle": "Role 3",
                        "locations": [],
                        "division": "Ops",
                        "skills": [],
                        "externalSource": {"sourceId": "3"},
                    },
                    {
                        "roleId": "4",
                        "jobTitle": "Role 4",
                        "locations": [],
                        "division": "Ops",
                        "skills": [],
                        "externalSource": {"sourceId": "4"},
                    },
                ],
            }
        }
    }
    respx.post(GRAPHQL_URL).mock(
        side_effect=[
            httpx.Response(200, json=page0),
            httpx.Response(200, json=page1),
        ]
    )
    adapter = _adapter()
    try:
        jobs = await _discover_all(adapter)
    finally:
        await adapter.aclose()
    assert [j.source_job_id for j in jobs] == ["1", "2", "3", "4"]


@respx.mock
async def test_empty_first_page_yields_nothing() -> None:
    empty = {"data": {"roleSearch": {"totalCount": 0, "items": []}}}
    respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(200, json=empty))
    adapter = _adapter()
    try:
        jobs = await _discover_all(adapter)
    finally:
        await adapter.aclose()
    assert jobs == []


@respx.mock
async def test_graphql_errors_raise_parsing_error() -> None:
    body = {"errors": [{"message": "Cannot query field jobTitle"}]}
    respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(200, json=body))
    adapter = _adapter()
    try:
        with pytest.raises(ParsingError):
            await _discover_all(adapter)
    finally:
        await adapter.aclose()


@respx.mock
async def test_transient_5xx_raises_transient_error() -> None:
    respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(503))
    adapter = _adapter()
    try:
        with pytest.raises(TransientSourceError):
            await _discover_all(adapter)
    finally:
        await adapter.aclose()


@respx.mock
async def test_access_denied_raises() -> None:
    respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(403))
    adapter = _adapter()
    try:
        with pytest.raises(AccessDeniedError):
            await _discover_all(adapter)
    finally:
        await adapter.aclose()


@respx.mock
async def test_fetch_detail_merges_listing_and_detail_then_normalizes() -> None:
    respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(200, text=PAGE1))
    respx.get("https://higher.gs.com/roles/100001").mock(
        return_value=httpx.Response(200, text=DETAIL_OK)
    )
    adapter = _adapter()
    try:
        jobs = await _discover_all(adapter)
        discovered = next(j for j in jobs if j.source_job_id == "100001")
        raw = await adapter.fetch_job_detail(discovered, _run_context())
        normalized = adapter.normalize(raw)
    finally:
        await adapter.aclose()

    # "skills" only exists on the listing payload, not the detail page.
    assert raw.payload["skills"] == ["Python", "AWS"]
    assert normalized.has_valid_us_location
    assert normalized.primary_location is not None
    assert normalized.primary_location.state == "NY"
    assert "Python" in normalized.description_text
    assert normalized.salary_min == 120000
    assert normalized.salary_max == 160000
    assert normalized.salary_currency == "USD"
    assert normalized.content_hash is not None


@respx.mock
async def test_fetch_detail_error_page_raises_parsing_error() -> None:
    respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(200, text=PAGE1))
    respx.get("https://higher.gs.com/roles/100001").mock(
        return_value=httpx.Response(200, text=DETAIL_ERROR)
    )
    adapter = _adapter()
    try:
        jobs = await _discover_all(adapter)
        discovered = next(j for j in jobs if j.source_job_id == "100001")
        with pytest.raises(ParsingError):
            await adapter.fetch_job_detail(discovered, _run_context())
    finally:
        await adapter.aclose()
