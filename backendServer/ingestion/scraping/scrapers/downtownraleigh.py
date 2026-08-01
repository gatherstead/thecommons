"""Downtown Raleigh Alliance events calendar scraper.

https://downtownraleigh.org/events/calendar loads its list via a client-side
XHR to a third-party widget (`https://xapi.citylightstudio.net/_bbq/_bbq_results.php
?fid=53&key=075313126&bbqparam=`) that returns a server-rendered HTML fragment
for the *current* week -- no JS is needed to read it, so this scraper fetches
that fragment URL directly (`source_type = "http"`) instead of the marketing
page. Paging forward/back is just a different `bbqparam` value, but a single
current-week fetch is enough for ingestion (nothing gates repeat polls from
picking up next week's events once they enter this window).

Fragility, audited 2026-07-31: `downtownraleigh.org` has no first-party
calendar of its own -- its marketing page's own JS still calls this exact
endpoint (confirmed live), so this vendor fragment *is* the source of
truth, not a workaround. The `key=` query param looked like a fragile
embedded credential, but empirically it is not validated at all: the same
`fid=53` feed renders identically with the current live key (`08613126`,
which has already drifted from this module's `075313126` since it was
first written), a garbage key, or no `key` param whatsoever. So the only
real fragility here is CityLightStudio/`fid=53` itself -- i.e. Downtown
Raleigh Alliance switching calendar vendors entirely, which would 404 or
change the markup outright rather than degrade quietly.

The fragment groups events into `.bbq-row` blocks, one per calendar day (month
abbreviation + day only, e.g. "Jul" / "31" -- no year), each holding an
`<li>` per event with a title and a free-text "time / venue" line (e.g.
"8pm-11pm / Crank Arm Brewing", or just a venue name with no time at all for
listings that omit hours). There's no per-event ISO date or JSON-LD anywhere
on this site, so the year comes from the fragment's own header ("Jul 31 –
Aug 6, 2026") and the start time is regex-parsed out of that free text,
defaulting to midnight when no time is present. A trailing `.bbq-row` with no
month/day (an "Ongoing" bucket for long-running exhibits) is skipped since it
carries no date to anchor a `start` on.

Recurring listings (e.g. a weekly karaoke night) reuse the same `/do/<slug>`
permalink across every date they appear on, so `source_uid` combines the slug
with that day's date to stay unique per occurrence while staying stable
across polls.
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

_BASE_URL = "https://downtownraleigh.org"
_LOCAL_TZ = ZoneInfo("America/New_York")
_YEAR_RE = re.compile(r"(\d{4})")
_RANGE_TIME_RE = re.compile(
    r"(\d{1,2})(?::(\d{2}))?\s*([ap]\.?m\.?)?\s*-\s*(\d{1,2})(?::(\d{2}))?\s*([ap]\.?m\.?)",
    re.IGNORECASE,
)
_SINGLE_TIME_RE = re.compile(r"(\d{1,2})(?::(\d{2}))?\s*([ap]\.?m\.?)", re.IGNORECASE)


def _parse_start_time(text: str) -> tuple[int, int] | None:
    """Best-effort (hour, minute) out of a free-text time string.

    Handles "8pm-11pm", "1-3pm" (meridiem only on the trailing number, applied
    to both), "11AM" (single token), and returns None for venue-only text with
    no time at all (e.g. "Haymaker").
    """
    if not text:
        return None
    match = _RANGE_TIME_RE.search(text)
    if match:
        ampm = match.group(3) or match.group(6)
        return _to_24h(match.group(1), match.group(2), ampm)
    match = _SINGLE_TIME_RE.search(text)
    if match:
        return _to_24h(match.group(1), match.group(2), match.group(3))
    return None


def _to_24h(hour_str: str, minute_str: str | None, ampm: str | None) -> tuple[int, int]:
    hour = int(hour_str) % 12
    minute = int(minute_str) if minute_str else 0
    if ampm and ampm.lower().startswith("p"):
        hour += 12
    return hour, minute


class DowntownraleighScraper(Scraper):
    key = "downtownraleigh"
    url = "https://xapi.citylightstudio.net/_bbq/_bbq_results.php?fid=53&key=075313126&bbqparam="
    name = "Downtown Raleigh Alliance"
    source_type = "http"

    def extract(self, html: str) -> list[RawEventData]:
        tree = lxml_html.fromstring(html)

        header_nodes = tree.xpath('//div[@class="bbq-results-header-middle"]')
        year_match = _YEAR_RE.search(header_nodes[0].text_content()) if header_nodes else None
        year = int(year_match.group(1)) if year_match else timezone.now().year

        events = []
        for row in tree.xpath('//div[@class="bbq-row"]'):
            month_nodes = row.xpath('.//div[@class="bbqdate-month"]')
            day_nodes = row.xpath('.//div[@class="bbqdate-day"]')
            if not month_nodes or not day_nodes:
                continue  # e.g. the trailing "Ongoing" bucket, no dated anchor
            month_abbr = month_nodes[0].text_content().strip()
            day = day_nodes[0].text_content().strip()

            for item in row.xpath('.//div[@class="bbq-row-list"]//li'):
                links = item.xpath("./a")
                if not links:
                    continue
                link = links[0]
                href = link.get("href", "")
                source_url = urljoin(_BASE_URL, href) if href else ""

                title_nodes = link.xpath('.//div[@class="lnk-primary"]')
                if not title_nodes:
                    continue
                title = title_nodes[0].text_content().strip()

                secondary_nodes = link.xpath('.//div[@class="lnk-secondary"]')
                secondary_text = (
                    secondary_nodes[0].text_content().strip() if secondary_nodes else ""
                )
                if "/" in secondary_text:
                    time_text, _, venue = secondary_text.partition("/")
                else:
                    time_text, venue = "", secondary_text
                venue = venue.strip()
                time_text = time_text.strip()

                hour, minute = _parse_start_time(time_text) or (0, 0)
                try:
                    naive = datetime.strptime(f"{month_abbr} {day} {year}", "%b %d %Y").replace(
                        hour=hour, minute=minute
                    )
                except ValueError:
                    continue
                start = naive.replace(tzinfo=_LOCAL_TZ)

                location = f"{venue}, Raleigh, NC" if venue else "Downtown Raleigh, NC"
                source_uid = f"{href}#{start.date().isoformat()}" if href else ""

                events.append(
                    RawEventData(
                        title=title,
                        start=start,
                        location=location,
                        source_url=source_url,
                        source_uid=source_uid,
                    )
                )

        # Compare by calendar date (America/New_York), not exact clock time --
        # a handful of events have no parsed time and default to midnight,
        # which would otherwise read as "already past" for today's own events.
        today_local = timezone.now().astimezone(_LOCAL_TZ).date()
        return [
            event for event in events if event.start.astimezone(_LOCAL_TZ).date() >= today_local
        ]
