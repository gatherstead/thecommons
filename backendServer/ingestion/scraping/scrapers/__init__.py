"""Scraper registry: scraper_key -> Scraper instance.

Mirrors `broadcast/adapters/__init__.py`'s adapter registry. Site-specific
extraction logic lives in each scraper's own module; this file only wires
them up by key.
"""

from ingestion.scraping.scrapers.carychamber import CarychamberScraper
from ingestion.scraping.scrapers.carysistercities import CarysistercitiesScraper
from ingestion.scraping.scrapers.chapelhillarts import ChapelhillartsScraper
from ingestion.scraping.scrapers.chapelhillnc import ChapelhillncScraper
from ingestion.scraping.scrapers.chathamchamber import ChathamchamberScraper
from ingestion.scraping.scrapers.downtowncarync import DowntowncarynScraper
from ingestion.scraping.scrapers.downtownraleigh import DowntownraleighScraper
from ingestion.scraping.scrapers.eventbritemorrisville import EventbritemorrisvilleScraper
from ingestion.scraping.scrapers.eventbritepittsboro import EventbritepittsboroScraper
from ingestion.scraping.scrapers.eventbriteraleigh import EventbriteraleighScraper
from ingestion.scraping.scrapers.morrisvillechamber import MorrisvillechamberScraper
from ingestion.scraping.scrapers.morrisvilleevents import MorrisvilleeventsScraper
from ingestion.scraping.scrapers.patchdurham import PatchdurhamScraper
from ingestion.scraping.scrapers.patchmorrisville import PatchmorrisvilleScraper
from ingestion.scraping.scrapers.patchpittsboro import PatchpittsboroScraper
from ingestion.scraping.scrapers.patchraleigh import PatchraleighScraper
from ingestion.scraping.scrapers.raleighnc import RaleighncScraper
from ingestion.scraping.scrapers.theplantnc import TheplantncScraper
from ingestion.scraping.scrapers.thrivinginraleigh import ThrivinginraleighScraper
from ingestion.scraping.scrapers.triangleonthecheap import TriangleonthecheapScraper
from ingestion.scraping.scrapers.visitchapelhill import VisitchapelhillScraper
from ingestion.scraping.scrapers.visitpittsboro import VisitpittsboroScraper
from ingestion.scraping.scrapers.visitraleigh import VisitraleighScraper
from ingestion.scraping.scrapers.visitraleigh_cary import VisitraleighCaryScraper

_SCRAPERS = [
    CarychamberScraper(),
    CarysistercitiesScraper(),
    ChapelhillartsScraper(),
    ChapelhillncScraper(),
    ChathamchamberScraper(),
    DowntowncarynScraper(),
    DowntownraleighScraper(),
    EventbritemorrisvilleScraper(),
    EventbritepittsboroScraper(),
    EventbriteraleighScraper(),
    MorrisvillechamberScraper(),
    MorrisvilleeventsScraper(),
    PatchdurhamScraper(),
    PatchmorrisvilleScraper(),
    PatchpittsboroScraper(),
    PatchraleighScraper(),
    RaleighncScraper(),
    TheplantncScraper(),
    ThrivinginraleighScraper(),
    TriangleonthecheapScraper(),
    VisitchapelhillScraper(),
    VisitpittsboroScraper(),
    VisitraleighScraper(),
    VisitraleighCaryScraper(),
]


def registry() -> dict:
    """All known scrapers by key."""
    return {s.key: s for s in _SCRAPERS}


def get_scraper(key: str):
    return registry().get(key)


def list_scrapers() -> list[dict]:
    """Registered scrapers as `{"key", "url", "name", "source_type"}` dicts, by key.

    Feeds the devtools playground's scraper picker and `seed_sources`: choosing
    a key auto-fills the target URL, the English source name, and whether the
    page needs Playwright ("scraper") or a plain fetch ("http"), since each
    scraper is custom-built for one site.
    """
    return [
        {
            "key": s.key,
            "url": getattr(s, "url", ""),
            "name": getattr(s, "name", ""),
            "source_type": getattr(s, "source_type", "scraper"),
        }
        for s in sorted(_SCRAPERS, key=lambda s: s.key)
    ]
