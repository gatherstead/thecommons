from django.apps import AppConfig


class BroadcastConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "broadcast"

    def ready(self):
        from . import signals  # noqa: F401  — registers cache-invalidation receivers
