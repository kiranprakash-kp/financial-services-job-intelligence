"""Command-line interface (Typer).

`scrape` runs extraction directly, in-process. `temporal-run` / `schedule-*`
orchestrate the same work through Temporal (retries, timeouts, history).
`app` (Streamlit UI) is not yet wired — arrives in Milestone 7.
"""

from __future__ import annotations

import asyncio

import typer

from .config import get_settings, load_companies_config
from .extraction.artifacts import dumps
from .logging import configure_logging, get_logger

app = typer.Typer(add_completion=False, help="Financial Services Job Intelligence POC")
log = get_logger("cli")


@app.command()
def version() -> None:
    """Print the package version."""
    from . import __version__

    typer.echo(__version__)


@app.command()
def initdb() -> None:
    """Create all tables directly (bootstrap/testing; Alembic owns real schema)."""
    from .persistence.database import create_all

    create_all()
    typer.echo(f"Initialized database at {get_settings().database_url}")


@app.command()
def recon(
    company: str = typer.Option(..., help="Company key (wells_fargo | goldman_sachs | bny)"),
    seconds: float = typer.Option(25.0, help="Max capture window in seconds"),
) -> None:
    """Run Playwright network reconnaissance against a company's start page.

    Requires `playwright install chromium`. Emits a sanitized summary of
    candidate job responses (secrets redacted).
    """
    configure_logging()
    from .extraction.network_discovery import run_recon

    settings = get_settings()
    load_companies_config().get(company)  # validate the key up front
    summary = asyncio.run(run_recon(company, settings, max_seconds=seconds))
    typer.echo(dumps(summary))


@app.command()
def companies() -> None:
    """List configured companies and their verified extraction strategy."""
    cfg = load_companies_config()
    typer.echo(f"recon_version: {cfg.recon_version}")
    for key, c in cfg.companies.items():
        flag = "active" if c.active else "inactive"
        typer.echo(f"  {key:16s} {c.code:14s} {c.extraction_strategy:12s} [{flag}]")


def _not_yet(milestone: str) -> None:
    raise typer.Exit(
        typer.echo(f"Not implemented yet — arrives in {milestone}.", err=True) or 1
    )


_WIRED_COMPANIES = ("wells_fargo", "goldman_sachs", "bny")


@app.command()
def scrape(
    company: str = typer.Option("all", help="Company key or 'all'"),
    limit: int = typer.Option(20, help="Dev job limit per company (0 = no limit)"),
) -> None:
    """Run extraction directly, bypassing Temporal (fast local iteration).

    For orchestrated runs with retries, timeouts, and history, use
    `temporal-run` (one-time) or the daily Schedule instead.
    """
    configure_logging()
    from .app.services import run_company_ingestion

    if company not in ("all", *_WIRED_COMPANIES):
        typer.echo(f"Unknown company: {company!r} (known: {_WIRED_COMPANIES})", err=True)
        raise typer.Exit(1)

    dev_job_limit = None if limit == 0 else limit
    targets = _WIRED_COMPANIES if company == "all" else (company,)

    for key in targets:
        result = asyncio.run(run_company_ingestion(key, dev_job_limit))
        typer.echo(
            f"{key}: discovered={result.jobs_discovered} fetched={result.jobs_fetched} "
            f"inserted={result.jobs_inserted} updated={result.jobs_updated} "
            f"unchanged={result.jobs_unchanged} failed={result.jobs_failed} "
            f"invalid={len(result.invalid_records)}"
        )


@app.command(name="temporal-worker")
def temporal_worker() -> None:
    """Start a Temporal worker (requires `docker compose up -d`)."""
    from .temporal.workers import main as run_worker_main

    run_worker_main()


@app.command(name="temporal-run")
def temporal_run(
    company: str = typer.Option("all", help="Company key or 'all'"),
    limit: int = typer.Option(20, help="Dev job limit per company (0 = no limit)"),
) -> None:
    """Start a one-time manual JobIntelligenceIngestionWorkflow execution."""
    from .temporal.schedules import run_once

    if company not in ("all", *_WIRED_COMPANIES):
        typer.echo(f"Unknown company: {company!r} (known: {_WIRED_COMPANIES})", err=True)
        raise typer.Exit(1)

    dev_job_limit = None if limit == 0 else limit
    targets: list[str] = list(_WIRED_COMPANIES) if company == "all" else [company]
    workflow_id = asyncio.run(run_once(targets, dev_job_limit))
    typer.echo(f"Started workflow {workflow_id!r} on task queue for companies: {targets}")


@app.command(name="schedule-create")
def schedule_create(
    cron: str = typer.Option("0 6 * * *", help="Cron expression (default: 06:00 UTC daily)"),
) -> None:
    """Create the daily ingestion Schedule (overlap policy: SKIP)."""
    from .temporal.schedules import create_schedule

    asyncio.run(create_schedule(cron=cron))
    typer.echo(f"Schedule created with cron {cron!r}")


@app.command(name="schedule-trigger")
def schedule_trigger() -> None:
    """Trigger the daily ingestion Schedule immediately."""
    from .temporal.schedules import trigger_schedule

    asyncio.run(trigger_schedule())
    typer.echo("Schedule triggered")


@app.command(name="schedule-pause")
def schedule_pause(note: str = typer.Option("paused via CLI")) -> None:
    """Pause the daily ingestion Schedule."""
    from .temporal.schedules import pause_schedule

    asyncio.run(pause_schedule(note=note))
    typer.echo("Schedule paused")


@app.command(name="schedule-unpause")
def schedule_unpause(note: str = typer.Option("unpaused via CLI")) -> None:
    """Unpause the daily ingestion Schedule."""
    from .temporal.schedules import unpause_schedule

    asyncio.run(unpause_schedule(note=note))
    typer.echo("Schedule unpaused")


@app.command(name="schedule-inspect")
def schedule_inspect() -> None:
    """Show the daily ingestion Schedule's current state."""
    from .temporal.schedules import describe_schedule

    typer.echo(dumps(asyncio.run(describe_schedule())))


@app.command(name="schedule-delete")
def schedule_delete() -> None:
    """Delete the daily ingestion Schedule."""
    from .temporal.schedules import delete_schedule

    asyncio.run(delete_schedule())
    typer.echo("Schedule deleted")


@app.command(name="app")
def streamlit_app() -> None:
    """Launch the Streamlit UI. Arrives in Milestone 7."""
    _not_yet("Milestone 7 (Streamlit UI)")


if __name__ == "__main__":
    app()
