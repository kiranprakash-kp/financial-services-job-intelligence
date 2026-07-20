"""Shared, per-domain async rate limiting.

Bounds concurrency per domain and enforces a minimum delay between operations so
the POC stays polite. A single limiter instance should be shared across all
requests to a given domain within a process.
"""

from __future__ import annotations

import asyncio
import time
from urllib.parse import urlparse


class DomainRateLimiter:
    """Concurrency cap + min-delay spacing, tracked independently per domain."""

    def __init__(self, concurrency: int = 2, min_delay_seconds: float = 1.0) -> None:
        self._concurrency = max(1, concurrency)
        self._min_delay = max(0.0, min_delay_seconds)
        self._semaphores: dict[str, asyncio.Semaphore] = {}
        self._last_call: dict[str, float] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    @staticmethod
    def _domain(url: str) -> str:
        return urlparse(url).netloc.lower()

    def _sem(self, domain: str) -> asyncio.Semaphore:
        if domain not in self._semaphores:
            self._semaphores[domain] = asyncio.Semaphore(self._concurrency)
            self._locks[domain] = asyncio.Lock()
        return self._semaphores[domain]

    def slot(self, url: str) -> _Slot:
        domain = self._domain(url)
        self._sem(domain)
        return _Slot(self, domain)

    async def _pace(self, domain: str) -> None:
        async with self._locks[domain]:
            last = self._last_call.get(domain, 0.0)
            wait = self._min_delay - (time.monotonic() - last)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_call[domain] = time.monotonic()


class _Slot:
    def __init__(self, limiter: DomainRateLimiter, domain: str) -> None:
        self._limiter = limiter
        self._domain = domain

    async def __aenter__(self) -> None:
        await self._limiter._semaphores[self._domain].acquire()
        await self._limiter._pace(self._domain)

    async def __aexit__(self, *_exc: object) -> None:
        self._limiter._semaphores[self._domain].release()
