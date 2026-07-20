"""Playwright Chromium lifecycle management.

Preserved as a first-class capability even though all three verified adapters use
direct HTTP: it powers reconnaissance and the browser fallback strategies. Pages,
contexts, and the browser are always closed reliably.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from ..config import Settings
from ..logging import get_logger

if TYPE_CHECKING:
    from playwright.async_api import BrowserContext

log = get_logger("browser")


@asynccontextmanager
async def browser_context(settings: Settings) -> AsyncIterator[BrowserContext]:
    """Yield a Chromium browser context, closing everything on exit."""
    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=settings.headless)
        context = await browser.new_context(user_agent=settings.scrape_user_agent)
        try:
            yield context
        finally:
            await context.close()
            await browser.close()
            log.debug("browser.closed")
