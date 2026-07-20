# Limitations & Compliance

## Known limitations
- **Career sites change.** HTML structure, feeds, and page layouts can change at
  any time and break extraction.
- **Public endpoints change.** The Goldman Sachs GraphQL operation names and the
  BNY Oracle `siteNumber` can change on redeploys. Adapters run from *versioned
  recon configuration*, and reconnaissance is re-run when parsing failures,
  count anomalies, or schema drift are detected — not on every scheduled run.
- **Posted dates may be missing.** Some sources do not expose a reliable posting
  date. **First-seen date is not equal to source-posted date.**
- **Disappearance does not prove a role was filled.** A posting absent from a
  crawl may have been paused, moved, or reformatted. Closure is only inferred
  after a *complete, validated* crawl and a grace period of consecutive misses.
- **Recruiting-priority scores are decision-support indicators, not
  predictions.** They are labeled "POC Recruiting Priority Indicator" and always
  show their component breakdown.
- **Skill extraction can produce false positives/negatives.** Matching is
  phrase-boundary and alias aware, but taxonomy coverage is finite.
- **Counts fluctuate between requests.** Live recon observed 1,689 vs 1,696 (BNY)
  and 1,254 vs 1,253 (GS) seconds apart — an endpoint that works once is not
  proven stable.
- **Internal legal & information-security approval is required** before wider
  deployment.

## Compliance constraints
This project operates **only on public job-listing information**. It does **not**
collect applicant information, employee profiles, names, emails, phone numbers,
application-form data, session data, or authentication data, and does **not** use
private/authenticated/employee-only APIs.

It does **not** log into any site, accept terms on anyone's behalf, bypass access
controls, solve CAPTCHAs, use stealth/evasion packages, rotate proxies, or
scrape pages unrelated to job listings/details. Each company has a **domain
allowlist**; redirects to unapproved domains are rejected.

On an explicit block, WAF challenge, or CAPTCHA the adapter **stops and reports**
the reason — it never attempts circumvention, and it never auto-switches to a
proxy. Enabling a proxy is an explicit, approval-gated configuration decision.

### Before a full crawl
Confirm: internal legal approval · information-security approval · acceptable-use
review of each site's terms · approved data-handling/logging controls. A proxy
changes the network route; it does **not** create permission to access data.

## Residential proxy (future production option only)
Bright Data support is scaffolded through configuration and **disabled by
default**. It is an *optional production transport*, not the POC solution, and
requires the full approval checklist in the instructions (legal, infosec,
procurement, client-account, credential storage, cost estimate, shutdown
procedure) before it may be enabled.
