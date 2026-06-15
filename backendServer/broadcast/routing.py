"""Tag-based routing: which sites an event is eligible for. Deterministic, no LLM.

The locality / category vocabularies here are deliberately independent of
events.Town and events.Category — broadcast/ must not import from events/
(isolation contract). Do not DRY this up.
"""
from dataclasses import dataclass

from broadcast.schema import CanonicalEvent

LOCALITIES = frozenset({
    "pittsboro", "chatham", "chapel-hill", "carrboro", "durham",
    "raleigh", "cary", "wake", "triangle",
})

CATEGORIES = frozenset({
    "music", "arts", "family-kids", "wellness", "food-drink", "festival",
    "market", "literary", "community", "nightlife", "education",
})

TRIANGLE = LOCALITIES  # region-wide sites accept every Triangle locality


@dataclass(frozen=True)
class Eligibility:
    localities: frozenset[str]  # event.locality must be in here (empty = accept any)
    categories: frozenset[str]  # event must have ≥1 category in here (empty = accept any)

    def matches(self, ev: CanonicalEvent) -> tuple[bool, str]:
        if self.localities and not (set(ev.locality) & self.localities):
            return False, f"localities {ev.locality} not covered"
        if self.categories and not (set(ev.categories) & self.categories):
            return False, f"none of {ev.categories} in accepted categories"
        return True, ""


def eligible_targets(ev: CanonicalEvent, enabled_adapters):
    """Split adapters into (eligible, excluded-with-reason) for this event."""
    eligible = []
    excluded = []
    for adapter in enabled_adapters:
        ok, reason = adapter.eligibility.matches(ev)
        if ok:
            eligible.append(adapter)
        else:
            excluded.append((adapter.key, reason))
    return eligible, excluded
