import ipaddress
import logging
import socket
from collections.abc import Callable
from urllib.parse import urlparse

import requests
from django.conf import settings
from django.utils import timezone

from ingestion.models import EventSource, RawEvent
from ingestion.scraping.browser import render_page
from ingestion.scraping.scrapers import get_scraper

logger = logging.getLogger(__name__)

# ── SSRF guard ────────────────────────────────────────────────────────────────
# Ported from devtools/views.py:_validate_url — devtools is a dev-only app and
# must not be imported from here.

_BLOCKED_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "169.254.169.254"}


def _is_public_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False

    hostname = parsed.hostname
    if not hostname:
        return False

    if hostname in _BLOCKED_HOSTS:
        return False

    try:
        resolved = socket.gethostbyname(hostname)
    except socket.gaierror:
        return False

    ip = ipaddress.ip_address(resolved)
    return not (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved)


def _fetch_via_http(url: str) -> str:
    """Fetch a page's raw HTML over plain HTTP. Returns "" on any error.

    Same failure contract as `render_page` so the two fetch strategies are
    interchangeable. Used by HTTP-type sources whose events are already present
    in the server-rendered HTML (e.g. schema.org JSON-LD) and so need no browser.
    """
    try:
        resp = requests.get(
            url,
            timeout=settings.INGEST_SCRAPER_TIMEOUT_MS / 1000,
            headers={"User-Agent": settings.INGEST_SCRAPER_USER_AGENT},
        )
        resp.raise_for_status()
        return resp.text
    except requests.RequestException:
        logger.exception("HTTP fetch failed for %s", url)
        return ""


def fetch_scraper_source(source: EventSource, *, limit: int | None = None) -> list[RawEvent]:
    """Render a scraper-type source's page with a headless browser, then extract
    and save events. See `_ingest_with_scraper` for the shared body.

    Looks up the scraper up front (rather than leaving it to `_ingest_with_scraper`)
    so its optional `wait_selector` can reach `render_page` -- pages whose event
    markup is injected by a post-load XHR need that to avoid snapshotting the
    DOM before the content arrives.
    """
    assert source.source_type == "scraper", "Source must be scraper type"
    scraper = get_scraper(source.scraper_key)
    wait_selector = getattr(scraper, "wait_selector", None) if scraper else None

    def fetch_html(url: str) -> str:
        return render_page(url, wait_selector=wait_selector)

    return _ingest_with_scraper(source, fetch_html, limit=limit)


def fetch_http_source(source: EventSource, *, limit: int | None = None) -> list[RawEvent]:
    """Fetch an HTTP-type source's page over plain HTTP (no browser), then
    extract and save events. See `_ingest_with_scraper` for the shared body.
    """
    assert source.source_type == "http", "Source must be http type"
    return _ingest_with_scraper(source, _fetch_via_http, limit=limit)


def _ingest_with_scraper(
    source: EventSource, fetch_html: Callable[[str], str], *, limit: int | None = None
) -> list[RawEvent]:
    """Fetch → extract → save, shared by the browser and HTTP fetch strategies.

    Only PHASE 1 (how the HTML is obtained) differs between source types; the
    per-site scraper, extraction, and ORM writes are identical. Returns the list
    of newly created RawEvents.
    """
    if not _is_public_url(source.url):
        logger.warning(f"Refusing to poll non-public URL for {source.name}: {source.url}")
        return []

    scraper = get_scraper(source.scraper_key)
    if scraper is None:
        logger.warning(f"Unknown or blank scraper_key for {source.name}: {source.scraper_key!r}")
        return []

    # PHASE 1: fetch HTML (no ORM). Both fetchers return "" on any error.
    html = fetch_html(source.url)
    if not html:
        # Bail before extract() — feeding empty HTML to a parser just raises a
        # cryptic "Document is empty" far from the real cause.
        logger.warning(f"Empty fetch for {source.name}: {source.url}")
        return []

    # PHASE 2: pure extraction (no ORM, no browser).
    items = scraper.extract(html)
    if limit is not None:
        items = items[:limit]

    # PHASE 3: ORM writes, after the fetch phase is done.
    new_events = []
    for item in items:
        raw_event, created = RawEvent.objects.get_or_create(
            source=source,
            source_uid=item.source_uid,
            defaults={
                "raw_title": item.title[:500],
                "raw_description": item.description,
                "raw_location": item.location[:500],
                "raw_start": item.start,
                "raw_end": item.end,
                "source_url": item.source_url[:500] if item.source_url else "",
            },
        )

        if created:
            new_events.append(raw_event)
            logger.info(f"Imported: {item.title}")
        else:
            logger.debug(f"Skipped (already exists): {item.title}")

    source.last_polled = timezone.now()
    source.save(update_fields=["last_polled"])

    logger.info(f"Imported {len(new_events)} new events from {source.name}")
    return new_events


# Both source types run a per-site scraper's extract(); they differ only in how
# the page HTML is fetched. Map each type to its fetch-and-save entrypoint.
_SCRAPER_FETCHERS = {
    "scraper": fetch_scraper_source,
    "http": fetch_http_source,
}


def poll_all_scraper_sources(shard: tuple[int, int] | None = None):
    """Poll all active scraper- and http-type sources that are due for a refresh.

    If `shard=(n, m)` is supplied, only sources where `id % m == n` are considered.
    This lets cron spread polling across `m` days so each run only touches ~1/m of
    the sources — load is even across the week and the per-source `poll_interval_hours`
    throttle still guards against accidental double-polls.
    """
    sources = EventSource.objects.filter(source_type__in=_SCRAPER_FETCHERS, active=True)
    if shard is not None:
        n, m = shard
        sources = sources.extra(where=["id %% %s = %s"], params=[m, n])
        logger.info(f"Sharded poll: only sources with id %% {m} == {n}")

    total_new = 0
    for source in sources:
        if source.last_polled:
            hours_since = (timezone.now() - source.last_polled).total_seconds() / 3600
            if hours_since < source.poll_interval_hours:
                logger.debug(f"Skipping {source.name} (polled {hours_since:.1f}h ago)")
                continue

        try:
            new_events = _SCRAPER_FETCHERS[source.source_type](source)
            total_new += len(new_events)
        except Exception as e:
            logger.error(f"Error polling {source.name}: {e}")

    return total_new
