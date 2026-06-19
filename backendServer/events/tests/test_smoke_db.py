"""DB tier: smoke test that the Postgres test DB is reachable."""
from django.test import TestCase, tag

from events.models import Town


@tag('db')
class TownTableReachableTests(TestCase):
    def test_town_table_is_queryable(self):
        self.assertGreaterEqual(Town.objects.count(), 0)
