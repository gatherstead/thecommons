import logging
from datetime import timedelta

from thefuzz import fuzz

from ingestion.models import StagedEvent

logger = logging.getLogger(__name__)

TITLE_SIMILARITY_THRESHOLD = 80
LOCATION_SIMILARITY_THRESHOLD = 75
TIME_WINDOW_HOURS = 3


def find_duplicate(staged_event: StagedEvent) -> StagedEvent | None:
    """
    Check if a staged event is a duplicate of another staged or published event.
    Returns the original event if a duplicate is found, None otherwise.
    """
    time_min = staged_event.start_datetime - timedelta(hours=TIME_WINDOW_HOURS)
    time_max = staged_event.start_datetime + timedelta(hours=TIME_WINDOW_HOURS)

    candidates = StagedEvent.objects.filter(
        start_datetime__range=(time_min, time_max),
        status__in=['pending', 'approved'],
    ).exclude(pk=staged_event.pk)

    for candidate in candidates:
        title_score = fuzz.ratio(
            staged_event.title.lower(),
            candidate.title.lower()
        )
        location_score = fuzz.ratio(
            staged_event.location_name.lower(),
            candidate.location_name.lower()
        )

        if (title_score >= TITLE_SIMILARITY_THRESHOLD and
                location_score >= LOCATION_SIMILARITY_THRESHOLD):
            logger.info(
                f"Duplicate found: '{staged_event.title}' matches '{candidate.title}' "
                f"(title={title_score}, location={location_score})"
            )
            return candidate

    return None


def dedup_all_pending():
    """Check all pending staged events for duplicates."""
    pending = StagedEvent.objects.filter(status='pending')
    dupes_found = 0

    for staged in pending:
        original = find_duplicate(staged)
        if original:
            staged.status = 'duplicate'
            staged.duplicate_of = original
            staged.save(update_fields=['status', 'duplicate_of'])
            dupes_found += 1

    logger.info(f"Found {dupes_found} duplicates out of {pending.count()} pending events")
    return dupes_found
