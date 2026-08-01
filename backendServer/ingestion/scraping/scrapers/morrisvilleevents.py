"""Town of Morrisville, NC "Events listing" scraper.

https://www.morrisvillenc.gov/Events-directory is the Town's OpenCities/
CivicPlus site content template `oc-events-listing`, server-rendered as a
plain list of `<article>` blocks (`.list-item-container`) -- a plain HTTP GET
already returns the full markup, so this is an `http` source, not `scraper`.

Two catches specific to this site:

* A plain `requests`/`curl` GET with a bare `User-Agent` gets a 403 "Access
  Denied" from the Akamai edge in front of morrisvillenc.gov; adding the
  ordinary `Accept`/`Accept-Language` headers a real browser sends is enough
  to pass. `settings.INGEST_SCRAPER_USER_AGENT` already sets a browser UA for
  the `http` fetch path, so no extra header wiring should be needed here --
  flag it if ingestion starts seeing empty fetches for this key.
* The listing gives no time of day, only a day/month/year (`.part-date`,
  `.part-month`, `.part-year`) -- recurring events show only their *next*
  occurrence here, with a "N more dates" note we don't attempt to follow. We
  default to midnight America/New_York, matching the convention used in
  `visitchapelhill.py` for sources with no time-of-day data.

The sibling page https://www.morrisvillenc.gov/Things-To-Do/Special-Events is
NOT a second source: it's prose plus a client-side-only "please wait while we
load this calendar" widget with no per-event dates in the static HTML, and
the events it will eventually render are a tagged subset of this same
Events-directory feed (several events above already carry a "Special Events"
tag). See `ingestion/tests/fixtures/morrisvilleevents.html` for a trimmed,
real sample of this page's markup.
"""

import hashlib
import logging
import re
from datetime import date, datetime
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
    """Unescape HTML entities, strip tags, and collapse whitespace."""
    return _WS_RE.sub(" ", _TAG_RE.sub(" ", unescape(text or ""))).strip()


def _clean_address(text: str) -> str:
    """Collapse the address `<p>`'s `&nbsp;`-joined, sometimes-trailing-comma text."""
    cleaned = _strip_html(text.replace("\xa0", " "))
    return re.sub(r"\s*,\s*(,\s*)*$", "", cleaned).strip()


def _parse_date(day: str, month_abbr: str, year: str) -> date | None:
    try:
        return datetime.strptime(f"{day} {month_abbr} {year}", "%d %b %Y").date()
    except ValueError:
        return None


class MorrisvilleeventsScraper(Scraper):
    key = "morrisvilleevents"
    url = "https://www.morrisvillenc.gov/Events-directory"
    name = "Town of Morrisville"
    source_type = "http"

    def extract(self, html: str) -> list[RawEventData]:
        tree = lxml_html.fromstring(html)
        items = tree.xpath('//div[contains(@class, "list-item-container")]//article')

        today_local = timezone.now().astimezone(_LOCAL_TZ).date()
        events = []
        for item in items:
            links = item.xpath("./a[@href]")
            if not links:
                continue
            link = links[0]
            source_url = link.get("href", "").strip()

            title_nodes = link.xpath('.//h2[@class="list-item-title"]')
            title = title_nodes[0].text_content().strip() if title_nodes else ""
            if not title or not source_url:
                continue

            day_nodes = link.xpath('.//span[@class="part-date"]')
            month_nodes = link.xpath('.//span[@class="part-month"]')
            year_nodes = link.xpath('.//span[@class="part-year"]')
            if not (day_nodes and month_nodes and year_nodes):
                continue
            event_date = _parse_date(
                day_nodes[0].text_content().strip(),
                month_nodes[0].text_content().strip(),
                year_nodes[0].text_content().strip(),
            )
            if event_date is None or event_date < today_local:
                continue
            start = datetime.combine(event_date, datetime.min.time(), tzinfo=_LOCAL_TZ)

            desc_nodes = link.xpath('.//span[@class="list-item-block-desc"]')
            description = _strip_html(desc_nodes[0].text_content()) if desc_nodes else ""

            address_nodes = link.xpath('.//p[@class="list-item-address"]')
            location = _clean_address(address_nodes[0].text_content()) if address_nodes else ""

            source_uid = (
                source_url
                or hashlib.sha256(f"{title}{event_date.isoformat()}".encode()).hexdigest()
            )

            events.append(
                RawEventData(
                    title=title,
                    start=start,
                    description=description,
                    location=location,
                    end=None,
                    source_url=source_url,
                    source_uid=source_uid,
                )
            )

        return events
