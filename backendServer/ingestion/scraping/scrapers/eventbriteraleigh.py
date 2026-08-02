"""Eventbrite NC city discovery pages (Raleigh, Pittsboro, Morrisville).

https://www.eventbrite.com/d/nc--<city>/events/ is a Next.js app, but
server-rendered: `curl` with no JS already returns the full event payload
via a `window.__SERVER_DATA__ = {...};` JSON blob, so this is an `http`
source rather than a `scraper` one.

The page also embeds a schema.org JSON-LD `ItemList` (see
`visitpittsboro.py` for why JSON-LD is normally preferred), but Eventbrite's
own JSON-LD here only carries date-level `startDate`/`endDate` (no
time-of-day). `__SERVER_DATA__.buckets[].events[]` — Eventbrite's internal
event objects — carries the same events with `start_date` + `start_time` +
an explicit `timezone`, plus a `primary_venue` street address and a stable
numeric `id`. We read that instead. The same `id` recurs across multiple
buckets (an event can be both "Popular" and "Music"), so events are deduped
by id before filtering.

`is_online_event` events (visible on every city's page as an "Online
Events" bucket) have no `primary_venue` at all and aren't location-bound to
the city being polled, so they're dropped.

Quality note (important for deciding whether to enable these sources):
Eventbrite discovery pages are a *metro* feed assembled from topic buckets
(nightlife/popular/music/food/etc.), not a strict "events in this town"
listing, and small towns without much inventory of their own get
backfilled with nearby-city and online events to fill the buckets out.
Inspecting the three pages this module covers (2026-07-31, unique events
after dedup, online events excluded):
  - Raleigh:     48 of 57 events actually in Raleigh (~85% signal)
  - Pittsboro:   12 of 28 events actually in Pittsboro (~45% signal;
                 remainder spills in from Raleigh, Durham, Charlotte,
                 Greensboro, Winston-Salem, and abroad)
  - Morrisville: 0 of 16 events actually in Morrisville (0% signal; every
                 non-online result was Raleigh/Durham/Cary spillover)
See `ingestion/tests/fixtures/eventbritemorrisville.html` — a trimmed real
capture of that page — for direct evidence: none of its "Popular" bucket
events are Morrisville-located. `eventbritemorrisville` extracts cleanly
but is not a Morrisville events source in practice; `eventbritepittsboro`
is borderline; only `eventbriteraleigh` is majority-local. This module
doesn't filter by venue city itself (same reasoning as
`patchdurham.py`: downstream standardization infers town from the location
string), so the enable/disable call belongs to whoever reviews these
sources, not the scraper.
"""

import json
import logging
import re
from datetime import datetime
from html import unescape
from zoneinfo import ZoneInfo

from django.utils import timezone

from ingestion.scraping.scrapers.base import RawEventData, Scraper

logger = logging.getLogger("ingestion")

_TAG_RE = re.compile(r"<[^>]+>")
_SERVER_DATA_MARKER = "window.__SERVER_DATA__ = "
_DEFAULT_TZ = "America/New_York"


def _strip_html(text: str) -> str:
    """Unescape HTML entities then strip tags, leaving plain text."""
    return _TAG_RE.sub("", unescape(text or "")).strip()


def _zone(tz_name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(tz_name or _DEFAULT_TZ)
    except (KeyError, ValueError):
        return ZoneInfo(_DEFAULT_TZ)


def _combine(date_str: str | None, time_str: str | None, tzinfo: ZoneInfo) -> datetime | None:
    if not date_str or not time_str:
        return None
    try:
        naive = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
    except ValueError:
        return None
    return naive.replace(tzinfo=tzinfo)


def _format_location(venue: dict | None) -> str:
    """Venue name plus street address, so the standardizer can infer the town."""
    if not isinstance(venue, dict):
        return ""
    address = venue.get("address") or {}
    parts = [
        venue.get("name"),
        address.get("address_1"),
        address.get("city"),
        address.get("region"),
    ]
    return ", ".join(p.strip() for p in parts if p and str(p).strip())


def _dedupe_event_nodes(buckets: list) -> dict[str, dict]:
    """Flatten `buckets[].events[]` into `{event_id: node}`.

    Discovery pages repeat the same event across several buckets (e.g. "This
    weekend" and "Music"), so keying by id collapses those to one row.
    """
    deduped: dict[str, dict] = {}
    for bucket in buckets:
        if not isinstance(bucket, dict):
            continue
        for node in bucket.get("events") or []:
            if isinstance(node, dict) and node.get("id"):
                deduped[str(node["id"])] = node
    return deduped


def extract_eventbrite_events(html: str) -> list[RawEventData]:
    """Shared extraction for every `eventbrite*` city-discovery scraper.

    Reads `window.__SERVER_DATA__.buckets[].events[]` out of the raw HTML.
    Used as-is by `eventbritepittsboro.py` and `eventbritemorrisville.py` —
    the three pages are one platform differing only by city slug.
    """
    idx = html.find(_SERVER_DATA_MARKER)
    if idx == -1:
        return []

    decoder = json.JSONDecoder()
    try:
        data, _ = decoder.raw_decode(html, idx + len(_SERVER_DATA_MARKER))
    except (json.JSONDecodeError, ValueError):
        return []

    buckets = data.get("buckets")
    if not isinstance(buckets, list):
        return []

    now = timezone.now()
    events = []
    for node in _dedupe_event_nodes(buckets).values():
        if node.get("is_online_event") or node.get("is_cancelled"):
            continue

        title = _strip_html(node.get("name", ""))
        if not title:
            continue

        tzinfo = _zone(node.get("timezone"))
        start = _combine(node.get("start_date"), node.get("start_time"), tzinfo)
        if start is None or start < now:
            continue

        end = _combine(node.get("end_date"), node.get("end_time"), tzinfo)
        source_url = node.get("url") or ""
        source_uid = str(node.get("id"))

        events.append(
            RawEventData(
                title=title,
                start=start,
                description=_strip_html(node.get("summary", "")),
                location=_format_location(node.get("primary_venue")),
                end=end,
                source_url=source_url,
                source_uid=source_uid,
            )
        )

    return events


class EventbriteraleighScraper(Scraper):
    key = "eventbriteraleigh"
    url = "https://www.eventbrite.com/d/nc--raleigh/events/"
    name = "Eventbrite Raleigh"
    source_type = "http"

    def extract(self, html: str) -> list[RawEventData]:
        return extract_eventbrite_events(html)
