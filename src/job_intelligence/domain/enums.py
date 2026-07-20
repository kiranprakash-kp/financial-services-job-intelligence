"""Enumerations shared across the domain."""

from __future__ import annotations

from enum import Enum


class CompanyCode(str, Enum):
    WELLS_FARGO = "WELLS_FARGO"
    GOLDMAN_SACHS = "GOLDMAN_SACHS"
    BNY = "BNY"


class ExtractionMethod(str, Enum):
    """How an adapter obtains listings/details. Chosen from verified recon."""

    DIRECT_API = "direct_api"  # public JSON/GraphQL via httpx
    SERVER_HTML = "server_html"  # server-rendered HTML via httpx
    BROWSER_API = "browser_api"  # Playwright captures a public API response
    BROWSER_DOM = "browser_dom"  # Playwright DOM extraction (last resort)


class TransportKind(str, Enum):
    DIRECT_HTTP = "direct_http"
    DIRECT_BROWSER = "direct_browser"
    PROXY_HTTP = "proxy_http"
    PROXY_BROWSER = "proxy_browser"


class TriggerType(str, Enum):
    MANUAL = "manual"
    SCHEDULE = "schedule"
    BACKFILL = "backfill"


class RunStatus(str, Enum):
    RUNNING = "running"
    SUCCESS = "success"
    DEGRADED = "degraded"  # completed but failed data-quality thresholds
    FAILED = "failed"
    PARTIAL = "partial"  # some companies succeeded, others failed


class JobChangeType(str, Enum):
    NEW = "NEW"
    UPDATED = "UPDATED"
    UNCHANGED = "UNCHANGED"
    CLOSED = "CLOSED"
    REOPENED = "REOPENED"


class WorkplaceType(str, Enum):
    ONSITE = "onsite"
    REMOTE = "remote"
    HYBRID = "hybrid"
    UNKNOWN = "unknown"


class KeySource(str, Enum):
    """Records how a job's canonical key was produced (for auditability)."""

    SOURCE_ID = "source_id"  # stable id supplied by the source
    DERIVED = "derived"  # hashed from normalized fields (fallback)


class DataSource(str, Enum):
    LIVE = "live"
    SYNTHETIC = "synthetic"
