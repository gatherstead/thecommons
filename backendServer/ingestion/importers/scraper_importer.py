import ipaddress
import logging
import socket
from urllib.parse import urlparse

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


def fetch_scraper_source(source: EventSource) -> list[RawEvent]:
    """
    Render a scraper-type source's page, extract events with its registered
    per-site scraper, and save as RawEvent records.
    Returns list of newly created RawEvents.
    """
    assert source.source_type == "scraper", "Source must be scraper type"

    if not _is_public_url(source.url):
        logger.warning(f"Refusing to poll non-public URL for {source.name}: {source.url}")
        return []

    scraper = get_scraper(source.scraper_key)
    if scraper is None:
        logger.warning(f"Unknown or blank scraper_key for {source.name}: {source.scraper_key!r}")
        return []

    # PHASE 1: browser render (no ORM).
    html = render_page(source.url)

    # PHASE 2: pure extraction (no ORM, no browser).
    items = scraper.extract(html)

    # PHASE 3: ORM writes, after the browser phase is done.
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


def poll_all_scraper_sources(shard: tuple[int, int] | None = None):
    """Poll all active scraper sources that are due for a refresh.

    If `shard=(n, m)` is supplied, only sources where `id % m == n` are considered.
    This lets cron spread polling across `m` days so each run only touches ~1/m of
    the sources — load is even across the week and the per-source `poll_interval_hours`
    throttle still guards against accidental double-polls.
    """
    sources = EventSource.objects.filter(source_type="scraper", active=True)
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
            new_events = fetch_scraper_source(source)
            total_new += len(new_events)
        except Exception as e:
            logger.error(f"Error polling {source.name}: {e}")

    return total_new
