"""VisitPittsboro month-view scraper.

https://visitpittsboro.com/events/month/ runs "The Events Calendar" (Tribe)
WordPress plugin and is server-rendered. Rather than scrape Tribe's CSS-class
DOM (brittle across plugin versions/themes), we read the page's own
schema.org JSON-LD: a `<script type="application/ld+json">` block containing
a list of `Event` objects with stable permalinks, ISO8601 dates with tz
offsets, and a `location.name`. See
`ingestion/tests/fixtures/visitpittsboro_month.html` for a trimmed, real
sample of this block.
"""

import hashlib
import json
import logging
import re
from datetime import datetime
from html import unescape

from django.utils import timezone
from lxml import html as lxml_html

from ingestion.scraping.scrapers.base import RawEventData, Scraper

logger = logging.getLogger("ingestion")

_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    """Unescape HTML entities then strip tags, leaving plain text."""
    return _TAG_RE.sub("", unescape(text or "")).strip()


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed)
    return parsed


def _iter_event_nodes(blocks: list):
    """Yield schema.org Event dicts out of a list of parsed JSON-LD payloads.

    A payload may be a list of nodes, a single node, or a `{"@graph": [...]}`
    wrapper — handle all three defensively.
    """
    for data in blocks:
        candidates = data.get("@graph", data) if isinstance(data, dict) else data
        if isinstance(candidates, dict):
            candidates = [candidates]
        if not isinstance(candidates, list):
            continue
        for node in candidates:
            if isinstance(node, dict) and node.get("@type") == "Event":
                yield node


class VisitpittsboroScraper(Scraper):
    key = "visitpittsboro"
    url = "https://visitpittsboro.com/events/month/"
    name = "Visit Pittsboro"
    source_type = "http"

    def extract(self, html: str) -> list[RawEventData]:
        tree = lxml_html.fromstring(html)
        raw_blocks = tree.xpath('//script[@type="application/ld+json"]/text()')

        parsed_blocks = []
        for raw in raw_blocks:
            try:
                parsed_blocks.append(json.loads(raw))
            except (json.JSONDecodeError, TypeError):
                continue

        events = []
        now = timezone.now()
        for node in _iter_event_nodes(parsed_blocks):
            start_raw = node.get("startDate")
            if not start_raw:
                continue
            try:
                start = _parse_datetime(start_raw)
            except ValueError:
                continue

            if start < now:
                continue

            end = None
            end_raw = node.get("endDate")
            if end_raw:
                try:
                    end = _parse_datetime(end_raw)
                except ValueError:
                    end = None

            title = _strip_html(node.get("name", ""))
            source_url = node.get("url") or ""
            location = node.get("location") or {}
            location_name = location.get("name", "") if isinstance(location, dict) else ""

            source_uid = source_url or hashlib.sha256(f"{title}{start_raw}".encode()).hexdigest()

            events.append(
                RawEventData(
                    title=title,
                    start=start,
                    description=_strip_html(node.get("description", "")),
                    location=location_name,
                    end=end,
                    source_url=source_url,
                    source_uid=source_uid,
                )
            )

        return events
