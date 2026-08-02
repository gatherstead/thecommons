"""Thriving in Raleigh events calendar scraper.

https://www.thrivinginraleigh.com/events runs Squarespace's built-in
"Events" summary block, which is server-rendered -- a plain `requests.get()`
already returns the full `.eventlist-event` markup, so `source_type =
"http"`. There's no schema.org JSON-LD on this page (unlike
`visitpittsboro.py`), but each event carries a "Add to Google Calendar"
link (`.eventlist-meta-export-google`) whose `dates=` query param is a UTC
start/end pair -- e.g. `dates=20260815T160000Z/20260815T170000Z`. That's
used instead of the localized `<time class="event-time-localized-start">`
text because multi-day events (e.g. a two-day festival) omit those
localized time elements entirely but still carry a full `dates=` range on
the Google Calendar link.

The venue name sits as a bare text node before the "(map)" link inside
`.eventlist-meta-address`; the fuller postal address (when present) is only
available in that link's `maps.google.com?q=...` query param, so both are
combined into `location`, deduplicated when they're identical (e.g. a venue
with no separately-listed address, where the map link just repeats the
venue name).
"""

import logging
import re
from datetime import UTC, datetime
from urllib.parse import parse_qs, unquote_plus, urljoin, urlparse

from django.utils import timezone
from lxml import html as lxml_html

from ingestion.scraping.scrapers.base import RawEventData, Scraper

logger = logging.getLogger("ingestion")

_BASE_URL = "https://www.thrivinginraleigh.com"
_GCAL_DATES_RE = re.compile(r"dates=(\d{8}T\d{6}Z)/(\d{8}T\d{6}Z)")


def _parse_gcal_utc(value: str) -> datetime:
    return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)


class ThrivinginraleighScraper(Scraper):
    key = "thrivinginraleigh"
    url = "https://www.thrivinginraleigh.com/events"
    name = "Thriving in Raleigh"
    source_type = "http"

    def extract(self, html: str) -> list[RawEventData]:
        tree = lxml_html.fromstring(html)
        now = timezone.now()
        events = []

        for article in tree.xpath('//article[contains(@class, "eventlist-event")]'):
            title_nodes = article.xpath('.//h1[@class="eventlist-title"]/a')
            if not title_nodes:
                continue
            title_link = title_nodes[0]
            title = title_link.text_content().strip()
            href = title_link.get("href", "")
            if not title or not href:
                continue
            source_url = urljoin(_BASE_URL, href)

            gcal_href = article.xpath(
                './/a[contains(@class, "eventlist-meta-export-google")]/@href'
            )
            if not gcal_href:
                continue
            match = _GCAL_DATES_RE.search(gcal_href[0])
            if not match:
                continue
            start = _parse_gcal_utc(match.group(1))
            end = _parse_gcal_utc(match.group(2))

            if start < now:
                continue

            location = self._extract_location(article)

            desc_nodes = article.xpath(
                './/div[@class="eventlist-description"]//div[contains(@class, "sqs-html-content")]'
            )
            description = " ".join(
                text for node in desc_nodes if (text := node.text_content().strip())
            )
            description = re.sub(r"\s+", " ", description).strip()

            events.append(
                RawEventData(
                    title=title,
                    start=start,
                    description=description,
                    location=location,
                    end=end,
                    source_url=source_url,
                    source_uid=href,
                )
            )

        return events

    @staticmethod
    def _extract_location(article) -> str:
        addr_nodes = article.xpath('.//li[contains(@class, "eventlist-meta-address")]')
        if not addr_nodes:
            return ""
        li = addr_nodes[0]
        venue = (li.text or "").strip()

        address = ""
        map_href = li.xpath('.//a[contains(@class, "eventlist-meta-address-maplink")]/@href')
        if map_href:
            query = urlparse(map_href[0]).query
            values = parse_qs(query).get("q", [])
            if values:
                address = unquote_plus(values[0]).strip()

        if address and address != venue:
            return f"{venue}, {address}" if venue else address
        return venue
