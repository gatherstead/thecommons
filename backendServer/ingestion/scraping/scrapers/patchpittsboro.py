"""Patch.com Pittsboro, NC calendar scraper.

https://patch.com/north-carolina/pittsboro-nc/calendar is the same server-
rendered Next.js app as Durham's (see `patchdurham.py`), but unlike
Durham/Raleigh, Pittsboro's calendar carries no Patch-authored `type:
"event"` nodes at all -- every listing as of 2026-07-31 is a
`patchAmFreeEvent`, Patch's syndicated third-party events feed (a date plus
a separate 12-hour time string, an address, and a link off patch.com to the
organizer's own page). Extraction is shared via `PatchScraper` in
`patch.py`, which reads both node shapes.
"""

from ingestion.scraping.scrapers.patch import PatchScraper


class PatchpittsboroScraper(PatchScraper):
    key = "patchpittsboro"
    url = "https://patch.com/north-carolina/pittsboro-nc/calendar"
    name = "Patch Pittsboro"
