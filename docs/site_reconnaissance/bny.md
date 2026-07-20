# Site Reconnaissance — BNY

| Field | Finding |
|---|---|
| **Company** | BNY (Bank of New York Mellon) |
| **Starting URL** | `https://eofe.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/BNY-Careers/jobs?...` |
| **Date inspected** | 2026-07-20 |
| **Rendering model** | Oracle Candidate Experience SPA that calls a **public REST API** |
| **Career-platform tech** | **Oracle Recruiting (Fusion) — Candidate Experience** (`hcmRestApi`) |
| **Listing data source** | Oracle REST resource `recruitingCEJobRequisitions` returning `application/vnd.oracle.adf.resourcecollection+json` |
| **Job-detail data source** | Oracle REST resource `recruitingCEJobRequisitionDetails` |
| **Request method** | `GET` |
| **API URL** | `https://eofe.fa.us2.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions?onlyData=true&expand=requisitionList.secondaryLocations&finder=findReqs;siteNumber=<SITE>,limit=<n>,offset=<n>,sortBy=POSTING_DATES_DESC` |
| **Response shape** | `items[0].requisitionList[]` with `Id`, `Title`, `PrimaryLocation`, `PrimaryLocationCountry`, `PostedDate`, `secondaryLocations[]`; `items[0].TotalJobsCount` for the total |
| **Pagination method** | `limit` / `offset` in the `finder` clause; stop when `offset ≥ TotalJobsCount` or an empty `requisitionList` |
| **Stable job identifier** | `Id` (requisition id, e.g. `73320`) |
| **Location-filter behavior** | `selectedLocationsFacet` / facet ids in the `finder`; `PrimaryLocationCountry` (`US`) and `PrimaryLocation` text enable **US validation after extraction** |
| **Direct HTTP test** | ✅ **Works with `httpx`.** `GET` returned `200`, `TotalJobsCount=1689`, clean records (e.g. `Id=73320`, "Associate, Client Processing I", "Lake Mary, FL, United States", `PrimaryLocationCountry=US`, `PostedDate=2026-07-20`) |
| **Browser requirement** | **None** |
| **Observed rate limiting** | None at conservative rates during recon |
| **Observed anti-automation** | None encountered on the REST resource |
| **Recommended POC strategy** | **Strategy 1 — direct HTTP REST.** List via `recruitingCEJobRequisitions`, enrich via `recruitingCEJobRequisitionDetails` |
| **Fallback strategy** | Browser-assisted capture of the same REST responses; DOM extraction last |
| **Production considerations** | Confirm and pin the exact `siteNumber` for BNY-Careers and the US `selectedLocationsFacet` during the recon step; Oracle exposes many optional fields via `expand=` |
| **Known uncertainties** | Exact `siteNumber` — recon used a provisional value (`CX_1001`) that returned real BNY records; must be confirmed before production |

### Decision
| Company | Primary extraction | Fallback | Pagination | Detail retrieval | Confidence |
|---|---|---|---|---|---|
| BNY | Direct HTTP REST (Oracle CE) | Browser-assisted capture / DOM | `limit`/`offset` | `recruitingCEJobRequisitionDetails` | **High** |

> No cookies, tokens, session identifiers, or personal data are stored. Only public listing structure is recorded.
