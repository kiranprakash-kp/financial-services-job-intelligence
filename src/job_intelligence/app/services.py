"""Ingestion service: the one entry point the CLI (and later Streamlit/Temporal
Activities) call to run a company's adapter and persist results.

Pre-Temporal (Milestone 3/4), this runs the adapter in-process. From Milestone 5
onward the same public function dispatches to a Temporal workflow instead — its
signature and return shape do not change, so callers are unaffected.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from ..config import get_settings, load_companies_config
from ..domain.enums import CompanyCode, JobChangeType
from ..domain.exceptions import ConfigurationError, JobIntelError
from ..domain.models import CompanyRunResult, InvalidRecord, RunContext
from ..extraction.transport import TransportFactory
from ..logging import get_logger
from ..persistence import orm_models as m
from ..persistence.unit_of_work import unit_of_work

log = get_logger("services.ingestion")

_ADAPTER_BUILDERS = {}


def _build_wells_fargo(transport_factory: TransportFactory):
    from ..adapters.wells_fargo import WellsFargoAdapter

    return WellsFargoAdapter(transport_factory)


_ADAPTER_BUILDERS["wells_fargo"] = _build_wells_fargo


async def run_company_ingestion(company_key: str, dev_job_limit: int | None) -> CompanyRunResult:
    """Run one company's adapter end to end and persist normalized jobs.

    Idempotent: re-running never duplicates a job (unique company+source id),
    and a snapshot is only appended when the content hash actually changes.
    """
    builder = _ADAPTER_BUILDERS.get(company_key)
    if builder is None:
        raise ConfigurationError(
            f"No adapter wired for {company_key!r} yet "
            f"(available: {sorted(_ADAPTER_BUILDERS)})."
        )

    settings = get_settings()
    cfg = load_companies_config().get(company_key)
    transport_factory = TransportFactory(settings)
    adapter = builder(transport_factory)

    run_context = RunContext(
        company_code=CompanyCode(cfg.code),
        workflow_id=f"cli-adhoc-{uuid.uuid4().hex[:8]}",
        run_id=str(uuid.uuid4()),
        triggered_by="cli",
        dev_job_limit=dev_job_limit,
    )
    result = CompanyRunResult(company_code=CompanyCode(cfg.code), status="running")
    invalid: list[InvalidRecord] = []

    try:
        with unit_of_work() as uow:
            company_row = uow.companies.ensure(cfg.code, cfg.name, cfg.career_site_url)
            run_row = m.IngestionRun(
                workflow_id=run_context.workflow_id,
                company_id=company_row.id,
                trigger_type=run_context.triggered_by,
                status="running",
            )
            uow.session.add(run_row)
            uow.session.flush()

            async for discovered in adapter.discover_jobs(run_context):
                result.jobs_discovered += 1
                try:
                    raw = await adapter.fetch_job_detail(discovered, run_context)
                    normalized = adapter.normalize(raw)
                    result.jobs_fetched += 1
                except JobIntelError as exc:
                    result.jobs_failed += 1
                    invalid.append(
                        InvalidRecord(
                            source_job_id=discovered.source_job_id,
                            reason="fetch_or_normalize_error",
                            detail=str(exc),
                        )
                    )
                    continue

                if not normalized.has_valid_us_location:
                    invalid.append(
                        InvalidRecord(
                            source_job_id=normalized.source_job_id,
                            reason="no_valid_us_location",
                            detail=normalized.primary_location.location_text
                            if normalized.primary_location
                            else None,
                        )
                    )
                    continue

                _, change_type = uow.jobs.upsert(normalized, company_row, run_row.id)
                if change_type == JobChangeType.NEW:
                    result.jobs_inserted += 1
                elif change_type == JobChangeType.UNCHANGED:
                    result.jobs_unchanged += 1
                else:  # UPDATED or REOPENED
                    result.jobs_updated += 1

            result.complete_result_set = dev_job_limit is None
            result.status = "success"
            result.invalid_records = invalid

            run_row.status = result.status
            run_row.completed_at = datetime.utcnow()
            run_row.pages_discovered = 1
            run_row.jobs_discovered = result.jobs_discovered
            run_row.jobs_fetched = result.jobs_fetched
            run_row.jobs_inserted = result.jobs_inserted
            run_row.jobs_updated = result.jobs_updated
            run_row.jobs_unchanged = result.jobs_unchanged
            run_row.jobs_failed = result.jobs_failed
    finally:
        await adapter.aclose()

    log.info(
        "ingestion.company_run_complete",
        company=company_key,
        discovered=result.jobs_discovered,
        inserted=result.jobs_inserted,
        updated=result.jobs_updated,
        unchanged=result.jobs_unchanged,
        failed=result.jobs_failed,
        invalid=len(invalid),
    )
    return result
