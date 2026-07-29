from django.test import TestCase, tag
from django.utils import timezone

from ingestion.models import EventSource, SourceRun


@tag("db")
class SourceRunTests(TestCase):
    def setUp(self):
        self.source = EventSource.objects.create(
            name="Test Feed", source_type="ics", url="https://feed.test/cal.ics"
        )

    def test_creates_row_with_defaults(self):
        run = SourceRun.objects.create(
            source=self.source,
            started_at=timezone.now(),
            status="ok",
        )
        run.refresh_from_db()
        self.assertEqual(run.trigger, "scheduled")
        self.assertEqual(run.items_fetched, 0)
        self.assertEqual(run.items_new, 0)
        self.assertEqual(run.items_duplicate, 0)
        self.assertEqual(run.error_class, "")
        self.assertEqual(run.error_message, "")
        self.assertEqual(run.traceback, "")
        self.assertIsNone(run.finished_at)

    def test_ordering_is_newest_first_per_source(self):
        now = timezone.now()
        older = SourceRun.objects.create(
            source=self.source,
            started_at=now - timezone.timedelta(hours=1),
            status="ok",
        )
        newer = SourceRun.objects.create(
            source=self.source,
            started_at=now,
            status="failed",
        )
        runs = list(SourceRun.objects.filter(source=self.source))
        self.assertEqual(runs, [newer, older])

    def test_status_and_trigger_choices_cover_expected_values(self):
        statuses = [choice[0] for choice in SourceRun.STATUS_CHOICES]
        triggers = [choice[0] for choice in SourceRun.TRIGGER_CHOICES]
        self.assertEqual(statuses, ["ok", "failed", "refused", "skipped"])
        self.assertEqual(triggers, ["scheduled", "probe", "manual"])
