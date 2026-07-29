"""Guards the Town rows seeded by migrations (events 0004, 0016).

Town coverage is not cosmetic: `publish_approved_events` drops any staged event
whose Gemini-classified town has no matching `Town` row (ingestion/services.py).
A migration that removes one of these silently stops publishing that town's
events, with no error anywhere — which is exactly what happened to Siler City
and Bynum before 0016.
"""

from django.test import TestCase, tag

from events.models import Town


@tag("db")
class TownSeedTests(TestCase):
    def test_covered_towns_seeded(self):
        expected = {"carrboro", "chapel-hill", "pittsboro", "siler-city", "bynum"}
        self.assertTrue(expected <= set(Town.objects.values_list("slug", flat=True)))

    def test_chatham_county_towns_have_display_names(self):
        # The slug is what the pipeline matches on, but the name is what the
        # reader sees, so a blank/placeholder name would ship to the site.
        self.assertEqual(Town.objects.get(slug="siler-city").name, "Siler City")
        self.assertEqual(Town.objects.get(slug="bynum").name, "Bynum")
