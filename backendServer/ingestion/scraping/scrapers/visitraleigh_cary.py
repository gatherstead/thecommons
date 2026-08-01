"""VisitRaleigh events scraper, filtered to Cary.

https://www.visitraleigh.com/plan-a-trip/cities-and-towns/cary/events/ runs
a distinct `data-sv-eventLayout` instance of the exact same Simpleview
jsrender events widget as the main calendar (`visitraleigh.py`) -- same
token-gated REST call, same `.eventItem[data-recid]` rendered markup, so
this reuses that module's `_extract_events` rather than duplicating the
parsing logic. See `visitraleigh.py`'s module docstring for the date/time
parsing rules.

At capture time (2026-07-31) this Cary-scoped widget returned zero live
results ("No events were found."), unlike the main calendar -- a real,
reproducible site state (confirmed across repeated renders, including a
30s wait and scrolling the widget into view), not a fetch failure. The
fixture therefore reuses other real event blocks from the same platform/
template (see `ingestion/tests/fixtures/visitraleigh_cary.html`) rather
than the page's own (empty) live output, since an empty fixture would
exercise nothing. The scraper itself is unaffected: the widget shape and
extraction logic are identical, and the source will pick up real Cary
events whenever the site returns any.
"""

from ingestion.scraping.scrapers.base import RawEventData, Scraper
from ingestion.scraping.scrapers.visitraleigh import _extract_events


class VisitraleighCaryScraper(Scraper):
    key = "visitraleigh_cary"
    url = "https://www.visitraleigh.com/plan-a-trip/cities-and-towns/cary/events/"
    name = "Visit Raleigh (Cary)"
    source_type = "scraper"
    wait_selector = "[data-recid]"

    def extract(self, html: str) -> list[RawEventData]:
        return _extract_events(html)
