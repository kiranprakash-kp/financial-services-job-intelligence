"""Goldman Sachs adapter.

Verified strategy (docs/site_reconnaissance/goldman_sachs.md): the `higher.gs.com`
SPA calls a public GraphQL gateway at `api-higher.gs.com` for listing (operation
`GetRoles`) with no authentication. Individual role pages
(`https://higher.gs.com/roles/{sourceId}`) are server-rendered by Next.js and
embed a `__NEXT_DATA__` JSON blob containing the full role — description,
compensation, and structured locations — so detail fetch is also direct HTTP,
never a browser.
"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator

from selectolax.parser import HTMLParser

from ..config import get_settings, load_companies_config
from ..domain.enums import CompanyCode, ExtractionMethod, KeySource, TransportKind, WorkplaceType
from ..domain.exceptions import ParsingError
from ..domain.models import (
    DiscoveredJob,
    ExtractionPlan,
    NormalizedJob,
    RawJobDetail,
    RunContext,
)
from ..extraction.transport import TransportFactory, TransportRequest
from ..logging import get_logger
from ..processing.hashing import compute_content_hash
from ..processing.locations import normalize_structured_location

log = get_logger("adapter.goldman_sachs")

_NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S
)

_GET_ROLES_QUERY = """
query GetRoles($searchQueryInput: RoleSearchQueryInput!) {
  roleSearch(searchQueryInput: $searchQueryInput) {
    totalCount
    items {
      roleId
      corporateTitle
      jobTitle
      jobFunction
      locations {
        primary
        state
        country
        city
      }
      status
      division
      skills
      jobType {
        code
        description
      }
      externalSource {
        sourceId
      }
    }
  }
}
"""


class GoldmanSachsAdapter:
    company_code = CompanyCode.GOLDMAN_SACHS.value

    def __init__(self, transport_factory: TransportFactory) -> None:
        self._cfg = load_companies_config().get("goldman_sachs")
        self._transport = transport_factory.for_company("goldman_sachs")
        self._settings = get_settings()

    def extraction_plan(self) -> ExtractionPlan:
        return ExtractionPlan(
            company_code=self.company_code,
            method=ExtractionMethod.DIRECT_API,
            transport=TransportKind.DIRECT_HTTP,
            listing_source_type="graphql",
            detail_source_type="server_rendered_next_data",
            pagination_type="page_number_zero_indexed",
            proxy_enabled=False,
            confidence=0.9,
            rationale=(
                "Verified live: api-higher.gs.com/gateway/api/v1/graphql answers GetRoles "
                "with no authentication (totalCount + full role fields), and "
                "higher.gs.com/roles/{sourceId} is server-rendered with the complete role "
                "(description, compensation, locations) embedded in __NEXT_DATA__."
            ),
        )

    async def discover_jobs(self, run_context: RunContext) -> AsyncIterator[DiscoveredJob]:
        page_size = int(self._cfg.settings.get("page_size", 20))
        experiences = self._cfg.settings.get("experiences", ["EARLY_CAREER", "PROFESSIONAL"])
        max_pages = run_context.dev_page_limit or self._settings.scrape_max_pages

        seen_ids: set[str] = set()
        yielded = 0
        page_number = 0

        while page_number < max_pages:
            variables = {
                "searchQueryInput": {
                    "page": {"pageSize": page_size, "pageNumber": page_number},
                    "experiences": experiences,
                    "filters": [],
                    "searchTerm": "",
                }
            }
            resp = await self._transport.post(
                TransportRequest(
                    url=self._cfg.settings["graphql_url"],
                    json={
                        "operationName": self._cfg.settings.get("operation_name", "GetRoles"),
                        "query": _GET_ROLES_QUERY,
                        "variables": variables,
                    },
                    headers={
                        "Content-Type": "application/json",
                        "apollographql-client-name": self._cfg.settings.get(
                            "apollo_client_name", "higher-web-poc"
                        ),
                    },
                )
            )
            body = resp.json()
            if body.get("errors"):
                raise ParsingError(f"GS GraphQL returned errors: {body['errors']}")

            role_search = (body.get("data") or {}).get("roleSearch") or {}
            items = role_search.get("items") or []
            total_count = role_search.get("totalCount")

            if not items:
                log.info("gs.discover.stop", reason="empty_page", page=page_number)
                return

            new_this_page = 0
            for item in items:
                source_id = ((item.get("externalSource") or {}).get("sourceId")) or item.get(
                    "roleId"
                )
                if not source_id or source_id in seen_ids:
                    continue
                seen_ids.add(source_id)
                new_this_page += 1

                yield DiscoveredJob(
                    company_code=CompanyCode.GOLDMAN_SACHS,
                    source_job_id=str(source_id),
                    title=item.get("jobTitle"),
                    posting_url=f"https://higher.gs.com/roles/{source_id}",
                    discovered_on_page=page_number + 1,
                    listing_payload=item,
                )
                yielded += 1
                if run_context.dev_job_limit is not None and yielded >= run_context.dev_job_limit:
                    log.info("gs.discover.stop", reason="dev_job_limit", limit=yielded)
                    return

            if new_this_page == 0:
                log.info("gs.discover.stop", reason="page_signature_repeat", page=page_number)
                return
            if total_count is not None and len(seen_ids) >= total_count:
                log.info("gs.discover.stop", reason="total_count_reached", total=total_count)
                return

            page_number += 1

        log.info("gs.discover.stop", reason="max_pages_reached", max_pages=max_pages)

    async def fetch_job_detail(
        self, discovered_job: DiscoveredJob, run_context: RunContext
    ) -> RawJobDetail:
        resp = await self._transport.get(TransportRequest(url=discovered_job.posting_url or ""))
        match = _NEXT_DATA_RE.search(resp.text)
        if not match:
            raise ParsingError(
                f"GS role page had no __NEXT_DATA__ block: {discovered_job.posting_url}"
            )
        try:
            data = json.loads(match.group(1))
        except json.JSONDecodeError as exc:
            raise ParsingError(f"GS __NEXT_DATA__ was not valid JSON: {exc}") from exc

        page_props = (data.get("props") or {}).get("pageProps") or {}
        role = page_props.get("role")
        if not role:
            raise ParsingError(
                f"GS role detail missing (error={page_props.get('error')!r}): "
                f"{discovered_job.source_job_id}"
            )

        merged = {**discovered_job.listing_payload, **role}
        return RawJobDetail(
            company_code=CompanyCode.GOLDMAN_SACHS,
            source_job_id=discovered_job.source_job_id,
            posting_url=discovered_job.posting_url,
            content_type="text/html+next_data",
            payload=merged,
        )

    def normalize(self, raw_job: RawJobDetail) -> NormalizedJob:
        payload = raw_job.payload

        raw_locations = payload.get("locations") or []
        locations = [
            normalize_structured_location(
                city=loc.get("city"),
                state=loc.get("state"),
                country=loc.get("country"),
                is_primary=bool(loc.get("primary")),
            )
            for loc in raw_locations
            if isinstance(loc, dict)
        ]
        if locations and not any(loc.is_primary for loc in locations):
            locations[0].is_primary = True

        description_text = HTMLParser(payload.get("descriptionHtml") or "").text(separator=" ")

        job_type = payload.get("jobType")
        if isinstance(job_type, dict):
            employment_type = job_type.get("description") or job_type.get("code")
        else:
            employment_type = job_type if isinstance(job_type, str) else None

        salary_min = salary_max = None
        salary_currency = salary_period = None
        compensation = payload.get("compensation")
        if isinstance(compensation, dict):
            salary_min = compensation.get("minSalary")
            salary_max = compensation.get("maxSalary")
            salary_currency = compensation.get("currency")
            # GS discloses these as annual base-pay ranges; not explicitly labeled
            # by the API, so this is a documented assumption, not an observed field.
            salary_period = "year" if (salary_min or salary_max) else None

        job = NormalizedJob(
            company_code=CompanyCode.GOLDMAN_SACHS,
            source_job_id=raw_job.source_job_id,
            canonical_key=f"GOLDMAN_SACHS:{raw_job.source_job_id}",
            key_source=KeySource.SOURCE_ID,
            title=payload.get("jobTitle") or "Untitled",
            business_unit=payload.get("division"),
            department=payload.get("jobFunction"),
            employment_type=employment_type,
            locations=locations,
            workplace_type=WorkplaceType.UNKNOWN,
            description_text=description_text,
            posting_url=raw_job.posting_url or "",
            salary_min=salary_min,
            salary_max=salary_max,
            salary_currency=salary_currency,
            salary_period=salary_period,
            raw_payload=payload,
        )
        job.content_hash = compute_content_hash(job)
        return job

    async def aclose(self) -> None:
        await self._transport.aclose()
