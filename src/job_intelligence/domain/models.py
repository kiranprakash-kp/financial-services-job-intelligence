"""Pydantic boundary models.

These are the contracts between layers (adapters -> processing -> persistence).
They are source-independent: an adapter's job is to turn source-specific payloads
into these shapes. All models are JSON-serializable so they can cross Temporal
activity boundaries.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from .enums import (
    CompanyCode,
    DataSource,
    ExtractionMethod,
    KeySource,
    TransportKind,
    TriggerType,
    WorkplaceType,
)


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# --------------------------------------------------------------------------- #
# Request / run context
# --------------------------------------------------------------------------- #
class IngestionRequest(_Model):
    companies: list[str]
    country: str = "United States"
    triggered_by: str
    trigger_type: TriggerType = TriggerType.MANUAL
    full_refresh: bool = False
    run_date: datetime | None = None
    dev_job_limit: int | None = None  # overrides settings when set (dev mode)


class RunContext(_Model):
    """Per-company execution context threaded through extraction."""

    company_code: CompanyCode
    workflow_id: str
    run_id: str
    ingestion_run_id: int | None = None
    triggered_by: str
    full_refresh: bool = False
    dev_job_limit: int | None = None
    dev_page_limit: int | None = None


class CompanyIngestionParams(_Model):
    """Input to CompanyJobIngestionWorkflow — company_key is the config/companies.yml key.

    Deliberately carries no CompanyCode/config lookups: workflow code must stay
    deterministic, so `company_key.upper()` (wells_fargo -> WELLS_FARGO, etc.) is
    used to derive the code wherever needed, rather than reading YAML config
    inside a workflow.
    """

    company_key: str
    triggered_by: str
    trigger_type: TriggerType = TriggerType.MANUAL
    dev_job_limit: int | None = None


class ExtractionActivityParams(_Model):
    """Input to the extraction Activity — the run record already exists."""

    company_key: str
    dev_job_limit: int | None
    ingestion_run_id: int
    workflow_id: str


# --------------------------------------------------------------------------- #
# Extraction plan (result of strategy resolution)
# --------------------------------------------------------------------------- #
class ExtractionPlan(_Model):
    company_code: str
    method: ExtractionMethod
    transport: TransportKind
    listing_source_type: str
    detail_source_type: str
    pagination_type: str
    proxy_enabled: bool = False
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str


# --------------------------------------------------------------------------- #
# Extraction payloads
# --------------------------------------------------------------------------- #
class DiscoveredJob(_Model):
    """A job reference found during listing discovery (pre-detail-fetch)."""

    company_code: CompanyCode
    source_job_id: str
    title: str | None = None
    posting_url: str | None = None
    location_text: str | None = None
    discovered_on_page: int | None = None
    listing_payload: dict = Field(default_factory=dict)


class RawJobDetail(_Model):
    """Raw detail as returned by a source; not yet normalized."""

    company_code: CompanyCode
    source_job_id: str
    posting_url: str | None = None
    content_type: str = "application/json"
    payload: dict = Field(default_factory=dict)
    fetched_at: datetime = Field(default_factory=datetime.utcnow)


class NormalizedLocation(_Model):
    location_text: str
    city: str | None = None
    state: str | None = None  # two-letter code where resolvable
    country: str | None = None
    is_us: bool = False
    is_remote: bool = False
    is_primary: bool = False


class ExtractedSkill(_Model):
    canonical_name: str
    category: str
    source: str = "taxonomy"  # taxonomy | llm
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    evidence_text: str | None = None


class NormalizedJob(_Model):
    """The normalized, source-independent job record persisted as `jobs`."""

    company_code: CompanyCode
    source_job_id: str
    canonical_key: str
    key_source: KeySource = KeySource.SOURCE_ID

    title: str
    normalized_title: str | None = None
    role_family: str | None = None
    role_subfamily: str | None = None
    classification_confidence: float | None = None

    employment_type: str | None = None
    experience_level: str | None = None
    business_unit: str | None = None
    department: str | None = None

    locations: list[NormalizedLocation] = Field(default_factory=list)
    workplace_type: WorkplaceType = WorkplaceType.UNKNOWN

    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str | None = None
    salary_period: str | None = None

    description_text: str | None = None
    qualifications_text: str | None = None
    responsibilities_text: str | None = None

    posting_url: str
    source_posted_at: datetime | None = None

    skills: list[ExtractedSkill] = Field(default_factory=list)
    content_hash: str | None = None
    raw_payload: dict = Field(default_factory=dict)
    data_source: DataSource = DataSource.LIVE

    @property
    def primary_location(self) -> NormalizedLocation | None:
        for loc in self.locations:
            if loc.is_primary:
                return loc
        return self.locations[0] if self.locations else None

    @property
    def has_valid_us_location(self) -> bool:
        return any(loc.is_us or loc.is_remote for loc in self.locations)


# --------------------------------------------------------------------------- #
# Results
# --------------------------------------------------------------------------- #
class InvalidRecord(_Model):
    source_job_id: str | None = None
    reason: str
    detail: str | None = None


class CompanyRunResult(_Model):
    company_code: CompanyCode
    status: str
    pages_discovered: int = 0
    jobs_discovered: int = 0
    jobs_fetched: int = 0
    jobs_inserted: int = 0
    jobs_updated: int = 0
    jobs_unchanged: int = 0
    jobs_closed: int = 0
    jobs_failed: int = 0
    stop_reason: str | None = None
    complete_result_set: bool = False
    error_summary: str | None = None
    invalid_records: list[InvalidRecord] = Field(default_factory=list)
