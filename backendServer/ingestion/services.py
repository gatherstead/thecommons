from django.db import transaction

from events.models import Event, Tag, Town
from ingestion.models import StagedEvent


def publish_all_approved():
    """
    Atomically moves all approved StagedEvents into the Events table,
    then deletes them from the staged table.

    Returns a dict with counts:
        published          — newly created Event records
        already_published  — approved staged events that already had an Event record
        removed            — total StagedEvents deleted
    """
    approved_staged = list(StagedEvent.objects.filter(status='approved'))

    if not approved_staged:
        return {'published': 0, 'already_published': 0, 'removed': 0}

    with transaction.atomic():
        published_count = 0
        already_published_count = 0

        for staged in approved_staged:
            if staged.published_event_id is None:
                town_obj = Town.objects.filter(slug=staged.town.lower()).first() if staged.town else None
                if town_obj is None:
                    continue
                event = Event.objects.create(
                    title=staged.title,
                    town=town_obj,
                    date=staged.start_datetime,
                    venue=staged.location_name,
                    description=staged.description,
                    price=staged.price,
                    link=staged.link,
                )
                for tag_name in staged.tags:
                    tag_obj, _ = Tag.objects.get_or_create(name=tag_name.strip().lower())
                    event.tags.add(tag_obj)
                published_count += 1
            else:
                already_published_count += 1

        removed_count = StagedEvent.objects.filter(status='approved').delete()[0]

    return {
        'published': published_count,
        'already_published': already_published_count,
        'removed': removed_count,
    }
