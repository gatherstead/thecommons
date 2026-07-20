"""Cache invalidation on writes to the cached access models.

Registered in BroadcastConfig.ready(). BroadcastAccess writes clear that
email's JWT-path cache entry; AccessCode writes clear that code's
trial-path meta entry.
"""

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from . import cache as access_cache
from .models import AccessCode, BroadcastAccess


@receiver(post_save, sender=BroadcastAccess)
@receiver(post_delete, sender=BroadcastAccess)
def invalidate_broadcast_access(sender, instance, **kwargs):
    access_cache.invalidate_jwt_access(instance.email)


@receiver(post_save, sender=AccessCode)
@receiver(post_delete, sender=AccessCode)
def invalidate_access_code(sender, instance, **kwargs):
    access_cache.invalidate_code_meta(instance.code_hash)
