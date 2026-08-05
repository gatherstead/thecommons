"""Anti-drift guard: CATEGORY_SLUGS must exactly match the `Category` rows
seeded by `events/migrations/0012_add_category_model.py`. If a future
migration adds/renames/removes a category without updating `events/categories.py`
(or vice versa), the ingestion prompt and server-side validation would silently
fall out of step with what the site actually filters on — this test is the
only thing standing between that drift and prod.
"""

from django.test import TestCase, tag

from events.categories import CATEGORY_SLUGS
from events.models import Category


@tag("db")
class CategorySlugsMatchCategoryTableTests(TestCase):
    def test_slugs_match_seeded_rows_exactly(self):
        seeded = set(Category.objects.values_list("slug", flat=True))
        self.assertEqual(set(CATEGORY_SLUGS), seeded)
        # Catch duplicates in the constant too, not just a set-vs-set mismatch.
        self.assertEqual(len(CATEGORY_SLUGS), len(seeded))
