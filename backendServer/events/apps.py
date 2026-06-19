from django.apps import AppConfig


class EventsConfig(AppConfig):
    name = "events"

    def ready(self):
        from . import signals  # noqa: F401  — registers cache-invalidation receivers
