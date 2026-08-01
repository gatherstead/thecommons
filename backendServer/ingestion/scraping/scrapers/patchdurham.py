"""Patch.com Durham, NC calendar scraper.

https://patch.com/north-carolina/durham-nc/calendar is a Next.js app, but
server-rendered: `curl` with no JS returns the full event list, so this is an
`http` source rather than a `scraper` one. Rather than scrape the calendar
DOM (Patch emits build-hashed CSS-module class names like
`styles_eventCard__x7Fq2` that change on any redeploy), we read Next.js's own
hydration state: the `<script id="__NEXT_DATA__" type="application/json">`
blob every page embeds, containing full event objects (id, title, body,
address, ISO8601 `displayDate`, canonical permalink).

Events live under `props.pageProps.mainContent.allEvents`, a dict keyed by
day-bucket epoch timestamp -> list of events. The bucket key is the *day*, not
the event's start, so we always read `displayDate` for the actual start time.
Patch's payload carries no end time, so `end` is left None. See
`ingestion/tests/fixtures/patchdurham.html` for a trimmed, real sample.
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
_WS_RE = re.compile(r"\s+")

_BASE_URL = "https://patch.com"


def _strip_html(text: str) -> str:
    """Unescape HTML entities then strip tags, collapsing whitespace."""
    return _WS_RE.sub(" ", _TAG_RE.sub(" ", unescape(text or ""))).strip()


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed)
    return parsed


def _format_location(address: dict) -> str:
    """Venue name plus street address.

    The standardizer infers `town` from this string, so keep the city/region
    rather than passing the venue name alone.
    """
    parts = [
        address.get("name"),
        address.get("streetAddress"),
        address.get("city"),
        address.get("region"),
    ]
    return ", ".join(p.strip() for p in parts if p and p.strip())


def _to_raw_event(node: dict) -> RawEventData | None:
    start_raw = node.get("displayDate")
    if not start_raw:
        return None
    try:
        start = _parse_datetime(start_raw)
    except ValueError:
        return None

    title = _strip_html(node.get("title", ""))
    if not title:
        return None

    path = node.get("canonicalUrl") or node.get("itemAlias") or ""
    source_url = f"{_BASE_URL}{path}" if path.startswith("/") else path

    address = node.get("address")
    location = _format_location(address) if isinstance(address, dict) else ""

    source_uid = node.get("id") or hashlib.sha256(f"{title}{start_raw}".encode()).hexdigest()

    return RawEventData(
        title=title,
        start=start,
        description=_strip_html(node.get("body") or node.get("summary") or ""),
        location=location,
        end=None,  # Patch's calendar payload carries no end time
        source_url=source_url,
        source_uid=source_uid,
    )


class PatchdurhamScraper(Scraper):
    key = "patchdurham"
    url = "https://patch.com/north-carolina/durham-nc/calendar"
    name = "Patch Durham"
    source_type = "http"

    def extract(self, html: str) -> list[RawEventData]:
        tree = lxml_html.fromstring(html)
        raw_blocks = tree.xpath('//script[@id="__NEXT_DATA__"]/text()')

        deduped: dict[str, dict] = {}
        for raw in raw_blocks:
            try:
                data = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                continue

            main_content = data.get("props", {}).get("pageProps", {}).get("mainContent") or {}
            all_events = main_content.get("allEvents")
            if not isinstance(all_events, dict):
                continue

            # Keyed by day-bucket epoch; a multi-day event repeats under each
            # bucket it spans, so dedupe by Patch's event id.
            for bucket in all_events.values():
                if not isinstance(bucket, list):
                    continue
                for node in bucket:
                    if isinstance(node, dict) and node.get("id"):
                        deduped[node["id"]] = node

        now = timezone.now()
        events = [_to_raw_event(node) for node in deduped.values()]
        return [event for event in events if event is not None and event.start >= now]
