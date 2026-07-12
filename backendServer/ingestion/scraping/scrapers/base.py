"""Per-site scraper contract: pure `html -> list[RawEventData]`.

Decoupled from the ORM row (like `broadcast/schema.py`'s CanonicalEvent) so
`extract()` can be unit-tested against a saved HTML fixture with no DB, no
browser, and no network.
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class RawEventData:
    title: str
    start: datetime  # tz-aware
    description: str = ""
    location: str = ""
    end: datetime | None = None
    source_url: str = ""
    source_uid: str = ""  # stable unique id per event


class Scraper:
    key: str

    def extract(self, html: str) -> list[RawEventData]:
        raise NotImplementedError
