# Site Reconnaissance — Goldman Sachs

| Field | Finding |
|---|---|
| **Company** | Goldman Sachs |
| **Starting URL** | `https://higher.gs.com/results?LOCATION=...&page=1&sort=RELEVANCE` |
| **Date inspected** | 2026-07-20 |
| **Rendering model** | **Client-rendered SPA** (Next.js; `/_next/static/chunks/...`), fronted by CloudFront. Initial HTML is an ~8 KB shell with **no job data** |
| **Career-platform tech** | Goldman "Higher" careers platform; **Apollo Client → GraphQL** backend |
| **Listing data source** | Public GraphQL API called by the SPA |
| **Job-detail data source** | Role detail route / GraphQL (list response is already field-rich) |
| **Request method** | `POST` (GraphQL) |
| **API URL** | `https://api-higher.gs.com/gateway/api/v1/graphql` |
| **Operation** | `GetRoles($searchQueryInput: RoleSearchQueryInput!)` → `roleSearch { totalCount items { roleId corporateTitle jobTitle jobFunction locations{primary state country city} status division skills jobType{code description} externalSource{sourceId} } }` |
| **Input shape** | `{ page:{ pageSize, pageNumber (0-indexed) }, experiences:["EARLY_CAREER","PROFESSIONAL"], filters:[...], searchTerm:"", sort:<RoleSearchSortInput> }` — `sort` is an input object; **omit it** rather than passing a string |
| **Pagination method** | `page.pageNumber` (0-indexed) + `page.pageSize`; stop on empty `items` or when cumulative ≥ `totalCount` |
| **Stable job identifier** | `roleId` (e.g. `178627_GS_MID_CAREER`); `externalSource.sourceId` also available |
| **Location-filter behavior** | `filters` array (LOCATION category, discoverable via `GetRoleFilters`); each item carries `locations[].country` so **US validation after extraction** is straightforward |
| **Direct HTTP test** | ✅ **Works with `httpx`.** `POST` returned `200 application/json`, `totalCount=1254` professional roles with full records. No authentication, no cookies, no CloudFront challenge |
| **Browser requirement** | **None** — direct GraphQL works. Browser-assisted capture retained as fallback only |
| **Observed rate limiting** | None at conservative rates during recon |
| **Observed anti-automation** | None encountered on the API; only `apollographql-client-name` client header expected |
| **Recommended POC strategy** | **Strategy 1 — direct HTTP GraphQL** to `api-higher.gs.com`, paginate `GetRoles` |
| **Fallback strategy** | Browser-assisted API capture (Playwright observing the same GraphQL response), then DOM extraction |
| **Production considerations** | GraphQL schema/operation names may change on SPA redeploys → recon re-run trigger; Bright Data proxy is a **disabled**, approval-gated future option, not needed now |
| **Known uncertainties** | Exact `filters` payload for the full US-city set; role-description field location for detail enrichment (resolve during adapter build) |

### Decision
| Company | Primary extraction | Fallback | Pagination | Detail retrieval | Confidence |
|---|---|---|---|---|---|
| Goldman Sachs | Direct HTTP GraphQL (`GetRoles`) | Browser-assisted capture / DOM | `page.pageNumber` (0-idx) | list is field-rich; detail route for description | **High** |

### Live-verified sample (sanitized)
```
totalCount = 1254
178627_GS_MID_CAREER | Global Banking & Markets ... Analyst, New York | Global Banking & Markets | [New York, NY, United States]
```

> No cookies, tokens, session identifiers, or personal data are stored. `apollographql-client-name` is a non-secret client label.
