You are a senior Python data-platform engineer, web-extraction engineer, Temporal architect, and product-oriented AI engineer.

Build a working local proof of concept named:

# Financial Services Client Job Intelligence

The product is being developed internally for Capgemini’s Financial Services unit. Capgemini serves multiple banking clients and needs timely intelligence about those clients’ public US job openings.

The initial companies are:

1. Wells Fargo
2. Goldman Sachs
3. BNY

## Business objective

Create a local application that periodically collects public United States job openings directly from the official career sites of these three companies.

The application must:

1. Navigate and paginate through each company’s job search.
2. collect every available US job listing;
3. open or request each job-detail page;
4. normalize the records into a common schema;
5. save current and historical data in a local database;
6. identify newly opened, changed, still-open, and apparently closed roles;
7. extract skills and role categories;
8. produce company-specific hiring intelligence;
9. allow internal users to filter, search, summarize, and ask predefined analytical questions;
10. run both manually and periodically through Temporal.

The users include:

* recruiters;
* staffing leaders;
* account executives;
* delivery leaders;
* business leaders;
* data and engineering reviewers.

This is a POC, but implement it with clear boundaries so it can grow into a production application.

## Starting career pages

Use these exact URLs as the initial entry points:

```text
Wells Fargo:
https://www.wellsfargojobs.com/en/jobs/?search=&country=United+States+of+America&pagesize=20#results

Goldman Sachs:
https://higher.gs.com/results?LOCATION=Arizona|Albany|New%20York|Atlanta|Boston|Chicago|Dallas|Houston|Richardson|Deerfield|Detroit|Draper|Irving|Jersey%20City|Los%20Angeles|Miami|West%20Palm%20Beach|Newport%20Beach|San%20Francisco|Philadelphia|Pittsburgh|Salt%20Lake%20City|Seattle|Washington|Wilmington&page=1&sort=RELEVANCE

BNY:
https://eofe.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/BNY-Careers/jobs?lastSelectedFacet=LOCATIONS&mode=location&selectedLocationsFacet=300000000378743
```

Only collect jobs located in the United States.

Do not scrape LinkedIn, Indeed, Google Jobs, or other aggregators. The official career sites are the sources of truth.

---

# Critical implementation strategy

Do not immediately hard-code CSS selectors and hope they work.

Implement the project in the following order:

## Phase 1: Site reconnaissance

For each website:

1. Load the starting page with Playwright.
2. record browser requests and responses associated with:

   * job search;
   * pagination;
   * filters;
   * job-detail retrieval.
3. inspect JSON, GraphQL, XHR, Fetch, and document responses;
4. determine whether the site exposes a stable public endpoint used by its own browser UI;
5. save a sanitized reconnaissance report under:

```text
docs/site_reconnaissance/
```

Create one Markdown report per company containing:

* rendering type observed;
* listing request method and URL pattern;
* request payload or query parameters;
* response content type;
* pagination mechanism;
* job-detail mechanism;
* required public headers;
* stable job identifier;
* sample sanitized response structure;
* recommended extraction strategy;
* fallback strategy;
* risks and uncertainties.

Never store cookies, authorization tokens, session identifiers, personal information, or secret headers in the report.

Prefer this strategy in order:

1. public JSON/XHR endpoint used by the career page;
2. server-rendered HTML through `httpx`;
3. Playwright DOM extraction.

Do not use a private, authenticated, employee-only, applicant-only, or undocumented administrative API.

Do not bypass CAPTCHA, authentication, bot protection, access controls, or rate limits.

If a site blocks automated access, fail clearly and record the reason. Do not add stealth plugins, CAPTCHA solvers, fingerprint spoofing, proxy rotation, or evasion techniques.

## Phase 2: Build extraction adapters

Create a common adapter interface and one implementation per company.

Suggested interface:

```python
from typing import Protocol, AsyncIterator

class JobSourceAdapter(Protocol):
    company_code: str

    async def discover_jobs(
        self,
        run_context: "RunContext",
    ) -> AsyncIterator["DiscoveredJob"]:
        ...

    async def fetch_job_detail(
        self,
        discovered_job: "DiscoveredJob",
        run_context: "RunContext",
    ) -> "RawJobDetail":
        ...

    def normalize(
        self,
        raw_job: "RawJobDetail",
    ) -> "NormalizedJob":
        ...
```

Implement:

```text
WellsFargoAdapter
GoldmanSachsAdapter
BNYAdapter
```

Each adapter must encapsulate:

* source URL;
* request strategy;
* pagination;
* location filtering;
* detail retrieval;
* source-specific parsing;
* source-specific identifiers;
* retryable versus non-retryable errors.

Do not spread company-specific selectors or JSON paths throughout the codebase.

## Phase 3: Temporal orchestration

Temporal is mandatory.

Use the Temporal Python SDK and create a parent workflow such as:

```text
JobIntelligenceIngestionWorkflow
```

The parent workflow receives:

```python
class IngestionRequest(BaseModel):
    companies: list[str]
    country: str = "United States"
    triggered_by: str
    full_refresh: bool = False
    run_date: datetime | None = None
```

The workflow should fan out into one child workflow per company:

```text
CompanyJobIngestionWorkflow
```

Suggested orchestration:

```text
JobIntelligenceIngestionWorkflow
    ├── CompanyJobIngestionWorkflow(WELLS_FARGO)
    ├── CompanyJobIngestionWorkflow(GOLDMAN_SACHS)
    └── CompanyJobIngestionWorkflow(BNY)
```

Each company workflow should run Activities for:

1. create ingestion-run record;
2. discover listing pages or API pages;
3. collect job references;
4. fetch job details in bounded batches;
5. normalize fields;
6. validate US location;
7. upsert current jobs;
8. create job snapshots;
9. classify role family;
10. extract skills;
11. calculate new, updated, unchanged, and closed jobs;
12. update aggregate metrics;
13. finalize the ingestion run.

Keep all network calls, database operations, Playwright operations, filesystem access, and nondeterministic processing inside Activities.

Workflows must contain only deterministic orchestration logic.

### Temporal requirements

Configure:

* Activity start-to-close timeouts;
* schedule-to-close timeouts where useful;
* retry policies with exponential backoff;
* maximum retry attempts;
* non-retryable exception types;
* bounded concurrency;
* heartbeats for long pagination or detail-fetch Activities;
* unique workflow IDs;
* idempotent Activities;
* cancellation handling;
* partial-company failure reporting.

Use separate task queues where useful:

```text
job-orchestration
job-http-extraction
job-browser-extraction
job-processing
```

For a local POC, it is acceptable to begin with fewer task queues, but preserve clean module boundaries.

Create a Temporal Schedule that runs once daily.

Use an overlap policy that prevents two full ingestion runs from running simultaneously. Provide commands to:

* create the schedule;
* trigger it immediately;
* pause it;
* unpause it;
* inspect it;
* delete it.

Also provide a CLI command that starts a one-time manual workflow.

Do not use a regular Python cron library as the primary scheduler.

## Phase 4: Persistence and historical tracking

Use:

* SQLite by default;
* SQLAlchemy 2.x;
* Alembic migrations.

The database URL must be configurable so the same code can later use PostgreSQL.

Suggested tables:

### `companies`

```text
id
code
name
career_site_url
active
created_at
updated_at
```

### `ingestion_runs`

```text
id
workflow_id
company_id
trigger_type
started_at
completed_at
status
pages_discovered
jobs_discovered
jobs_fetched
jobs_inserted
jobs_updated
jobs_unchanged
jobs_closed
jobs_failed
error_summary
metadata_json
```

### `jobs`

Represents the latest known state of each job.

```text
id
company_id
source_job_id
canonical_key
title
normalized_title
role_family
role_subfamily
employment_type
experience_level
business_unit
department
location_text
city
state
country
workplace_type
salary_min
salary_max
salary_currency
salary_period
description_text
qualifications_text
responsibilities_text
posting_url
source_posted_at
first_seen_at
last_seen_at
closed_at
is_active
content_hash
raw_payload_json
created_at
updated_at
```

Add a unique constraint on:

```text
(company_id, source_job_id)
```

If a source job ID is unavailable, derive a stable fallback canonical key from carefully normalized fields, but store how the key was produced.

### `job_locations`

Use this table when one posting has multiple locations.

```text
id
job_id
location_text
city
state
country
is_primary
```

### `job_snapshots`

Store one historical snapshot when meaningful content changes.

```text
id
job_id
ingestion_run_id
captured_at
title
location_text
description_text
content_hash
change_type
changed_fields_json
```

Do not create duplicate snapshots when the content hash has not changed.

### `skills`

```text
id
canonical_name
category
aliases_json
```

### `job_skills`

```text
job_id
skill_id
source
confidence
evidence_text
```

### `role_taxonomy`

```text
id
role_family
role_subfamily
keywords_json
```

### `monthly_company_metrics`

Optional materialized aggregate table:

```text
company_id
year_month
active_jobs
new_jobs
closed_jobs
updated_jobs
technology_jobs
operations_jobs
risk_jobs
data_ai_jobs
top_skills_json
top_locations_json
calculated_at
```

## Job lifecycle rules

A job can be:

```text
NEW
UPDATED
UNCHANGED
CLOSED
REOPENED
```

Rules:

* NEW: source job ID has never been seen.
* UPDATED: job exists and the normalized meaningful-content hash changed.
* UNCHANGED: job exists and meaningful content is identical.
* CLOSED: a previously active job is absent from a successful complete crawl.
* REOPENED: a previously closed source job ID appears again.

Do not mark jobs closed after an incomplete or failed crawl.

Only perform closure reconciliation when:

* all listing pages were successfully processed;
* the run passed minimum validation thresholds;
* the adapter confirms that a complete result set was retrieved.

Add a configurable closure grace period, such as two successful consecutive runs, to avoid false closures caused by temporary source failures.

## Normalized content hash

Generate the content hash from stable normalized fields, not timestamps or raw HTML.

Suggested fields:

```text
title
locations
employment_type
business_unit
description
responsibilities
qualifications
salary
```

Normalize whitespace and harmless formatting differences before hashing.

## US location filtering

Do not depend only on the URL filter.

Validate each result after extraction.

Support:

* US state names;
* two-letter state abbreviations;
* District of Columbia;
* multiple-location jobs;
* “United States”;
* remote-US postings;
* city/state strings;
* malformed location strings.

Exclude clearly non-US-only jobs.

When a posting has both US and non-US locations, retain it and store only or separately mark its US locations, while preserving the original location text.

Create tests for edge cases such as:

```text
New York, NY
Jersey City, NJ
Remote - United States
United States
New York / London
Dallas, TX; Bengaluru, India
Washington, DC
Multiple Locations
```

## Pagination requirements

Support these possible mechanisms:

* page query parameter;
* offset and limit;
* cursor;
* “load more” button;
* infinite scroll;
* POST-based search payload;
* GraphQL pagination.

Do not assume that page count remains constant during a crawl.

Maintain a set of discovered source job IDs to prevent duplicates and infinite pagination.

Stop pagination when one of the following is true:

* endpoint reports no next page;
* returned result list is empty;
* cursor repeats;
* page signature repeats;
* maximum safety-page limit is reached;
* configured job limit for development mode is reached.

Log the exact stop reason.

## HTTP and browser behavior

Implement a shared rate limiter.

Initial conservative defaults:

```text
HTTP concurrency per domain: 2
Browser page concurrency per domain: 1
Delay between page operations: configurable
Request timeout: configurable
```

Use a descriptive user agent identifying the internal POC where appropriate.

Use retries only for transient errors such as:

```text
408
429
500
502
503
504
connection reset
temporary DNS failure
```

Respect `Retry-After` when present.

Do not retry indefinitely.

Distinguish:

* transient source error;
* parsing/schema error;
* access-denied error;
* validation error;
* configuration error;
* database error.

Capture HTML or JSON debug artifacts only when configured. Redact cookies, query secrets, headers, and personal information.

For Playwright:

* use Chromium;
* use async APIs;
* wait for concrete page or network conditions, not arbitrary long sleeps;
* use resilient role/text/data-attribute locators where DOM extraction is needed;
* capture a screenshot and sanitized HTML on parsing failure;
* intercept network responses during reconnaissance;
* close pages, contexts, and browsers reliably;
* allow headed mode through configuration for debugging.

## Data models

Use Pydantic models for boundaries such as:

```text
DiscoveredJob
RawJobDetail
NormalizedJob
NormalizedLocation
ExtractedSkill
IngestionRequest
CompanyRunResult
RunContext
```

Validate required fields.

A usable normalized job must at minimum contain:

```text
company
source_job_id or canonical fallback key
title
posting_url
at least one valid US location or explicit remote-US status
description or sufficient detail text
```

Store invalid records in the run error report rather than silently discarding them.

## Skill extraction

For the first POC, implement deterministic extraction before adding an LLM.

Create a configurable taxonomy file such as:

```text
config/skills.yml
```

Include categories such as:

### Programming

```text
Python
Java
C#
C++
JavaScript
TypeScript
Scala
Go
SQL
Shell
```

### Data and AI

```text
Machine Learning
Generative AI
LLM
NLP
RAG
Data Science
Pandas
Spark
Databricks
Snowflake
Kafka
Airflow
TensorFlow
PyTorch
MLOps
```

### Cloud and platform

```text
AWS
Azure
GCP
Docker
Kubernetes
Terraform
OpenShift
Linux
CI/CD
```

### Databases

```text
Oracle
PostgreSQL
SQL Server
MySQL
MongoDB
Redis
Cassandra
```

### Financial-services domain

```text
Risk Management
Market Risk
Credit Risk
Model Risk
Operational Risk
Regulatory Reporting
AML
KYC
Fraud
Payments
Treasury
Securities
Asset Management
Wealth Management
Investment Banking
Capital Markets
Trade Surveillance
```

### Enterprise and delivery

```text
Agile
Scrum
Product Management
Business Analysis
Project Management
Stakeholder Management
```

Support aliases, for example:

```text
Amazon Web Services -> AWS
Google Cloud Platform -> GCP
K8s -> Kubernetes
Large Language Models -> LLM
Anti-Money Laundering -> AML
Know Your Customer -> KYC
```

Avoid naïve substring matches that create false positives. Use normalized phrase boundaries and aliases.

Store short evidence snippets for each extracted skill.

Build the skill extraction behind an interface:

```python
class SkillExtractor(Protocol):
    def extract(self, job: NormalizedJob) -> list[ExtractedSkill]:
        ...
```

Implement:

```text
TaxonomySkillExtractor
```

Also create, but do not require, an optional:

```text
LLMSkillExtractor
```

The LLM extractor must be disabled by default and configured through environment variables. The application must work fully without an LLM or API key.

Do not send raw data to an external model unless explicitly enabled.

## Role classification

Implement explainable rule-based role classification.

Initial role families:

```text
Software Engineering
Data and AI
Cloud and Infrastructure
Cybersecurity
Risk and Compliance
Finance and Accounting
Operations
Product Management
Project and Program Management
Business Analysis
Sales and Relationship Management
Human Resources
Legal
Audit
Other
```

Use title first and job description second.

Return:

```text
role_family
role_subfamily
classification_confidence
matched_evidence
```

Store classifications so they can later be reviewed.

## Company-level intelligence

Every metric and summary must support filtering by company.

The application must answer questions such as:

1. How many active US jobs does each company currently have?
2. How many jobs were newly observed this week or month?
3. Which roles are growing at each company?
4. Which jobs disappeared or closed this month?
5. What are the top role families at Wells Fargo?
6. What are the top skills requested by Goldman Sachs?
7. What skills are rising at BNY?
8. Which US cities and states have the most openings?
9. Which job titles occur most frequently?
10. Which technology stacks appear together?
11. Which skills are common across all three companies?
12. Which skills are company-specific?
13. What role and skill combinations should Capgemini prioritize for recruiting?
14. What roles appear to have sustained demand rather than one-time demand?
15. Which roles have many postings but limited internal candidate supply, once an internal supply dataset is added later?

For the current POC, question 15 should be shown as a future extension because no Capgemini supply dataset is yet available.

## Recruiting-priority score

Create an explainable POC scoring model, calculated separately for each company and role family.

Example:

```text
priority_score =
    0.35 * normalized_active_opening_volume
  + 0.25 * normalized_recent_growth
  + 0.20 * normalized_persistence
  + 0.20 * normalized_skill_concentration
```

Definitions:

* active opening volume: current number of active jobs;
* recent growth: new jobs in the selected period compared with the previous period;
* persistence: number of distinct collection periods in which demand appears;
* skill concentration: how consistently a skill set occurs within the role family.

Do not present this as a scientifically validated prediction.

Label it:

```text
POC Recruiting Priority Indicator
```

Show the score components and methodology in the UI.

Never claim that Capgemini “must” recruit a role solely from this score. Use language such as:

```text
Potential recruiting focus
Observed demand signal
Suggested area for review
```

## Application UI

Build a Streamlit application.

Jupyter may be included for exploratory analysis, but it is not the primary presentation layer.

Required pages:

### 1. Executive Overview

Show:

* total active jobs;
* new jobs this month;
* jobs closed this month;
* number of companies;
* most in-demand role families;
* most in-demand skills;
* top US locations;
* last successful refresh;
* data-quality status.

Include company filters and date filters.

### 2. Company Intelligence

The user selects one company.

Show:

* active jobs;
* jobs opened by week or month;
* jobs closed by week or month;
* top role families;
* top normalized titles;
* top skills;
* top locations;
* recruiting-priority indicators;
* company-specific narrative summary generated from deterministic metrics.

### 3. Job Explorer

Support:

* keyword search;
* company;
* active/closed;
* role family;
* skill;
* state;
* city;
* workplace type;
* first-seen date;
* source-posted date where available.

Display the official source link.

### 4. Skill Intelligence

Show:

* skill frequency by company;
* role-to-skill matrix;
* skills trending upward;
* frequently co-occurring skills;
* common versus company-specific skills;
* period-over-period change.

### 5. Monthly Comparison

Let the user select two periods.

Show:

* new roles;
* closed roles;
* net change;
* role-family change;
* skill change;
* location change;
* company-by-company comparison.

### 6. Ask the Data

Do not build an unrestricted autonomous SQL agent in the first POC.

Implement a safe catalog of parameterized analytical questions.

Examples:

```text
What are the top skills for [company] in [period]?
Which role families grew most for [company]?
What jobs were newly opened for [company] this month?
What recruiting areas should be reviewed for [company]?
Which skills occur across all three companies?
```

Map each question to tested SQL or analytics functions.

Optionally allow a local or hosted LLM to turn the structured result into a natural-language summary, but:

* the analytics result remains the source of truth;
* include record counts and date scope;
* prohibit the LLM from inventing statistics;
* make the LLM optional;
* show a deterministic template summary when no LLM is configured.

### 7. Pipeline Operations

Show:

* latest Temporal workflow runs;
* status per company;
* start and end time;
* jobs discovered;
* inserted;
* updated;
* unchanged;
* closed;
* failed;
* error summaries;
* last successful run;
* manual refresh control.

The manual refresh button should trigger a Temporal workflow through an application service, not call scrapers directly.

## Deterministic narrative summaries

Build summaries directly from metrics.

Example:

```text
During July 2026, Wells Fargo had 420 observed active US openings.
Software Engineering represented 28% of openings, followed by Risk and
Compliance at 17%. Java, SQL, and AWS were the most frequently observed
technical skills. Charlotte, New York, and Dallas were the leading locations.
Based on opening volume, recent growth, and persistence, Software Engineering
and Risk Technology are suggested areas for recruiter review.
```

All values must come from database queries.

Include:

* company;
* reporting period;
* last successful collection time;
* data completeness warning when relevant.

## Project structure

Create a clean repository similar to:

```text
financial-services-job-intelligence/
├── README.md
├── pyproject.toml
├── uv.lock
├── .env.example
├── .gitignore
├── docker-compose.yml
├── alembic.ini
├── Makefile
├── config/
│   ├── companies.yml
│   ├── skills.yml
│   ├── roles.yml
│   └── logging.yml
├── docs/
│   ├── architecture.md
│   ├── data_model.md
│   ├── operating_guide.md
│   ├── limitations.md
│   └── site_reconnaissance/
├── notebooks/
│   └── 01_job_market_analysis.ipynb
├── src/
│   └── job_intelligence/
│       ├── __init__.py
│       ├── config.py
│       ├── cli.py
│       ├── logging.py
│       ├── domain/
│       │   ├── models.py
│       │   ├── enums.py
│       │   └── exceptions.py
│       ├── adapters/
│       │   ├── base.py
│       │   ├── wells_fargo.py
│       │   ├── goldman_sachs.py
│       │   └── bny.py
│       ├── extraction/
│       │   ├── http_client.py
│       │   ├── browser.py
│       │   ├── network_discovery.py
│       │   ├── rate_limit.py
│       │   └── artifacts.py
│       ├── temporal/
│       │   ├── workflows.py
│       │   ├── activities.py
│       │   ├── workers.py
│       │   ├── schedules.py
│       │   └── client.py
│       ├── persistence/
│       │   ├── database.py
│       │   ├── orm_models.py
│       │   ├── repositories.py
│       │   └── unit_of_work.py
│       ├── processing/
│       │   ├── normalization.py
│       │   ├── locations.py
│       │   ├── hashing.py
│       │   ├── skills.py
│       │   ├── role_classifier.py
│       │   └── lifecycle.py
│       ├── analytics/
│       │   ├── metrics.py
│       │   ├── trends.py
│       │   ├── priority.py
│       │   ├── questions.py
│       │   └── summaries.py
│       └── app/
│           ├── Home.py
│           ├── services.py
│           └── pages/
├── migrations/
├── tests/
│   ├── fixtures/
│   ├── unit/
│   ├── integration/
│   └── temporal/
└── data/
    ├── app.db
    ├── exports/
    └── debug/
```

Do not commit generated database files, raw debug payloads, secrets, or browser profiles.

## CLI

Provide commands similar to:

```bash
uv run job-intel recon --company wells_fargo
uv run job-intel recon --company goldman_sachs
uv run job-intel recon --company bny

uv run job-intel scrape --company wells_fargo --limit 20
uv run job-intel scrape --company all

uv run job-intel temporal-worker
uv run job-intel temporal-run --company all
uv run job-intel schedule-create
uv run job-intel schedule-trigger
uv run job-intel schedule-pause
uv run job-intel schedule-unpause
uv run job-intel schedule-delete

uv run job-intel app
uv run job-intel export --format csv
```

The exact command framework may use Typer.

## Development mode

Add configuration:

```text
DEV_JOB_LIMIT
DEV_PAGE_LIMIT
HEADLESS
CAPTURE_DEBUG_ARTIFACTS
DATABASE_URL
TEMPORAL_ADDRESS
TEMPORAL_NAMESPACE
TEMPORAL_TASK_QUEUE
SCRAPE_REQUEST_TIMEOUT_SECONDS
SCRAPE_MAX_RETRIES
SCRAPE_DOMAIN_CONCURRENCY
```

Development mode must allow collecting only 10–20 jobs per company so iteration is fast.

Production-like local mode should remove the limit.

## Logging and observability

Use structured logs containing:

```text
timestamp
level
workflow_id
run_id
company
activity
page_number
source_job_id
event
duration_ms
attempt
status
error_type
```

Never log complete descriptions by default.

Record metrics such as:

```text
pages_processed
jobs_discovered
jobs_fetched
jobs_validated
jobs_inserted
jobs_updated
jobs_unchanged
jobs_closed
jobs_failed
HTTP status counts
request duration
parsing failure count
```

Expose these in logs and the Pipeline Operations page.

Use Temporal UI for workflow inspection.

## Data-quality checks

Before marking a company run successful, validate:

* nonzero job count unless the source explicitly confirms zero;
* duplicate source ID ratio;
* missing title rate;
* missing description rate;
* invalid-US-location rate;
* detail-fetch success rate;
* unexpected field changes;
* pagination completeness;
* large count deviation from the previous successful run.

A large sudden decrease must create a warning and prevent automatic closure reconciliation until reviewed.

Suggested configurable threshold:

```text
If current discovered count falls by more than 40% from the previous
successful run, classify the run as DEGRADED and do not mark missing jobs closed.
```

## Exports

Support CSV export of normalized jobs and aggregated insights.

Do not export raw payloads by default.

Create:

```text
active_jobs_<timestamp>.csv
company_skill_summary_<timestamp>.csv
monthly_role_summary_<timestamp>.csv
```

## Testing requirements

Write tests before considering the POC complete.

### Unit tests

Test:

* title normalization;
* whitespace cleanup;
* location parsing;
* US filtering;
* multi-location parsing;
* salary parsing;
* content hashing;
* deterministic skill extraction;
* alias handling;
* false-positive skill matching;
* role classification;
* lifecycle transition rules;
* recruiting-priority score;
* deterministic summaries.

### Adapter tests

Use saved sanitized HTML or JSON fixtures.

Do not hit live websites in normal unit tests.

Test:

* first page;
* pagination;
* duplicate jobs;
* empty response;
* changed response shape;
* missing optional fields;
* malformed job;
* non-US result;
* multiple locations;
* transient HTTP failure;
* permanent access denial.

### Temporal tests

Use Temporal’s testing facilities where practical.

Test:

* successful multi-company run;
* one company fails while others succeed;
* retryable Activity error;
* non-retryable parsing error;
* cancellation;
* workflow idempotency;
* closure reconciliation skipped after degraded crawl.

### Integration test

Provide an opt-in live smoke test controlled by an environment variable:

```text
RUN_LIVE_SCRAPER_TESTS=true
```

The live smoke test should fetch only one page or a small number of jobs and use conservative traffic.

## Documentation

Create a strong README containing:

1. business problem;
2. architecture;
3. prerequisites;
4. local installation;
5. Temporal startup;
6. Playwright browser installation;
7. database migration;
8. reconnaissance commands;
9. worker startup;
10. manual ingestion;
11. schedule creation;
12. Streamlit startup;
13. test commands;
14. troubleshooting;
15. known limitations;
16. compliance considerations;
17. next-step roadmap.

Also create:

### `docs/architecture.md`

Include Mermaid diagrams for:

* component architecture;
* Temporal workflow;
* ingestion sequence;
* job lifecycle;
* data model.

### `docs/limitations.md`

Explicitly state:

* career sites may change;
* public endpoints may change;
* some posted dates may be unavailable;
* first-seen date is not always equal to source-posted date;
* disappearance does not prove a role was filled;
* recruiting-priority scores are decision-support indicators, not predictions;
* skill extraction can produce false positives or negatives;
* internal legal and information-security approval is required before wider deployment.

## Security and compliance constraints

This project operates only on public job-listing information.

Do not collect:

* applicant information;
* employee profiles;
* names of applicants;
* email addresses;
* phone numbers;
* application form data;
* session data;
* authentication data;
* private APIs.

Do not:

* log into any site;
* accept terms on behalf of a user;
* bypass controls;
* solve CAPTCHAs;
* use stealth or evasion packages;
* rotate proxies;
* overwhelm a website;
* scrape pages unrelated to job listings and job details.

Implement an allowlist of permitted domains.

Reject redirects to unapproved domains, except for explicitly configured official static-asset or API domains discovered during reconnaissance.

Add a dry-run and development limit.

Before running a full crawl, display a clear note in the README that the team should confirm internal legal, security, and acceptable-use approval.

## Architecture principles

Follow these rules:

* adapters are source-specific;
* domain models are source-independent;
* workflows orchestrate;
* Activities perform side effects;
* repositories own database access;
* analytics query normalized data;
* UI does not scrape directly;
* workflow runs are idempotent;
* partial failure is visible;
* external models are optional;
* historical facts are not overwritten;
* source URLs and raw source IDs are retained;
* every reported metric has a defined query;
* no statistic may be invented by an LLM.

## POC acceptance criteria

The POC is complete when:

1. Temporal runs locally.
2. A worker starts successfully.
3. Each of the three adapters has a reconnaissance report.
4. At least a development-sized sample can be collected from each accessible source.
5. Jobs are restricted to the United States.
6. Records are normalized and stored in SQLite.
7. Re-running does not duplicate jobs.
8. Changed jobs create snapshots.
9. incomplete crawls do not falsely close jobs.
10. Skills and role families are extracted.
11. Streamlit shows company-specific dashboards.
12. Monthly comparisons work after seeded or repeated snapshots.
13. A manual Temporal run can be triggered.
14. A recurring Temporal Schedule can be created.
15. Tests pass.
16. README instructions work on a clean local machine.
17. Failures are reported clearly rather than silently ignored.

## Seed data for demonstration

Because a monthly trend requires historical observations, add an optional synthetic demo-data generator.

The generator must:

* be clearly labeled synthetic;
* never mix silently with live collected data;
* use a `data_source = "synthetic"` marker;
* generate several months of plausible job snapshots;
* allow the dashboard to demonstrate trends before sufficient live history exists.

The UI must visibly distinguish:

```text
LIVE SOURCE DATA
SYNTHETIC DEMO DATA
```

## Implementation sequence

Work in these milestones.

### Milestone 1

* initialize project;
* configure dependencies;
* add Docker Compose for Temporal;
* implement configuration and logging;
* create database schema and migrations;
* create domain models;
* create README startup skeleton.

### Milestone 2

* implement Playwright reconnaissance utility;
* inspect each of the three sites;
* write reconnaissance reports;
* identify extraction strategy per site.

### Milestone 3

* implement one adapter end to end, preferably Wells Fargo;
* collect a development sample;
* normalize and persist it;
* add adapter fixtures and tests.

### Milestone 4

* implement Goldman Sachs and BNY adapters;
* add browser fallback where required;
* add all adapter tests.

### Milestone 5

* implement Temporal workflows, Activities, worker, client, and Schedule;
* add retries, timeouts, heartbeats, idempotency, and failure handling.

### Milestone 6

* implement lifecycle tracking, skills, role classification, analytics, and summaries.

### Milestone 7

* implement Streamlit pages;
* add synthetic demo history;
* add CSV exports.

### Milestone 8

* run formatting, linting, type checking, and tests;
* verify setup from README;
* document limitations and next steps.

After each milestone:

1. show the files created or changed;
2. explain the key decisions;
3. run relevant tests;
4. report failures honestly;
5. fix failures before proceeding when possible.

## Code-quality expectations

Use:

* type hints;
* async I/O where appropriate;
* small cohesive functions;
* dependency injection;
* clear exceptions;
* docstrings for public interfaces;
* Ruff;
* Pyright or MyPy;
* Pytest;
* no unexplained magic values;
* no broad `except Exception` unless re-raised with context at a boundary;
* no hidden global mutable state.

Prefer straightforward maintainable Python over unnecessary abstraction.

## Important first action

Do not begin by generating every application file blindly.

First:

1. inspect the current repository;
2. propose the final dependency list;
3. propose the initial directory structure;
4. create Milestone 1;
5. implement the site-reconnaissance utility;
6. execute reconnaissance against all three provided starting pages;
7. show the findings;
8. then implement adapters based on evidence.

When a public JSON endpoint is discovered, preserve the Playwright discovery tool and browser fallback. Do not remove them.

When an endpoint cannot be safely or reliably identified, use Playwright DOM extraction with tested, source-specific logic.

Build a working vertical slice early:

```text
one company
→ Temporal workflow
→ extraction
→ normalization
→ SQLite
→ analytics
→ one Streamlit page
```

Then add the other companies.

Begin now with Milestone 1 and the reconnaissance utility.

