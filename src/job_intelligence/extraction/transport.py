"""Transport abstraction (direct HTTP now; proxy scaffolded for later).

Adapters request a transport from the factory rather than constructing HTTP or
proxy connections directly. This keeps a future Bright Data proxy transport a
configuration switch — no adapter rewrites. A proxy changes the network route;
it never creates permission to access data, so proxy transports stay disabled by
default and must be explicitly enabled per company.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urlparse

import httpx

from ..config import Settings, load_companies_config
from ..domain.enums import TransportKind
from ..domain.exceptions import (
    AccessDeniedError,
    ConfigurationError,
    DisallowedDomainError,
    RateLimitedError,
    TransientSourceError,
)
from ..logging import get_logger
from .rate_limit import DomainRateLimiter

log = get_logger("transport")

_TRANSIENT_STATUS = {408, 500, 502, 503, 504}
_ACCESS_DENIED_STATUS = {401, 403, 451}


@dataclass(slots=True)
class TransportRequest:
    url: str
    method: str = "GET"
    params: dict | None = None
    json: dict | None = None
    data: dict | str | None = None
    headers: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class TransportResponse:
    status_code: int
    url: str
    headers: dict[str, str]
    text: str
    content_type: str

    def json(self) -> dict:
        import json

        return json.loads(self.text)


class DirectHttpTransport:
    """httpx-backed transport with an allowlist and transient/denied classification."""

    kind = TransportKind.DIRECT_HTTP

    def __init__(
        self,
        settings: Settings,
        allowed_domains: set[str],
        rate_limiter: DomainRateLimiter,
    ) -> None:
        self._settings = settings
        self._allowed = {d.lower() for d in allowed_domains}
        self._rl = rate_limiter
        self._client = httpx.AsyncClient(
            timeout=settings.scrape_request_timeout_seconds,
            follow_redirects=True,
            headers={"User-Agent": settings.scrape_user_agent},
        )

    def _check_domain(self, url: str) -> None:
        host = urlparse(url).netloc.lower()
        if host not in self._allowed:
            raise DisallowedDomainError(f"Domain not in allowlist: {host}")

    async def get(self, request: TransportRequest) -> TransportResponse:
        request.method = "GET"
        return await self._send(request)

    async def post(self, request: TransportRequest) -> TransportResponse:
        request.method = "POST"
        return await self._send(request)

    async def _send(self, request: TransportRequest) -> TransportResponse:
        self._check_domain(request.url)
        form_data = request.data if isinstance(request.data, dict) else None
        raw_content = request.data if isinstance(request.data, str) else None
        async with self._rl.slot(request.url):
            try:
                resp = await self._client.request(
                    request.method,
                    request.url,
                    params=request.params,
                    json=request.json,
                    data=form_data,
                    content=raw_content,
                    headers=request.headers or None,
                )
            except (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError) as exc:
                raise TransientSourceError(f"{type(exc).__name__}: {exc}") from exc

        # A followed redirect must still land on an allowed domain.
        self._check_domain(str(resp.url))

        if resp.status_code == 429:
            retry_after = resp.headers.get("Retry-After")
            hint = float(retry_after) if retry_after and retry_after.isdigit() else None
            raise RateLimitedError("HTTP 429 from source", retry_after_seconds=hint)
        if resp.status_code in _ACCESS_DENIED_STATUS:
            raise AccessDeniedError(
                f"HTTP {resp.status_code} — access denied; stopping (no evasion)."
            )
        if resp.status_code in _TRANSIENT_STATUS:
            raise TransientSourceError(f"HTTP {resp.status_code} from source")

        return TransportResponse(
            status_code=resp.status_code,
            url=str(resp.url),
            headers=dict(resp.headers),
            text=resp.text,
            content_type=resp.headers.get("content-type", ""),
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> DirectHttpTransport:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()


class TransportFactory:
    """Builds the transport a company adapter should use.

    For the POC only DirectHttpTransport is enabled. Proxy transports are
    recognized in configuration but raise until an approved, explicit rollout.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._companies = load_companies_config()
        self._rate_limiter = DomainRateLimiter(
            concurrency=settings.scrape_domain_concurrency,
            min_delay_seconds=settings.scrape_page_delay_seconds,
        )

    def for_company(self, company_code: str, browser_required: bool = False) -> DirectHttpTransport:
        cfg = self._companies.get(company_code)
        proxy_enabled = cfg.proxy_enabled or self._settings.proxy_enabled
        if proxy_enabled:
            raise ConfigurationError(
                "Proxy transport is scaffolded but disabled in the POC. Enabling it "
                "requires explicit legal/security approval (see limitations.md)."
            )
        if browser_required:
            # DirectBrowserTransport is provided via extraction.browser for
            # browser-assisted capture; HTTP transport is returned here for
            # direct-API adapters. All three verified adapters use direct HTTP.
            log.info("transport.browser_requested", company=company_code)
        return DirectHttpTransport(
            settings=self._settings,
            allowed_domains=set(cfg.allowed_domains),
            rate_limiter=self._rate_limiter,
        )
