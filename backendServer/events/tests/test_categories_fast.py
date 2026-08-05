"""No-DB checks on the category vocabulary shape — see test_categories_db.py
for the anti-drift assertion against the live `Category` table."""

import unittest

from django.test import tag

from events.categories import CATEGORY_SLUGS


@tag("fast")
class CategorySlugsTests(unittest.TestCase):
    def test_nine_unique_slugs(self):
        self.assertEqual(len(CATEGORY_SLUGS), 9)
        self.assertEqual(len(CATEGORY_SLUGS), len(set(CATEGORY_SLUGS)))

    def test_slugs_are_lowercase_hyphenated(self):
        for slug in CATEGORY_SLUGS:
            self.assertEqual(slug, slug.lower())
            self.assertNotIn(" ", slug)
