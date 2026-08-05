from unittest import mock

from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, tag

from events import cache as events_cache
from events.models import Category, Event
from events.tests.factories import make_event


@tag("db")
class BackfillEventCategoriesCommandTests(TestCase):
    def setUp(self):
        cache.clear()

    def _patch_infer(self, side_effect=None, return_value=None):
        target = "ingestion.management.commands.backfill_event_categories.infer_categories"
        if side_effect is not None:
            return mock.patch(target, side_effect=side_effect)
        return mock.patch(target, return_value=return_value)

    def test_dry_run_writes_nothing(self):
        event = make_event(title="Jazz Night", description="live jazz downtown")

        with self._patch_infer(return_value=["music"]) as mocked:
            call_command("backfill_event_categories", "--dry-run")

        mocked.assert_called_once()
        event.refresh_from_db()
        self.assertEqual(list(event.categories.all()), [])

    def test_real_run_attaches_matching_category_rows(self):
        event = make_event(title="Jazz Night", description="live jazz downtown")

        with self._patch_infer(return_value=["music", "nightlife"]):
            call_command("backfill_event_categories")

        event.refresh_from_db()
        slugs = sorted(c.slug for c in event.categories.all())
        self.assertEqual(slugs, ["music", "nightlife"])

    def test_second_run_is_a_no_op(self):
        make_event(title="Jazz Night", description="live jazz downtown")

        with self._patch_infer(return_value=["music"]):
            call_command("backfill_event_categories")

        with self._patch_infer(return_value=["music"]) as mocked:
            call_command("backfill_event_categories")

        mocked.assert_not_called()

    def test_limit_is_respected(self):
        make_event(title="Event A", description="a", days_offset=1)
        make_event(title="Event B", description="b", days_offset=2)

        with self._patch_infer(return_value=["music"]) as mocked:
            call_command("backfill_event_categories", "--limit", "1")

        self.assertEqual(mocked.call_count, 1)
        categorized = Event.objects.filter(categories__isnull=False).count()
        self.assertEqual(categorized, 1)

    def test_no_categories_inferred_is_left_uncategorized_without_crashing(self):
        event = make_event(title="Mystery Event", description="unclear")

        with self._patch_infer(return_value=[]):
            call_command("backfill_event_categories")

        event.refresh_from_db()
        self.assertEqual(list(event.categories.all()), [])

    def test_real_run_invalidates_events_cache(self):
        make_event(title="Jazz Night", description="live jazz downtown")
        version_before = events_cache._events_list_version()

        with self._patch_infer(return_value=["music"]):
            call_command("backfill_event_categories")

        self.assertGreater(events_cache._events_list_version(), version_before)

    def test_already_categorized_events_are_skipped(self):
        event = make_event(title="Jazz Night", description="live jazz downtown")
        event.categories.add(Category.objects.get(slug="music"))

        with self._patch_infer(return_value=["nightlife"]) as mocked:
            call_command("backfill_event_categories")

        mocked.assert_not_called()
        event.refresh_from_db()
        self.assertEqual([c.slug for c in event.categories.all()], ["music"])
