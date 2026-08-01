"""Chatham Chamber of Commerce community events scraper.

https://business.chathamchambernc.org/chatham-community-events runs
GrowthZone/ChamberMaster's events widget on the chamber's `business.`
subdomain and is server-rendered: a plain `requests.get()` already returns
the full event list, so this is an `http` source rather than a `scraper`
one. The chamber's site has no ICS/iCal export (checked common paths:
`/events.ics`, `/calendar.ics`, `/feed.ics`, none exist).

Rather than scrape GrowthZone's CSS layout classes (`gz-*`, which are
theme-controlled and could be restyled), we read the schema.org microdata
GrowthZone embeds on each `.gz-events-card`: an `itemtype="...Event"` block
whose `<meta itemprop="startDate"|"endDate">` tags carry the real date/time
even when the visible card only shows a "Jan 17 - Dec 22" range, and whose
`itemprop="url"` anchor carries both the title text and the permalink. See
`ingestion/tests/fixtures/chathamchamber.html` for a trimmed, real sample.

The listing page carries no venue/location field, only date, title, and an
optional `itemprop="about"` description -- so `location` is left blank.

Dates are naive `M/D/YYYY H:MM:SS AM/PM` strings with no UTC offset; treated
as America/New_York wall-clock time like `visitchapelhill.py`. Some cards
are recurring/ongoing series whose `startDate` has already passed but whose
`endDate` is still in the future (e.g. a weekly series spanning several
months) -- filtering on `start` alone would drop those live series, so we
keep an event if its last known occurrence (`end` if present, else `start`)
hasn't passed yet.
"""

import logging
import re
from datetime import datetime
from html import unescape
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

from django.utils import timezone
from lxml import html as lxml_html

from ingestion.scraping.scrapers.base import RawEventData, Scraper

logger = logging.getLogger("ingestion")

_BASE_URL = "https://business.chathamchambernc.org"
_LOCAL_TZ = ZoneInfo("America/New_York")
_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    """Unescape HTML entities then strip tags, leaving plain text."""
    return _TAG_RE.sub("", unescape(text or "")).strip()


def _parse_datetime(value: str) -> datetime | None:
    try:
        naive = datetime.strptime(value.strip(), "%m/%d/%Y %I:%M:%S %p")
    except ValueError:
        return None
    return naive.replace(tzinfo=_LOCAL_TZ)


class ChathamchamberScraper(Scraper):
    key = "chathamchamber"
    url = "https://business.chathamchambernc.org/chatham-community-events"
    name = "Chatham Chamber of Commerce"
    source_type = "http"

    def extract(self, html: str) -> list[RawEventData]:
        tree = lxml_html.fromstring(html)
        cards = tree.xpath(
            '//div[contains(concat(" ", normalize-space(@class), " "), " gz-events-card ")]'
        )

        now = timezone.now()
        events = []
        for card in cards:
            title_links = card.xpath('.//h5[@class="card-title"]//a[@itemprop="url"]')
            if not title_links:
                continue
            title_link = title_links[0]
            title = _strip_html(title_link.text_content())
            if not title:
                continue
            href = title_link.get("href", "")
            source_url = urljoin(_BASE_URL, href.split("?")[0]) if href else ""

            start_nodes = card.xpath('.//meta[@itemprop="startDate"]/@content')
            if not start_nodes:
                continue
            start = _parse_datetime(start_nodes[0])
            if start is None:
                continue

            end_nodes = card.xpath('.//meta[@itemprop="endDate"]/@content')
            end = _parse_datetime(end_nodes[0]) if end_nodes else None

            # An ongoing/recurring series keeps its original startDate even
            # after later occurrences fire -- compare against whichever of
            # end/start is later so a still-running series isn't dropped.
            last_known = end or start
            if last_known < now:
                continue

            description_nodes = card.xpath('.//p[@itemprop="about"]')
            description = (
                _strip_html(description_nodes[0].text_content()) if description_nodes else ""
            )

            source_uid = source_url or f"{title}{start_nodes[0]}"

            events.append(
                RawEventData(
                    title=title,
                    start=start,
                    description=description,
                    end=end,
                    source_url=source_url,
                    source_uid=source_uid,
                )
            )

        return events
