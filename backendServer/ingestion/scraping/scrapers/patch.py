"""Shared extraction logic for Patch.com city calendars.

Every `patch.com/north-carolina/<slug>/calendar` page is the same Next.js
app, differing only by city slug, and (like Durham's — see
`patchdurham.py`, where this was first reverse engineered) is server-
rendered: a plain `curl` returns the full event list embedded in the page's
own hydration state, a `<script id="__NEXT_DATA__" type="application/json">`
blob, under `props.pageProps.mainContent.allEvents` (a dict keyed by
day-bucket epoch timestamp -> list of event nodes).

Two different node shapes show up there, and which one a city's calendar
uses is not predictable from the URL alone:

- `type: "event"` — a Patch-staff/community-authored post: a full ISO8601
  `displayDate`, a `canonicalUrl` back to patch.com, and `body` HTML.
  Durham's and Raleigh's calendars are built entirely from these.
- `type: "patchAmFreeEvent"` — a listing syndicated from Patch's "Patch AM"
  third-party aggregator: a date-only `dateForGroupBy` plus a separate
  12-hour `displayTime` string (e.g. "6:00 pm"), a `locationTerm.timezone`,
  and an `externalUrl` pointing off patch.com to the organizer's own event
  page. There is no body/description field at all. Pittsboro's and
  Morrisville's calendars are built entirely from these — as of 2026-07-31
  neither city has a single Patch-authored "event" node.

`PatchScraper` reads both shapes (a page could in principle mix them), so a
per-city subclass only needs to set `key`/`url`/`name`. See
`ingestion/tests/fixtures/patchraleigh.html`,
`ingestion/tests/fixtures/patchpittsboro.html`, and
`ingestion/tests/fixtures/patchmorrisville.html` for trimmed, real samples
of each shape.
"""

import hashlib
import json
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from django.utils import timezone
from lxml import html as lxml_html

from ingestion.scraping.scrapers.base import RawEventData, Scraper
from ingestion.scraping.scrapers.patchdurham import _format_location, _strip_html
from ingestion.scraping.scrapers.patchdurham import _to_raw_event as _to_raw_event_native

logger = logging.getLogger("ingestion")

_DEFAULT_TZ_NAME = "America/New_York"


def _extract_events_by_id(html: str) -> dict[str, dict]:
    """Parse every `__NEXT_DATA__` blob on the page, deduped by event id.

    A multi-day event repeats under each day-bucket it spans, so dedupe by
    Patch's own event id rather than trusting bucket membership.
    """
    tree = lxml_html.fromstring(html)
    raw_blocks = tree.xpath('//script[@id="__NEXT_DATA__"]/text()')

    deduped: dict[str, dict] = {}
    for raw in raw_blocks:
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue

        main_content = data.get("props", {}).get("pageProps", {}).get("mainContent") or {}
        all_events = main_content.get("allEvents")
        if not isinstance(all_events, dict):
            continue

        for bucket in all_events.values():
            if not isinstance(bucket, list):
                continue
            for node in bucket:
                if isinstance(node, dict) and node.get("id"):
                    deduped[node["id"]] = node

    return deduped


def _format_am_free_location(node: dict) -> str:
    """`patchAmAddressStr` already reads "Venue, Street, City" -- just add the region.

    Falls back to `_format_location` (which skips the null `streetAddress`
    these nodes carry) if the aggregator didn't supply that string.
    """
    address = node.get("address")
    if not isinstance(address, dict):
        return ""
    addr_str = address.get("patchAmAddressStr")
    if not addr_str:
        return _format_location(address)
    region = address.get("region")
    if region and region not in addr_str:
        return f"{addr_str}, {region}"
    return addr_str


def _to_raw_event_am_free(node: dict) -> RawEventData | None:
    date_str = node.get("dateForGroupBy")
    if not date_str:
        return None

    location_term = node.get("locationTerm") or {}
    tz_name = location_term.get("timezone") or _DEFAULT_TZ_NAME
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo(_DEFAULT_TZ_NAME)

    hour, minute = 0, 0
    display_time = node.get("displayTime")
    if display_time:
        try:
            parsed_time = datetime.strptime(display_time.strip().upper(), "%I:%M %p")
            hour, minute = parsed_time.hour, parsed_time.minute
        except ValueError:
            pass

    try:
        naive = datetime.strptime(date_str, "%Y-%m-%d").replace(hour=hour, minute=minute)
    except ValueError:
        return None
    start = naive.replace(tzinfo=tz)

    title = _strip_html(node.get("title", ""))
    if not title:
        return None

    source_url = node.get("externalUrl") or ""
    source_uid = node.get("id") or hashlib.sha256(f"{title}{date_str}".encode()).hexdigest()

    return RawEventData(
        title=title,
        start=start,
        description="",  # patchAmFreeEvent nodes carry no body/summary field
        location=_format_am_free_location(node),
        end=None,
        source_url=source_url,
        source_uid=source_uid,
    )


def _to_raw_event(node: dict) -> RawEventData | None:
    if node.get("type") == "patchAmFreeEvent":
        return _to_raw_event_am_free(node)
    return _to_raw_event_native(node)


class PatchScraper(Scraper):
    """Base for Patch.com city calendar scrapers -- subclasses set key/url/name."""

    source_type = "http"

    def extract(self, html: str) -> list[RawEventData]:
        nodes = _extract_events_by_id(html)
        now = timezone.now()
        events = [_to_raw_event(node) for node in nodes.values()]
        return [event for event in events if event is not None and event.start >= now]
