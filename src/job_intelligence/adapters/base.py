"""Common adapter interface.

Adapters encapsulate everything source-specific: URLs, request strategy,
pagination, location filtering, detail retrieval, parsing, identifiers, and the
retryable-vs-non-retryable error boundary. No company-specific selector or JSON
path may leak outside its adapter.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

from ..domain.models import (
    DiscoveredJob,
    ExtractionPlan,
    NormalizedJob,
    RawJobDetail,
    RunContext,
)


@runtime_checkable
class JobSourceAdapter(Protocol):
    """Contract every company adapter implements."""

    company_code: str

    def extraction_plan(self) -> ExtractionPlan:
        """Return the verified extraction plan (method, transport, confidence)."""
        ...

    def discover_jobs(self, run_context: RunContext) -> AsyncIterator[DiscoveredJob]:
        """Yield job references, paginating the listing until a stop condition."""
        ...

    async def fetch_job_detail(
        self, discovered_job: DiscoveredJob, run_context: RunContext
    ) -> RawJobDetail:
        """Fetch a single job's detail payload."""
        ...

    def normalize(self, raw_job: RawJobDetail) -> NormalizedJob:
        """Turn a source-specific payload into a source-independent NormalizedJob."""
        ...
