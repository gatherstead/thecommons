"""VisitRaleigh (and town-filtered) events scraper.

https://www.visitraleigh.com/events/ runs Simpleview's tourism CMS -- the
same platform family as visitchapelhill.org (see that module for the
general pattern). The events list is loaded client-side via a token-gated
REST call (`includes/rest_v2/plugins_events_events/aggregate/`, gated by a
per-session `core.simpleToken` the page's JS mints at runtime) into an
initially-empty `.eventsContainer` widget templated with jsrender
(`{{:...}}` placeholders visible in the raw HTML) -- a plain HTTP fetch
returns none of the rendered event markup, so this must run through
Playwright (`source_type = scraper`), not `http`. Once rendered, each event
is an `.eventItem[data-recid]` block; see
`ingestion/tests/fixtures/visitraleigh.html` for a trimmed, real sample of
that rendered markup.

Unlike visitchapelhill, the rendered date text here (`li.dateInfo`) always
carries at least one full "Month D, YYYY" date -- e.g. "July 31, 2026",
"Dates vary between July 31, 2026 - August 1, 2026", or "Recurring weekly
on ... until August 9, 2026" -- so no year-rollover inference is needed. We
take the first full date found as `start` and the last one (if a second is
present) as `end`; a bare "Recurring ... until <date>" listing has only one
date to find, so it becomes `start` with no `end` -- this loses the exact
next-occurrence date for recurring events but keeps them correctly dated in
the future, matching the site's own "still showing" semantics rather than
dropping them. Time-of-day comes from `li.times` (e.g. "Fri., 8:30pm",
"Fri., 9:15pm; Sat., 9pm", "Fri., 6pm & Sat., 12pm or 2pm"): the first
H[:MM] am/pm token found is used as the start time and applied to `start`
only (correlating each token to a specific day across a range isn't
reliable from this free text); everything else defaults to midnight. The
site gives no UTC offset, so times are treated as America/New_York
wall-clock time (Raleigh, NC) -- see visitchapelhill.py for the same
convention.

`visitraleigh_cary.py` is a town-filtered view of the same calendar (a
distinct `data-sv-eventLayout` widget instance) and reuses `_extract_events`
below -- see that module for its own notes. `visitraleigh_morrisville.py`
does not exist: that URL is a static editorial page with no dated event
listing or widget at all (see the source-creation report).
"""

import logging
import re
from datetime import datetime
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

from django.utils import timezone
from lxml import html as lxml_html

from ingestion.scraping.scrapers.base import RawEventData, Scraper

logger = logging.getLogger("ingestion")

_BASE_URL = "https://www.visitraleigh.com"
_LOCAL_TZ = ZoneInfo("America/New_York")
_DATE_RE = re.compile(r"[A-Z][a-z]+ \d{1,2}, \d{4}")
_TIME_RE = re.compile(r"\d{1,2}(?::\d{2})?\s*[APap][Mm]")


def _parse_date(date_str: str) -> datetime | None:
    try:
        return datetime.strptime(date_str, "%B %d, %Y")
    except ValueError:
        return None


def _parse_time(time_str: str) -> tuple[int, int]:
    """Parse a "H:MM AM/PM" or "H AM/PM" token into (hour, minute)."""
    cleaned = time_str.strip().upper().replace(" ", "")
    for fmt in ("%I:%M%p", "%I%p"):
        try:
            parsed = datetime.strptime(cleaned, fmt)
            return parsed.hour, parsed.minute
        except ValueError:
            continue
    return 0, 0


def _combine(date_part: datetime, hour: int, minute: int) -> datetime:
    return date_part.replace(hour=hour, minute=minute, tzinfo=_LOCAL_TZ)


def _extract_events(html: str) -> list[RawEventData]:
    """Shared extraction for the main calendar and its town-filtered views.

    Both run the identical jsrender `.eventItem[data-recid]` template --
    only the widget instance (and therefore which events it returns) differs
    per page.
    """
    tree = lxml_html.fromstring(html)
    items = tree.xpath(
        '//div[@data-recid and contains(concat(" ", normalize-space(@class), " "), " item ")]'
    )

    now = timezone.now()
    events = []
    for item in items:
        recid = item.get("data-recid", "")
        if not recid or recid == "{{recId}}":
            continue  # unrendered jsrender template placeholder

        title_links = item.xpath(".//h3/a")
        if not title_links:
            continue
        title_link = title_links[0]
        title = title_link.text_content().strip()
        if not title:
            continue
        href = title_link.get("href", "")
        source_url = urljoin(_BASE_URL, href) if href else ""

        date_nodes = item.xpath('.//li[contains(@class, "dateInfo")]')
        date_text = date_nodes[0].text_content().strip() if date_nodes else ""
        date_matches = _DATE_RE.findall(date_text)
        if not date_matches:
            continue
        start_date = _parse_date(date_matches[0])
        if start_date is None:
            continue
        end_date = _parse_date(date_matches[-1]) if len(date_matches) > 1 else None

        time_nodes = item.xpath('.//li[contains(@class, "times")]')
        time_text = time_nodes[0].text_content().strip() if time_nodes else ""
        time_matches = _TIME_RE.findall(time_text)
        hour, minute = _parse_time(time_matches[0]) if time_matches else (0, 0)

        start = _combine(start_date, hour, minute)
        end = _combine(end_date, 0, 0) if end_date else None

        location_links = item.xpath('.//li[contains(@class, "location")]//a')
        location = location_links[0].text_content().strip() if location_links else ""

        events.append(
            RawEventData(
                title=title,
                start=start,
                location=location,
                end=end,
                source_url=source_url,
                source_uid=recid,
            )
        )

    # Compare by calendar date, not exact clock time -- same rationale as
    # visitchapelhill.py: keep all of "today"'s events regardless of whether
    # their start time already passed, matching what a human sees on the page.
    today_local = now.astimezone(_LOCAL_TZ).date()
    return [event for event in events if event.start.astimezone(_LOCAL_TZ).date() >= today_local]


class VisitraleighScraper(Scraper):
    key = "visitraleigh"
    url = "https://www.visitraleigh.com/events/"
    name = "Visit Raleigh"
    source_type = "scraper"
    # The list is empty at "domcontentloaded" -- it's filled in by a
    # client-side XHR to a token-gated REST endpoint that fires after
    # initial page load.
    wait_selector = "[data-recid]"

    def extract(self, html: str) -> list[RawEventData]:
        return _extract_events(html)
