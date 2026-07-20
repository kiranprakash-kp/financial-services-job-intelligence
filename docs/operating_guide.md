# Operating Guide

## Setup
```bash
uv sync --extra dev
uv run playwright install chromium
cp .env.example .env
docker compose up -d          # Temporal :7233, UI http://localhost:8080
uv run alembic upgrade head
```

## Everyday commands
```bash
uv run job-intel companies                         # show configured sources
uv run job-intel recon --company goldman_sachs     # sanitized network recon
uv run job-intel initdb                            # bootstrap tables (tests)
uv run pytest                                       # unit + adapter tests
RUN_LIVE_SCRAPER_TESTS=true uv run pytest -m live   # opt-in live smoke test
```

## Development mode
Keep runs fast and polite: `DEV_JOB_LIMIT=20`, `DEV_PAGE_LIMIT=2`,
`HEADLESS=true`. Production-like local mode removes the limits. HTTP concurrency
per domain defaults to 2, browser page concurrency to 1, with a configurable
inter-request delay and `Retry-After` respected.

## Later milestones (stubs today, fail loudly)
```bash
uv run job-intel temporal-worker                   # M5
uv run job-intel temporal-run --company all        # M5
uv run job-intel scrape --company wells_fargo --limit 20   # M3
uv run job-intel app                               # M7 (Streamlit)
uv run job-intel export --format csv               # M7
```

## Data-quality gate
Before a company run is marked success, thresholds are checked (nonzero count,
duplicate-id ratio, missing-title/description rates, detail-fetch success,
pagination completeness, deviation vs previous run). A drop >40% from the last
successful run marks the run **DEGRADED** and **suppresses closure
reconciliation** until reviewed.

## Safety
Domain allowlist per company; stop-and-report on access denial/WAF/CAPTCHA; no
evasion; proxy disabled and approval-gated. Confirm legal/infosec/acceptable-use
approval before any full crawl.
