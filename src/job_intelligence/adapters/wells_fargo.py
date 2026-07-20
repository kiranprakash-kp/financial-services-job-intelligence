"""Wells Fargo adapter.

Verified strategy (docs/site_reconnaissance/wells_fargo.md): the public XML feed
at `/en/jobs/xml/` is server-rendered and already contains the full job record —
title, location, full description, employment type, category, and a stable
`referencenumber` id. Discovery and detail are therefore the SAME fetch: one
feed request yields everything, so no per-job detail request is made. This
keeps traffic minimal and avoids ever needing a browser for this source.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET

from selectolax.parser import HTMLParser

from ..config import load_companies_config
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

log = get_logger("adapter.wells_fargo")

_US_COUNTRY_TEXT = "united states"


def _field(elem: ET.Element, tag: str) -> str:
    child = elem.find(tag)
    return (child.text or "").strip() if child is not None else ""


class WellsFargoAdapter:
    company_code = CompanyCode.WELLS_FARGO.value

    def __init__(self, transport_factory: TransportFactory) -> None:
        self._cfg = load_companies_config().get("wells_fargo")
        self._transport = transport_factory.for_company("wells_fargo")

    def extraction_plan(self) -> ExtractionPlan:
        return ExtractionPlan(
            company_code=self.company_code,
            method=ExtractionMethod.SERVER_HTML,
            transport=TransportKind.DIRECT_HTTP,
            listing_source_type="xml_feed",
            detail_source_type="embedded_in_feed",
            pagination_type="full_feed",
            proxy_enabled=False,
            confidence=0.95,
            rationale=(
                "Verified live: the /en/jobs/xml/ feed is server-rendered, requires no "
                "authentication, and embeds full job detail (description, location, "
                "jobtype, category) alongside a stable referencenumber id."
            ),
        )

    async def discover_jobs(self, run_context: RunContext) -> AsyncIterator[DiscoveredJob]:
        feed_url = self._cfg.settings["feed_url"]
        resp = await self._transport.get(TransportRequest(url=feed_url))
        try:
            root = ET.fromstring(resp.text)
        except ET.ParseError as exc:
            raise ParsingError(f"Wells Fargo feed did not parse as XML: {exc}") from exc

        seen_ids: set[str] = set()
        yielded = 0
        limit = run_context.dev_job_limit

        for job_elem in root.findall("job"):
            ref = _field(job_elem, "referencenumber")
            if not ref:
                log.warning("wf.discover.missing_reference_number")
                continue
            if ref in seen_ids:
                continue  # duplicate id safety net
            seen_ids.add(ref)

            country = _field(job_elem, "country")
            if _US_COUNTRY_TEXT not in country.lower():
                continue  # fast pre-filter; normalize() still validates independently

            payload = {
                "title": _field(job_elem, "title"),
                "referencenumber": ref,
                "url": _field(job_elem, "url"),
                "city": _field(job_elem, "city"),
                "state": _field(job_elem, "state"),
                "country": country,
                "description": _field(job_elem, "description"),
                "jobtype": _field(job_elem, "jobtype"),
                "category": _field(job_elem, "category"),
                "remotetype": _field(job_elem, "remotetype"),
                "date": _field(job_elem, "date"),
            }

            yield DiscoveredJob(
                company_code=CompanyCode.WELLS_FARGO,
                source_job_id=ref,
                title=payload["title"],
                posting_url=payload["url"],
                location_text=", ".join(p for p in [payload["city"], payload["state"]] if p),
                discovered_on_page=1,
                listing_payload=payload,
            )
            yielded += 1
            if limit is not None and yielded >= limit:
                log.info("wf.discover.dev_limit_reached", limit=limit)
                return

    async def fetch_job_detail(
        self, discovered_job: DiscoveredJob, run_context: RunContext
    ) -> RawJobDetail:
        # The feed already carries full detail; no extra request is made.
        return RawJobDetail(
            company_code=CompanyCode.WELLS_FARGO,
            source_job_id=discovered_job.source_job_id,
            posting_url=discovered_job.posting_url,
            content_type="application/xml+embedded",
            payload=discovered_job.listing_payload,
        )

    def normalize(self, raw_job: RawJobDetail) -> NormalizedJob:
        payload = raw_job.payload
        location = normalize_structured_location(
            city=payload.get("city"), state=payload.get("state"), country=payload.get("country")
        )
        description_text = HTMLParser(payload.get("description") or "").text(separator=" ")
        posted_at = None
        if payload.get("date"):
            try:
                posted_at = parsedate_to_datetime(payload["date"])
            except (TypeError, ValueError):
                posted_at = None

        job = NormalizedJob(
            company_code=CompanyCode.WELLS_FARGO,
            source_job_id=raw_job.source_job_id,
            canonical_key=f"WELLS_FARGO:{raw_job.source_job_id}",
            key_source=KeySource.SOURCE_ID,
            title=payload.get("title") or "Untitled",
            employment_type=payload.get("jobtype") or None,
            business_unit=payload.get("category") or None,
            locations=[location],
            workplace_type=WorkplaceType.REMOTE if location.is_remote else WorkplaceType.UNKNOWN,
            description_text=description_text,
            posting_url=raw_job.posting_url or payload.get("url", ""),
            source_posted_at=posted_at,
            raw_payload=payload,
        )
        job.content_hash = compute_content_hash(job)
        return job

    async def aclose(self) -> None:
        await self._transport.aclose()
