"""Triangle on the Cheap regional events aggregator scraper.

https://triangleonthecheap.com/events/ is **not** WordPress "The Events
Calendar" (Tribe) -- despite the site's own "brewery calendar" copy, there's
no `tribe-events` markup anywhere on the page. It's a custom "Living on the
Cheap" network theme: day buckets are `<h2 class="lotc-event">` headers
("Today: Friday, July 31, 2026", "Tomorrow: Saturday, August 1, 2026", or
just "Sunday, August 2, 2026" further out) followed by a flat run of sibling
`<div class="lotc-v2 row event">` blocks -- one event each -- until the next
`h2.lotc-event`. The page is fully server-rendered by a plain
`requests.get()`, so `source_type = "http"`. No ICS feed exists (`?ical=1`,
`/events.ics`, `/feed.ics` all 404 or fall through to the HTML page).

Each event block has a title link and a single free-text "meta" line
(`<p class="meta">`) pipe-delimited as `time | price | venue` -- venue is
omitted for a chunk of listings (2 segments only), so it's read
defensively. Time is always written with an explicit am/pm on the leading
token (unlike `downtownraleigh.py`'s "8pm-11pm" compression), so only the
first token needs to be parsed; "All Day" and other non-clock text default
to midnight.

This is a regional aggregator spanning many Triangle towns (Raleigh,
Durham, Cary, Hillsborough, Apex, ...), and its own recurring listings
(e.g. a monthly brewery night) reuse the same permalink across multiple
dates *and*, on the same date, across multiple distinct sub-listings (e.g.
three different "Last Fridays" entries all linking to one Hillsborough art
walk page) -- so `source_uid` combines the permalink, the calendar date, and
the title to stay unique per occurrence while staying stable across polls.
"""

import logging
import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

from django.utils import timezone
from lxml import html as lxml_html

from ingestion.scraping.scrapers.base import RawEventData, Scraper

logger = logging.getLogger("ingestion")

_LOCAL_TZ = ZoneInfo("America/New_York")
_DATE_HEADER_RE = re.compile(r"(?:Today: |Tomorrow: )?(.+)")
_START_TIME_RE = re.compile(r"(\d{1,2}):(\d{2})\s*([ap]m)", re.IGNORECASE)


def _parse_header_date(text: str) -> date | None:
    match = _DATE_HEADER_RE.match(text.strip())
    body = match.group(1) if match else text.strip()
    try:
        return datetime.strptime(body, "%A, %B %d, %Y").date()
    except ValueError:
        return None


def _parse_start_time(text: str) -> tuple[int, int]:
    match = _START_TIME_RE.search(text)
    if not match:
        return (0, 0)
    hour = int(match.group(1)) % 12
    minute = int(match.group(2))
    if match.group(3).lower() == "pm":
        hour += 12
    return (hour, minute)


class TriangleonthecheapScraper(Scraper):
    key = "triangleonthecheap"
    url = "https://triangleonthecheap.com/events/"
    name = "Triangle on the Cheap"
    source_type = "http"

    def extract(self, html: str) -> list[RawEventData]:
        tree = lxml_html.fromstring(html)
        headers = tree.xpath('//h2[@class="lotc-event"]')
        if not headers:
            return []
        container = headers[0].getparent()

        events = []
        current_date = None
        for child in container.iterchildren():
            classes = (child.get("class") or "").split()
            if child.tag == "h2" and "lotc-event" in classes:
                current_date = _parse_header_date(child.text_content())
                continue
            if child.tag != "div" or "lotc-v2" not in classes or "event" not in classes:
                continue
            if current_date is None:
                continue

            link_nodes = child.xpath(".//h3/a")
            if not link_nodes:
                continue
            link = link_nodes[0]
            title = link.text_content().strip()
            href = link.get("href", "")
            if not title or not href:
                continue

            meta_nodes = child.xpath('.//p[@class="meta"]')
            meta_text = meta_nodes[0].text_content().strip() if meta_nodes else ""
            parts = [p.strip() for p in meta_text.split("|")]
            time_text = parts[0] if parts else ""
            venue = parts[-1] if len(parts) >= 3 else ""

            hour, minute = _parse_start_time(time_text)
            naive = datetime(current_date.year, current_date.month, current_date.day, hour, minute)
            start = naive.replace(tzinfo=_LOCAL_TZ)

            events.append(
                RawEventData(
                    title=title,
                    start=start,
                    location=venue,
                    source_url=href,
                    source_uid=f"{href}#{current_date.isoformat()}#{title}",
                )
            )

        today_local = timezone.now().astimezone(_LOCAL_TZ).date()
        return [e for e in events if e.start.astimezone(_LOCAL_TZ).date() >= today_local]
