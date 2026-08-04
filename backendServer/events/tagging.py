"""Day-part tags derived from an event's start time.

`weekends` / `evenings` / `daytime` used to depend on the standardizer LLM
following a prompt instruction — unreliable, and it never ran at all for
human-submitted events (those skip Gemini entirely). They're pure functions
of `Event.date`, so compute them instead of asking a model.

`USE_TZ=True` (see `backend/settings/base.py`) means `Event.date` is stored
and handed back in UTC regardless of the project's `TIME_ZONE` setting — so
every caller here converts to America/New_York *first*. Skipping that
conversion silently mis-tags evening events that cross the UTC day boundary
(e.g. a 9pm ET Friday show is already Saturday in UTC).
"""

from collections.abc import Iterable
from datetime import datetime
from zoneinfo import ZoneInfo

from django.utils import timezone as django_timezone

from events.models import Tag

DAY_PART_TAGS = frozenset({"weekends", "evenings", "daytime"})

_LOCAL_TZ = ZoneInfo("America/New_York")


def day_part_tags(dt: datetime) -> set[str]:
    """Tags derived from an event's start time, in local (ET) wall-clock terms.

    - `daytime`: local start hour < 18 (before 6:00pm)
    - `evenings`: local start hour >= 16 (4:00pm or later)
      The 4-6pm band deliberately yields BOTH tags — events have no end time,
      so a 4:30pm event plausibly runs into both. Err inclusive.
    - `weekends`: local weekday is Sat or Sun, OR Friday at 17:00 or later.
    """
    if django_timezone.is_naive(dt):
        local = dt.replace(tzinfo=_LOCAL_TZ)
    else:
        local = dt.astimezone(_LOCAL_TZ)

    tags = set()
    if local.hour < 18:
        tags.add("daytime")
    if local.hour >= 16:
        tags.add("evenings")

    weekday = local.weekday()  # Mon=0 ... Sun=6
    if weekday in (5, 6) or (weekday == 4 and local.hour >= 17):
        tags.add("weekends")

    return tags


def apply_tags(event, supplied: Iterable[str]) -> None:
    """Set `event.tags` to `supplied` (lowercased, deduped) with the computed
    day-part tags for `event.date` layered on top — computed always wins over
    a stale or LLM/user-supplied day-part slug, so those are stripped first.
    """
    names = {t.strip().lower() for t in supplied} - DAY_PART_TAGS
    names |= day_part_tags(event.date)
    event.tags.set([Tag.objects.get_or_create(name=n)[0] for n in sorted(names)])
