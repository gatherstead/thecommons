"""Sync-Playwright page render: renders a JS-heavy page and returns its HTML.

Runs inside a Celery worker / management command (plain sync code — no
asyncio, no ORM). Per-site scrapers in later tickets call `render_page` and
parse the returned HTML string themselves.

No Django ORM inside `sync_playwright()` blocks — see broadcast/runner.py
for why (Playwright keeps an asyncio loop on the thread, which the ORM's
async-aware connection locals mishandle). This module takes plain args and
returns a plain str, so that guardrail is moot here, but the discipline
(one browser per call, always closed) is kept for the same memory-safety
reasons on the 6 GB VM.
"""

import logging

from django.conf import settings
from playwright.sync_api import sync_playwright

logger = logging.getLogger("ingestion")

# Conservative flags for the 6 GB ARM64 VM. Bundled Chromium only —
# never set a branded Chrome channel (unsupported on arm64 Linux).
CHROMIUM_ARGS = ["--disable-dev-shm-usage"]


def render_page(
    url: str, *, wait_selector: str | None = None, timeout_ms: int | None = None
) -> str:
    """Render a page with headless Chromium and return its HTML. Returns "" on any error."""
    effective_timeout = timeout_ms if timeout_ms is not None else settings.INGEST_SCRAPER_TIMEOUT_MS
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=settings.INGEST_SCRAPER_HEADLESS, args=CHROMIUM_ARGS
            )
            try:
                context = browser.new_context(user_agent=settings.INGEST_SCRAPER_USER_AGENT)
                page = context.new_page()
                # "domcontentloaded", not "networkidle": ad/analytics-heavy sites
                # (WordPress especially) keep firing background requests that never
                # settle, so networkidle reliably times out and we lose the page.
                # For content that needs JS/XHR, pass `wait_selector` instead.
                page.goto(url, wait_until="domcontentloaded", timeout=effective_timeout)
                if wait_selector:
                    page.wait_for_selector(wait_selector, timeout=effective_timeout)
                return page.content()
            finally:
                browser.close()
    except Exception:
        logger.exception("render_page failed for %s", url)
        return ""
