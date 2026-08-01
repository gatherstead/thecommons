"""Patch.com Morrisville, NC calendar scraper.

The assigned URL (https://patch.com/north-carolina/morrisville-nc) is a
section landing page with no dated event listing (`allEvents` is absent
from its `__NEXT_DATA__`). Its `/calendar` sibling --
https://patch.com/north-carolina/morrisville-nc/calendar -- does exist and
is the same server-rendered Next.js app as Durham's (see `patchdurham.py`),
so that's what this scraper targets. Like Pittsboro, Morrisville's calendar
carries no Patch-authored `type: "event"` nodes as of 2026-07-31 -- every
listing is a `patchAmFreeEvent` syndicated from Patch's third-party
aggregator. Extraction is shared via `PatchScraper` in `patch.py`, which
reads both node shapes.
"""

from ingestion.scraping.scrapers.patch import PatchScraper


class PatchmorrisvilleScraper(PatchScraper):
    key = "patchmorrisville"
    url = "https://patch.com/north-carolina/morrisville-nc/calendar"
    name = "Patch Morrisville"
