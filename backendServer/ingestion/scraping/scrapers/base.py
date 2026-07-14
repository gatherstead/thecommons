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
    # The single site this scraper targets. Each scraper is custom-built for one
    # page's markup, so the URL travels with the module and can auto-fill the UI.
    url: str = ""
    # Human-readable English name of the source site, used to attribute published
    # events (Event.source_name) — e.g. "Visit Pittsboro", not "visitpittsboro.com".
    name: str = ""
    # CSS selector `render_page` should wait for before snapshotting the DOM.
    # Only needed when the event markup itself is injected by a client-side
    # XHR that fires after "domcontentloaded" (e.g. a widget that calls a REST
    # API on mount) — plain server-rendered pages can leave this None.
    wait_selector: str | None = None

    def extract(self, html: str) -> list[RawEventData]:
        raise NotImplementedError
