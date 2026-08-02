from datetime import timedelta

from django.conf import settings
from django.db import OperationalError, ProgrammingError
from django.test import TestCase, override_settings, tag
from django.utils import timezone

from broadcast.models import BroadcastSubmission, BroadcastTarget
from devtools.monitoring import (
    _STAGED_STATUSES,
    RUNS_AVAILABLE,
    RUNS_DB_NOT_CONFIGURED,
    RUNS_MISSING_TABLE,
    RUNS_NO_PERMISSION,
    RUNS_UNREACHABLE,
    broadcast_inbound_summary,
    broadcast_outbound_summary,
    collector_summary,
    drilldown,
    resolve_source_runs_state,
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
        # a7: staged, published (terminal status — swept by publish_all_approved,
        # not deleted; see services.publish_all_approved)
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
            status="published",
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

    def _expected_staged_by_status(self, **nonzero):
        """Build a full `staged_by_status` expectation from `_STAGED_STATUSES`.

        `staged_by_status` always has one key per `StagedEvent.STATUS_CHOICES`
        (see `_STAGED_STATUSES` in monitoring.py), so a dict hardcoding only
        the statuses that existed when a test was written breaks the moment a
        new status is added — exactly what happened when ticket 36.1 added
        `skipped_no_town`. Deriving the full key set here instead means these
        tests only need to say which counts are nonzero, and still fail loudly
        if any count (including a newly-added status's) is wrong.
        """
        expected = dict.fromkeys(_STAGED_STATUSES, 0)
        expected.update(nonzero)
        return expected

    def test_collector_summary_counts_are_exact(self):
        rows = {r["name"]: r for r in collector_summary("default", self.start, self.end)}

        self.assertEqual(set(rows.keys()), {"Collector A", "Collector B"})

        a = rows["Collector A"]
        self.assertEqual(a["source_type"], "ics")
        self.assertEqual(a["raw_count"], 7)
        self.assertEqual(
            a["staged_by_status"],
            self._expected_staged_by_status(
                pending=2, approved=0, rejected=1, duplicate=1, published=1
            ),
        )
        self.assertEqual(a["published_count"], 1)

        b = rows["Collector B"]
        self.assertEqual(b["raw_count"], 1)
        self.assertEqual(
            b["staged_by_status"],
            self._expected_staged_by_status(
                pending=0, approved=0, rejected=0, duplicate=0, published=0
            ),
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
                "approved": 0,
                "no_town": 0,
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
                "approved": 0,
                "no_town": 0,
                "published": 0,
            },
        )

    def test_funnel_buckets_reconcile_against_raw(self):
        """Every funnel bucket is disjoint, so they sum to `raw` exactly.

        An event is either unprocessed, processed-with-no-staged-row, or staged
        into exactly one bucket. The `approved`/`published` split is the subtle
        one: `published` counts rows carrying a live Event regardless of status,
        and `approved` is the residual (approved but not yet published), so the
        two can't double-count.

        That split is deliberate. `publish_all_approved` now flips a swept row to
        a terminal `status="published"` instead of deleting it, but
        `ingest_direct_submission` publishes an Event and leaves the row
        `approved` until some later sweep. Keying `published` off the status
        alone would report those genuinely-live events as unpublished — on prod,
        indefinitely, since `auto_publish_safe_events` early-returns when nothing
        is pending. This test therefore reads both from `funnel`, not from
        `staged_by_status`.

        Sums every bucket *except* `raw` itself, rather than naming each bucket,
        so a future bucket added to `funnel` without being wired into the sum
        (as happened when ticket 36.1 added `skipped_no_town` and it fell into
        no bucket at all — see `test_skipped_no_town_bucket_reconciles`) fails
        this test instead of silently passing.
        """
        rows = collector_summary("default", self.start, self.end) + broadcast_inbound_summary(
            "default", self.start, self.end
        )
        for row in rows:
            funnel = row["funnel"]
            accounted = sum(v for k, v in funnel.items() if k != "raw")
            self.assertEqual(accounted, funnel["raw"], row["name"])

    def test_skipped_no_town_bucket_reconciles(self):
        """A source with a `skipped_no_town` row still sums to `raw`.

        Ticket 36.1 added the terminal-ish `skipped_no_town` status for staged
        events whose town has no matching `Town` row (previously these stayed
        `approved` forever and were re-logged on every pipeline run). The
        `funnel` dict has a dedicated `no_town` bucket for it — without one,
        these rows fall through into no bucket at all and the funnel silently
        stops summing to `raw`, which is exactly what happened before this fix.
        """
        raw = RawEvent.objects.create(
            source=self.collector_a,
            raw_title="No Matching Town",
            raw_start=self.start + timedelta(hours=1),
            processed=True,
        )
        StagedEvent.objects.create(
            raw_event=raw,
            title="No Matching Town",
            description="d",
            location_name="l",
            town="some-uncovered-town",
            start_datetime=self.start + timedelta(hours=1),
            status="skipped_no_town",
        )

        row = {r["name"]: r for r in collector_summary("default", self.start, self.end)}[
            "Collector A"
        ]
        funnel = row["funnel"]
        self.assertEqual(funnel["no_town"], 1)
        accounted = sum(v for k, v in funnel.items() if k != "raw")
        self.assertEqual(accounted, funnel["raw"])
        self.assertEqual(
            row["no_town_note"],
            "1 skipped — town not in coverage (see `manage.py reopen_skipped_towns` once added)",
        )

    def test_published_bucket_counts_approved_rows_with_a_live_event(self):
        """A row that has an Event but hasn't been swept yet still reads as
        published — the `ingest_direct_submission` state, and the reason the
        bucket keys off `published_event` rather than `status`."""
        raw = RawEvent.objects.create(
            source=self.collector_a,
            raw_title="Approved With Event",
            raw_description="d",
            raw_location="Venue",
            raw_start=self.start + timedelta(hours=1),
            processed=True,
        )
        event = make_event(title="Approved With Event")
        StagedEvent.objects.create(
            raw_event=raw,
            title="Approved With Event",
            description="d",
            location_name="Venue",
            town="Carrboro",
            start_datetime=self.start + timedelta(hours=1),
            status="approved",
            published_event=event,
        )

        row = {r["name"]: r for r in collector_summary("default", self.start, self.end)}[
            "Collector A"
        ]
        self.assertEqual(row["funnel"]["published"], 2)
        self.assertEqual(row["funnel"]["approved"], 0)
        self.assertEqual(row["published_count"], 2)

    def test_duplicate_row_with_prior_event_is_not_double_counted(self):
        """40.4: `ingest_direct_submission`'s duplicate/held/no_town early
        returns now keep `published_event` pointed at a Event a *prior* call
        already published, instead of orphaning it (production audit 40.3
        found 4 of 4 live direct-submission Events orphaned this way). Such a
        row must be counted once — in its own status bucket — not also in
        `published`, or the funnel buckets stop summing to `raw`.
        """
        raw = RawEvent.objects.create(
            source=self.collector_a,
            raw_title="Duplicate With Prior Event",
            raw_start=self.start + timedelta(hours=1),
            processed=True,
        )
        prior_event = make_event(title="Prior Live Event")
        StagedEvent.objects.create(
            raw_event=raw,
            title="Duplicate With Prior Event",
            description="d",
            location_name="l",
            town="carrboro",
            start_datetime=self.start + timedelta(hours=1),
            status="duplicate",
            published_event=prior_event,
        )

        row = {r["name"]: r for r in collector_summary("default", self.start, self.end)}[
            "Collector A"
        ]
        funnel = row["funnel"]
        # Counted once, in `duplicate` (setUp's a6 + this new row) — not
        # also folded into `published`, which stays at setUp's a7 alone.
        self.assertEqual(funnel["duplicate"], 2)
        self.assertEqual(funnel["published"], 1)
        accounted = sum(v for k, v in funnel.items() if k != "raw")
        self.assertEqual(accounted, funnel["raw"])

    def test_published_note_is_none_when_window_has_published_rows(self):
        # Collector A already has one published row in this window (setUp's
        # "a7" StagedEvent) — nothing to disambiguate, so no note.
        row = {r["name"]: r for r in collector_summary("default", self.start, self.end)}[
            "Collector A"
        ]
        self.assertGreater(row["funnel"]["published"], 0)
        self.assertIsNone(row["published_note"])

    def test_published_all_time_counts_live_events_by_source_name(self):
        # Attribution is purely by Event.source_name — no source FK exists on
        # Event, and Event carries no creation timestamp, so this is
        # necessarily an un-windowed, all-time count (ticket 36.6).
        make_event(title="Live Event One", source_name="Collector B")
        make_event(title="Live Event Two", source_name="Collector B")
        make_event(title="Unrelated Event", source_name="Some Other Source")

        row = {r["name"]: r for r in collector_summary("default", self.start, self.end)}[
            "Collector B"
        ]
        self.assertEqual(row["published_all_time"], 2)
        self.assertEqual(row["published_note"], "0 in window; 2 events live all-time")

    def test_direct_source_published_all_time_counts_prefix_and_literal_names(self):
        # Ticket 40.1: two different code paths stamp two different
        # `Event.source_name` shapes for direct submissions — the
        # per-submission path (ingestion/services.py:220-222) stamps a
        # per-organizer prefix, the bulk sweep path (services.py:80-83)
        # stamps the literal `EventSource.name`. Both must count toward the
        # direct source's all-time attribution.
        make_event(title="Prefixed, with organizer", source_name="Direct submission by Alice")
        make_event(title="Prefixed, no organizer", source_name="Direct submission by host")
        make_event(title="Literal EventSource.name", source_name="Direct Host Submission")
        make_event(title="Unrelated collector event", source_name="Collector A")

        row = broadcast_inbound_summary("default", self.start, self.end)[0]
        self.assertEqual(row["name"], "Direct Host Submission")
        self.assertEqual(row["published_all_time"], 3)

    def test_direct_source_published_note_fires_when_all_time_nonzero(self):
        # The window's `published` count is 0 for this source (setUp's "d1"
        # StagedEvent is `duplicate`, not published) — `published_note`
        # (ticket 36.6) must still fire off the all-time count now that
        # ticket 40.1 makes that count nonzero for direct sources.
        make_event(title="Live direct event", source_name="Direct submission by Bob")

        row = broadcast_inbound_summary("default", self.start, self.end)[0]
        self.assertEqual(row["published_count"], 0)
        self.assertEqual(row["published_all_time"], 1)
        self.assertEqual(row["published_note"], "0 in window; 1 events live all-time")

    def test_collector_published_all_time_still_exact_match_only(self):
        # Ticket 40.1 adds a separate prefix-matching branch used only for
        # `source_type == "direct"` rows. Collector sources must keep the
        # original exact-match-on-EventSource.name behavior, unaffected by a
        # direct-shaped source_name existing elsewhere in the table.
        make_event(title="Live Event One", source_name="Collector B")
        make_event(title="Looks like a direct event", source_name="Direct submission by Nobody")

        row = {r["name"]: r for r in collector_summary("default", self.start, self.end)}[
            "Collector B"
        ]
        self.assertEqual(row["published_all_time"], 1)

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
            self._expected_staged_by_status(duplicate=1),
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
        rows, total = drilldown("default", "collector", self.collector_a.id, self.start, self.end)
        self.assertEqual(len(rows), 7)
        self.assertEqual(total, 7)
        self.assertEqual(rows[0]["raw_title"], "A7")
        self.assertEqual(rows[-1]["raw_title"], "A1")

        published_row = next(r for r in rows if r["raw_title"] == "A7")
        self.assertEqual(published_row["staged_status"], "published")
        self.assertTrue(published_row["published"])
        self.assertTrue(published_row["processed"])

        pending_row = next(r for r in rows if r["raw_title"] == "A3")
        self.assertEqual(pending_row["staged_status"], "pending")
        self.assertFalse(pending_row["published"])

        unprocessed_row = next(r for r in rows if r["raw_title"] == "A1")
        self.assertFalse(unprocessed_row["processed"])
        self.assertIsNone(unprocessed_row["staged_status"])

    def test_drilldown_respects_limit(self):
        rows, total = drilldown(
            "default", "collector", self.collector_a.id, self.start, self.end, limit=2
        )
        self.assertEqual(len(rows), 2)
        # `total` is the unpaginated count — stays 7 regardless of the limit.
        self.assertEqual(total, 7)

    def test_drilldown_respects_offset(self):
        # Non-overlapping pages: offset=2, limit=2 picks up exactly where
        # limit=2 offset=0 left off, most-recent-first.
        page_one, _ = drilldown(
            "default", "collector", self.collector_a.id, self.start, self.end, limit=2, offset=0
        )
        page_two, total = drilldown(
            "default", "collector", self.collector_a.id, self.start, self.end, limit=2, offset=2
        )
        self.assertEqual(len(page_one), 2)
        self.assertEqual(len(page_two), 2)
        self.assertFalse(set(r["raw_id"] for r in page_one) & set(r["raw_id"] for r in page_two))
        self.assertEqual(total, 7)

    def test_drilldown_inbound_uses_direct_source(self):
        rows, total = drilldown("default", "inbound", self.direct_source.id, self.start, self.end)
        self.assertEqual(len(rows), 1)
        self.assertEqual(total, 1)
        self.assertEqual(rows[0]["raw_title"], "D1")
        self.assertEqual(rows[0]["staged_status"], "duplicate")
        self.assertEqual(rows[0]["source_name"], self.direct_source.name)

    def test_drilldown_collector_absent_key_returns_all_collector_sources(self):
        # Ticket 40.5: an absent key now means "every source of this kind",
        # not "filter on source_id=None" (which used to silently match
        # nothing). Direct/inbound sources must not leak into this mode.
        rows, total = drilldown("default", "collector", None, self.start, self.end)
        source_names = {r["source_name"] for r in rows}
        self.assertIn("Collector A", source_names)
        self.assertIn("Collector B", source_names)
        self.assertNotIn(self.direct_source.name, source_names)
        # 7 from Collector A + 1 from Collector B, per setUp.
        self.assertEqual(total, 8)

    def test_drilldown_inbound_absent_key_returns_all_direct_sources(self):
        rows, total = drilldown("default", "inbound", None, self.start, self.end)
        source_names = {r["source_name"] for r in rows}
        self.assertEqual(source_names, {self.direct_source.name})
        self.assertEqual(total, 1)

    def test_drilldown_runs_absent_key_returns_empty_not_a_fan_out(self):
        # Run history is inherently per-source — no "all sources" mode here.
        rows, total = drilldown("default", "runs", None, self.start, self.end)
        self.assertEqual(rows, [])
        self.assertEqual(total, 0)

    def test_drilldown_outbound_all_sites(self):
        rows, total = drilldown("default", "outbound", None, self.start, self.end)
        self.assertEqual(len(rows), 1)
        self.assertEqual(total, 1)
        row = rows[0]
        self.assertEqual(row["submission_id"], str(self.submission.id))
        self.assertEqual(row["title"], "Broadcast Event")
        self.assertEqual(row["status"], "done")
        site_keys = {t["site_key"] for t in row["targets"]}
        self.assertEqual(site_keys, {"site-one", "site-two"})

    def test_drilldown_outbound_filters_by_site_key(self):
        rows, total = drilldown("default", "outbound", "site-one", self.start, self.end)
        self.assertEqual(len(rows), 1)
        self.assertEqual(total, 1)

        rows, total = drilldown("default", "outbound", "nonexistent-site", self.start, self.end)
        self.assertEqual(rows, [])
        self.assertEqual(total, 0)

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
                ([], 0),
            )
            self.assertEqual(
                drilldown("prod_readonly", "runs", self.collector_a.id, self.start, self.end),
                ([], 0),
            )

    def test_drilldown_runs_returns_most_recent_first_unwindowed(self):
        """Run history ignores the start/end funnel window entirely — it's
        "what has this source been doing", not scoped to the current window.
        """
        old_run = SourceRun.objects.create(
            source=self.collector_a,
            started_at=self.now - timedelta(days=60),
            finished_at=self.now - timedelta(days=60),
            status="ok",
            trigger="scheduled",
            items_fetched=2,
            items_new=2,
        )
        recent_run = SourceRun.objects.create(
            source=self.collector_a,
            started_at=self.now - timedelta(minutes=5),
            finished_at=self.now - timedelta(minutes=5),
            status="failed",
            trigger="manual",
            error_message="kaboom",
        )
        # Narrow window that would exclude both runs' created_at-equivalent
        # if the runs helper (wrongly) windowed on started_at.
        narrow_start = self.now - timedelta(minutes=1)
        narrow_end = self.now + timedelta(minutes=1)
        rows, total = drilldown("default", "runs", self.collector_a.id, narrow_start, narrow_end)
        self.assertEqual(len(rows), 2)
        self.assertEqual(total, 2)
        self.assertEqual(rows[0]["status"], "failed")
        self.assertEqual(rows[0]["error_message"], "kaboom")
        self.assertEqual(rows[1]["status"], "ok")
        self.assertIsNotNone(old_run.id)
        self.assertIsNotNone(recent_run.id)

    def test_drilldown_runs_respects_limit(self):
        for i in range(3):
            SourceRun.objects.create(
                source=self.collector_a,
                started_at=self.now - timedelta(hours=i),
                finished_at=self.now - timedelta(hours=i),
                status="ok",
            )
        rows, total = drilldown(
            "default", "runs", self.collector_a.id, self.start, self.end, limit=2
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual(total, 3)

    def test_drilldown_runs_respects_offset(self):
        for i in range(3):
            SourceRun.objects.create(
                source=self.collector_a,
                started_at=self.now - timedelta(hours=i),
                finished_at=self.now - timedelta(hours=i),
                status="ok",
            )
        page_one, _ = drilldown(
            "default", "runs", self.collector_a.id, self.start, self.end, limit=2, offset=0
        )
        page_two, total = drilldown(
            "default", "runs", self.collector_a.id, self.start, self.end, limit=2, offset=2
        )
        self.assertEqual(len(page_one), 2)
        self.assertEqual(len(page_two), 1)
        self.assertEqual(total, 3)

    def test_drilldown_runs_unknown_source_returns_empty(self):
        rows, total = drilldown("default", "runs", 999999, self.start, self.end)
        self.assertEqual(rows, [])
        self.assertEqual(total, 0)

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

    def test_direct_source_reports_push_not_inactive(self):
        # Ticket 40.2: the direct source is created `active=False` by
        # `ingestion/views.py:76-80` (pushed to, never polled) — wired through
        # `_source_rows`, it must report "push", not "inactive".
        EventSource.objects.create(
            name="Direct Host Submission",
            source_type="direct",
            url="",
            active=False,
            last_polled=None,
        )
        rows = broadcast_inbound_summary("default", self.start, self.end)
        row = next(r for r in rows if r["name"] == "Direct Host Submission")
        self.assertEqual(row["health"]["level"], "push")
        self.assertIn("direct/push source — not polled", row["health"]["reasons"])

    def test_never_polled_active_source_is_unknown_not_error(self):
        # `created_at` is auto_now_add, so this source is seconds old — inside
        # its first-poll grace period, and therefore `unknown`, not `error`.
        EventSource.objects.create(
            name="New Source",
            source_type="ics",
            url="https://new.example.com/feed.ics",
            active=True,
            last_polled=None,
        )
        rows = collector_summary("default", self.start, self.end)
        row = next(r for r in rows if r["name"] == "New Source")
        self.assertEqual(row["health"]["level"], "unknown")
        self.assertTrue(any("never polled" in r for r in row["health"]["reasons"]))

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
            status="published",
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
        self.assertIn("polling but zero new raw events in window", row["health"]["reasons"])

    def test_zero_published_in_window_but_live_all_time_downgrades_warn(self):
        # Ticket 36.6: a source published entirely before suite 34 (e.g.
        # Carrboro, The Plant NC) has zero *surviving* StagedEvent anchors
        # windowed on raw_event__created_at, forever — but its events are
        # still live on the site. That must not warn.
        source = EventSource.objects.create(
            name="Carrboro Commons",
            source_type="ics",
            url="https://carrboro.example.com/feed.ics",
            active=True,
            poll_interval_hours=1,
            last_polled=self.now - timedelta(minutes=5),
        )
        RawEvent.objects.create(
            source=source,
            raw_title="Raw With No Surviving Anchor",
            raw_start=self.now,
            processed=True,
            source_uid="carrboro-1",
        )
        # The live Event that proves this source has genuinely worked before,
        # attributed purely by source_name (Event has no source FK).
        make_event(title="Old Carrboro Event", source_name="Carrboro Commons")

        rows = collector_summary("default", self.start, self.end)
        row = next(r for r in rows if r["name"] == "Carrboro Commons")
        self.assertEqual(row["funnel"]["published"], 0)
        self.assertEqual(row["published_all_time"], 1)
        self.assertNotEqual(row["health"]["level"], "warn")
        self.assertFalse(
            any("none published in window" in reason for reason in row["health"]["reasons"])
        )
        self.assertEqual(row["published_note"], "0 in window; 1 events live all-time")

    def test_zero_published_and_zero_ever_still_warns(self):
        # Regression: a source with raw in-window and genuinely zero live
        # events ever must still warn — the downgrade is scoped to sources
        # with a real all-time publish history, not a blanket suppression.
        source = EventSource.objects.create(
            name="Never Published Source",
            source_type="ics",
            url="https://never.example.com/feed.ics",
            active=True,
            poll_interval_hours=1,
            last_polled=self.now - timedelta(minutes=5),
        )
        RawEvent.objects.create(
            source=source,
            raw_title="Raw With Nothing Downstream",
            raw_start=self.now,
            processed=True,
            source_uid="never-1",
        )

        rows = collector_summary("default", self.start, self.end)
        row = next(r for r in rows if r["name"] == "Never Published Source")
        self.assertEqual(row["funnel"]["published"], 0)
        self.assertEqual(row["published_all_time"], 0)
        self.assertEqual(row["health"]["level"], "warn")
        self.assertIn("raw events arriving but none published in window", row["health"]["reasons"])
        self.assertIsNone(row["published_note"])

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
        # staged-by-status, funnel-staged) + 1 for the un-windowed all-time
        # raw/latest-created_at query (35.4) + 1 for the un-windowed all-time
        # published-Event-by-source_name query (36.6) + 1 for the single
        # recent-runs fetch + 1 for the `resolve_source_runs_state()` probe
        # that gates it = 9 total.
        #
        # The invariant under test is unchanged: still *independent of source
        # count*, still no N+1. The availability probe is a fixed O(1) cost
        # paid once per collector_summary() call, not once per source — it's
        # what lets the monitor degrade instead of 500 when prod lacks
        # `ingestion_sourcerun` (see monitoring.resolve_source_runs_state).
        # Both all-time queries are the same shape: one grouped query over
        # every source in the call regardless of source count, not one per source.
        with self.assertNumQueries(9):
            collector_summary("default", self.start, self.end)

    def test_direct_published_all_time_query_is_one_query_regardless_of_source_count(self):
        # Ticket 40.1: the prefix-or-literal count backing a direct source's
        # `published_all_time` must be one additional query for the whole
        # call, not one per direct source.
        for i in range(3):
            EventSource.objects.create(
                name=f"Direct Extra {i}",
                source_type="direct",
                url="",
                active=False,
                poll_interval_hours=24,
            )

        # Same 9 queries as `test_raw_events_recent_runs_fetched_in_single_query`
        # (that test's breakdown doesn't depend on source_type) + 1 for the
        # direct published_all_time count (40.1), gated on there being any
        # direct sources in this call at all — still independent of how many.
        with self.assertNumQueries(10):
            broadcast_inbound_summary("default", self.start, self.end)

    def test_passing_runs_state_skips_the_availability_probe(self):
        # A page render resolves availability once and threads it into both
        # summaries; the second caller must not pay the round trip again. On
        # the prod path that probe is a WAN hop to Neon.
        #
        # Needs at least one source: `_source_rows` returns early on an empty
        # source list, which would make this pass for the wrong reason.
        source = EventSource.objects.create(
            name="Threaded State Source",
            source_type="ics",
            url="https://threaded.example.com/feed.ics",
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

        # The same 9 queries as the test above, minus the availability probe.
        with self.assertNumQueries(8):
            collector_summary("default", self.start, self.end, runs_state=RUNS_AVAILABLE)


@tag("db")
class RawZeroDisambiguationTests(TestCase):
    """35.4: `raw == 0` in the funnel window must distinguish "zero in this
    window" (real rows exist, just older than the window) from "zero ever"
    (this source has never produced a single RawEvent) — the real-prod
    scenario that motivated this ticket: Carrboro Public Events had 63
    all-time rows invisible at the default 30d window, while Visit Pittsboro
    and The Plant NC had genuinely never ingested anything.
    """

    def setUp(self):
        self.now = timezone.now()
        self.start = self.now - timedelta(days=30)
        self.end = self.now + timedelta(days=1)

    def test_zero_in_window_with_all_time_rows_reports_newest_and_count(self):
        source = EventSource.objects.create(
            name="Carrboro Public Events",
            source_type="ics",
            url="https://carrboro.example.com/feed.ics",
            active=True,
        )
        newest = self.now - timedelta(days=75)
        RawEvent.objects.create(
            source=source, raw_title="Old 1", raw_start=newest, source_uid="old1"
        )
        RawEvent.objects.filter(source=source, source_uid="old1").update(created_at=newest)
        older = newest - timedelta(days=5)
        RawEvent.objects.create(
            source=source, raw_title="Old 2", raw_start=older, source_uid="old2"
        )
        RawEvent.objects.filter(source=source, source_uid="old2").update(created_at=older)

        rows = collector_summary("default", self.start, self.end)
        row = next(r for r in rows if r["name"] == "Carrboro Public Events")
        self.assertEqual(row["funnel"]["raw"], 0)
        self.assertEqual(row["raw_all_time"], 2)
        self.assertEqual(row["latest_raw_created_at"], newest.isoformat())
        self.assertIn("2 all-time", row["raw_zero_note"])
        self.assertIn("widen the window", row["raw_zero_note"])
        self.assertNotIn("never produced", row["raw_zero_note"])

    def test_zero_in_window_and_zero_ever_reports_never_produced(self):
        EventSource.objects.create(
            name="Visit Pittsboro",
            source_type="ics",
            url="https://pittsboro.example.com/feed.ics",
            active=True,
        )
        rows = collector_summary("default", self.start, self.end)
        row = next(r for r in rows if r["name"] == "Visit Pittsboro")
        self.assertEqual(row["funnel"]["raw"], 0)
        self.assertEqual(row["raw_all_time"], 0)
        self.assertIsNone(row["latest_raw_created_at"])
        self.assertEqual(row["raw_zero_note"], "never produced a raw event")

    def test_raw_zero_note_is_none_when_window_has_rows(self):
        source = EventSource.objects.create(
            name="Healthy Source",
            source_type="ics",
            url="https://healthy.example.com/feed.ics",
            active=True,
        )
        RawEvent.objects.create(
            source=source, raw_title="Fresh", raw_start=self.now, source_uid="fresh1"
        )
        rows = collector_summary("default", self.start, self.end)
        row = next(r for r in rows if r["name"] == "Healthy Source")
        self.assertEqual(row["funnel"]["raw"], 1)
        self.assertIsNone(row["raw_zero_note"])

    def test_windowed_raw_count_is_unaffected_by_all_time_query(self):
        # 35.4 only adds signal — the existing windowed funnel values (already
        # verified correct against prod) must not change.
        source = EventSource.objects.create(
            name="Mixed History Source",
            source_type="ics",
            url="https://mixed.example.com/feed.ics",
            active=True,
        )
        RawEvent.objects.create(
            source=source, raw_title="In window", raw_start=self.now, source_uid="new1"
        )
        old = self.now - timedelta(days=90)
        RawEvent.objects.create(
            source=source, raw_title="Out of window", raw_start=old, source_uid="old1"
        )
        RawEvent.objects.filter(source=source, source_uid="old1").update(created_at=old)

        rows = collector_summary("default", self.start, self.end)
        row = next(r for r in rows if r["name"] == "Mixed History Source")
        self.assertEqual(row["funnel"]["raw"], 1)
        self.assertEqual(row["raw_count"], 1)
        self.assertEqual(row["raw_all_time"], 2)
        self.assertIsNone(row["raw_zero_note"])


@tag("db")
class SourceRowSortOrderTests(TestCase):
    """`_source_rows` sorts by health severity (error, warn, unknown, ok,
    inactive) then by name — this replaced the plain `order_by("name")` the
    monitor UI used to render in.
    """

    def setUp(self):
        self.now = timezone.now()
        self.start = self.now - timedelta(days=1)
        self.end = self.now + timedelta(days=1)

        # Named so alphabetical order would otherwise put them
        # ok < warn < error, the opposite of the expected health-rank order.
        EventSource.objects.create(
            name="A Ok Source",
            source_type="ics",
            url="https://a-ok.example.com/feed.ics",
            active=True,
            poll_interval_hours=1,
            last_polled=self.now - timedelta(minutes=5),
        )
        SourceRun.objects.create(
            source=EventSource.objects.get(name="A Ok Source"),
            started_at=self.now - timedelta(minutes=5),
            finished_at=self.now - timedelta(minutes=5),
            status="ok",
        )
        ok_raw = RawEvent.objects.create(
            source=EventSource.objects.get(name="A Ok Source"),
            raw_title="raw",
            raw_start=self.now,
            processed=True,
            source_uid="ok1",
        )
        # Staged + published so this source clears both warn rules (zero raw,
        # and raw-with-nothing-published) and lands squarely at "ok".
        published_event = make_event(title="Published via A Ok Source")
        StagedEvent.objects.create(
            raw_event=ok_raw,
            title="raw",
            description="d",
            location_name="l",
            town="carrboro",
            start_datetime=self.now,
            status="published",
            published_event=published_event,
        )

        # Polled, then stopped — evidenced failure, which is what `error` is
        # for. (A never-polled source is `unknown`/`warn`, not `error`; see
        # "D Unknown Source" below.)
        EventSource.objects.create(
            name="B Error Source",
            source_type="ics",
            url="https://b-error.example.com/feed.ics",
            active=True,
            poll_interval_hours=1,
            last_polled=self.now - timedelta(hours=10),
        )

        EventSource.objects.create(
            name="C Inactive Source",
            source_type="ics",
            url="https://c-inactive.example.com/feed.ics",
            active=False,
            last_polled=None,
        )

        # Never polled and seconds old (created_at is auto_now_add) -> inside
        # its first-poll grace period -> `unknown`.
        EventSource.objects.create(
            name="D Unknown Source",
            source_type="ics",
            url="https://d-unknown.example.com/feed.ics",
            active=True,
            last_polled=None,
        )

        EventSource.objects.create(
            name="Z Warn Source",
            source_type="ics",
            url="https://z-warn.example.com/feed.ics",
            active=True,
            poll_interval_hours=1,
            last_polled=self.now - timedelta(minutes=5),
        )
        SourceRun.objects.create(
            source=EventSource.objects.get(name="Z Warn Source"),
            started_at=self.now - timedelta(minutes=5),
            finished_at=self.now - timedelta(minutes=5),
            status="ok",
        )
        # No raw events in window -> "warn" (zero new raw events).

    def test_rows_sorted_by_health_severity_then_name(self):
        rows = collector_summary("default", self.start, self.end)
        levels = [r["health"]["level"] for r in rows]
        self.assertEqual(levels, ["error", "warn", "unknown", "ok", "inactive"])
        names = [r["name"] for r in rows]
        self.assertEqual(
            names,
            [
                "B Error Source",
                "Z Warn Source",
                "D Unknown Source",
                "A Ok Source",
                "C Inactive Source",
            ],
        )


@tag("db")
class SourceRunsUnavailableTests(TestCase):
    """Degradation when `ingestion_sourcerun` isn't readable on the target DB.

    `prod_readonly` tracks whatever prod has actually deployed, which can lag
    local by a migration — prod sat on 0013 while local was on 0014, and
    querying SourceRun there took the entire monitor down with a
    ProgrammingError.

    There are three distinct causes, and they are simulated by raising what
    Postgres would actually raise rather than by hiding the table from
    introspection. Introspection cannot distinguish them at all: Django's
    PostgreSQL backend lists tables from `pg_catalog.pg_class`, which has no
    privilege predicate, so a table the role cannot SELECT is still reported as
    present. That is precisely the gap that made the missing-GRANT case a
    latent 500 — dropping the real table isn't an option either, since the rest
    of the suite needs it.
    """

    def setUp(self):
        self.source = EventSource.objects.create(
            name="Unmigrated Source",
            source_type="ics",
            url="https://example.com/a.ics",
            active=True,
            last_polled=timezone.now(),
        )
        SourceRun.objects.create(
            source=self.source,
            started_at=timezone.now() - timedelta(minutes=5),
            finished_at=timezone.now(),
            status="failed",
            error_message="should never be read",
        )
        self.end = timezone.now() + timedelta(minutes=1)
        self.start = self.end - timedelta(days=7)

    def _raise_on_sourcerun(self, exc):
        """Patch the SourceRun query to raise `exc`, as Postgres would.

        Only `SourceRun.objects.using(...)` is patched, so every other query in
        the page still runs for real — the point is that the *rest* of the
        monitor keeps working while run history degrades.
        """
        from unittest.mock import patch

        return patch.object(SourceRun.objects, "using", side_effect=exc, autospec=True)

    @staticmethod
    def _pg_error(django_exc, sqlstate):
        """A Django DB error wrapping a driver error carrying `sqlstate`.

        Mirrors how psycopg 3 surfaces it: Django re-raises its own exception
        type `from` the driver error, so the SQLSTATE lives on `__cause__`.
        """

        class _DriverError(Exception):
            pass

        cause = _DriverError("simulated")
        cause.sqlstate = sqlstate
        exc = django_exc("simulated")
        exc.__cause__ = cause
        return exc

    def test_state_is_not_configured_for_unknown_alias(self):
        self.assertEqual(resolve_source_runs_state("definitely_not_a_db"), RUNS_DB_NOT_CONFIGURED)

    def test_state_is_available_when_table_is_readable(self):
        self.assertEqual(resolve_source_runs_state("default"), RUNS_AVAILABLE)

    def test_missing_table_sqlstate_maps_to_missing_table(self):
        exc = self._pg_error(ProgrammingError, "42P01")
        with self._raise_on_sourcerun(exc):
            self.assertEqual(resolve_source_runs_state("default"), RUNS_MISSING_TABLE)

    def test_missing_grant_sqlstate_maps_to_no_permission(self):
        # The case introspection could never see: the table exists and is
        # listed in pg_class, but the role has no SELECT on it. Against
        # pre-33.1 code this path reported the table as *readable* and the
        # ProgrammingError propagated as a 500.
        exc = self._pg_error(ProgrammingError, "42501")
        with self._raise_on_sourcerun(exc):
            self.assertEqual(resolve_source_runs_state("default"), RUNS_NO_PERMISSION)

    def test_unreachable_database_maps_to_unreachable(self):
        with self._raise_on_sourcerun(OperationalError("connection refused")):
            self.assertEqual(resolve_source_runs_state("default"), RUNS_UNREACHABLE)

    def test_unrecognised_sqlstate_is_not_swallowed(self):
        # A ProgrammingError we can't attribute to a deployment difference is a
        # bug in our own SQL; masking it behind a banner naming a cause we
        # haven't detected would be worse than the traceback.
        exc = self._pg_error(ProgrammingError, "42703")  # undefined_column
        with self._raise_on_sourcerun(exc), self.assertRaises(ProgrammingError):
            resolve_source_runs_state("default")

    def test_collector_summary_does_not_raise_without_the_table(self):
        rows = collector_summary("default", self.start, self.end, runs_state=RUNS_MISSING_TABLE)
        self.assertEqual(len(rows), 1)
        # The run exists, but isn't read — so the row reports no run history
        # rather than surfacing the `failed` status.
        self.assertIsNone(rows[0]["last_run"])

    def test_collector_summary_does_not_raise_without_the_grant(self):
        rows = collector_summary("default", self.start, self.end, runs_state=RUNS_NO_PERMISSION)
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0]["last_run"])

    def test_health_falls_back_to_staleness_rules_without_the_table(self):
        rows = collector_summary("default", self.start, self.end, runs_state=RUNS_MISSING_TABLE)
        health = rows[0]["health"]
        # The seeded run is `failed`, which would normally force `error` with a
        # "latest run failed" reason. With runs unread, the only signal left is
        # the zero-raw-events warn rule.
        self.assertEqual(health["level"], "warn")
        self.assertFalse(any("latest run" in r for r in health["reasons"]))

    def test_drilldown_runs_returns_empty_without_the_table(self):
        self.assertEqual(
            drilldown(
                "default",
                "runs",
                self.source.id,
                self.start,
                self.end,
                runs_state=RUNS_MISSING_TABLE,
            ),
            ([], 0),
        )

    def test_drilldown_runs_returns_empty_without_the_grant(self):
        self.assertEqual(
            drilldown(
                "default",
                "runs",
                self.source.id,
                self.start,
                self.end,
                runs_state=RUNS_NO_PERMISSION,
            ),
            ([], 0),
        )
