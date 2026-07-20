from datetime import timedelta

from django.conf import settings
from django.test import TestCase, override_settings, tag
from django.utils import timezone

from broadcast.models import BroadcastSubmission, BroadcastTarget
from devtools.monitoring import (
    broadcast_inbound_summary,
    broadcast_outbound_summary,
    collector_summary,
    drilldown,
)
from events.tests.factories import make_event
from ingestion.models import EventSource, RawEvent, StagedEvent


@tag("db")
class MonitoringQueryServiceTests(TestCase):
    """Exercises devtools/monitoring.py against real rows in the test Postgres DB.

    Window is [start, end) on RawEvent.created_at / BroadcastSubmission.created_at.
    `created_at` is `auto_now_add`, so rows created in setUp all land "now" —
    the window in each test is padded generously around `timezone.now()`.
    """

    def setUp(self):
        self.now = timezone.now()
        self.start = self.now - timedelta(days=1)
        self.end = self.now + timedelta(days=1)

        self.collector_a = EventSource.objects.create(
            name="Collector A", source_type="ics", url="https://a.example.com/feed.ics"
        )
        self.collector_b = EventSource.objects.create(
            name="Collector B", source_type="scraper", url="https://b.example.com/events"
        )
        self.direct_source = EventSource.objects.create(
            name="Direct Host Submission", source_type="direct", url="https://commons.local/direct"
        )

        event = make_event(title="Published via A")

        # Collector A: 3 raw events -> 1 pending, 1 approved+published, 1 rejected
        raw_a1 = RawEvent.objects.create(
            source=self.collector_a, raw_title="A1", raw_start=self.now, source_uid="a1"
        )
        StagedEvent.objects.create(
            raw_event=raw_a1,
            title="A1",
            description="d",
            location_name="l",
            town="carrboro",
            start_datetime=self.now,
            status="pending",
        )
        raw_a2 = RawEvent.objects.create(
            source=self.collector_a,
            raw_title="A2",
            raw_start=self.now,
            processed=True,
            source_uid="a2",
        )
        StagedEvent.objects.create(
            raw_event=raw_a2,
            title="A2",
            description="d",
            location_name="l",
            town="carrboro",
            start_datetime=self.now,
            status="approved",
            published_event=event,
        )
        raw_a3 = RawEvent.objects.create(
            source=self.collector_a, raw_title="A3", raw_start=self.now, source_uid="a3"
        )
        StagedEvent.objects.create(
            raw_event=raw_a3,
            title="A3",
            description="d",
            location_name="l",
            town="carrboro",
            start_datetime=self.now,
            status="rejected",
        )

        # Collector B: 1 raw event, no staged row yet
        RawEvent.objects.create(
            source=self.collector_b, raw_title="B1", raw_start=self.now, source_uid="b1"
        )

        # Direct source: 1 raw event, duplicate status
        raw_d1 = RawEvent.objects.create(
            source=self.direct_source, raw_title="D1", raw_start=self.now, source_uid="d1"
        )
        StagedEvent.objects.create(
            raw_event=raw_d1,
            title="D1",
            description="d",
            location_name="l",
            town="carrboro",
            start_datetime=self.now,
            status="duplicate",
        )

        # Broadcast submission with mixed-status targets
        self.submission = BroadcastSubmission.objects.create(
            client_label="client-1",
            title="Broadcast Event",
            description="desc",
            start_datetime=self.now,
            venue_name="Venue",
            address_line1="123 Main St",
            zip="27510",
            status="done",
        )
        BroadcastTarget.objects.create(
            submission=self.submission, site_key="site-one", status="succeeded"
        )
        BroadcastTarget.objects.create(
            submission=self.submission, site_key="site-two", status="failed"
        )

    def test_collector_summary_counts_are_exact(self):
        rows = {r["name"]: r for r in collector_summary("default", self.start, self.end)}

        self.assertEqual(set(rows.keys()), {"Collector A", "Collector B"})

        a = rows["Collector A"]
        self.assertEqual(a["source_type"], "ics")
        self.assertEqual(a["raw_count"], 3)
        self.assertEqual(
            a["staged_by_status"],
            {"pending": 1, "approved": 1, "rejected": 1, "duplicate": 0},
        )
        self.assertEqual(a["published_count"], 1)

        b = rows["Collector B"]
        self.assertEqual(b["raw_count"], 1)
        self.assertEqual(
            b["staged_by_status"],
            {"pending": 0, "approved": 0, "rejected": 0, "duplicate": 0},
        )
        self.assertEqual(b["published_count"], 0)

    def test_direct_source_excluded_from_collector_summary(self):
        names = [r["name"] for r in collector_summary("default", self.start, self.end)]
        self.assertNotIn("Direct Host Submission", names)

    def test_direct_source_only_in_inbound_summary(self):
        rows = broadcast_inbound_summary("default", self.start, self.end)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["name"], "Direct Host Submission")
        self.assertEqual(row["source_type"], "direct")
        self.assertEqual(row["raw_count"], 1)
        self.assertEqual(
            row["staged_by_status"],
            {"pending": 0, "approved": 0, "rejected": 0, "duplicate": 1},
        )
        self.assertEqual(row["published_count"], 0)

    def test_broadcast_outbound_summary_counts(self):
        result = broadcast_outbound_summary("default", self.start, self.end)
        self.assertEqual(result["total"], 1)
        self.assertEqual(
            result["by_status"],
            {"queued": 0, "running": 0, "done": 1, "failed": 0, "canceled": 0},
        )
        self.assertEqual(
            result["targets_by_status"],
            {
                "pending": 0,
                "in_progress": 0,
                "succeeded": 1,
                "failed": 1,
                "needs_manual": 0,
                "skipped": 0,
            },
        )

    def test_drilldown_collector_returns_rows_most_recent_first(self):
        rows = drilldown("default", "collector", self.collector_a.id, self.start, self.end)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["raw_title"], "A3")
        self.assertEqual(rows[-1]["raw_title"], "A1")

        published_row = next(r for r in rows if r["raw_title"] == "A2")
        self.assertEqual(published_row["staged_status"], "approved")
        self.assertTrue(published_row["published"])
        self.assertTrue(published_row["processed"])

        pending_row = next(r for r in rows if r["raw_title"] == "A1")
        self.assertEqual(pending_row["staged_status"], "pending")
        self.assertFalse(pending_row["published"])

    def test_drilldown_respects_limit(self):
        rows = drilldown("default", "collector", self.collector_a.id, self.start, self.end, limit=2)
        self.assertEqual(len(rows), 2)

    def test_drilldown_inbound_uses_direct_source(self):
        rows = drilldown("default", "inbound", self.direct_source.id, self.start, self.end)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["raw_title"], "D1")
        self.assertEqual(rows[0]["staged_status"], "duplicate")

    def test_drilldown_outbound_all_sites(self):
        rows = drilldown("default", "outbound", None, self.start, self.end)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["submission_id"], str(self.submission.id))
        self.assertEqual(row["title"], "Broadcast Event")
        self.assertEqual(row["status"], "done")
        site_keys = {t["site_key"] for t in row["targets"]}
        self.assertEqual(site_keys, {"site-one", "site-two"})

    def test_drilldown_outbound_filters_by_site_key(self):
        rows = drilldown("default", "outbound", "site-one", self.start, self.end)
        self.assertEqual(len(rows), 1)

        rows = drilldown("default", "outbound", "nonexistent-site", self.start, self.end)
        self.assertEqual(rows, [])

    def test_unconfigured_prod_readonly_returns_empty_not_crash(self):
        """Force `prod_readonly` out of DATABASES (this dev env may have it set via
        PROD_DATABASE_URL) to exercise the guard that keeps an unconfigured alias
        from ever raising.
        """
        databases_without_prod = {
            k: v for k, v in settings.DATABASES.items() if k != "prod_readonly"
        }
        with override_settings(DATABASES=databases_without_prod):
            self.assertEqual(collector_summary("prod_readonly", self.start, self.end), [])
            self.assertEqual(broadcast_inbound_summary("prod_readonly", self.start, self.end), [])
            self.assertEqual(broadcast_outbound_summary("prod_readonly", self.start, self.end), {})
            self.assertEqual(
                drilldown("prod_readonly", "collector", self.collector_a.id, self.start, self.end),
                [],
            )
