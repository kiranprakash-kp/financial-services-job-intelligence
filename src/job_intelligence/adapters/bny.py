"""BNY adapter.

Verified strategy (docs/site_reconnaissance/bny.md): the Oracle Recruiting
(Candidate Experience) public REST resources answer directly to `httpx` with no
authentication. Listing uses `recruitingCEJobRequisitions` (limit/offset
pagination, `TotalJobsCount`); full text (description, qualifications,
responsibilities, workplace type, department) lives on the single-record
`recruitingCEJobRequisitionDetails/{Id}` resource.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime

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
from ..processing.locations import parse_location_text

log = get_logger("adapter.bny")

# The exact Candidate Experience deep-link path was not exhaustively verified
# during recon (see docs/site_reconnaissance/bny.md "Known uncertainties");
# this follows Oracle CE's standard job-detail URL convention.
_DETAIL_URL_TEMPLATE = (
    "https://eofe.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/en/"
    "sites/BNY-Careers/job/{req_id}"
)

_WORKPLACE_MAP = {
    "remote": WorkplaceType.REMOTE,
    "home": WorkplaceType.REMOTE,
    "hybrid": WorkplaceType.HYBRID,
    "office": WorkplaceType.ONSITE,
    "on-site": WorkplaceType.ONSITE,
    "onsite": WorkplaceType.ONSITE,
}


def _map_workplace_type(text: str | None) -> WorkplaceType:
    if not text:
        return WorkplaceType.UNKNOWN
    return _WORKPLACE_MAP.get(text.strip().lower(), WorkplaceType.UNKNOWN)


class BNYAdapter:
    company_code = CompanyCode.BNY.value

    def __init__(self, transport_factory: TransportFactory) -> None:
        self._cfg = load_companies_config().get("bny")
        self._transport = transport_factory.for_company("bny")
        self._settings = get_settings()

    def extraction_plan(self) -> ExtractionPlan:
        return ExtractionPlan(
            company_code=self.company_code,
            method=ExtractionMethod.DIRECT_API,
            transport=TransportKind.DIRECT_HTTP,
            listing_source_type="oracle_recruiting_rest",
            detail_source_type="oracle_recruiting_rest_detail",
            pagination_type="limit_offset",
            proxy_enabled=False,
            confidence=0.85,
            rationale=(
                "Verified live: recruitingCEJobRequisitions and "
                "recruitingCEJobRequisitionDetails/{Id} both answer 200 JSON with no "
                "authentication; TotalJobsCount drives limit/offset pagination."
            ),
        )

    async def discover_jobs(self, run_context: RunContext) -> AsyncIterator[DiscoveredJob]:
        page_size = int(self._cfg.settings.get("page_size", 25))
        site_number = self._cfg.settings["site_number"]
        max_pages = run_context.dev_page_limit or self._settings.scrape_max_pages

        seen_ids: set[str] = set()
        yielded = 0
        offset = 0
        page = 0

        while page < max_pages:
            finder = (
                f"findReqs;siteNumber={site_number},limit={page_size},"
                f"offset={offset},sortBy=POSTING_DATES_DESC"
            )
            resp = await self._transport.get(
                TransportRequest(
                    url=f"{self._cfg.settings['api_base']}/{self._cfg.settings['requisitions_resource']}",
                    params={
                        "onlyData": "true",
                        "expand": "requisitionList.secondaryLocations",
                        "finder": finder,
                    },
                )
            )
            body = resp.json()
            items = body.get("items") or []
            if not items:
                log.info("bny.discover.stop", reason="empty_response", offset=offset)
                return

            block = items[0]
            total_count = block.get("TotalJobsCount")
            requisitions = block.get("requisitionList") or []
            if not requisitions:
                log.info("bny.discover.stop", reason="empty_page", offset=offset)
                return

            new_this_page = 0
            for req in requisitions:
                req_id = req.get("Id")
                if not req_id or str(req_id) in seen_ids:
                    continue
                seen_ids.add(str(req_id))
                new_this_page += 1

                country = req.get("PrimaryLocationCountry") or ""
                if country.upper() not in ("US", "USA"):
                    continue  # fast pre-filter; normalize() still validates independently

                yield DiscoveredJob(
                    company_code=CompanyCode.BNY,
                    source_job_id=str(req_id),
                    title=req.get("Title"),
                    posting_url=_DETAIL_URL_TEMPLATE.format(req_id=req_id),
                    location_text=req.get("PrimaryLocation"),
                    discovered_on_page=page + 1,
                    listing_payload=req,
                )
                yielded += 1
                if run_context.dev_job_limit is not None and yielded >= run_context.dev_job_limit:
                    log.info("bny.discover.stop", reason="dev_job_limit", limit=yielded)
                    return

            if new_this_page == 0:
                log.info("bny.discover.stop", reason="page_signature_repeat", offset=offset)
                return
            offset += page_size
            if total_count is not None and offset >= total_count:
                log.info("bny.discover.stop", reason="total_count_reached", total=total_count)
                return
            page += 1

        log.info("bny.discover.stop", reason="max_pages_reached", max_pages=max_pages)

    async def fetch_job_detail(
        self, discovered_job: DiscoveredJob, run_context: RunContext
    ) -> RawJobDetail:
        detail_resource = self._cfg.settings["detail_resource"]
        resp = await self._transport.get(
            TransportRequest(
                url=f"{self._cfg.settings['api_base']}/{detail_resource}/{discovered_job.source_job_id}",
                params={"onlyData": "true"},
            )
        )
        detail = resp.json()
        if not detail.get("Id"):
            raise ParsingError(
                f"BNY requisition detail missing Id for {discovered_job.source_job_id}"
            )

        merged = {**discovered_job.listing_payload, **detail}
        return RawJobDetail(
            company_code=CompanyCode.BNY,
            source_job_id=discovered_job.source_job_id,
            posting_url=discovered_job.posting_url,
            content_type="application/json",
            payload=merged,
        )

    def normalize(self, raw_job: RawJobDetail) -> NormalizedJob:
        payload = raw_job.payload

        locations = parse_location_text(payload.get("PrimaryLocation"))
        if locations:
            locations[0].is_primary = True
        for secondary in payload.get("secondaryLocations") or []:
            if not isinstance(secondary, dict):
                continue
            text = secondary.get("Location") or secondary.get("PrimaryLocation")
            if text:
                locations.extend(parse_location_text(text))

        description_text = HTMLParser(payload.get("ExternalDescriptionStr") or "").text(
            separator=" "
        )
        qualifications_text = HTMLParser(payload.get("ExternalQualificationsStr") or "").text(
            separator=" "
        )
        responsibilities_text = HTMLParser(payload.get("ExternalResponsibilitiesStr") or "").text(
            separator=" "
        )

        posted_at = None
        if payload.get("PostedDate"):
            try:
                posted_at = datetime.strptime(payload["PostedDate"], "%Y-%m-%d")
            except ValueError:
                posted_at = None

        job = NormalizedJob(
            company_code=CompanyCode.BNY,
            source_job_id=raw_job.source_job_id,
            canonical_key=f"BNY:{raw_job.source_job_id}",
            key_source=KeySource.SOURCE_ID,
            title=payload.get("Title") or "Untitled",
            employment_type=payload.get("JobSchedule"),
            business_unit=payload.get("BusinessUnit"),
            department=payload.get("Department"),
            locations=locations,
            workplace_type=_map_workplace_type(payload.get("WorkplaceType")),
            description_text=description_text or None,
            qualifications_text=qualifications_text or None,
            responsibilities_text=responsibilities_text or None,
            posting_url=raw_job.posting_url or "",
            source_posted_at=posted_at,
            salary_min=payload.get("MinimumSalary"),
            salary_max=payload.get("MaximumSalary"),
            salary_currency=payload.get("SalaryCurrency"),
            raw_payload=payload,
        )
        job.content_hash = compute_content_hash(job)
        return job

    async def aclose(self) -> None:
        await self._transport.aclose()
