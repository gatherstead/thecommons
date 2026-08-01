"""Cary Chamber of Commerce events scraper.

https://www.carychamber.com/upcoming-events.html embeds a "WeblinkConnect"
(Atlas AMS) events widget (`<div data-wli-widget="event-org-block">`) that's
empty in the server-rendered page and filled in by a client-side XHR after
load. Rather than pay for a Playwright render, we call the widget's own
backing data endpoint directly -- captured via a headless-render network
trace -- which returns plain XML with no auth required:

    https://web.carychamber.com/External/WCControls/V12/WebDeps/Widgets/events/wli-org-events2.aspx?maxresults=60&entityid=0

So `source_type = "http"` targets that XML endpoint directly instead of the
HTML page. Each `<Event_List_Scrolling_org_Result_v2>` node carries a stable
numeric `EventId`, a date (`StartDate`, e.g. "Aug 05, 2026") and a separate
free-text time (`StartTime`, e.g. "9:00 AM" or "12:00 Noon") -- `StartDateTime`
looks ISO8601 with a UTC offset but is a placeholder that's always
`T12:00:00+00:00` regardless of the real time, so we build the real
start/end from `StartDate` + `StartTime`/`EndTime` instead. The site gives no
UTC offset for the real time, so (like `visitchapelhill.py`) we treat it as
America/New_York wall-clock time (Cary, NC). The event permalink is built
from `EventId` using the same path the widget's own XSL template renders
(`/events/eventdetail.aspx?eventid=<id>`, confirmed to redirect to the
friendly Atlas URL). See `ingestion/tests/fixtures/carychamber.html` for a
trimmed, real sample of this XML feed (with one event back-dated to exercise
the past-event filter).
"""

import logging
import re
from datetime import datetime
from html import unescape
from zoneinfo import ZoneInfo

from django.utils import timezone
from lxml import etree

from ingestion.scraping.scrapers.base import RawEventData, Scraper

logger = logging.getLogger("ingestion")

_BASE_URL = "https://web.carychamber.com"
_LOCAL_TZ = ZoneInfo("America/New_York")
_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    """Unescape HTML entities then strip tags, leaving plain text.

    `Description` is XML-escaped HTML: the XML parser only undoes one layer
    of escaping, leaving literal `<p>`/`&nbsp;` text behind that still needs
    an HTML-level unescape + tag strip.
    """
    return _TAG_RE.sub("", unescape(text or "")).strip()


def _parse_time_of_day(time_str: str) -> tuple[int, int]:
    """Parse a free-text time like "9:00 AM" or the site's own "12:00 Noon"."""
    cleaned = time_str.strip()
    if cleaned.lower() == "12:00 noon":
        return 12, 0
    if cleaned.lower() == "12:00 midnight":
        return 0, 0
    try:
        parsed = datetime.strptime(cleaned.upper(), "%I:%M %p")
    except ValueError:
        return 0, 0
    return parsed.hour, parsed.minute


def _parse_datetime(date_str: str, time_str: str | None) -> datetime | None:
    try:
        naive = datetime.strptime(date_str.strip(), "%b %d, %Y")
    except ValueError:
        return None
    hour, minute = _parse_time_of_day(time_str) if time_str else (0, 0)
    return naive.replace(hour=hour, minute=minute, tzinfo=_LOCAL_TZ)


class CarychamberScraper(Scraper):
    key = "carychamber"
    url = (
        "https://web.carychamber.com/External/WCControls/V12/WebDeps/Widgets/"
        "events/wli-org-events2.aspx?maxresults=60&entityid=0"
    )
    name = "Cary Chamber of Commerce"
    source_type = "http"

    def extract(self, html: str) -> list[RawEventData]:
        try:
            root = etree.fromstring(html.encode("utf-8"))
        except etree.XMLSyntaxError:
            return []

        now = timezone.now()
        events = []
        for node in root.findall(".//Event_List_Scrolling_org_Result_v2"):
            event_id = (node.findtext("EventId") or "").strip()
            title = _strip_html(node.findtext("EventName") or "")
            start_date = node.findtext("StartDate") or ""
            if not event_id or not title or not start_date:
                continue

            start = _parse_datetime(start_date, node.findtext("StartTime"))
            if start is None:
                continue
            if start < now:
                continue

            end_date = node.findtext("EndDate") or start_date
            end = _parse_datetime(end_date, node.findtext("EndTime"))

            events.append(
                RawEventData(
                    title=title,
                    start=start,
                    description=_strip_html(node.findtext("Description") or ""),
                    end=end,
                    source_url=f"{_BASE_URL}/events/eventdetail.aspx?eventid={event_id}",
                    source_uid=event_id,
                )
            )

        return events
