"""Chapel Hill Community Arts & Culture events feed.

https://www.chapelhillarts.org/festivals-events/ (the assigned URL) turns
out to be a hand-curated marketing page ("Fall & Winter Happenings") with no
machine-readable dates. But its nav links to https://www.chapelhillarts.org/
calendar/, a WordPress page that renders a FullCalendar.js widget backed by
a real REST endpoint the page's own inline script points at:

    GET /wp-json/nmc-feeds/v1/events?start=<date>&end=<date>

This is a plain public JSON API -- no auth, no WAF, works over a bare
`requests.get()` with just a UA header -- so this is an `http` source, no
browser needed. The endpoint requires the `start`/`end` query params (an
unparameterized request returns `[]`); rather than encode "now" into a URL
that would go stale, `url` uses a fixed wide window (2020-2035) so the same
static URL keeps working over the scraper's whole lifetime -- the past-event
filter below discards anything before "now" regardless of how wide the feed
is.

The API caps out at 5 items per query and appears to sort by post id
(creation order) rather than by date, so a few upcoming events can be
missing from any given response -- that's a limitation of the feed itself,
not something to work around here.

The feed's `end` field is not valid ISO8601 (e.g.
`"2026-07-25T3:00 pm"` -- a date-only ISO prefix pasted next to a
free-text 12-hour clock string), so it's dropped rather than parsed.
"""

import json
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from django.utils import timezone

from ingestion.scraping.scrapers.base import RawEventData, Scraper

logger = logging.getLogger("ingestion")

_LOCAL_TZ = ZoneInfo("America/New_York")


def _parse_start(value: str) -> datetime | None:
    try:
        naive = datetime.fromisoformat(value)
    except ValueError:
        return None
    # The feed gives no UTC offset; these are Chapel Hill, NC events, so
    # treat the wall-clock time as America/New_York (see visitchapelhill.py
    # for the same convention on a source with no offset).
    return naive.replace(tzinfo=_LOCAL_TZ)


class ChapelhillartsScraper(Scraper):
    key = "chapelhillarts"
    url = (
        "https://www.chapelhillarts.org/wp-json/nmc-feeds/v1/events?start=2020-01-01&end=2035-12-31"
    )
    name = "Chapel Hill Community Arts & Culture"
    source_type = "http"

    def extract(self, html: str) -> list[RawEventData]:
        try:
            items = json.loads(html)
        except (json.JSONDecodeError, TypeError):
            return []
        if not isinstance(items, list):
            return []

        now = timezone.now()
        events = []
        for node in items:
            if not isinstance(node, dict):
                continue
            start_raw = node.get("start")
            title = (node.get("title") or "").strip()
            if not start_raw or not title:
                continue

            start = _parse_start(start_raw)
            if start is None or start < now:
                continue

            event_id = node.get("id")
            source_uid = str(event_id) if event_id is not None else ""
            if not source_uid:
                continue

            events.append(
                RawEventData(
                    title=title,
                    start=start,
                    source_url=node.get("url") or "",
                    source_uid=source_uid,
                )
            )

        return events
