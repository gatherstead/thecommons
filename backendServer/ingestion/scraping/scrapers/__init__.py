"""Scraper registry: scraper_key -> Scraper instance.

Mirrors `broadcast/adapters/__init__.py`'s adapter registry. Site-specific
extraction logic lives in each scraper's own module; this file only wires
them up by key.
"""

from ingestion.scraping.scrapers.theplantnc import TheplantncScraper
from ingestion.scraping.scrapers.visitchapelhill import VisitchapelhillScraper
from ingestion.scraping.scrapers.visitpittsboro import VisitpittsboroScraper

_SCRAPERS = [
    TheplantncScraper(),
    VisitchapelhillScraper(),
    VisitpittsboroScraper(),
]


def registry() -> dict:
    """All known scrapers by key."""
    return {s.key: s for s in _SCRAPERS}


def get_scraper(key: str):
    return registry().get(key)


def list_scrapers() -> list[dict]:
    """Registered scrapers as `{"key", "url", "name"}` dicts, sorted by key.

    Feeds the devtools playground's scraper picker: choosing a key auto-fills
    the target URL and the English source name, since each scraper is
    custom-built for one site.
    """
    return [
        {"key": s.key, "url": getattr(s, "url", ""), "name": getattr(s, "name", "")}
        for s in sorted(_SCRAPERS, key=lambda s: s.key)
    ]
