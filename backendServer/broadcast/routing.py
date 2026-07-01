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

# Deliberately local — do NOT import from events/.
_LOCALITY_LABELS: dict[str, str] = {
    "pittsboro":   "Pittsboro",
    "chatham":     "Chatham County",
    "chapel-hill": "Chapel Hill",
    "carrboro":    "Carrboro",
    "durham":      "Durham",
    "raleigh":     "Raleigh",
    "cary":        "Cary",
    "wake":        "Wake County",
    "triangle":    "the Triangle",
}

_CATEGORY_LABELS: dict[str, str] = {
    "music":       "music",
    "arts":        "arts",
    "family-kids": "family/kids",
    "wellness":    "wellness",
    "food-drink":  "food & drink",
    "festival":    "festival",
    "market":      "market",
    "literary":    "literary",
    "community":   "community",
    "nightlife":   "nightlife",
    "education":   "education",
}


def _join_labels(labels: list[str]) -> str:
    if not labels:
        return ""
    if len(labels) == 1:
        return labels[0]
    if len(labels) == 2:
        return f"{labels[0]} & {labels[1]}"
    return ", ".join(labels[:-1]) + " & " + labels[-1]


@dataclass(frozen=True)
class Eligibility:
    localities: frozenset[str]  # event.locality must be in here (empty = accept any)
    categories: frozenset[str]  # event must have ≥1 category in here (empty = accept any)

    def matches(self, ev: CanonicalEvent) -> tuple[bool, str]:
        if self.localities and not (set(ev.locality) & self.localities):
            if self.localities == TRIANGLE:
                loc_desc = "the Triangle"
            else:
                labels = [_LOCALITY_LABELS.get(s, s) for s in sorted(self.localities)]
                loc_desc = _join_labels(labels)
            return False, (
                f"Covers {loc_desc} only — "
                "check one of those localities to include it."
            )
        if self.categories and not (set(ev.categories) & self.categories):
            labels = [_CATEGORY_LABELS.get(s, s) for s in sorted(self.categories)]
            cat_desc = _join_labels(labels)
            return False, (
                f"Only accepts {cat_desc} events — add a matching category."
            )
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
