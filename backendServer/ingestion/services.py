import logging

from django.db import transaction

from accounts.models import BetterAuthUser
from events.models import Category, Event, Town
from events.tagging import apply_tags
from ingestion.deduplicator import (
    BROADCAST_LOCATION_SIMILARITY_THRESHOLD,
    BROADCAST_TIME_WINDOW_HOURS,
    BROADCAST_TITLE_SIMILARITY_THRESHOLD,
    find_duplicate,
)
from ingestion.models import RawEvent, StagedEvent
from ingestion.safety_scorer import SAFETY_SCORE_THRESHOLD, score_event
from ingestion.standardizer import standardize_event

logger = logging.getLogger(__name__)


def resolve_town(raw_town: str, fallback: Town | None) -> Town | None:
    """Resolve Gemini's per-event town guess to a `Town` row, falling back only
    when the guess is empty or doesn't match a known town.

    `fallback` (devtools' "force town" selector, or — in the normal cron path
    — the staged event's own `EventSource.default_town`, per 45.4) exists for
    the case Gemini can't determine a town at all — the standardizer prompt
    tells it to return `""` when unclear. It is a fallback, not an override: a
    source that mostly covers one city but occasionally surfaces a
    neighboring one (e.g. a Raleigh events site listing a Cary show) should
    keep Gemini's correct per-event guess rather than have every event
    flattened to the operator's (or source's) blanket selection.
    """
    town_slug = raw_town.lower().replace(" ", "-") if raw_town else None
    town = Town.objects.filter(slug=town_slug).first() if town_slug else None
    return town or fallback


def publish_all_approved(source=None, force_town=None):  # noqa: C901  # inherent pipeline complexity
    """
    Atomically moves all approved StagedEvents into the Events table, then
    flips them to a terminal `status="published"` — they are NOT deleted.

    These rows are the deduplicator's matching corpus (see
    `deduplicator.CANDIDATE_STATUSES`): a re-scraped or re-submitted copy of an
    already-published event still needs something to match against, and
    `StagedEvent.duplicate_of` is `on_delete=SET_NULL`, so deleting a published
    anchor would also orphan any `duplicate` rows pointing at it. Published
    rows are eventually reaped by `cleanup_old_events` once their
    `start_datetime` is in the past.

    Returns a dict with counts:
        published          — newly created Event records
        already_published  — approved staged events that already had an Event record
        removed            — staged rows swept out of the approved queue (now
                              `status="published"`; no longer "deleted")
    """
    # NOTE: do not eager-join `submitted_by` — it maps to the cross-schema
    # `neon_auth."user"` mirror, which is absent on isolated dev DB branches and
    # makes the whole query fail there. Pipeline events have submitted_by=None
    # (no lazy query fires), so dropping the join is result-identical and also
    # avoids a pointless LEFT JOIN in prod.
    approved_qs = StagedEvent.objects.filter(status="approved").select_related("raw_event__source")
    if source:
        approved_qs = approved_qs.filter(raw_event__source=source)
    approved_staged = list(approved_qs)

    if not approved_staged:
        return {"published": 0, "already_published": 0, "removed": 0}

    with transaction.atomic():
        published_count = 0
        already_published_count = 0

        for staged in approved_staged:
            if staged.published_event_id is None:
                # 45.4: `force_town` is a *runtime* argument the nightly cron
                # path always passes as `None` (only devtools' playground and
                # "force town" pipeline stage set it). Per-source
                # `default_town` is resolved here, per staged event, rather
                # than threaded down from the caller: a single batch can span
                # multiple sources, so one run-wide fallback would be wrong,
                # and an explicit `force_town` (an operator's deliberate
                # override for this run) still wins when both are set.
                fallback = force_town
                if fallback is None and staged.raw_event_id and staged.raw_event:
                    source = staged.raw_event.source
                    if source is not None:
                        fallback = source.default_town
                town_obj = resolve_town(staged.town, fallback)
                if town_obj is None:
                    # Terminal-ish status, not a delete: `skipped_no_town` rows
                    # stay out of the `approved` queryset above, so this branch
                    # (and its log line) only ever fires once per row instead of
                    # re-logging on every subsequent run. They remain dedupe
                    # candidates (CANDIDATE_STATUSES in deduplicator.py) and are
                    # reopened deliberately via `manage.py reopen_skipped_towns`
                    # once coverage is added — see that command's docstring.
                    logger.warning(
                        "Skipping staged event '%s' — no Town matches gemini town=%r",
                        staged.title,
                        staged.town,
                    )
                    staged.status = "skipped_no_town"
                    staged.save(update_fields=["status"])
                    continue
                if staged.raw_event_id and staged.raw_event and staged.raw_event.source:
                    source_name = staged.raw_event.source.name
                else:
                    source_name = "Community Submission"
                is_verified = (
                    staged.submitted_by is not None and staged.submitted_by.user_type == "BUSINESS"
                )
                event = Event.objects.create(
                    title=staged.title,
                    town=town_obj,
                    date=staged.start_datetime,
                    venue=staged.location_name,
                    description=staged.description,
                    price=staged.price,
                    link=staged.link,
                    created_by=staged.submitted_by,
                    source_name=source_name,
                    is_verified=is_verified,
                )
                apply_tags(event, staged.tags)
                if staged.category:
                    cat = Category.objects.filter(slug=staged.category).first()
                    if cat:
                        event.categories.add(cat)
                staged.published_event = event
                staged.save(update_fields=["published_event"])
                published_count += 1
            else:
                already_published_count += 1

        removed_qs = StagedEvent.objects.filter(status="approved", published_event__isnull=False)
        if source:
            removed_qs = removed_qs.filter(raw_event__source=source)
        removed_count = removed_qs.update(status="published")

    return {
        "published": published_count,
        "already_published": already_published_count,
        "removed": removed_count,
    }


def auto_publish_safe_events(source=None, force_town=None):
    """
    Auto-approve and publish scored events below the safety threshold.
    Events above the threshold remain pending for manual review.

    Returns a dict with counts:
        auto_approved  — events moved to approved and published
        held_for_review — events left pending (score above threshold or unscored)
    """
    pending = StagedEvent.objects.filter(status="pending", safety_score__isnull=False)
    if source:
        pending = pending.filter(raw_event__source=source)

    to_approve = [s for s in pending if s.safety_score <= SAFETY_SCORE_THRESHOLD]
    held_count = pending.count() - len(to_approve)

    if not to_approve:
        return {"auto_approved": 0, "held_for_review": held_count}

    with transaction.atomic():
        for staged in to_approve:
            staged.status = "approved"
            staged.save(update_fields=["status"])

    result = publish_all_approved(source=source, force_town=force_town)
    logger.info(
        f"Auto-published {result['published']} events "
        f"(threshold={SAFETY_SCORE_THRESHOLD}); {held_count} held for review"
    )

    return {"auto_approved": result["published"], "held_for_review": held_count}


def ingest_direct_submission(raw_event_id, user_id):
    """
    Turn a persisted RawEvent into a live Event via Gemini standardize + dedupe +
    safety gate, attributed to the caller's JWT user when present.  Idempotent: a
    second call on the same raw_event replaces the staged row and updates the
    existing Event in place.  user_id may be None for anonymous submissions.

    40.4: if a prior call already published this RawEvent and a resubmission
    (edited content) then hits the duplicate/safety/no-town gate, the new
    content does not go live — but the *previously* published Event must not
    be orphaned either (Event has no soft-delete/unpublish, so its existence
    is its publication). Every terminal branch below therefore keeps
    `published_event` pointed at that prior Event, whether it lands there
    (happy path) or not (early returns).

    Returns the Event if published, None if held (pending / duplicate / no-town).
    """
    raw_event = RawEvent.objects.get(id=raw_event_id)
    user = BetterAuthUser.objects.get(id=user_id) if user_id is not None else None

    # Idempotency: tear down any prior staged row so re-standardization is fresh.
    # Capture the published Event first so we can update it in place on re-edits.
    prior_event = None
    try:
        existing_staged = raw_event.staged
        prior_event = existing_staged.published_event
        existing_staged.delete()
    except StagedEvent.DoesNotExist:
        pass

    staged = standardize_event(raw_event)
    staged.submitted_by = user
    staged.save(update_fields=["submitted_by"])

    score, notes = score_event(staged)
    staged.safety_score = score
    staged.safety_notes = notes
    staged.save(update_fields=["safety_score", "safety_notes"])

    dup = find_duplicate(
        staged,
        title_threshold=BROADCAST_TITLE_SIMILARITY_THRESHOLD,
        location_threshold=BROADCAST_LOCATION_SIMILARITY_THRESHOLD,
        time_window_hours=BROADCAST_TIME_WINDOW_HOURS,
    )
    if dup is not None:
        staged.status = "duplicate"
        staged.duplicate_of = dup
        # 40.4: an edited resubmission that now matches an existing event must
        # not orphan whatever this RawEvent previously published — the live
        # Event has no soft-delete/unpublish concept, so it stays up and this
        # row keeps pointing at it (moderatable, not a dangling live Event).
        staged.published_event = prior_event
        staged.save(update_fields=["status", "duplicate_of", "published_event"])
        return None

    if score > SAFETY_SCORE_THRESHOLD:
        # 40.4: this used to save `status` without ever assigning it, so the
        # row silently kept whatever `standardize_event` left it at (the model
        # default, "pending") instead of an intentional value. "pending" is
        # actually correct here — it's the same value the automated pipeline
        # uses for held-for-review rows (see `auto_publish_safe_events`), and
        # `monitoring.py`'s funnel already buckets status="pending" with a
        # non-null `safety_score` as `held_for_review` — so make the
        # assignment explicit rather than inventing a new status.
        staged.status = "pending"
        staged.published_event = prior_event
        staged.save(update_fields=["status", "published_event"])
        return None

    with transaction.atomic():
        town_slug = staged.town.lower().replace(" ", "-") if staged.town else None
        town_obj = Town.objects.filter(slug=town_slug).first() if town_slug else None
        if town_obj is None:
            logger.warning(
                "Skipping direct submission '%s' — no Town matches slug '%s' (gemini town=%r)",
                staged.title,
                town_slug,
                staged.town,
            )
            staged.status = "skipped_no_town"
            staged.published_event = prior_event
            staged.save(update_fields=["status", "published_event"])
            return None

        is_verified = user is not None and user.user_type == "BUSINESS"
        organizer = raw_event.raw_organizer.strip()
        source_name = (
            f"Direct submission by {organizer}" if organizer else "Direct submission by host"
        )

        category_obj = (
            Category.objects.filter(slug=staged.category).first() if staged.category else None
        )

        if prior_event is not None:
            event = prior_event
            event.title = staged.title
            event.town = town_obj
            event.date = staged.start_datetime
            event.venue = staged.location_name
            event.description = staged.description
            event.price = staged.price
            event.link = staged.link
            event.created_by = user
            event.source_name = source_name
            event.is_verified = is_verified
            event.save()
            apply_tags(event, staged.tags)
            event.categories.clear()
            if category_obj:
                event.categories.add(category_obj)
            staged.published_event = event
        else:
            event = Event.objects.create(
                title=staged.title,
                town=town_obj,
                date=staged.start_datetime,
                venue=staged.location_name,
                description=staged.description,
                price=staged.price,
                link=staged.link,
                created_by=user,
                source_name=source_name,
                is_verified=is_verified,
            )
            apply_tags(event, staged.tags)
            if category_obj:
                event.categories.add(category_obj)
            staged.published_event = event

        staged.status = "approved"
        staged.save(update_fields=["published_event", "status"])

    return event
