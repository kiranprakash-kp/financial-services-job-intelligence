# Data Model

Sync SQLAlchemy 2.x; SQLite by default, PostgreSQL-ready via `DATABASE_URL`.
Alembic owns schema evolution (`migrations/`). See the ER diagram in
[`architecture.md`](architecture.md).

| Table | Purpose | Key points |
|---|---|---|
| `companies` | Company registry | unique `code` |
| `ingestion_runs` | One row per company run | run metrics + `status` (running/success/degraded/failed) |
| `jobs` | Latest known state of each job | **unique `(company_id, source_job_id)`**; `content_hash`, `is_active`, `first_seen_at`/`last_seen_at`/`closed_at`, `missed_crawls` (closure grace), `key_source`, `data_source` (live/synthetic) |
| `job_locations` | Multi-location postings | `is_primary` flag |
| `job_snapshots` | Historical content snapshots | append-only; one per *meaningful* change (deduped by `content_hash`) |
| `skills` | Canonical skill catalog | `category`, `aliases_json` |
| `job_skills` | Job↔skill with evidence | `source`, `confidence`, `evidence_text` |
| `role_taxonomy` | Role classification rules store | reviewable |
| `monthly_company_metrics` | Materialized monthly aggregates | unique `(company_id, year_month)` |

## Canonical key
Prefer the source's stable id (`key_source = source_id`). When absent, derive a
stable key from carefully normalized fields (`key_source = derived`) and record
how it was produced. Source URLs and raw source ids are always retained.

## Content hash
Computed from stable normalized fields — title, locations, employment type,
business unit, description, responsibilities, qualifications, salary — after
whitespace/formatting normalization. Never from timestamps or raw HTML.
