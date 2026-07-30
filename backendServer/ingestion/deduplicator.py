import logging
import re
from datetime import timedelta

from thefuzz import fuzz

from ingestion.models import StagedEvent

logger = logging.getLogger(__name__)

TITLE_SIMILARITY_THRESHOLD = 80
LOCATION_SIMILARITY_THRESHOLD = 75
TIME_WINDOW_HOURS = 3

# Broadcast-sourced events are submitted to external calendars that are later
# scraped back in, so the same event can re-enter with reformatted title/location.
# Use a looser match (more aggressive dedup) and a wider time window for this path.
# The window is deliberately wide enough to cover a host re-submitting with a
# corrected start time, which is the case a tight ±hours window always misses.
BROADCAST_TITLE_SIMILARITY_THRESHOLD = 60
BROADCAST_LOCATION_SIMILARITY_THRESHOLD = 55
BROADCAST_TIME_WINDOW_HOURS = 12

# Statuses worth comparing against. `duplicate` is included so dedup chains
# survive: once A is published-and-swept, B (marked duplicate-of-A) is the only
# row still carrying that title, and a third submission must still match it.
# `published` is included because `publish_all_approved` no longer deletes
# published rows — it flips them to `status="published"` specifically so they
# remain permanent dedupe anchors (see `services.publish_all_approved`).
# `rejected` is deliberately excluded: matching against it would silently
# duplicate-mark a host who fixed a flagged problem and resubmitted.
# `skipped_no_town` is included so a re-scrape of an already-skipped,
# out-of-coverage event matches the existing row instead of creating a fresh
# `skipped_no_town` row every poll — one terminal row per event, not one per
# scrape (see services.publish_all_approved).
CANDIDATE_STATUSES = ["pending", "approved", "duplicate", "published", "skipped_no_town"]

_LEADING_ARTICLE_RE = re.compile(r"^(the|a|an)\s+")


def _normalize(text: str | None) -> str:
    """Lowercase, drop a leading article and punctuation, collapse whitespace.

    Deliberately conservative. An earlier version also stripped presenter
    clauses ("... Presented by Acme"), but the same keywords appear as a
    *prefix* too — "The Wheelhouse Presents: Onyx Club Boys" — where stripping
    deletes the event name and leaves only the promoter, which collapses
    unrelated events onto each other. `token_set_ratio` below already scores
    "X, Presented by Y" against "X" at 100 because the shared tokens cover one
    side entirely, so the rewrite buys nothing and risks false positives.
    """
    text = (text or "").strip().lower()
    text = _LEADING_ARTICLE_RE.sub("", text)
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _similarity(left: str | None, right: str | None) -> int | None:
    """Fuzzy score for two strings, or None when either side is blank.

    None means "not comparable" — distinct from a score of 0. `fuzz.ratio`
    scores a blank against a real string as 0, which would veto an otherwise
    solid title match just because one side had no venue.

    `token_set_ratio` catches word-order and subset differences ("Jazz Night at
    the Cradle" vs "Cat's Cradle Jazz Night"); plain `ratio` is kept alongside it
    because token_set is weak on short strings that differ by a character or two.
    """
    left, right = _normalize(left), _normalize(right)
    if not left or not right:
        return None
    return max(fuzz.ratio(left, right), fuzz.token_set_ratio(left, right))


def _field_score(staged: StagedEvent, candidate: StagedEvent, field: str, raw_field: str):
    """Best score for a field, comparing both the LLM output and the raw source text.

    Standardized titles/locations are Gemini output and are *not* stable across
    runs — the same raw title has come back as both "The Wheelhouse Presents:
    Onyx Club Boys" and "Onyx Club Boys Live at Fair Game Beverage Company"
    (fuzz.ratio 32, a clean miss). The underlying RawEvent text is byte-identical
    in that case, so scoring both and taking the best makes dedup immune to the
    LLM's rewording.
    """
    scores = [_similarity(getattr(staged, field), getattr(candidate, field))]

    staged_raw, candidate_raw = staged.raw_event, candidate.raw_event
    if staged_raw is not None and candidate_raw is not None:
        scores.append(
            _similarity(getattr(staged_raw, raw_field), getattr(candidate_raw, raw_field))
        )

    comparable = [s for s in scores if s is not None]
    return max(comparable) if comparable else None


def find_duplicate(
    staged_event: StagedEvent,
    title_threshold: int = TITLE_SIMILARITY_THRESHOLD,
    location_threshold: int = LOCATION_SIMILARITY_THRESHOLD,
    time_window_hours: int = TIME_WINDOW_HOURS,
) -> StagedEvent | None:
    """
    Check if a staged event is a duplicate of another staged or published event.
    Returns the original event if a duplicate is found, None otherwise.
    """
    time_min = staged_event.start_datetime - timedelta(hours=time_window_hours)
    time_max = staged_event.start_datetime + timedelta(hours=time_window_hours)

    # Only ever match against *older* rows. Two submissions racing through
    # ingest_direct_submission on the concurrency-2 default worker could
    # otherwise each see the other and both mark themselves duplicate, dropping
    # the event entirely. Anchoring on pk makes the pair resolve one way only.
    candidates = (
        StagedEvent.objects.filter(
            start_datetime__range=(time_min, time_max),
            status__in=CANDIDATE_STATUSES,
            pk__lt=staged_event.pk,
        )
        .select_related("raw_event")
        .order_by("pk")
    )

    for candidate in candidates:
        title_score = _field_score(staged_event, candidate, "title", "raw_title")
        if title_score is None or title_score < title_threshold:
            continue

        # An uncomparable location (either side blank) abstains rather than
        # vetoing — the title match already carried the decision.
        location_score = _field_score(staged_event, candidate, "location_name", "raw_location")
        if location_score is not None and location_score < location_threshold:
            continue

        logger.info(
            f"Duplicate found: '{staged_event.title}' matches '{candidate.title}' "
            f"(title={title_score}, location={location_score})"
        )
        return candidate

    return None


def dedup_all_pending(source=None):
    """Check all pending staged events for duplicates."""
    pending = StagedEvent.objects.filter(status="pending")
    if source:
        pending = pending.filter(raw_event__source=source)
    pending_count = pending.count()
    dupes_found = 0

    for staged in pending.select_related("raw_event").order_by("pk"):
        original = find_duplicate(staged)
        if original:
            staged.status = "duplicate"
            staged.duplicate_of = original
            staged.save(update_fields=["status", "duplicate_of"])
            dupes_found += 1

    logger.info(f"Found {dupes_found} duplicates out of {pending_count} pending events")
    return dupes_found
