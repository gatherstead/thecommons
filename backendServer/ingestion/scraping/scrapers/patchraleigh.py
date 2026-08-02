"""Patch.com Raleigh, NC calendar scraper.

https://patch.com/north-carolina/raleigh/calendar is the same server-
rendered Next.js app as Durham's (see `patchdurham.py`) and, as of
2026-07-31, carries only Patch-authored `type: "event"` nodes (no
aggregated `patchAmFreeEvent` listings on this page). Extraction is shared
via `PatchScraper` in `patch.py`, which reads both node shapes.
"""

from ingestion.scraping.scrapers.patch import PatchScraper


class PatchraleighScraper(PatchScraper):
    key = "patchraleigh"
    url = "https://patch.com/north-carolina/raleigh/calendar"
    name = "Patch Raleigh"
