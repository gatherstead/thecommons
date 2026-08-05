"""Canonical event-category vocabulary.

The Commons classifies events into 9 fixed categories, seeded as `events.Category`
rows by `events/migrations/0012_add_category_model.py` (`SEED_CATEGORIES`). That
migration is the origin of the rows in the database; `CATEGORY_SLUGS` here is a
plain-Python mirror of the same slugs so callers that only need the vocabulary
(prompt-building, server-side validation) don't have to hit the database or
import Django's ORM. `events/tests/test_categories_db.py` asserts this constant
matches the live `Category` table row-for-row, so the two can't silently drift —
edit the migration's `SEED_CATEGORIES` and this list together.

Deliberately separate from `broadcast`'s category vocabulary (`CATEGORIES` in
`broadcast/routing.py`), which maps onto destination sites' taxonomies and
genuinely differs — `art` vs `arts`, `markets-fairs` vs `market`, plus
`family-kids`/`literary`/`festival` that have no equivalent here. Never import
from or align the two.
"""

CATEGORY_SLUGS = [
    "music",
    "art",
    "food-drink",
    "sports-outdoors",
    "community",
    "nightlife",
    "markets-fairs",
    "comedy",
    "wellness",
]
