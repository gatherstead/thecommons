import logging

from django.db import transaction

from events.models import BetterAuthUser, Event, Tag, Town, Category
from ingestion.deduplicator import find_duplicate
from ingestion.models import RawEvent, StagedEvent
from ingestion.safety_scorer import SAFETY_SCORE_THRESHOLD, score_event
from ingestion.standardizer import standardize_event

logger = logging.getLogger(__name__)


def publish_all_approved(source=None, force_town=None):
    """
    Atomically moves all approved StagedEvents into the Events table,
    then deletes them from the staged table.

    Returns a dict with counts:
        published          — newly created Event records
        already_published  — approved staged events that already had an Event record
        removed            — total StagedEvents deleted
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
                if force_town is not None:
                    town_obj = force_town
                else:
                    town_slug = staged.town.lower().replace(" ", "-") if staged.town else None
                    town_obj = Town.objects.filter(slug=town_slug).first() if town_slug else None
                    if town_obj is None:
                        logger.warning(
                            "Dropping staged event '%s' — no Town matches slug '%s' (gemini town=%r)",
                            staged.title,
                            town_slug,
                            staged.town,
                        )
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
                for tag_name in staged.tags:
                    tag_obj, _ = Tag.objects.get_or_create(name=tag_name.strip().lower())
                    event.tags.add(tag_obj)
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
        removed_count = removed_qs.delete()[0]

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

    dup = find_duplicate(staged)
    if dup is not None:
        staged.status = "duplicate"
        staged.duplicate_of = dup
        staged.save(update_fields=["status", "duplicate_of"])
        return None

    if score > SAFETY_SCORE_THRESHOLD:
        staged.save(update_fields=["status"])
        return None

    with transaction.atomic():
        town_slug = staged.town.lower().replace(" ", "-") if staged.town else None
        town_obj = Town.objects.filter(slug=town_slug).first() if town_slug else None
        if town_obj is None:
            logger.warning(
                "Holding direct submission '%s' — no Town matches slug '%s' (gemini town=%r)",
                staged.title,
                town_slug,
                staged.town,
            )
            return None

        is_verified = user is not None and user.user_type == "BUSINESS"
        source_name = "Direct submission by host"

        tags = []
        for t in staged.tags:
            tag_obj, _ = Tag.objects.get_or_create(name=t.strip().lower())
            tags.append(tag_obj)
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
            event.tags.set(tags)
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
            event.tags.set(tags)
            if category_obj:
                event.categories.add(category_obj)
            staged.published_event = event

        staged.status = "approved"
        staged.save(update_fields=["published_event", "status"])

    return event
