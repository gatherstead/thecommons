"""Cache invalidation on writes to the cached read models.

Registered in EventsConfig.ready(). Event writes bump the event-list version;
Town writes clear their own near-static cache.
"""

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from . import cache as events_cache
from .models import Event, Town


@receiver(post_save, sender=Event)
@receiver(post_delete, sender=Event)
def invalidate_event_list(sender, **kwargs):
    events_cache.invalidate_events_list()


@receiver(post_save, sender=Town)
@receiver(post_delete, sender=Town)
def invalidate_towns(sender, **kwargs):
    events_cache.invalidate_towns()
