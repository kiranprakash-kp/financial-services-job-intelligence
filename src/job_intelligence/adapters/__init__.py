"""Source-specific extraction adapters (one per company)."""

from __future__ import annotations

from ..domain.enums import CompanyCode
from .base import JobSourceAdapter

# Registry is populated lazily to avoid importing browser/httpx at module load.
_REGISTRY: dict[CompanyCode, str] = {
    CompanyCode.WELLS_FARGO: "job_intelligence.adapters.wells_fargo:WellsFargoAdapter",
    CompanyCode.GOLDMAN_SACHS: "job_intelligence.adapters.goldman_sachs:GoldmanSachsAdapter",
    CompanyCode.BNY: "job_intelligence.adapters.bny:BNYAdapter",
}

__all__ = ["JobSourceAdapter", "get_adapter_ref"]


def get_adapter_ref(company: CompanyCode) -> str:
    """Return the 'module:Class' reference for a company's adapter."""
    return _REGISTRY[company]
