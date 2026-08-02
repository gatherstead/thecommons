"""Cary Sister Cities events scraper.

https://www.carysistercities.org/events-1 runs Squarespace's built-in Events
collection, server-rendered: `curl` with no JS returns the full upcoming +
past listing as `<article class="eventlist-event">` blocks (Squarespace's
stock "eventlist" template), so `source_type = "http"`. There's no JSON-LD
`Event` block or `?format=ical` feed at the collection level (Squarespace
only exposes `?format=ical` per-event), so we parse the rendered markup
directly.

Each event's date/time meta (`.eventlist-meta-date`,
`.eventlist-meta-time`) only gives a *local* date/time string with no UTC
offset, but the page's own "Add to Google Calendar" link
(`.eventlist-meta-export-google`) embeds a `dates=<start>/<end>` query
param already resolved to UTC (`YYYYMMDDTHHMMSSZ`) — that's a more
reliable source of truth than re-deriving America/New_York offsets
ourselves (DST), so we parse it from there. See
`ingestion/tests/fixtures/carysistercities.html` for a trimmed, real
sample.
"""

import hashlib
import logging
import re
from datetime import UTC, datetime
from urllib.parse import urljoin

from django.utils import timezone
from lxml import html as lxml_html

from ingestion.scraping.scrapers.base import RawEventData, Scraper

logger = logging.getLogger("ingestion")

_BASE_URL = "https://www.carysistercities.org"
_GCAL_DATES_RE = re.compile(r"dates=(\d{8}T\d{6}Z)/(\d{8}T\d{6}Z)")


def _parse_gcal_stamp(stamp: str) -> datetime:
    return datetime.strptime(stamp, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)


def _collapse_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


class CarysistercitiesScraper(Scraper):
    key = "carysistercities"
    url = "https://www.carysistercities.org/events-1"
    name = "Cary Sister Cities"
    source_type = "http"

    def extract(self, html: str) -> list[RawEventData]:
        tree = lxml_html.fromstring(html)
        articles = tree.xpath(
            '//article[contains(concat(" ", normalize-space(@class), " "), " eventlist-event ")]'
        )

        now = timezone.now()
        events = []
        for article in articles:
            title_links = article.xpath('.//h1[contains(@class, "eventlist-title")]/a')
            if not title_links:
                continue
            title_link = title_links[0]
            title = _collapse_whitespace(title_link.text_content())
            href = title_link.get("href", "")
            source_url = urljoin(_BASE_URL, href) if href else ""

            gcal_links = article.xpath(
                './/a[contains(@class, "eventlist-meta-export-google")]/@href'
            )
            if not gcal_links:
                continue
            match = _GCAL_DATES_RE.search(gcal_links[0])
            if not match:
                continue
            try:
                start = _parse_gcal_stamp(match.group(1))
                end = _parse_gcal_stamp(match.group(2))
            except ValueError:
                continue

            if start < now:
                continue

            address_items = article.xpath('.//li[contains(@class, "eventlist-meta-address")]')
            location = ""
            if address_items:
                # The venue name is the direct text node before the nested
                # "(map)" link, not the link's own text.
                own_text = address_items[0].xpath("./text()")
                location = _collapse_whitespace("".join(own_text))

            description_nodes = article.xpath('.//div[contains(@class, "eventlist-description")]')
            description = (
                _collapse_whitespace(description_nodes[0].text_content())
                if description_nodes
                else ""
            )

            source_uid = (
                source_url or hashlib.sha256(f"{title}{match.group(1)}".encode()).hexdigest()
            )

            events.append(
                RawEventData(
                    title=title,
                    start=start,
                    description=description,
                    location=location,
                    end=end,
                    source_url=source_url,
                    source_uid=source_uid,
                )
            )

        return events
