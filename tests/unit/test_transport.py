"""Transport safety: allowlist enforcement and artifact sanitization."""

from __future__ import annotations

import pytest

from job_intelligence.config import get_settings
from job_intelligence.domain.exceptions import ConfigurationError, DisallowedDomainError
from job_intelligence.extraction.artifacts import sanitize_headers, sanitize_url
from job_intelligence.extraction.rate_limit import DomainRateLimiter
from job_intelligence.extraction.transport import (
    DirectHttpTransport,
    TransportFactory,
    TransportRequest,
)


async def test_disallowed_domain_is_rejected() -> None:
    transport = DirectHttpTransport(
        settings=get_settings(),
        allowed_domains={"www.wellsfargojobs.com"},
        rate_limiter=DomainRateLimiter(),
    )
    try:
        with pytest.raises(DisallowedDomainError):
            await transport.get(TransportRequest(url="https://evil.example.com/jobs"))
    finally:
        await transport.aclose()


def test_factory_refuses_proxy_until_approved(monkeypatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "proxy_enabled", True)
    factory = TransportFactory(settings)
    with pytest.raises(ConfigurationError):
        factory.for_company("wells_fargo")


def test_sanitizers_redact_secrets() -> None:
    headers = sanitize_headers(
        {"Cookie": "s=abc", "Authorization": "Bearer x", "Accept": "application/json"}
    )
    assert headers["Cookie"] == "<redacted>"
    assert headers["Authorization"] == "<redacted>"
    assert headers["Accept"] == "application/json"
    assert "SECRET" not in sanitize_url("https://x.com/j?token=SECRET&page=1")
    assert "page=1" in sanitize_url("https://x.com/j?token=SECRET&page=1")
