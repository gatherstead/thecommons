"""Town of Chapel Hill "Town Calendar" scraper.

https://www.chapelhillnc.gov/Events-and-Activities/Town-Calendar runs on
Granicus's OpenCities CMS (an ASP.NET/Telerik platform, *not* CivicPlus --
there is no `/common/modules/iCalendar/` feed here, and no `.ics`/`webcal`
link on the page). The calendar grid is populated client-side: the page
issues `POST /ocapi/calendars/getcalendaritems` with a JSON body
(`{"Ids": [...], "StartDate": ..., "EndDate": ...}`) and injects the results
into `.calendar-body-content-day` cells, so a plain HTTP fetch of the page
returns an empty grid -- this must run through Playwright
(`source_type = "scraper"`).

The site sits behind an Akamai edge WAF that 403s *every* plain `curl`/
`requests` request against the domain -- including, surprisingly, the JSON
API itself even when the exact browser-observed headers (Referer, Origin,
Accept) are replayed -- while headless Chromium passes cleanly. So `http`
is not viable even for the JSON endpoint; `scraper` is the only path in.

The rendered DOM is data-poor: each day cell exposes only the event title
and a stable per-series GUID (`data-item-id`) via `.calendar-item`, grouped
under a `.calendar-body-content-day[data-date]` cell whose `.full-date`
paragraph carries the accessible month/day/year text (e.g. "Thursday, July
2, 2026"). No start time, location, description, or permalink is present in
the DOM -- those only exist in the JSON response body, which `extract()`
never sees since it's handed the rendered page HTML, not the XHR payload.
So `start` is set to local midnight for every event (same fallback
`visitchapelhill.py` uses when a source gives no time), and `location`/
`description`/`source_url` are left blank rather than invented.

Recurring series (e.g. a monthly "Food Distribution") reuse the same
`data-item-id` across multiple dates, so `source_uid` combines the item id
with the day's date to stay unique per occurrence while remaining stable
across polls.
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
# ".full-date" accessible text reads e.g. "Thursday, July 2, 2026" (weekday
# and day-of-month are split across separate <span>s by the day number, but
# `text_content()` concatenates them in document order).
_DATE_RE = re.compile(r"([A-Z][a-z]+)\s+(\d{1,2}),\s*(\d{4})")


def _parse_day(full_date_text: str) -> date | None:
    match = _DATE_RE.search(full_date_text)
    if not match:
        return None
    month_name, day, year = match.groups()
    try:
        return datetime.strptime(f"{month_name} {day} {year}", "%B %d %Y").date()
    except ValueError:
        return None


class ChapelhillncScraper(Scraper):
    key = "chapelhillnc"
    url = "https://www.chapelhillnc.gov/Events-and-Activities/Town-Calendar"
    name = "Town of Chapel Hill"
    source_type = "scraper"
    # The grid is empty until the client-side XHR to /ocapi/calendars/getcalendaritems
    # resolves and populates it.
    wait_selector = ".calendar-item"

    def extract(self, html: str) -> list[RawEventData]:
        tree = lxml_html.fromstring(html)
        day_cells = tree.xpath('//div[contains(@class, "calendar-body-content-day")][@data-date]')

        now = timezone.now()
        today_local = now.astimezone(_LOCAL_TZ).date()

        events = []
        for cell in day_cells:
            full_date_nodes = cell.xpath('.//p[contains(@class, "full-date")]')
            if not full_date_nodes:
                continue
            day = _parse_day(full_date_nodes[0].text_content())
            if day is None or day < today_local:
                continue

            start = datetime(day.year, day.month, day.day, tzinfo=_LOCAL_TZ)

            for item in cell.xpath('.//li[contains(@class, "calendar-item")]'):
                title = (item.get("title") or "").strip()
                if not title:
                    title_nodes = item.xpath('.//span[contains(@class, "calendar-item-title")]')
                    title = title_nodes[0].text_content().strip() if title_nodes else ""
                if not title:
                    continue

                item_id_nodes = item.xpath(".//a[@data-item-id]")
                item_id = item_id_nodes[0].get("data-item-id") if item_id_nodes else ""
                source_uid = (
                    f"{item_id}:{day.isoformat()}" if item_id else f"{title}:{day.isoformat()}"
                )

                events.append(
                    RawEventData(
                        title=title,
                        start=start,
                        source_uid=source_uid,
                    )
                )

        return events
