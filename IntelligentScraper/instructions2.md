# Required planning and approval checkpoint

Before creating files, installing dependencies, writing scraper code, or implementing the architecture, first analyze the requirement and present recommendations.

Your first response must contain:

1. your understanding of the business requirement;
2. findings about Wells Fargo, Goldman Sachs, and BNY career sites;
3. the likely rendering and data-loading approach for each site;
4. proposed extraction method for each company;
5. proposed POC architecture;
6. recommended technology stack;
7. important risks, limitations, and assumptions;
8. suggested improvements or alternatives;
9. implementation milestones;
10. any decisions that materially affect the implementation.

Do not begin building immediately.

If you recommend changing any requested technology, architecture, database, UI framework, workflow structure, or extraction method, explain the recommendation before implementing it.

Explicitly separate recommendations into:

```text
Required for the initial POC
Recommended for later iterations
Optional production enhancements
```

Wait for approval before making major architectural deviations.

Minor implementation decisions that follow the approved architecture do not need separate approval, but document them clearly.

---

# Research-first requirement for the three companies

The initial implementation must be based specifically on research of these three career sites:

```text
Wells Fargo:
https://www.wellsfargojobs.com/en/jobs/?search=&country=United+States+of+America&pagesize=20#results

Goldman Sachs:
https://higher.gs.com/results?LOCATION=Arizona|Albany|New%20York|Atlanta|Boston|Chicago|Dallas|Houston|Richardson|Deerfield|Detroit|Draper|Irving|Jersey%20City|Los%20Angeles|Miami|West%20Palm%20Beach|Newport%20Beach|San%20Francisco|Philadelphia|Pittsburgh|Salt%20Lake%20City|Seattle|Washington|Wilmington&page=1&sort=RELEVANCE

BNY:
https://eofe.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/BNY-Careers/jobs?lastSelectedFacet=LOCATIONS&mode=location&selectedLocationsFacet=300000000378743
```

Do not design generic adapters based only on assumptions.

Research each site individually and determine:

* whether the initial document is server-rendered or client-rendered;
* whether job data appears in the page HTML;
* whether job data is embedded in script tags or hydration state;
* whether the page calls a public JSON, REST, GraphQL, Oracle Recruiting, or other backend endpoint;
* whether searching sends GET or POST requests;
* whether pagination uses page numbers, offsets, cursors, tokens, or infinite scrolling;
* whether job details are loaded from a separate endpoint;
* whether filters are sent as URL parameters or request payloads;
* whether a stable source job ID is available;
* whether the endpoint requires cookies or temporary browser-generated values;
* whether direct HTTP access works outside the browser;
* whether rate limiting or anti-automation behavior is observed.

Research and implement only against publicly accessible job-search and job-detail functionality.

---

# API and network interception as the primary discovery method

For every company, begin with Playwright-based network observation.

Create a reconnaissance utility that:

1. opens the provided starting URL in Chromium;
2. starts request and response listeners before navigation;
3. records relevant document, Fetch, XHR, and GraphQL traffic;
4. performs user-like search and pagination interactions;
5. observes requests produced when a job card is opened;
6. identifies responses containing job records;
7. stores sanitized request and response metadata;
8. compares network behavior between the first and second result pages;
9. determines whether the discovered endpoint can be called directly with `httpx`;
10. produces a recommendation for the company adapter.

Observe at minimum:

```text
request URL
HTTP method
resource type
request headers, sanitized
query parameters
POST body, sanitized
response status
response content type
response JSON structure
pagination fields
total-count fields
job-ID fields
detail-page fields
location fields
posted-date fields
```

Add Playwright listeners similar in purpose to:

```python
page.on("request", handle_request)
page.on("response", handle_response)
```

Also use targeted response waiting when performing a search or pagination interaction:

```python
async with page.expect_response(response_predicate) as response_info:
    await perform_search_or_pagination_action()

response = await response_info.value
```

Do not assume that every XHR or Fetch response contains job data.

Develop heuristics that flag candidate job responses based on fields such as:

```text
job
jobs
requisition
requisitions
posting
postings
position
positions
title
location
description
jobId
requisitionId
totalCount
results
items
```

The reconnaissance process must preserve enough metadata to reproduce the public request but must redact:

```text
cookies
authorization headers
session identifiers
CSRF tokens
tracking identifiers
personal data
browser fingerprints
```

Do not print complete sensitive request headers to the terminal.

---

# Extraction-strategy decision tree

Choose the extraction method independently for each company.

Use the following priority order.

## Strategy 1: Direct public API request

Use direct requests when the career page itself calls a publicly accessible endpoint and that endpoint:

* contains the required job data;
* does not require authentication;
* can be called consistently;
* does not require bypassing access controls;
* supports complete pagination;
* works with conservative request rates.

Use `httpx.AsyncClient` for this strategy.

This is the preferred method because it is generally faster, easier to test, and less resource-intensive than browser-based extraction.

## Strategy 2: Server-rendered HTML extraction

Use direct HTML extraction when job results and details are present in returned HTML.

Use:

```text
httpx
selectolax or Beautiful Soup
Pydantic validation
```

## Strategy 3: Browser-assisted API extraction

Use Playwright to establish the browser session and capture public API responses when:

* the API request depends on browser-generated session state;
* direct calls are unreliable;
* the response is otherwise publicly delivered to the job-search page;
* no access control is being bypassed.

Prefer parsing the captured JSON response rather than scraping visible card text when possible.

## Strategy 4: Browser DOM extraction

Use Playwright DOM extraction only when:

* no usable structured response is available;
* required information exists only in rendered content;
* browser interaction is necessary for pagination or detail loading.

Use resilient selectors and tested fallback selectors.

Do not select an extraction strategy until reconnaissance is completed for that company.

The three companies are allowed to use three different extraction approaches.

---

# Company reconnaissance report

Generate one report per company:

```text
docs/site_reconnaissance/wells_fargo.md
docs/site_reconnaissance/goldman_sachs.md
docs/site_reconnaissance/bny.md
```

Each report must include:

```text
Company
Starting URL
Date and time inspected
Rendering model
Observed career-platform technology
Listing data source
Job-detail data source
Request method
API or page URL pattern
Pagination method
Stable job identifier
Location-filter behavior
Direct HTTP test result
Browser requirement
Observed rate limiting
Observed anti-automation behavior
Recommended POC strategy
Fallback strategy
Production considerations
Known uncertainties
```

Include a concise decision table:

| Company | Primary extraction | Fallback | Pagination | Detail retrieval | Confidence |
| ------- | ------------------ | -------- | ---------- | ---------------- | ---------- |

Do not describe an endpoint as stable merely because it worked once.

---

# Public endpoint validation

When a candidate API is identified, test it carefully.

Validate:

1. first page;
2. second page;
3. last available page where practical;
4. empty-result search;
5. US location filtering;
6. duplicate behavior;
7. result-count consistency;
8. job-detail retrieval;
9. missing optional fields;
10. behavior without browser cookies;
11. behavior with a fresh browser context;
12. moderate repeated requests.

Compare a sample of API records against visible career-page results.

For each tested job verify:

```text
source job ID
title
location
posting URL
description
posted date, if available
employment type, if available
business unit, if available
```

If the API and visible UI disagree, document the discrepancy before proceeding.

---

# Proxy-ready architecture

The initial local POC must run without a residential proxy unless ordinary access fails during testing.

However, design the networking layer so residential proxies can be added later without rewriting the company adapters.

Create a transport abstraction such as:

```python
from typing import Protocol

class ExtractionTransport(Protocol):
    async def get(self, request: "TransportRequest") -> "TransportResponse":
        ...

    async def post(self, request: "TransportRequest") -> "TransportResponse":
        ...
```

Suggested implementations:

```text
DirectHttpTransport
DirectBrowserTransport
ProxyHttpTransport
ProxyBrowserTransport
```

For the initial POC, implement and enable:

```text
DirectHttpTransport
DirectBrowserTransport
```

A Bright Data integration may be scaffolded through configuration, but it must be disabled by default.

Configuration should support future settings such as:

```text
PROXY_ENABLED=false
PROXY_PROVIDER=brightdata
PROXY_ENDPOINT=
PROXY_USERNAME=
PROXY_PASSWORD=
PROXY_COUNTRY=us
PROXY_SESSION_MODE=rotating
PROXY_MAX_RETRIES=2
```

Never commit proxy credentials.

Store credentials only in environment variables or an approved secret manager.

The adapters must request a transport from a transport factory rather than constructing proxy connections directly.

For example:

```python
transport = transport_factory.for_company(
    company_code=company_code,
    browser_required=browser_required,
)
```

This will allow direct and proxy-based traffic to be switched through configuration.

---

# Residential proxy production option

Residential proxy support may be considered later for production when ordinary direct requests or normal browser automation are consistently blocked.

Bright Data is an acceptable candidate provider for future evaluation.

Treat it as:

```text
Optional production transport
```

not as:

```text
The default POC solution
```

Before enabling a residential proxy, require:

* Capgemini legal approval;
* information-security approval;
* procurement approval;
* client-account approval where applicable;
* confirmation that collection is permitted;
* review of the career site's applicable terms and policies;
* approved credential storage;
* approved data-handling and logging controls;
* an operational cost estimate;
* an escalation and shutdown procedure.

Residential proxies must not be used to:

* defeat authentication;
* access private or applicant-only data;
* bypass CAPTCHA challenges;
* evade an explicit block after access has been prohibited;
* conceal prohibited collection;
* create unreasonable traffic;
* rotate identities aggressively;
* imitate many unrelated users;
* bypass geographic, contractual, or authorization restrictions.

A proxy changes the network route. It does not create permission to access data.

---

# Anti-bot and access-failure policy

Differentiate among:

```text
temporary network failure
rate limiting
JavaScript rendering requirement
cookie or session requirement
WAF challenge
CAPTCHA
explicit access denial
schema or parsing failure
```

Handle them differently.

## Temporary failure

Use bounded retries with exponential backoff.

## HTTP 429

Respect `Retry-After`, reduce concurrency, and pause the company workflow when necessary.

## JavaScript rendering requirement

Use Playwright.

## Browser-session requirement

Use browser-assisted API extraction where permitted.

## WAF challenge or CAPTCHA

Do not attempt automated circumvention in the initial POC.

Record the failure and identify proxy or approved managed collection as a future option.

## Explicit access denial

Stop the adapter and report the reason.

Do not automatically switch to a residential proxy merely because a direct request receives an access-denied response.

Proxy activation must be an explicit approved configuration decision.

---

# Request routing and fallback behavior

The adapter must not silently change traffic methods.

For each run, record:

```text
company
selected extraction strategy
selected transport
direct or proxy
HTTP or browser
fallback reason
request count
retry count
rate-limit events
access-denied events
```

Recommended fallback sequence:

```text
Public API using direct HTTP
        ↓
Server-rendered HTML using direct HTTP
        ↓
Browser-assisted API capture
        ↓
Browser DOM extraction
        ↓
Stop and report access limitation
        ↓
Evaluate approved proxy support for a later production iteration
```

Do not automatically perform the final proxy step in the initial POC.

---

# Bright Data integration design for later

Create a documented extension point for Bright Data, but do not make live Bright Data credentials a prerequisite for local development.

The future integration should support:

* authenticated proxy URL construction;
* US geo-targeting where approved;
* bounded session reuse;
* request-level proxy metrics;
* bandwidth and cost tracking;
* provider error classification;
* safe credential redaction;
* circuit breaker behavior;
* company-level opt-in;
* direct-versus-proxy comparison testing.

Allow configuration by company:

```yaml
companies:
  wells_fargo:
    extraction_strategy: auto
    proxy_enabled: false

  goldman_sachs:
    extraction_strategy: auto
    proxy_enabled: false

  bny:
    extraction_strategy: auto
    proxy_enabled: false
```

Do not make the proxy decision globally mandatory.

One company may use direct HTTP while another may require Playwright or an approved proxy transport.

---

# Temporal integration for extraction strategies

Temporal must orchestrate the extraction without knowing site-specific API paths or CSS selectors.

The company workflow should request the adapter's selected strategy:

```text
ResearchCompanySourceActivity
        ↓
ResolveExtractionStrategyActivity
        ↓
DiscoverJobPagesActivity
        ↓
FetchJobDetailsActivity
        ↓
NormalizeAndPersistActivity
```

The strategy-resolution result should include:

```python
class ExtractionPlan(BaseModel):
    company_code: str
    method: str
    transport: str
    listing_source_type: str
    detail_source_type: str
    pagination_type: str
    proxy_enabled: bool = False
    confidence: float
    rationale: str
```

Do not perform live site reconnaissance inside every scheduled production run.

Use versioned adapter configuration created from verified reconnaissance.

Run reconnaissance again when:

* parsing failures exceed a threshold;
* job counts change unexpectedly;
* API response shape changes;
* pagination stops working;
* detail retrieval fails broadly;
* the career site is redesigned.

---

# Updated implementation sequence

Follow this order.

## Step 1: Analyze and recommend

Before coding, present:

* interpretation of the business problem;
* recommendations;
* alternative approaches;
* proposed stack;
* architecture;
* milestones;
* concerns;
* decisions requiring approval.

Do not build until these recommendations have been presented.

## Step 2: Create reconnaissance tooling

Implement Playwright network interception and sanitized request/response recording.

Do not implement full adapters yet.

## Step 3: Research Wells Fargo

Determine:

* listing source;
* pagination;
* detail source;
* US filtering;
* direct HTTP feasibility;
* browser fallback.

Present the findings.

## Step 4: Research Goldman Sachs

Perform the same analysis independently.

Present the findings.

## Step 5: Research BNY

Perform the same analysis independently, including investigation of the Oracle Candidate Experience network requests.

Present the findings.

## Step 6: Recommend adapter plans

Produce the company comparison table and recommend one strategy per company.

Before building the full adapters, explain any major new finding or architectural change.

## Step 7: Build one vertical slice

Choose the simplest and most reliable of the three companies and implement:

```text
Temporal
→ company adapter
→ extraction
→ normalization
→ SQLite
→ analytics
→ Streamlit
```

## Step 8: Add the remaining companies

Implement each according to its verified extraction plan.

## Step 9: Add historical analysis

Implement snapshots, lifecycle states, trends, skill extraction, and company summaries.

## Step 10: Prepare the demo

Add data-quality reporting, pipeline operations, synthetic historical data where necessary, and documentation.

---

# Updated important first action

Begin by responding with a research and architecture proposal.

Do not begin writing the complete application immediately.

Your first response should include:

```text
1. Business understanding
2. Site-by-site research plan
3. API-interception approach
4. Proposed architecture
5. Technology recommendations
6. Direct HTTP versus Playwright decision criteria
7. Proxy-ready design
8. Initial POC scope
9. Later production scope
10. Risks and compliance considerations
11. Milestone plan
12. Questions or decisions requiring approval
```

Provide suggestions before implementing them.

After the recommendations are reviewed, begin with:

```text
Milestone 1:
Repository setup, Temporal local environment, database schema,
configuration, logging, and Playwright reconnaissance utility.
```

Do not generate all company adapters based on assumptions.

Research the three named career sites first, record evidence, recommend the extraction plan, and then build.
