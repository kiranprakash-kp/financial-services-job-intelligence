"""Ingestion service: the one entry point the CLI, Temporal Activities, and
(later) Streamlit all call to run a company's adapter and persist results.

Split into two steps so Temporal can wrap each in its own Activity with its own
retry/idempotency boundary:

- `create_ingestion_run` — cheap, creates the company + run record, returns its id.
- `run_company_ingestion` — the extraction/normalize/persist loop; always leaves
  the run record in a terminal state (success/degraded/failed) before returning
  or raising, so a run is never left stuck at "running" even if this call itself
  ultimately fails after Temporal's retries are exhausted.

This module has no Temporal import — it stays usable directly from the CLI
(pre-Temporal manual runs) and from Temporal Activities alike.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import datetime

from ..config import get_settings, load_companies_config
from ..domain.enums import CompanyCode, JobChangeType
from ..domain.exceptions import ConfigurationError, JobIntelError
from ..domain.models import CompanyRunResult, InvalidRecord, RunContext
from ..extraction.transport import TransportFactory
from ..logging import get_logger
from ..persistence import orm_models as m
from ..persistence.unit_of_work import unit_of_work
from ..processing import lifecycle
from ..processing.role_classifier import RuleBasedRoleClassifier
from ..processing.skills import TaxonomySkillExtractor

log = get_logger("services.ingestion")

_role_classifier = RuleBasedRoleClassifier()
_skill_extractor = TaxonomySkillExtractor()

_ADAPTER_BUILDERS = {}


def _build_wells_fargo(transport_factory: TransportFactory):
    from ..adapters.wells_fargo import WellsFargoAdapter

    return WellsFargoAdapter(transport_factory)


def _build_goldman_sachs(transport_factory: TransportFactory):
    from ..adapters.goldman_sachs import GoldmanSachsAdapter

    return GoldmanSachsAdapter(transport_factory)


def _build_bny(transport_factory: TransportFactory):
    from ..adapters.bny import BNYAdapter

    return BNYAdapter(transport_factory)


_ADAPTER_BUILDERS["wells_fargo"] = _build_wells_fargo
_ADAPTER_BUILDERS["goldman_sachs"] = _build_goldman_sachs
_ADAPTER_BUILDERS["bny"] = _build_bny


def _require_adapter_builder(company_key: str):
    builder = _ADAPTER_BUILDERS.get(company_key)
    if builder is None:
        raise ConfigurationError(
            f"No adapter wired for {company_key!r} yet (available: {sorted(_ADAPTER_BUILDERS)})."
        )
    return builder


def create_ingestion_run(company_key: str, workflow_id: str, trigger_type: str) -> int:
    """Create the company (if new) and an ingestion_run row; return its id."""
    cfg = load_companies_config().get(company_key)
    with unit_of_work() as uow:
        company_row = uow.companies.ensure(cfg.code, cfg.name, cfg.career_site_url)
        run_row = m.IngestionRun(
            workflow_id=workflow_id,
            company_id=company_row.id,
            trigger_type=trigger_type,
            status="running",
        )
        uow.session.add(run_row)
        uow.session.flush()
        return run_row.id


async def run_company_ingestion(
    company_key: str,
    dev_job_limit: int | None,
    ingestion_run_id: int | None = None,
    workflow_id: str | None = None,
    on_progress: Callable[[int], None] | None = None,
) -> CompanyRunResult:
    """Run one company's adapter end to end and persist normalized jobs.

    Idempotent: re-running never duplicates a job (unique company+source id),
    and a snapshot is only appended when the content hash actually changes.

    If `ingestion_run_id` is None, a run record is created here too (the CLI's
    direct, pre-Temporal path). Either way, the run record always ends up in a
    terminal status — success, degraded, or failed — before this returns or
    the exception propagates.
    """
    builder = _require_adapter_builder(company_key)
    settings = get_settings()
    cfg = load_companies_config().get(company_key)
    transport_factory = TransportFactory(settings)
    adapter = builder(transport_factory)

    owns_run_record = ingestion_run_id is None
    run_id = ingestion_run_id or create_ingestion_run(
        company_key, workflow_id or f"cli-adhoc-{uuid.uuid4().hex[:8]}", "manual"
    )

    run_context = RunContext(
        company_code=CompanyCode(cfg.code),
        workflow_id=workflow_id or f"cli-adhoc-{uuid.uuid4().hex[:8]}",
        run_id=str(run_id),
        triggered_by="cli" if owns_run_record else "temporal",
        dev_job_limit=dev_job_limit,
    )
    result = CompanyRunResult(company_code=CompanyCode(cfg.code), status="running")
    invalid: list[InvalidRecord] = []
    error_summary: str | None = None

    # Company id only — never hold a DB transaction open across the network
    # calls below. SQLite allows exactly one writer at a time; with several
    # companies' workflows running concurrently (Milestone 5's whole point),
    # a transaction left open for the duration of a slow HTTP fetch starves
    # the others and they time out waiting for the lock ("database is
    # locked"). Each job's write below is therefore its own short-lived
    # transaction, opened only after all network I/O for that job is done.
    with unit_of_work() as uow:
        company_id = uow.companies.ensure(cfg.code, cfg.name, cfg.career_site_url).id

    seen_source_job_ids: set[str] = set()

    try:
        async for discovered in adapter.discover_jobs(run_context):
            result.jobs_discovered += 1
            seen_source_job_ids.add(discovered.source_job_id)
            if on_progress is not None:
                on_progress(result.jobs_discovered)
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

            # Deterministic, taxonomy/rule-based — no LLM involved or required.
            classification = _role_classifier.classify(normalized)
            normalized.role_family = classification.role_family
            normalized.role_subfamily = classification.role_subfamily
            normalized.classification_confidence = classification.confidence
            normalized.skills = _skill_extractor.extract(normalized)

            with unit_of_work() as uow:
                job_row, change_type = uow.jobs.upsert(normalized, company_id, run_id)
                uow.jobs.set_job_skills(job_row, normalized.skills)
            if change_type == JobChangeType.NEW:
                result.jobs_inserted += 1
            elif change_type == JobChangeType.UNCHANGED:
                result.jobs_unchanged += 1
            else:  # UPDATED or REOPENED
                result.jobs_updated += 1

        result.complete_result_set = dev_job_limit is None
        result.status = "success"
        result.invalid_records = invalid

        # Closure reconciliation only ever runs after a complete, healthy
        # crawl — never after a dev-limited/partial one, and never when this
        # run's count dropped sharply vs. the last success (that marks the
        # run DEGRADED and defers closure until reviewed, per spec).
        if result.complete_result_set:
            previous_count = lifecycle.previous_successful_discovered_count(company_id, run_id)
            if lifecycle.is_degraded(result.jobs_discovered, previous_count):
                result.status = "degraded"
            else:
                result.jobs_closed = lifecycle.reconcile_closures(company_id, seen_source_job_ids)
    except JobIntelError as exc:
        result.status = "failed"
        error_summary = str(exc)
        raise
    except BaseException as exc:
        # Catches asyncio.CancelledError (e.g. Temporal forcibly cancelling
        # this activity on a timeout) and anything else unexpected.
        # CancelledError subclasses BaseException, not Exception, so it would
        # otherwise skip the JobIntelError handler above and leave the run
        # record stuck at "running" forever, even though it's truly over.
        # Always re-raised immediately after — never swallowed.
        result.status = "failed"
        error_summary = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        await adapter.aclose()
        with unit_of_work() as uow:
            run_row = uow.session.get(m.IngestionRun, run_id)
            if run_row is not None:
                run_row.status = result.status
                run_row.completed_at = datetime.utcnow()
                run_row.pages_discovered = 1 if result.jobs_discovered else 0
                run_row.jobs_discovered = result.jobs_discovered
                run_row.jobs_fetched = result.jobs_fetched
                run_row.jobs_inserted = result.jobs_inserted
                run_row.jobs_updated = result.jobs_updated
                run_row.jobs_unchanged = result.jobs_unchanged
                run_row.jobs_failed = result.jobs_failed
                run_row.jobs_closed = result.jobs_closed
                run_row.error_summary = error_summary

    log.info(
        "ingestion.company_run_complete",
        company=company_key,
        discovered=result.jobs_discovered,
        inserted=result.jobs_inserted,
        updated=result.jobs_updated,
        unchanged=result.jobs_unchanged,
        failed=result.jobs_failed,
        closed=result.jobs_closed,
        invalid=len(invalid),
    )
    return result
