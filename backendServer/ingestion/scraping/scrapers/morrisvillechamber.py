"""Morrisville Area Chamber of Commerce event calendar scraper.

https://morrisvillechamber.org/events-and-programs/eventcalendar is a
ChamberMate (chambermate.com) single-page app -- the static HTML is an empty
`<div id="root">` shell, so a plain GET of that page has no event markup. But
the SPA itself loads its calendar from a public, unauthenticated JSON
endpoint (found by watching network requests during a local headless
render):

    https://api.chambermate.com/core/biz/webPresence/getEventsInfo
        ?websiteShorthand=morrisvillechamber
        &websiteDomain=www.morrisvillechamber.org
        &isPortal=false&includeCategories=true
        &includePastEvents=false&rowCount=20

A plain `curl` with only a browser `User-Agent` header (no Referer/Origin,
no auth) returns this same JSON, so we fetch the API endpoint directly
instead of rendering the SPA -- `source_type = "http"`, and `url` on this
class is the API endpoint itself, not the chamber's events page. See
`ingestion/tests/fixtures/morrisvillechamber.html` for a trimmed, real
sample of that JSON response (the `.html` extension is just this repo's
fixture-naming convention; the body is JSON).

`startDateTime`/`endDateTime` in the API have no UTC offset, but despite the
chamber's own event copy claiming "Time zone: America/New_York", the values
are actually already UTC -- e.g. a ribbon-cutting whose description says
"Time of Ceremony: 4:30" (pm) ships `startDateTime` of `20:00:00`, which is
4:30pm EDT converted to UTC, not 8:00pm wall-clock local. Attaching
`America/New_York` directly (as this scraper originally did) double-applies
the offset and publishes every event ~4 hours later than its real start, so
we attach UTC instead. Titles the chamber has manually marked `*CANCELLED*`
are dropped rather than published as live events.
"""

import json
import logging
from datetime import UTC, datetime
from html import unescape

from django.utils import timezone

from ingestion.scraping.scrapers.base import RawEventData, Scraper

logger = logging.getLogger("ingestion")


def _parse_local(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).replace(tzinfo=UTC)
    except ValueError:
        return None


def _format_address(address: dict | None) -> str:
    if not isinstance(address, dict):
        return ""
    parts = [
        address.get("name"),
        address.get("street1"),
        address.get("street2"),
        address.get("city"),
        address.get("stateCode"),
        address.get("zip"),
    ]
    return ", ".join(str(p).strip() for p in parts if p)


class MorrisvillechamberScraper(Scraper):
    key = "morrisvillechamber"
    url = (
        "https://api.chambermate.com/core/biz/webPresence/getEventsInfo"
        "?websiteShorthand=morrisvillechamber"
        "&websiteDomain=www.morrisvillechamber.org"
        "&isPortal=false&includeCategories=true"
        "&includePastEvents=false&rowCount=20"
    )
    name = "Morrisville Area Chamber of Commerce"
    source_type = "http"

    def extract(self, html: str) -> list[RawEventData]:
        try:
            payload = json.loads(html)
        except (json.JSONDecodeError, TypeError):
            return []

        raw_events = (payload.get("data") or {}).get("events") or []

        now = timezone.now()
        events = []
        for node in raw_events:
            if not isinstance(node, dict):
                continue

            title = unescape((node.get("eventName") or "").strip())
            if not title or "cancelled" in title.lower():
                continue

            start = _parse_local(node.get("startDateTime"))
            if start is None or start < now:
                continue
            end = None if node.get("noEndTime") else _parse_local(node.get("endDateTime"))

            description = unescape((node.get("eventDescription") or "").strip())

            address = node.get("address")
            if address:
                location = _format_address(address)
            elif node.get("contactTypeCode") == "Online":
                location = "Online"
            else:
                location = ""

            source_url = node.get("eventDetailUrl") or ""
            source_uid = node.get("activityKey") or source_url

            events.append(
                RawEventData(
                    title=title,
                    start=start,
                    description=description,
                    location=location,
                    end=end,
                    source_url=source_url,
                    source_uid=source_uid,
                )
            )

        return events
