"""Scraper registry: scraper_key -> Scraper instance.

Mirrors `broadcast/adapters/__init__.py`'s adapter registry. Site-specific
extraction logic lives in each scraper's own module; this file only wires
them up by key.
"""

from ingestion.scraping.scrapers.visitpittsboro import VisitpittsboroScraper

_SCRAPERS = [
    VisitpittsboroScraper(),
]


def registry() -> dict:
    """All known scrapers by key."""
    return {s.key: s for s in _SCRAPERS}


def get_scraper(key: str):
    return registry().get(key)
