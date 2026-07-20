# Site Reconnaissance — Wells Fargo

| Field | Finding |
|---|---|
| **Company** | Wells Fargo |
| **Starting URL** | `https://www.wellsfargojobs.com/en/jobs/?search=&country=United+States+of+America&pagesize=20#results` |
| **Date inspected** | 2026-07-20 |
| **Rendering model** | **Server-rendered HTML** (ASP.NET; `ASP.NET_SessionId` cookie), fronted by Cloudflare |
| **Career-platform tech** | Custom Wells Fargo careers site (jQuery front end) |
| **Listing data source** | Job cards embedded in the initial HTML **plus** a full job-board **XML feed** |
| **Job-detail data source** | Server-rendered detail page HTML |
| **Request method** | `GET` |
| **API / page URL pattern** | Listing: `/en/jobs/?country=United+States+of+America&pagesize=20&pg={n}` · Feed: `/en/jobs/xml/` · Detail: `/en/jobs/{ref}/{slug}/` |
| **Pagination method** | Page number (`pg=`) with a "Go to next page of results" control; the XML feed returns the complete set in one document |
| **Stable job identifier** | `<referencenumber>` e.g. `R-547754` (also present in the detail URL) |
| **Location-filter behavior** | URL `country` param; the XML feed is global (contains non-US rows) so **US validation after extraction is required** |
| **Direct HTTP test** | ✅ Works with `httpx`. Landing page 200 (143 KB HTML with 20 job cards at `pagesize=20`); feed 200, `text/xml`, ~15.6 MB |
| **Browser requirement** | **None** for listing or detail |
| **Observed rate limiting** | None at conservative rates during recon |
| **Observed anti-automation** | Cloudflare present but served content to a plain client with a descriptive UA; no challenge encountered |
| **Recommended POC strategy** | **Strategy 2 — direct HTTP.** Use the XML feed for discovery (complete set, stable ids), fetch each detail page's server-rendered HTML for full text |
| **Fallback strategy** | Paginate the HTML listing pages via `pg=`; Playwright DOM extraction if HTML structure changes |
| **Production considerations** | Cache the feed's `lastBuildDate`; the feed may omit some detail fields (description) that only exist on the detail page |
| **Known uncertainties** | Feed field coverage vs. detail page; whether `pagesize` upper bound is enforced |

### Decision
| Company | Primary extraction | Fallback | Pagination | Detail retrieval | Confidence |
|---|---|---|---|---|---|
| Wells Fargo | Direct HTTP (XML feed + server HTML) | HTML listing pages / Playwright DOM | feed (full) / `pg=` | Server-rendered detail HTML | **High** |

### Sample sanitized feed structure
```xml
<job>
  <title><![CDATA[Customer Service Representative ...]]></title>
  <date><![CDATA[Thu, 21 May 2026 00:00:00 GMT]]></date>
  <referencenumber><![CDATA[R-547754]]></referencenumber>
  <url><![CDATA[https://www.wellsfargojobs.com/en/jobs/r-547754/.../]]></url>
  <city><![CDATA[...]]></city>
</job>
```

> No cookies, tokens, session identifiers, or personal data are stored. Only public listing structure is recorded.
