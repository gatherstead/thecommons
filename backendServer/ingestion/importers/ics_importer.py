import hashlib
import logging
import re
from datetime import datetime, date

import requests
from django.utils import timezone
from icalendar import Calendar

from ingestion.models import EventSource, RawEvent

logger = logging.getLogger(__name__)


def fetch_ics_feed(source: EventSource) -> list[RawEvent]:
    """
    Fetch an ICS feed URL, parse events, and save as RawEvent records.
    Returns list of newly created RawEvents.
    """
    assert source.source_type == 'ics', "Source must be ICS type"

    response = requests.get(source.url, timeout=30)
    response.raise_for_status()

    cal = Calendar.from_ical(response.text)
    new_events = []

    for component in cal.walk():
        if component.name != "VEVENT":
            continue

        raw_title = str(component.get('SUMMARY', 'Untitled Event'))
        raw_description = str(component.get('DESCRIPTION', ''))
        raw_location = str(component.get('LOCATION', ''))

        # Get the UID for dedup
        uid = str(component.get('UID', ''))
        if not uid:
            uid = hashlib.sha256(
                f"{raw_title}{component.get('DTSTART').dt}".encode()
            ).hexdigest()

        # Parse start/end times
        dtstart = component.get('DTSTART')
        dtend = component.get('DTEND')

        if dtstart is None:
            continue

        raw_start = dtstart.dt
        raw_end = dtend.dt if dtend else None

        # Convert date objects to datetime (all-day events)
        if isinstance(raw_start, date) and not isinstance(raw_start, datetime):
            raw_start = datetime.combine(raw_start, datetime.min.time())
            raw_start = timezone.make_aware(raw_start)
        elif timezone.is_naive(raw_start):
            raw_start = timezone.make_aware(raw_start)

        if raw_end:
            if isinstance(raw_end, date) and not isinstance(raw_end, datetime):
                raw_end = datetime.combine(raw_end, datetime.min.time())
                raw_end = timezone.make_aware(raw_end)
            elif timezone.is_naive(raw_end):
                raw_end = timezone.make_aware(raw_end)

        # Skip past events
        if raw_start < timezone.now():
            continue

        # Get URL: first try the ICS URL property, then extract from description
        raw_url = str(component.get('URL', ''))
        source_url = raw_url if raw_url.startswith(('http://', 'https://')) else ''
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
                'raw_title': raw_title[:500],
                'raw_description': raw_description,
                'raw_location': raw_location[:500],
                'raw_start': raw_start,
                'raw_end': raw_end,
                'source_url': source_url[:500] if source_url else '',
            }
        )

        if created:
            new_events.append(raw_event)
            logger.info(f"Imported: {raw_title}")
        else:
            logger.debug(f"Skipped (already exists): {raw_title}")

    # Update last_polled
    source.last_polled = timezone.now()
    source.save(update_fields=['last_polled'])

    logger.info(f"Imported {len(new_events)} new events from {source.name}")
    return new_events


def poll_all_ics_sources():
    """Poll all active ICS sources that are due for a refresh."""
    sources = EventSource.objects.filter(source_type='ics', active=True)

    total_new = 0
    for source in sources:
        if source.last_polled:
            hours_since = (timezone.now() - source.last_polled).total_seconds() / 3600
            if hours_since < source.poll_interval_hours:
                logger.debug(f"Skipping {source.name} (polled {hours_since:.1f}h ago)")
                continue

        try:
            new_events = fetch_ics_feed(source)
            total_new += len(new_events)
        except Exception as e:
            logger.error(f"Error polling {source.name}: {e}")

    return total_new
