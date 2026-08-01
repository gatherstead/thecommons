"""Eventbrite Morrisville, NC discovery page.

Same platform as `eventbriteraleigh.py` — see that module's docstring for
the `__SERVER_DATA__` extraction strategy and the shared
`extract_eventbrite_events` helper this class delegates to. Only the city
slug differs.

Quality warning: this page's "Popular" bucket returned ZERO
Morrisville-located events on inspection (2026-07-31 capture) — every
non-online result was spillover from Raleigh, Durham, or Cary. Extraction
works (see `ingestion/tests/fixtures/eventbritemorrisville.html`, a trimmed
real capture), but this is not, in practice, a Morrisville events source.
Think hard before enabling it — it will surface events already covered by
the Raleigh/Cary sources, misattributed to Morrisville-adjacent noise
rather than adding real local coverage. See `eventbriteraleigh.py` for the
full signal comparison across all three NC cities this suite covers.
"""

from ingestion.scraping.scrapers.base import RawEventData, Scraper
from ingestion.scraping.scrapers.eventbriteraleigh import extract_eventbrite_events


class EventbritemorrisvilleScraper(Scraper):
    key = "eventbritemorrisville"
    url = "https://www.eventbrite.com/d/nc--morrisville/events/"
    name = "Eventbrite Morrisville"
    source_type = "http"

    def extract(self, html: str) -> list[RawEventData]:
        return extract_eventbrite_events(html)
