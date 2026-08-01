from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase, tag

from ingestion.models import EventSource
from ingestion.scraping.scrapers import list_scrapers

VALID_SOURCE_TYPES = {"scraper", "http"}


@tag("fast")
class ScraperRegistryContractTests(SimpleTestCase):
    """The registry is what `seed_sources` and the playground picker project from."""

    def test_every_scraper_declares_a_fetchable_source_type(self):
        for scraper in list_scrapers():
            with self.subTest(key=scraper["key"]):
                self.assertIn(scraper["source_type"], VALID_SOURCE_TYPES)

    def test_every_scraper_carries_a_url_and_name(self):
        for scraper in list_scrapers():
            with self.subTest(key=scraper["key"]):
                self.assertTrue(scraper["url"], "url is needed to seed an EventSource")
                self.assertTrue(scraper["name"], "name attributes published events")


@tag("db")
class SeedSourcesTests(TestCase):
    # Tests run under settings.test, where DEBUG is off — the same guard that
    # stops this command from ever touching prod, so every call opts in via force.

    def test_refuses_to_seed_when_debug_is_off(self):
        with self.assertRaises(CommandError):
            call_command("seed_sources", stdout=StringIO())

        self.assertEqual(EventSource.objects.count(), 0)

    def test_creates_one_source_per_registered_scraper(self):
        call_command("seed_sources", force=True, stdout=StringIO())

        scrapers = list_scrapers()
        self.assertEqual(EventSource.objects.count(), len(scrapers))
        for scraper in scrapers:
            source = EventSource.objects.get(scraper_key=scraper["key"])
            self.assertEqual(source.url, scraper["url"])
            self.assertEqual(source.name, scraper["name"])
            self.assertEqual(source.source_type, scraper["source_type"])
            self.assertTrue(source.active)

    def test_is_idempotent(self):
        call_command("seed_sources", force=True, stdout=StringIO())
        call_command("seed_sources", force=True, stdout=StringIO())

        self.assertEqual(EventSource.objects.count(), len(list_scrapers()))

    def test_adopts_a_row_hand_made_in_the_playground(self):
        """Same url, wrong type — seeding should correct it, not duplicate it."""
        scraper = list_scrapers()[0]
        EventSource.objects.create(
            name="hand-typed", source_type="ics", url=scraper["url"], scraper_key=""
        )

        call_command("seed_sources", force=True, stdout=StringIO())

        source = EventSource.objects.get(url=scraper["url"])
        self.assertEqual(source.scraper_key, scraper["key"])
        self.assertEqual(source.source_type, scraper["source_type"])
        self.assertEqual(EventSource.objects.count(), len(list_scrapers()))
