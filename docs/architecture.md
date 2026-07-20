# Architecture

## Milestone status
- [x] **M1** — repo, config, logging, DB schema + Alembic, domain models, Docker Temporal, README skeleton
- [x] **M2** — Playwright reconnaissance utility + three site reports (evidence-based)
- [ ] **M3** — first vertical slice (Wells Fargo → Temporal → SQLite → analytics → one Streamlit page)
- [ ] **M4** — BNY + Goldman Sachs adapters
- [ ] **M5** — Temporal workflows / activities / worker / schedule
- [ ] **M6** — lifecycle, skills, role classification, analytics, summaries
- [ ] **M7** — Streamlit pages, synthetic demo history, CSV exports
- [ ] **M8** — lint/type/test, README verification, limitations & roadmap

## Principles
Adapters are source-specific; domain models are source-independent; workflows
orchestrate deterministically; **Activities perform all side effects** (network,
DB, Playwright, filesystem); repositories own DB access; analytics query
normalized data; the UI never scrapes directly; runs are idempotent; partial
failure is visible; external models are optional; historical facts are never
overwritten; every reported metric has a defined query.

## Component architecture
```mermaid
flowchart TD
    CLI[Typer CLI] --> SVC[App services]
    UI[Streamlit] --> SVC
    SVC --> TC[Temporal client]
    TC --> WF[JobIntelligenceIngestionWorkflow]
    WF --> CWF[CompanyJobIngestionWorkflow x3]
    CWF --> ACT[Activities]
    ACT --> AD[Adapters: WF / GS / BNY]
    AD --> EX[extraction: transport, rate-limit, browser]
    ACT --> PR[processing: normalize, locations, hashing, skills, roles, lifecycle]
    ACT --> REPO[repositories]
    REPO --> DB[(SQLite / PostgreSQL)]
    AN[analytics] --> DB
    UI --> AN
```

## Temporal workflow
```mermaid
flowchart TD
    P[JobIntelligenceIngestionWorkflow] --> A[CompanyJobIngestionWorkflow WELLS_FARGO]
    P --> B[CompanyJobIngestionWorkflow GOLDMAN_SACHS]
    P --> C[CompanyJobIngestionWorkflow BNY]
    A --> A1[create run] --> A2[resolve strategy] --> A3[discover pages]
    A3 --> A4[fetch details batched] --> A5[normalize + validate US]
    A5 --> A6[upsert + snapshot] --> A7[classify + skills]
    A7 --> A8[lifecycle: new/updated/closed] --> A9[metrics] --> A10[finalize]
```

## Ingestion sequence
```mermaid
sequenceDiagram
    participant W as CompanyWorkflow
    participant Ad as Adapter
    participant Src as Career site
    participant DB as Database
    W->>Ad: discover_jobs(run_context)
    Ad->>Src: listing request (httpx / GraphQL / REST)
    Src-->>Ad: listing page(s)
    W->>Ad: fetch_job_detail(job)
    Ad->>Src: detail request
    Src-->>Ad: raw detail
    W->>Ad: normalize(raw)
    Ad-->>W: NormalizedJob
    W->>DB: upsert + snapshot (idempotent)
```

## Job lifecycle
```mermaid
stateDiagram-v2
    [*] --> NEW: source id unseen
    NEW --> UNCHANGED: hash identical
    NEW --> UPDATED: hash changed
    UNCHANGED --> UPDATED: hash changed
    UPDATED --> UNCHANGED: hash identical
    UNCHANGED --> CLOSED: absent from complete crawl (after grace)
    UPDATED --> CLOSED: absent from complete crawl (after grace)
    CLOSED --> REOPENED: source id reappears
    REOPENED --> UNCHANGED
```

## Data model
```mermaid
erDiagram
    companies ||--o{ jobs : has
    companies ||--o{ ingestion_runs : has
    companies ||--o{ monthly_company_metrics : has
    jobs ||--o{ job_locations : has
    jobs ||--o{ job_snapshots : has
    jobs ||--o{ job_skills : has
    skills ||--o{ job_skills : referenced_by
    ingestion_runs ||--o{ job_snapshots : produced
```

## Extraction strategy (verified 2026-07-20)
| Company | Method | Endpoint | Pagination | Stable id |
|---|---|---|---|---|
| Wells Fargo | Direct HTTP (server HTML + XML feed) | `/en/jobs/xml/`, `/en/jobs/…` | feed / `pg=` | `R-######` |
| Goldman Sachs | Direct HTTP GraphQL | `api-higher.gs.com/gateway/api/v1/graphql` (`GetRoles`) | `page.pageNumber` (0-idx) | `roleId` |
| BNY | Direct HTTP REST (Oracle CE) | `…/recruitingCEJobRequisitions` | `limit`/`offset` | `Id` |
