"""Command-line interface (Typer).

Milestone 1/2 implements `recon` and `initdb`. Later milestones fill in the
scrape / temporal / app / export commands. Every command that is not yet wired
fails loudly rather than pretending to work.
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
    """Run extraction directly (no Temporal yet — arrives in Milestone 5)."""
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
    if company == "all":
        typer.echo("goldman_sachs, bny: not yet wired (Milestone 4)")


@app.command(name="temporal-worker")
def temporal_worker() -> None:
    """Start a Temporal worker. Arrives in Milestone 5."""
    _not_yet("Milestone 5 (Temporal orchestration)")


@app.command(name="temporal-run")
def temporal_run(company: str = typer.Option("all")) -> None:
    """Trigger a one-time ingestion workflow. Arrives in Milestone 5."""
    _not_yet("Milestone 5 (Temporal orchestration)")


@app.command(name="app")
def streamlit_app() -> None:
    """Launch the Streamlit UI. Arrives in Milestone 7."""
    _not_yet("Milestone 7 (Streamlit UI)")


if __name__ == "__main__":
    app()
