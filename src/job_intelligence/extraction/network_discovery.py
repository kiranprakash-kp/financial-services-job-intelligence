"""Playwright-based network reconnaissance.

Opens a company's starting URL, records document/XHR/Fetch traffic (sanitized),
scores each response for the likelihood it carries job records, and emits a
sanitized summary. This is the evidence-gathering tool that precedes writing an
adapter — it never bypasses access controls and redacts all secrets.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from ..config import Settings, load_companies_config
from ..logging import get_logger
from .artifacts import sanitize_body, sanitize_headers, sanitize_url

log = get_logger("recon")

# Field names that suggest a response carries job records.
_JOB_SIGNAL_KEYS = {
    "job",
    "jobs",
    "requisition",
    "requisitions",
    "posting",
    "postings",
    "position",
    "positions",
    "title",
    "location",
    "description",
    "jobid",
    "requisitionid",
    "totalcount",
    "results",
    "items",
    "roles",
    "rolesearch",
    "recruitingcejobrequisitions",
}
_RESOURCE_TYPES = {"xhr", "fetch", "document"}


@dataclass(slots=True)
class CapturedResponse:
    url: str
    method: str
    resource_type: str
    status: int
    content_type: str
    request_headers: dict[str, str]
    post_data: str | None
    job_score: int
    matched_keys: list[str] = field(default_factory=list)
    total_count_hint: int | None = None

    def to_dict(self) -> dict:
        return {
            "url": sanitize_url(self.url),
            "method": self.method,
            "resource_type": self.resource_type,
            "status": self.status,
            "content_type": self.content_type,
            "job_score": self.job_score,
            "matched_keys": self.matched_keys,
            "total_count_hint": self.total_count_hint,
            "request_headers": sanitize_headers(self.request_headers),
            "post_data": sanitize_body(self.post_data),
        }


def _score_json(payload: object) -> tuple[int, list[str], int | None]:
    """Return (score, matched keys, total-count hint) for a JSON body."""
    text = json.dumps(payload).lower() if not isinstance(payload, str) else payload.lower()
    matched = sorted({k for k in _JOB_SIGNAL_KEYS if f'"{k}"' in text})
    score = len(matched)
    total_hint: int | None = None
    if isinstance(payload, dict):
        for key in ("totalCount", "TotalJobsCount", "total", "count"):
            val = _deep_get_int(payload, key)
            if val is not None:
                total_hint = val
                break
    return score, matched, total_hint


def _deep_get_int(obj: object, key: str, depth: int = 4) -> int | None:
    if depth < 0:
        return None
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == key and isinstance(v, int):
                return v
            found = _deep_get_int(v, key, depth - 1)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for item in obj[:10]:
            found = _deep_get_int(item, key, depth - 1)
            if found is not None:
                return found
    return None


async def run_recon(company_key: str, settings: Settings, max_seconds: float = 25.0) -> dict:
    """Open the company's start page, capture traffic, and rank job candidates.

    Returns a sanitized summary dict. Requires Playwright browsers to be
    installed (`playwright install chromium`).
    """
    from .browser import browser_context

    cfg = load_companies_config().get(company_key)
    start_url = cfg.career_site_url
    captured: list[CapturedResponse] = []

    async with browser_context(settings) as context:
        page = await context.new_page()

        async def handle_response(response) -> None:
            try:
                req = response.request
                if req.resource_type not in _RESOURCE_TYPES:
                    return
                ctype = (response.headers or {}).get("content-type", "")
                if "json" not in ctype and req.resource_type != "document":
                    return
                score, matched, total = 0, [], None
                if "json" in ctype:
                    try:
                        body = await response.json()
                        score, matched, total = _score_json(body)
                    except Exception:
                        return
                captured.append(
                    CapturedResponse(
                        url=response.url,
                        method=req.method,
                        resource_type=req.resource_type,
                        status=response.status,
                        content_type=ctype,
                        request_headers=await req.all_headers(),
                        post_data=req.post_data,
                        job_score=score,
                        matched_keys=matched,
                        total_count_hint=total,
                    )
                )
            except Exception as exc:  # recon must never crash on a single response
                log.debug("recon.response_error", error=str(exc))

        page.on("response", handle_response)

        log.info("recon.navigate", company=company_key, url=sanitize_url(start_url))
        await page.goto(start_url, wait_until="networkidle", timeout=int(max_seconds * 1000))
        # Give late XHR/GraphQL calls a moment to complete.
        await page.wait_for_timeout(3000)
        await page.close()

    candidates = sorted(
        (c for c in captured if c.job_score >= 3),
        key=lambda c: c.job_score,
        reverse=True,
    )
    summary = {
        "company": company_key,
        "start_url": sanitize_url(start_url),
        "responses_observed": len(captured),
        "job_candidates": [c.to_dict() for c in candidates[:10]],
    }
    log.info(
        "recon.done",
        company=company_key,
        responses=len(captured),
        candidates=len(candidates),
    )
    return summary
