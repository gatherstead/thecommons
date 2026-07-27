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
from ingestion.models import EventSource, RawEvent, SourceRun, StagedEvent


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

        # Collector A: 7 raw events, one per funnel bucket.
        # a1: unprocessed (standardizer never reached it / errored)
        RawEvent.objects.create(
            source=self.collector_a, raw_title="A1", raw_start=self.now, source_uid="a1"
        )
        # a2: processed but no staged row (silent standardizer failure)
        RawEvent.objects.create(
            source=self.collector_a,
            raw_title="A2",
            raw_start=self.now,
            processed=True,
            source_uid="a2",
        )
        # a3: staged, pending, unscored (safety scorer hasn't run yet)
        raw_a3 = RawEvent.objects.create(
            source=self.collector_a,
            raw_title="A3",
            raw_start=self.now,
            processed=True,
            source_uid="a3",
        )
        StagedEvent.objects.create(
            raw_event=raw_a3,
            title="A3",
            description="d",
            location_name="l",
            town="carrboro",
            start_datetime=self.now,
            status="pending",
        )
        # a4: staged, pending, scored above threshold (held for human review)
        raw_a4 = RawEvent.objects.create(
            source=self.collector_a,
            raw_title="A4",
            raw_start=self.now,
            processed=True,
            source_uid="a4",
        )
        StagedEvent.objects.create(
            raw_event=raw_a4,
            title="A4",
            description="d",
            location_name="l",
            town="carrboro",
            start_datetime=self.now,
            status="pending",
            safety_score=0.9,
        )
        # a5: staged, rejected
        raw_a5 = RawEvent.objects.create(
            source=self.collector_a,
            raw_title="A5",
            raw_start=self.now,
            processed=True,
            source_uid="a5",
        )
        StagedEvent.objects.create(
            raw_event=raw_a5,
            title="A5",
            description="d",
            location_name="l",
            town="carrboro",
            start_datetime=self.now,
            status="rejected",
        )
        # a6: staged, duplicate
        raw_a6 = RawEvent.objects.create(
            source=self.collector_a,
            raw_title="A6",
            raw_start=self.now,
            processed=True,
            source_uid="a6",
        )
        StagedEvent.objects.create(
            raw_event=raw_a6,
            title="A6",
            description="d",
            location_name="l",
            town="carrboro",
            start_datetime=self.now,
            status="duplicate",
        )
        # a7: staged, approved + published
        raw_a7 = RawEvent.objects.create(
            source=self.collector_a,
            raw_title="A7",
            raw_start=self.now,
            processed=True,
            source_uid="a7",
        )
        StagedEvent.objects.create(
            raw_event=raw_a7,
            title="A7",
            description="d",
            location_name="l",
            town="carrboro",
            start_datetime=self.now,
            status="approved",
            published_event=event,
        )

        # Collector B: 1 raw event, no staged row yet
        RawEvent.objects.create(
            source=self.collector_b, raw_title="B1", raw_start=self.now, source_uid="b1"
        )

        # Direct source: 1 raw event, duplicate status
        raw_d1 = RawEvent.objects.create(
            source=self.direct_source,
            raw_title="D1",
            raw_start=self.now,
            processed=True,
            source_uid="d1",
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
        self.assertEqual(a["raw_count"], 7)
        self.assertEqual(
            a["staged_by_status"],
            {"pending": 2, "approved": 1, "rejected": 1, "duplicate": 1},
        )
        self.assertEqual(a["published_count"], 1)

        b = rows["Collector B"]
        self.assertEqual(b["raw_count"], 1)
        self.assertEqual(
            b["staged_by_status"],
            {"pending": 0, "approved": 0, "rejected": 0, "duplicate": 0},
        )
        self.assertEqual(b["published_count"], 0)

    def test_collector_summary_funnel_buckets(self):
        rows = {r["name"]: r for r in collector_summary("default", self.start, self.end)}

        a = rows["Collector A"]
        self.assertEqual(
            a["funnel"],
            {
                "raw": 7,
                "unprocessed": 1,
                "no_staged": 1,
                "duplicate": 1,
                "unscored": 1,
                "held_for_review": 1,
                "rejected": 1,
                "published": 1,
            },
        )

        b = rows["Collector B"]
        self.assertEqual(
            b["funnel"],
            {
                "raw": 1,
                "unprocessed": 1,
                "no_staged": 0,
                "duplicate": 0,
                "unscored": 0,
                "held_for_review": 0,
                "rejected": 0,
                "published": 0,
            },
        )

    def test_funnel_buckets_reconcile_against_raw(self):
        """unprocessed + no_staged + duplicate + unscored + held_for_review +
        rejected + approved (not its own bucket — see report) accounts for
        every raw event exactly once, since the pipeline stages are mutually
        exclusive: an event is either unprocessed, processed-with-no-staged-
        row, or staged into exactly one terminal-or-pending status. `published`
        is NOT included here — it's a subset of the `approved` staged rows,
        not a disjoint bucket.
        """
        rows = collector_summary("default", self.start, self.end) + broadcast_inbound_summary(
            "default", self.start, self.end
        )
        for row in rows:
            funnel = row["funnel"]
            approved = row["staged_by_status"]["approved"]
            accounted = (
                funnel["unprocessed"]
                + funnel["no_staged"]
                + funnel["duplicate"]
                + funnel["unscored"]
                + funnel["held_for_review"]
                + funnel["rejected"]
                + approved
            )
            self.assertEqual(accounted, funnel["raw"], row["name"])

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
        self.assertEqual(len(rows), 7)
        self.assertEqual(rows[0]["raw_title"], "A7")
        self.assertEqual(rows[-1]["raw_title"], "A1")

        published_row = next(r for r in rows if r["raw_title"] == "A7")
        self.assertEqual(published_row["staged_status"], "approved")
        self.assertTrue(published_row["published"])
        self.assertTrue(published_row["processed"])

        pending_row = next(r for r in rows if r["raw_title"] == "A3")
        self.assertEqual(pending_row["staged_status"], "pending")
        self.assertFalse(pending_row["published"])

        unprocessed_row = next(r for r in rows if r["raw_title"] == "A1")
        self.assertFalse(unprocessed_row["processed"])
        self.assertIsNone(unprocessed_row["staged_status"])

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

    def test_rows_carry_health_and_last_run_keys(self):
        rows = collector_summary("default", self.start, self.end)
        self.assertTrue(rows)
        for row in rows:
            self.assertIn("health", row)
            self.assertIn("level", row["health"])
            self.assertIn("reasons", row["health"])
            self.assertIn("last_run", row)

    def test_source_with_no_runs_has_last_run_none(self):
        rows = {r["name"]: r for r in collector_summary("default", self.start, self.end)}
        self.assertIsNone(rows["Collector A"]["last_run"])

    def test_source_with_runs_has_last_run_from_most_recent(self):
        SourceRun.objects.create(
            source=self.collector_b,
            started_at=self.now - timedelta(hours=2),
            finished_at=self.now - timedelta(hours=2),
            status="failed",
            error_message="older failure",
        )
        SourceRun.objects.create(
            source=self.collector_b,
            started_at=self.now - timedelta(minutes=5),
            finished_at=self.now - timedelta(minutes=5),
            status="ok",
            error_message="",
        )
        rows = {r["name"]: r for r in collector_summary("default", self.start, self.end)}
        last_run = rows["Collector B"]["last_run"]
        self.assertEqual(last_run["status"], "ok")
        self.assertEqual(last_run["error_message"], "")
        self.assertIsNotNone(last_run["finished_at"])


@tag("db")
class SourceHealthIntegrationTests(TestCase):
    """Exercises source_health wired through _source_rows against real SourceRun rows."""

    def setUp(self):
        self.now = timezone.now()
        self.start = self.now - timedelta(days=1)
        self.end = self.now + timedelta(days=1)

    def test_inactive_source_reports_inactive_not_error(self):
        EventSource.objects.create(
            name="Dead Source",
            source_type="ics",
            url="https://dead.example.com/feed.ics",
            active=False,
            last_polled=None,
        )
        rows = collector_summary("default", self.start, self.end)
        row = next(r for r in rows if r["name"] == "Dead Source")
        self.assertEqual(row["health"]["level"], "inactive")

    def test_never_polled_active_source_is_error(self):
        EventSource.objects.create(
            name="New Source",
            source_type="ics",
            url="https://new.example.com/feed.ics",
            active=True,
            last_polled=None,
        )
        rows = collector_summary("default", self.start, self.end)
        row = next(r for r in rows if r["name"] == "New Source")
        self.assertEqual(row["health"]["level"], "error")
        self.assertIn("never polled", row["health"]["reasons"])

    def test_stale_source_is_error(self):
        source = EventSource.objects.create(
            name="Stale Source",
            source_type="ics",
            url="https://stale.example.com/feed.ics",
            active=True,
            poll_interval_hours=1,
            last_polled=self.now - timedelta(hours=10),
        )
        SourceRun.objects.create(
            source=source,
            started_at=self.now - timedelta(hours=10),
            finished_at=self.now - timedelta(hours=10),
            status="ok",
        )
        rows = collector_summary("default", self.start, self.end)
        row = next(r for r in rows if r["name"] == "Stale Source")
        self.assertEqual(row["health"]["level"], "error")

    def test_two_consecutive_failed_runs_is_error(self):
        source = EventSource.objects.create(
            name="Flaky Source",
            source_type="ics",
            url="https://flaky.example.com/feed.ics",
            active=True,
            poll_interval_hours=1,
            last_polled=self.now - timedelta(minutes=5),
        )
        SourceRun.objects.create(
            source=source,
            started_at=self.now - timedelta(hours=2),
            finished_at=self.now - timedelta(hours=2),
            status="failed",
            error_message="first failure",
        )
        SourceRun.objects.create(
            source=source,
            started_at=self.now - timedelta(minutes=5),
            finished_at=self.now - timedelta(minutes=5),
            status="failed",
            error_message="second failure",
        )
        rows = collector_summary("default", self.start, self.end)
        row = next(r for r in rows if r["name"] == "Flaky Source")
        self.assertEqual(row["health"]["level"], "error")
        self.assertTrue(any("consecutive" in reason for reason in row["health"]["reasons"]))
        self.assertTrue(any("second failure" in reason for reason in row["health"]["reasons"]))

    def test_skipped_runs_between_ok_polls_stay_healthy(self):
        # A correctly-throttled source: skipped runs because it's not due
        # yet, most recent poll succeeded, recent window has activity and a
        # publish. Must not be flagged error just for having skipped runs.
        source = EventSource.objects.create(
            name="Throttled Source",
            source_type="ics",
            url="https://throttled.example.com/feed.ics",
            active=True,
            poll_interval_hours=24,
            last_polled=self.now - timedelta(hours=1),
        )
        SourceRun.objects.create(
            source=source,
            started_at=self.now - timedelta(hours=25),
            finished_at=self.now - timedelta(hours=25),
            status="ok",
        )
        SourceRun.objects.create(
            source=source,
            started_at=self.now - timedelta(hours=13),
            finished_at=self.now - timedelta(hours=13),
            status="skipped",
        )
        SourceRun.objects.create(
            source=source,
            started_at=self.now - timedelta(hours=1),
            finished_at=self.now - timedelta(hours=1),
            status="ok",
        )
        raw = RawEvent.objects.create(
            source=source, raw_title="T1", raw_start=self.now, source_uid="t1", processed=True
        )
        published_event = make_event(title="Published via Throttled")
        StagedEvent.objects.create(
            raw_event=raw,
            title="T1",
            description="d",
            location_name="l",
            town="carrboro",
            start_datetime=self.now,
            status="approved",
            published_event=published_event,
        )
        rows = collector_summary("default", self.start, self.end)
        row = next(r for r in rows if r["name"] == "Throttled Source")
        self.assertEqual(row["health"]["level"], "ok")

    def test_zero_raw_events_in_window_is_warn(self):
        source = EventSource.objects.create(
            name="Quiet Source",
            source_type="ics",
            url="https://quiet.example.com/feed.ics",
            active=True,
            poll_interval_hours=1,
            last_polled=self.now - timedelta(minutes=5),
        )
        SourceRun.objects.create(
            source=source,
            started_at=self.now - timedelta(minutes=5),
            finished_at=self.now - timedelta(minutes=5),
            status="ok",
        )
        rows = collector_summary("default", self.start, self.end)
        row = next(r for r in rows if r["name"] == "Quiet Source")
        self.assertEqual(row["health"]["level"], "warn")
        self.assertIn(
            "polling but zero new raw events in window", row["health"]["reasons"]
        )

    def test_raw_events_recent_runs_fetched_in_single_query(self):
        # Regardless of source count, the recent-runs fetch backing
        # source_health must be one query, not one per source.
        sources = [
            EventSource.objects.create(
                name=f"Source {i}",
                source_type="ics",
                url=f"https://source{i}.example.com/feed.ics",
                active=True,
                poll_interval_hours=1,
                last_polled=self.now - timedelta(minutes=5),
            )
            for i in range(5)
        ]
        for source in sources:
            SourceRun.objects.create(
                source=source,
                started_at=self.now - timedelta(minutes=5),
                finished_at=self.now - timedelta(minutes=5),
                status="ok",
            )

        # 5 queries as documented pre-existing (sources, raw, no_staged,
        # staged-by-status, funnel-staged) + 1 for the single recent-runs
        # fetch added by this ticket = 6 total, independent of source count.
        with self.assertNumQueries(6):
            collector_summary("default", self.start, self.end)
