import logging

from django.db import transaction

from events.models import Event, Tag, Town, Category
from ingestion.models import StagedEvent
from ingestion.safety_scorer import SAFETY_SCORE_THRESHOLD

logger = logging.getLogger(__name__)


def publish_all_approved():
    """
    Atomically moves all approved StagedEvents into the Events table,
    then deletes them from the staged table.

    Returns a dict with counts:
        published          — newly created Event records
        already_published  — approved staged events that already had an Event record
        removed            — total StagedEvents deleted
    """
    approved_staged = list(
        StagedEvent.objects.filter(status='approved')
        .select_related('raw_event__source', 'submitted_by')
    )

    if not approved_staged:
        return {'published': 0, 'already_published': 0, 'removed': 0}

    with transaction.atomic():
        published_count = 0
        already_published_count = 0

        for staged in approved_staged:
            if staged.published_event_id is None:
                town_slug = staged.town.lower().replace(' ', '-') if staged.town else None
                town_obj = Town.objects.filter(slug=town_slug).first() if town_slug else None
                if town_obj is None:
                    continue
                if staged.raw_event_id and staged.raw_event and staged.raw_event.source:
                    source_name = staged.raw_event.source.name
                else:
                    source_name = 'Community Submission'
                is_verified = (
                    staged.submitted_by is not None
                    and staged.submitted_by.user_type == 'BUSINESS'
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
                staged.save(update_fields=['published_event'])
                published_count += 1
            else:
                already_published_count += 1

        removed_count = StagedEvent.objects.filter(
            status='approved', published_event__isnull=False
        ).delete()[0]

    return {
        'published': published_count,
        'already_published': already_published_count,
        'removed': removed_count,
    }


def auto_publish_safe_events():
    """
    Auto-approve and publish scored events below the safety threshold.
    Events above the threshold remain pending for manual review.

    Returns a dict with counts:
        auto_approved  — events moved to approved and published
        held_for_review — events left pending (score above threshold or unscored)
    """
    pending = StagedEvent.objects.filter(status='pending', safety_score__isnull=False)

    to_approve = [s for s in pending if s.safety_score <= SAFETY_SCORE_THRESHOLD]
    held_count = pending.count() - len(to_approve)

    if not to_approve:
        return {'auto_approved': 0, 'held_for_review': held_count}

    with transaction.atomic():
        for staged in to_approve:
            staged.status = 'approved'
            staged.save(update_fields=['status'])

    result = publish_all_approved()
    logger.info(
        f"Auto-published {result['published']} events "
        f"(threshold={SAFETY_SCORE_THRESHOLD}); {held_count} held for review"
    )

    return {'auto_approved': result['published'], 'held_for_review': held_count}
