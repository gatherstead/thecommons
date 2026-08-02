"""Eventbrite Pittsboro, NC discovery page.

Same platform as `eventbriteraleigh.py` — see that module's docstring for
the `__SERVER_DATA__` extraction strategy and the shared
`extract_eventbrite_events` helper this class delegates to. Only the city
slug differs.

Quality note: of this page's unique, non-online events (2026-07-31 capture),
only ~45% (12 of 28) were actually Pittsboro-located; the rest spilled in
from Raleigh, Durham, and cities hours away (Charlotte, Greensboro,
Winston-Salem). See `eventbriteraleigh.py` for the full signal comparison
across all three NC cities this suite covers.
"""

from ingestion.scraping.scrapers.base import RawEventData, Scraper
from ingestion.scraping.scrapers.eventbriteraleigh import extract_eventbrite_events


class EventbritepittsboroScraper(Scraper):
    key = "eventbritepittsboro"
    url = "https://www.eventbrite.com/d/nc--pittsboro/events/"
    name = "Eventbrite Pittsboro"
    source_type = "http"

    def extract(self, html: str) -> list[RawEventData]:
        return extract_eventbrite_events(html)
