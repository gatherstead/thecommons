"""Downtown Cary, NC (downtowncarync.org) month-view calendar scraper.

https://downtowncarync.org/events/ runs WordPress "The Events Calendar"
(Tribe) and is server-rendered as a month grid (`tribe-events-calendar-month`
body classes), so this is an `http` source rather than a `scraper` one. Tribe
also exposes an `?ical=1` export on this site, but it only echoes the single
event landing on "today" rather than the full month -- confirmed by fetching
it directly -- so it is not usable as a real feed. The DOM itself carries
every event for the visible month as `<article class="tribe-events-
calendar-month__calendar-event ...">` blocks, each with a compact 24-hour
`<time datetime="HH:MM">` pair in the header and a full `<time
datetime="YYYY-MM-DD">` in a hidden tooltip block that also holds the
plain-text description. No venue/location markup is present in month view,
so `location` is left blank. See
`ingestion/tests/fixtures/downtowncarync.html` for a trimmed, real sample.
"""

import logging
import re
from datetime import datetime
from html import unescape
from zoneinfo import ZoneInfo

from django.utils import timezone
from lxml import html as lxml_html

from ingestion.scraping.scrapers.base import RawEventData, Scraper

logger = logging.getLogger("ingestion")

_LOCAL_TZ = ZoneInfo("America/New_York")
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _strip_html(text: str) -> str:
    """Unescape HTML entities then strip tags, collapsing whitespace."""
    return _WS_RE.sub(" ", _TAG_RE.sub(" ", unescape(text or ""))).strip()


def _parse_datetime(date_str: str, time_str: str | None) -> datetime | None:
    """Combine a tooltip `YYYY-MM-DD` date with a header `HH:MM` 24h time."""
    hour, minute = 0, 0
    if time_str:
        try:
            hour, minute = (int(part) for part in time_str.split(":"))
        except ValueError:
            pass
    try:
        naive = datetime.strptime(date_str, "%Y-%m-%d").replace(hour=hour, minute=minute)
    except ValueError:
        return None
    return naive.replace(tzinfo=_LOCAL_TZ)


class DowntowncarynScraper(Scraper):
    key = "downtowncarync"
    url = "https://downtowncarync.org/events/"
    name = "Downtown Cary, NC"
    source_type = "http"

    def extract(self, html: str) -> list[RawEventData]:
        tree = lxml_html.fromstring(html)
        articles = tree.xpath(
            '//article[contains(concat(" ", normalize-space(@class), " "), '
            '" tribe-events-calendar-month__calendar-event ")]'
        )

        now = timezone.now()
        events = []
        for article in articles:
            title_links = article.xpath(
                './/a[contains(@class, "tribe-events-calendar-month__calendar-event-title-link")]'
            )
            if not title_links:
                continue
            title_link = title_links[0]
            title = _strip_html(title_link.text_content())
            source_url = title_link.get("href", "")
            if not title or not source_url:
                continue

            date_nodes = article.xpath(
                './/div[contains(@class, "tribe-events-calendar-month__calendar-event-'
                'tooltip-datetime")]//time/@datetime'
            )
            if not date_nodes:
                continue
            date_str = date_nodes[0]

            time_nodes = article.xpath(
                './/div[contains(concat(" ", normalize-space(@class), " "), '
                '" tribe-events-calendar-month__calendar-event-datetime ")]/time/@datetime'
            )
            start_time = time_nodes[0] if len(time_nodes) >= 1 else None
            end_time = time_nodes[1] if len(time_nodes) >= 2 else None

            start = _parse_datetime(date_str, start_time)
            if start is None:
                continue
            if start < now:
                continue

            end = _parse_datetime(date_str, end_time) if end_time else None

            description_nodes = article.xpath(
                './/div[contains(@class, "tribe-events-calendar-month__calendar-event-'
                'tooltip-description")]'
            )
            description = (
                _strip_html(description_nodes[0].text_content()) if description_nodes else ""
            )

            # The permalink is stable across polls (WordPress slug), so use it
            # directly as the unique id rather than hashing.
            source_uid = source_url

            events.append(
                RawEventData(
                    title=title,
                    start=start,
                    description=description,
                    location="",
                    end=end,
                    source_url=source_url,
                    source_uid=source_uid,
                )
            )

        return events
