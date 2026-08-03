import hashlib
import logging
import re
from datetime import date, datetime

import requests
from django.conf import settings
from django.utils import timezone
from icalendar import Calendar

from ingestion.importers.source_run import poll_sources_with_run_tracking
from ingestion.models import EventSource, RawEvent

logger = logging.getLogger(__name__)


def fetch_ics_feed(source: EventSource) -> list[RawEvent]:  # noqa: C901  # ICS parsing; complexity is inherent to datetime handling
    """
    Fetch an ICS feed URL, parse events, and save as RawEvent records.
    Returns list of newly created RawEvents.
    """
    assert source.source_type == "ics", "Source must be ICS type"

    response = requests.get(
        source.url,
        timeout=30,
        headers={"User-Agent": settings.INGEST_SCRAPER_USER_AGENT},
    )
    response.raise_for_status()

    cal = Calendar.from_ical(response.text)
    new_events = []

    for component in cal.walk():
        if component.name != "VEVENT":
            continue

        raw_title = str(component.get("SUMMARY", "Untitled Event"))
        raw_description = str(component.get("DESCRIPTION", ""))
        raw_location = str(component.get("LOCATION", ""))

        # Get the UID for dedup
        uid = str(component.get("UID", ""))
        if not uid:
            uid = hashlib.sha256(f"{raw_title}{component.get('DTSTART').dt}".encode()).hexdigest()

        # Parse start/end times
        dtstart = component.get("DTSTART")
        dtend = component.get("DTEND")

        if dtstart is None:
            continue

        raw_start_datetime = dtstart.dt
        raw_end_datetime = dtend.dt if dtend else None

        # Convert date objects to datetime (all-day events)
        if isinstance(raw_start_datetime, date) and not isinstance(raw_start_datetime, datetime):
            raw_start_datetime = datetime.combine(raw_start_datetime, datetime.min.time())
            raw_start_datetime = timezone.make_aware(raw_start_datetime)
        elif timezone.is_naive(raw_start_datetime):
            raw_start_datetime = timezone.make_aware(raw_start_datetime)

        if raw_end_datetime:
            if isinstance(raw_end_datetime, date) and not isinstance(raw_end_datetime, datetime):
                raw_end_datetime = datetime.combine(raw_end_datetime, datetime.min.time())
                raw_end_datetime = timezone.make_aware(raw_end_datetime)
            elif timezone.is_naive(raw_end_datetime):
                raw_end_datetime = timezone.make_aware(raw_end_datetime)

        # Skip past events
        if raw_start_datetime < timezone.now():
            continue

        # Get URL: first try the ICS URL property, then extract from description
        raw_url = str(component.get("URL", ""))
        source_url = raw_url if raw_url.startswith(("http://", "https://")) else ""
        if not source_url:
            # Extract first https URL from description
            url_match = re.search(r'https?://[^\s<>"\']+', raw_description)
            if url_match:
                source_url = url_match.group(0)

        # Create or skip (unique_together handles dedup)
        raw_event, created = RawEvent.objects.get_or_create(
            source=source,
            source_uid=uid,
            defaults={
                "raw_title": raw_title[:500],
                "raw_description": raw_description,
                "raw_location": raw_location[:500],
                "raw_start_datetime": raw_start_datetime,
                "raw_end_datetime": raw_end_datetime,
                "source_url": source_url[:500] if source_url else "",
            },
        )

        if created:
            new_events.append(raw_event)
            logger.info(f"Imported: {raw_title}")
        else:
            logger.debug(f"Skipped (already exists): {raw_title}")

    # Update last_polled
    source.last_polled = timezone.now()
    source.save(update_fields=["last_polled"])

    logger.info(f"Imported {len(new_events)} new events from {source.name}")
    return new_events


def poll_all_ics_sources(shard: tuple[int, int] | None = None):
    """Poll all active ICS sources that are due for a refresh.

    If `shard=(n, m)` is supplied, only sources where `id % m == n` are considered.
    This lets cron spread polling across `m` days so each run only touches ~1/m of
    the sources — load is even across the week and the per-source `poll_interval_hours`
    throttle still guards against accidental double-polls.
    """
    sources = EventSource.objects.filter(source_type="ics", active=True)
    if shard is not None:
        n, m = shard
        sources = sources.extra(where=["id %% %s = %s"], params=[m, n])
        logger.info(f"Sharded poll: only sources with id %% {m} == {n}")

    return poll_sources_with_run_tracking(sources, fetch_ics_feed)
