"""The Plant NC events scraper.

https://www.theplantnc.com/events runs Wix's Events app, server-rendered:
`curl` with no JS returns the full event list. Rather than scrape the
calendar grid's DOM (Wix emits obfuscated, build-specific CSS-module class
names like `ExCBIq` that will change on any site republish), we read the
site's own SSR state: a `<script type="application/json"
id="wix-warmup-data">` blob that Wix embeds on every page load, containing
the Events app's warmed-up data with full event objects (id, slug, title,
description, ISO8601 scheduling, location). The exact nesting under
`appsWarmupData` varies by page (random per-widget component ids, and pages
with multiple Wix Events widgets duplicate the same events under each), so
we walk the parsed JSON recursively for any dict that looks like an event
(`scheduling` + `title` + `location` keys) rather than hard-coding a path,
and dedupe by `id`. See
`ingestion/tests/fixtures/theplantnc.html` for a trimmed, real sample.
"""

import hashlib
import json
import logging
from datetime import datetime

from django.utils import timezone
from lxml import html as lxml_html

from ingestion.scraping.scrapers.base import RawEventData, Scraper

logger = logging.getLogger("ingestion")

_EVENT_KEYS = {"scheduling", "title", "location"}


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed)
    return parsed


def _iter_event_dicts(node):
    """Recursively walk parsed warmup-data JSON, yielding Wix event dicts.

    Wix nests the Events app's data under a per-page-instance,
    per-widget-component path (`appsWarmupData/<appDefId>/<widgetCompId>/...`)
    that isn't stable across builds, so we scan structurally instead.
    """
    if isinstance(node, dict):
        if _EVENT_KEYS.issubset(node.keys()):
            yield node
            return
        for value in node.values():
            yield from _iter_event_dicts(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_event_dicts(item)


def _to_raw_event(node: dict) -> RawEventData | None:
    config = (node.get("scheduling") or {}).get("config") or {}
    start_raw = config.get("startDate")
    if not start_raw:
        return None
    try:
        start = _parse_datetime(start_raw)
    except ValueError:
        return None

    end = None
    end_raw = config.get("endDate")
    if end_raw:
        try:
            end = _parse_datetime(end_raw)
        except ValueError:
            end = None

    title = node.get("title", "")
    slug = node.get("slug", "")
    source_url = f"https://www.theplantnc.com/event-details/{slug}" if slug else ""
    location = (node.get("location") or {}).get("name", "")
    source_uid = node.get("id") or hashlib.sha256(f"{title}{start_raw}".encode()).hexdigest()

    return RawEventData(
        title=title,
        start=start,
        description=node.get("description", ""),
        location=location,
        end=end,
        source_url=source_url,
        source_uid=source_uid,
    )


class TheplantncScraper(Scraper):
    key = "theplantnc"
    url = "https://www.theplantnc.com/events"
    name = "The Plant"
    source_type = "http"

    def extract(self, html: str) -> list[RawEventData]:
        tree = lxml_html.fromstring(html)
        raw_blocks = tree.xpath('//script[@id="wix-warmup-data"]/text()')

        deduped: dict[str, dict] = {}
        for raw in raw_blocks:
            try:
                data = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                continue
            for node in _iter_event_dicts(data):
                event_id = node.get("id")
                if event_id:
                    deduped[event_id] = node

        now = timezone.now()
        events = [_to_raw_event(node) for node in deduped.values()]
        return [event for event in events if event is not None and event.start >= now]
