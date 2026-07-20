# Financial Services Client Job Intelligence (POC)

Internal Capgemini Financial Services proof of concept that collects **public US
job openings** directly from the official career sites of **Wells Fargo, Goldman
Sachs, and BNY**, normalizes them into a common schema, tracks history, extracts
skills and role families, and surfaces company-level hiring intelligence.

> ⚠️ **Before running a full crawl**, confirm internal **legal, information-
> security, and acceptable-use approval**. This POC collects only public
> job-listing data, never bypasses access controls, and stays dev-limited by
> default. See [`docs/limitations.md`](docs/limitations.md).

---

## 1. Business problem
Capgemini FS serves multiple banking clients and needs timely intelligence about
those clients' public US job openings — who is hiring, for what roles and skills,
where, and how demand is trending — to guide recruiting and staffing decisions.

## 2. Architecture (high level)
```
CLI / Streamlit ─▶ Application services ─▶ Temporal workflows
                                              │  (deterministic orchestration)
                                              ▼
                                          Activities  ─▶ Adapters (per company)
                                          (all I/O)       ├─ Wells Fargo  (httpx: XML feed + HTML)
                                                          ├─ Goldman Sachs(httpx: GraphQL API)
                                                          └─ BNY          (httpx: Oracle REST)
                                              │
                          processing (normalize · locations · hashing · skills · roles · lifecycle)
                                              ▼
                                     SQLite (SQLAlchemy 2.x + Alembic)
                                              ▼
                                       analytics ─▶ Streamlit dashboards
```
Full detail: [`docs/architecture.md`](docs/architecture.md) ·
per-site evidence: [`docs/site_reconnaissance/`](docs/site_reconnaissance/).

### Verified extraction strategy (from live reconnaissance, 2026-07-20)
| Company | Primary | Detail | Pagination | Proxy |
|---|---|---|---|---|
| Wells Fargo | Direct `httpx` — `/en/jobs/xml/` feed + server HTML | Server HTML page | feed / next-page | No |
| Goldman Sachs | Direct `httpx` — GraphQL `GetRoles` @ `api-higher.gs.com` | role detail | `page.pageNumber` (0-idx) | No |
| BNY | Direct `httpx` — Oracle `recruitingCEJobRequisitions` REST | detail REST | `limit`/`offset` | No |

All three work over direct HTTP; Bright Data proxy support is **scaffolded but
disabled** (future production option only).

## 3. Prerequisites
- Python 3.11+
- [`uv`](https://docs.astral.sh/uv/) (`pip install uv`)
- Docker (for the local Temporal stack)

## 4. Local installation
```bash
uv sync --extra dev
uv run playwright install chromium      # for reconnaissance / browser fallback
cp .env.example .env                     # adjust as needed
```

## 5. Start Temporal (local)
```bash
docker compose up -d                     # Temporal gRPC :7233, UI http://localhost:8080
```

## 6. Database migration
```bash
uv run alembic upgrade head              # or: uv run job-intel initdb  (bootstrap)
```

## 7. Reconnaissance
```bash
uv run job-intel companies
uv run job-intel recon --company wells_fargo
uv run job-intel recon --company goldman_sachs
uv run job-intel recon --company bny
```

## 8. Worker startup
```bash
uv run job-intel temporal-worker          # requires `docker compose up -d`
```

## 9. Manual ingestion (one-time, orchestrated)
```bash
uv run job-intel temporal-run --company all --limit 20
uv run job-intel scrape --company wells_fargo --limit 20   # or: direct, no Temporal
```

## 10. Schedule (daily, overlap-safe)
```bash
uv run job-intel schedule-create                      # 06:00 UTC daily, overlap policy: SKIP
uv run job-intel schedule-trigger                      # run it right now
uv run job-intel schedule-inspect                      # paused state, recent/next runs
uv run job-intel schedule-pause
uv run job-intel schedule-unpause
uv run job-intel schedule-delete
```

## 11. Streamlit
```bash
uv run job-intel seed-demo --months 6   # optional: backfill synthetic trend history
uv run job-intel app                    # launches http://localhost:8501
```
Seven pages: Executive Overview (Home), Company Intelligence, Job Explorer,
Skill Intelligence, Monthly Comparison, Ask the Data, Pipeline Operations.
Synthetic demo rows are always labeled 🟡 SYNTHETIC DEMO DATA and never
overwrite real (🟢 LIVE) data for the same period.

```bash
uv run job-intel export --format csv    # writes to data/exports/
```

## 12. Tests
```bash
uv run pytest                            # unit + adapter (fixtures, no live sites)
RUN_LIVE_SCRAPER_TESTS=true uv run pytest -m live   # opt-in live smoke test
```

## 13. Troubleshooting
- **`playwright` errors during recon** → run `uv run playwright install chromium`.
- **Temporal connection refused** → ensure `docker compose up -d` is healthy.
- **Workflow stuck, Temporal UI shows "No Workers Running"** → `job-intel
  temporal-worker` isn't running (or was closed). Start it in its own
  terminal — it must stay running to pick up work from the task queue.
- **`sqlite3.OperationalError: database is locked`** → shouldn't happen as of
  the WAL-mode + short-transaction fix (see `persistence/database.py` and
  `app/services.py`); if you see it, check nothing else has `data/app.db` open
  (a stray DB browser tool, etc.).
- **Docker Desktop errors like `open //./pipe/dockerDesktopLinuxEngine`** →
  Docker Desktop itself isn't running yet; start it and wait for the whale
  icon to show "running" before retrying `docker compose up -d`.

## 14. Known limitations & 15. Compliance
See [`docs/limitations.md`](docs/limitations.md). Career sites and public
endpoints can change; disappearance of a posting does not prove a role was
filled; recruiting-priority scores are decision-support indicators, not
predictions.

## 16. Roadmap (next steps)
PostgreSQL backend for heavier write concurrency · optional LLM skill/summary
extractors · approved Bright Data proxy transport · broader company coverage ·
period-over-period growth folded into the narrative summaries · a reviewable
role-classification evidence table (`role_taxonomy` is reserved for this,
currently unused) · pinning BNY's exact Candidate Experience `siteNumber` and
detail-URL pattern with production-grade certainty.

---
Built milestone-by-milestone; see the milestone status in
[`docs/architecture.md`](docs/architecture.md).
