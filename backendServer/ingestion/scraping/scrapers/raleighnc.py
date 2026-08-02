"""City of Raleigh citywide events calendar scraper.

https://raleighnc.gov/events is Drupal-rendered (city government site,
Drupal "Emulsify"-style theme). No JSON-LD is present, but the "Upcoming
Events" section -- unlike the separate "Ongoing Events" sidebar block, whose
`field--name-field-date` div is always empty -- is a genuine server-rendered
listing: each `<article class="c-event-teaser ...">` carries a `<time
datetime="...">` with a full ISO8601 timestamp and UTC offset, so no
day-header text parsing is needed at all (contrast `downtownraleigh.py`,
which has to reconstruct dates from a "Jul"/"31" split with no year on the
row itself). A plain `requests.get()` already returns this markup, so
`source_type = "http"`.

The listing carries no venue/address field anywhere -- confirmed absent from
every teaser and its category "subtitle" tags on a saved live sample -- so
`location` defaults to a flat "Raleigh, NC" for every event; that's still
enough for the downstream town standardizer since this is a citywide feed.
The subtitle `field__item` tags (city department / event category, e.g.
"Boards and Commissions") are the only descriptive text on the listing page
itself, so they're joined into `description` rather than left empty.

A single page fetch only returns the first ~12 upcoming events (the view is
paginated), but that's enough for ingestion the same way a single current-
week fetch is enough for `downtownraleigh.py` -- repeat polls pick up events
as they enter this window.
"""

import logging
from datetime import datetime
from urllib.parse import urljoin

from django.utils import timezone
from lxml import html as lxml_html

from ingestion.scraping.scrapers.base import RawEventData, Scraper

logger = logging.getLogger("ingestion")

_BASE_URL = "https://raleighnc.gov"


class RaleighncScraper(Scraper):
    key = "raleighnc"
    url = "https://raleighnc.gov/events"
    name = "City of Raleigh"
    source_type = "http"

    def extract(self, html: str) -> list[RawEventData]:
        tree = lxml_html.fromstring(html)
        now = timezone.now()
        events = []

        for article in tree.xpath('//article[contains(@class, "c-event-teaser")]'):
            time_nodes = article.xpath('.//time[@class="c-event-teaser__time"]')
            if not time_nodes:
                continue
            dt_raw = time_nodes[0].get("datetime")
            if not dt_raw:
                continue
            try:
                start = datetime.fromisoformat(dt_raw)
            except ValueError:
                continue
            if timezone.is_naive(start):
                start = timezone.make_aware(start)
            if start < now:
                continue

            link_nodes = article.xpath('.//a[contains(@class, "c-event-teaser__title-link")]')
            if not link_nodes:
                continue
            link = link_nodes[0]
            href = link.get("href", "")
            title = link.text_content().strip()
            if not title:
                continue
            source_url = urljoin(_BASE_URL, href) if href else ""

            category_nodes = article.xpath(
                './/div[@class="c-event-teaser__subtitle"]//p[@class="field__item"]'
            )
            description = "; ".join(
                text for node in category_nodes if (text := node.text_content().strip())
            )

            events.append(
                RawEventData(
                    title=title,
                    start=start,
                    description=description,
                    location="Raleigh, NC",
                    source_url=source_url,
                    source_uid=href or source_url,
                )
            )

        return events
