"""VisitChapelHill events scraper.

https://www.visitchapelhill.org/events/ runs Simpleview's tourism CMS. The
events list is loaded client-side via a token-gated REST call
(`includes/rest_v2/plugins_events_events_by_date/find/`, gated by a
per-session `core.simpleToken` the page's JS mints at runtime) into an
initially-empty `.layoutjsContainer` div, so a plain HTTP fetch returns none
of the event markup -- this must run through Playwright (`source_type =
scraper`), not `http`. Once rendered, each event is a `.item[data-recid]`
block; see `ingestion/tests/fixtures/visitchapelhill.html` for a trimmed,
real sample of that rendered markup, captured via claude-in-chrome.

The rendered list gives no ISO dates: only a month abbreviation + day (no
year, e.g. "Jul 13") and a free-text time string (a "H:MM AM/PM to H:MM
AM/PM" range, a single "H:MM AM/PM", or no time element at all for
recurring/open-ended listings). We infer the year relative to `now` (rolling
forward across a Dec->Jan boundary) and default to midnight when no time is
present. The site gives no UTC offset either, so times are treated as
America/New_York wall-clock time (Chapel Hill, NC) rather than the project's
default UTC -- see `visitpittsboro.py`/`theplantnc.py` for contrast, where
tz-aware ISO8601 was already available from the source.
"""

import hashlib
import logging
import re
from datetime import datetime
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

from django.utils import timezone
from lxml import html as lxml_html

from ingestion.scraping.scrapers.base import RawEventData, Scraper

logger = logging.getLogger("ingestion")

_BASE_URL = "https://www.visitchapelhill.org"
_LOCAL_TZ = ZoneInfo("America/New_York")
_TIME_RE = re.compile(r"(\d{1,2}:\d{2}\s*[AP]M)", re.IGNORECASE)


def _infer_year(month_abbr: str, now: datetime) -> int:
    """Pick the year for a bare "Mon DD" date relative to `now`.

    The listing is always current-or-future, so a month earlier than `now`'s
    month means it wrapped into next year (e.g. "now" is December, event
    month is "Jan").
    """
    try:
        event_month = datetime.strptime(month_abbr, "%b").month
    except ValueError:
        return now.year
    return now.year + 1 if event_month < now.month else now.year


def _parse_datetime(month_abbr: str, day: str, year: int, time_str: str | None) -> datetime | None:
    hour, minute = 0, 0
    if time_str:
        try:
            parsed_time = datetime.strptime(time_str.strip().upper(), "%I:%M %p")
            hour, minute = parsed_time.hour, parsed_time.minute
        except ValueError:
            pass
    try:
        naive = datetime.strptime(f"{month_abbr} {day} {year}", "%b %d %Y").replace(hour=hour, minute=minute)
    except ValueError:
        return None
    return naive.replace(tzinfo=_LOCAL_TZ)


class VisitchapelhillScraper(Scraper):
    key = "visitchapelhill"
    url = "https://www.visitchapelhill.org/events/"
    name = "Visit Chapel Hill"
    # The list is empty at "domcontentloaded" -- it's filled in by a client-side
    # XHR to a token-gated REST endpoint that fires after initial page load.
    wait_selector = "[data-recid]"

    def extract(self, html: str) -> list[RawEventData]:
        tree = lxml_html.fromstring(html)
        items = tree.xpath('//div[@data-recid and contains(concat(" ", normalize-space(@class), " "), " item ")]')

        now = timezone.now()
        events = []
        for item in items:
            title_links = item.xpath('.//h4/a[contains(@class, "title")]')
            if not title_links:
                continue
            title_link = title_links[0]
            title = title_link.text_content().strip()
            href = title_link.get("href", "")
            source_url = urljoin(_BASE_URL, href) if href else ""

            month_nodes = item.xpath('.//span[@class="mini-date-container"]/span[@class="month"]')
            day_nodes = item.xpath('.//span[@class="mini-date-container"]/span[@class="day"]')
            if not month_nodes or not day_nodes:
                continue
            month_abbr = month_nodes[0].text_content().strip()
            day = day_nodes[0].text_content().strip()

            time_nodes = item.xpath('.//li[contains(@class, "time")]')
            time_text = time_nodes[0].text_content().strip() if time_nodes else ""
            times = _TIME_RE.findall(time_text)
            start_time = times[0] if len(times) >= 1 else None
            end_time = times[1] if len(times) >= 2 else None

            year = _infer_year(month_abbr, now)
            start = _parse_datetime(month_abbr, day, year, start_time)
            if start is None:
                continue
            end = _parse_datetime(month_abbr, day, year, end_time) if end_time else None

            location_links = item.xpath('.//li[contains(@class, "locations")]//a')
            location = location_links[0].text_content().strip() if location_links else ""

            recid = item.get("data-recid", "")
            source_uid = recid or hashlib.sha256(f"{title}{month_abbr}{day}{year}".encode()).hexdigest()

            events.append(
                RawEventData(
                    title=title,
                    start=start,
                    location=location,
                    end=end,
                    source_url=source_url,
                    source_uid=source_uid,
                )
            )

        # Compare by calendar date, not exact clock time: the source site's own
        # date-range filter keeps all of "today"'s events regardless of whether
        # their start time has already passed, and we want the same events a
        # human sees on the page, not a stricter subset.
        today_local = now.astimezone(_LOCAL_TZ).date()
        return [event for event in events if event.start.astimezone(_LOCAL_TZ).date() >= today_local]
