from datetime import UTC, datetime, timedelta

from django.test import SimpleTestCase, tag

from devtools.monitoring import (
    _CONSECUTIVE_FAILURE_THRESHOLD,
    _STALE_POLL_MULTIPLIER,
    source_health,
)

NOW = datetime(2026, 7, 26, 12, 0, 0, tzinfo=UTC)


def make_row(
    *,
    active=True,
    poll_interval_hours=24,
    last_polled_dt=NOW,
    created_at=NOW,
    raw_count=1,
    published=1,
):
    return {
        "active": active,
        "poll_interval_hours": poll_interval_hours,
        "last_polled_dt": last_polled_dt,
        "created_at": created_at,
        "raw_count": raw_count,
        "funnel": {"published": published},
    }


def make_run(status, error_message=""):
    return {
        "status": status,
        "finished_at": NOW,
        "error_message": error_message,
    }


@tag("fast")
class SourceHealthTests(SimpleTestCase):
    """source_health is pure: plain dicts in, no DB, no I/O."""

    def test_inactive_source_is_never_error(self):
        row = make_row(active=False, last_polled_dt=None, raw_count=0, published=0)
        runs = [make_run("failed", "boom"), make_run("failed", "boom")]
        result = source_health(row, runs, NOW)
        self.assertEqual(result["level"], "inactive")
        self.assertEqual(result["reasons"], [])

    def test_healthy_active_source_is_ok(self):
        row = make_row()
        runs = [make_run("ok")]
        result = source_health(row, runs, NOW)
        self.assertEqual(result["level"], "ok")
        self.assertEqual(result["reasons"], [])

    def test_never_polled_inside_grace_is_unknown_not_error(self):
        # Absence of signal, not evidence of failure: a source created minutes
        # ago simply isn't due for its first poll yet.
        row = make_row(last_polled_dt=None, created_at=NOW - timedelta(minutes=5))
        result = source_health(row, [], NOW)
        self.assertEqual(result["level"], "unknown")
        self.assertTrue(any("not yet due for a first poll" in r for r in result["reasons"]))

    def test_never_polled_past_grace_is_warn_not_error(self):
        # Past `poll_interval_hours * _STALE_POLL_MULTIPLIER` from creation,
        # something should have polled it — worth surfacing, but still not the
        # evidenced failure that `error` is reserved for.
        grace_hours = 24 * _STALE_POLL_MULTIPLIER
        row = make_row(
            poll_interval_hours=24,
            last_polled_dt=None,
            created_at=NOW - timedelta(hours=grace_hours + 1),
        )
        result = source_health(row, [], NOW)
        self.assertEqual(result["level"], "warn")
        self.assertTrue(any("never polled since creation" in r for r in result["reasons"]))

    def test_never_polled_boundary_is_unknown(self):
        grace_hours = 24 * _STALE_POLL_MULTIPLIER
        row = make_row(
            poll_interval_hours=24,
            last_polled_dt=None,
            created_at=NOW - timedelta(hours=grace_hours),
        )
        self.assertEqual(source_health(row, [], NOW)["level"], "unknown")

    def test_never_polled_without_created_at_falls_back_to_warn(self):
        row = make_row(last_polled_dt=None, created_at=None)
        result = source_health(row, [], NOW)
        self.assertEqual(result["level"], "warn")
        self.assertIn("never polled", result["reasons"])

    def test_never_polled_does_not_also_claim_it_is_polling(self):
        # The zero-raw-events warn rule presupposes polling; without the
        # suppression the tooltip read "never polled; polling but zero new raw
        # events in window" — two contradictory claims in one hover.
        row = make_row(
            last_polled_dt=None,
            created_at=NOW - timedelta(minutes=5),
            raw_count=0,
            published=0,
        )
        reasons = source_health(row, [], NOW)["reasons"]
        self.assertTrue(any("never polled" in r for r in reasons))
        self.assertFalse(any("polling but" in r for r in reasons))

    def test_last_polled_within_threshold_is_not_stale(self):
        stale_hours = 24 * _STALE_POLL_MULTIPLIER
        row = make_row(
            poll_interval_hours=24,
            last_polled_dt=NOW - timedelta(hours=stale_hours - 1),
        )
        result = source_health(row, [make_run("ok")], NOW)
        self.assertEqual(result["level"], "ok")

    def test_last_polled_past_threshold_is_error(self):
        stale_hours = 24 * _STALE_POLL_MULTIPLIER
        row = make_row(
            poll_interval_hours=24,
            last_polled_dt=NOW - timedelta(hours=stale_hours + 1),
        )
        result = source_health(row, [make_run("ok")], NOW)
        self.assertEqual(result["level"], "error")
        self.assertTrue(any("last polled" in r for r in result["reasons"]))

    def test_latest_run_failed_is_error_with_message(self):
        row = make_row()
        runs = [make_run("failed", "HTTP 500 from feed")]
        result = source_health(row, runs, NOW)
        self.assertEqual(result["level"], "error")
        self.assertTrue(any("HTTP 500 from feed" in r for r in result["reasons"]))

    def test_latest_run_refused_is_error(self):
        row = make_row()
        runs = [make_run("refused", "robots.txt disallow")]
        result = source_health(row, runs, NOW)
        self.assertEqual(result["level"], "error")

    def test_missing_error_message_gets_placeholder(self):
        row = make_row()
        runs = [make_run("failed", "")]
        result = source_health(row, runs, NOW)
        self.assertEqual(result["level"], "error")
        self.assertTrue(any("no error message recorded" in r for r in result["reasons"]))

    def test_single_failure_then_ok_is_not_consecutive_error(self):
        # Most recent run is ok, so neither the "latest failed" rule nor the
        # consecutive-failure rule (which stops counting at the first `ok`)
        # should fire.
        row = make_row()
        runs = [make_run("ok"), make_run("failed", "transient")]
        result = source_health(row, runs, NOW)
        self.assertEqual(result["level"], "ok")

    def test_two_consecutive_failures_trip_threshold(self):
        self.assertEqual(_CONSECUTIVE_FAILURE_THRESHOLD, 2)
        row = make_row()
        runs = [make_run("failed", "second"), make_run("failed", "first")]
        result = source_health(row, runs, NOW)
        self.assertEqual(result["level"], "error")
        self.assertTrue(any("consecutive non-ok" in r for r in result["reasons"]))

    def test_skipped_runs_do_not_count_toward_consecutive_failures(self):
        # A source correctly throttled by poll_interval_hours emits `skipped`
        # runs. A single real failure followed by legitimate skips must not
        # be treated as 2 consecutive failures.
        row = make_row()
        runs = [make_run("skipped"), make_run("skipped"), make_run("failed", "one-off")]
        result = source_health(row, runs, NOW)
        # Latest non-skipped run is still "failed" -> that rule alone fires,
        # but the *consecutive* count is 1, not >= threshold.
        self.assertEqual(result["level"], "error")
        self.assertFalse(any("consecutive non-ok" in r for r in result["reasons"]))

    def test_skipped_runs_filtered_out_still_count_two_real_failures(self):
        # Two real failures with skipped runs interleaved should still trip
        # the consecutive-failure rule once skips are filtered out.
        row = make_row()
        runs = [
            make_run("failed", "latest"),
            make_run("skipped"),
            make_run("failed", "earlier"),
        ]
        result = source_health(row, runs, NOW)
        self.assertEqual(result["level"], "error")
        self.assertTrue(any("consecutive non-ok" in r for r in result["reasons"]))

    def test_all_skipped_runs_no_run_based_error(self):
        # A brand-new throttled source with only skipped runs and healthy
        # polling should not be flagged for run-based errors.
        row = make_row()
        runs = [make_run("skipped"), make_run("skipped")]
        result = source_health(row, runs, NOW)
        self.assertEqual(result["level"], "ok")

    def test_zero_raw_events_in_window_is_warn(self):
        row = make_row(raw_count=0, published=0)
        result = source_health(row, [make_run("ok")], NOW)
        self.assertEqual(result["level"], "warn")
        self.assertIn("polling but zero new raw events in window", result["reasons"])

    def test_raw_events_but_none_published_is_warn(self):
        row = make_row(raw_count=5, published=0)
        result = source_health(row, [make_run("ok")], NOW)
        self.assertEqual(result["level"], "warn")
        self.assertIn("raw events arriving but none published in window", result["reasons"])

    def test_raw_events_and_published_is_ok(self):
        row = make_row(raw_count=5, published=2)
        result = source_health(row, [make_run("ok")], NOW)
        self.assertEqual(result["level"], "ok")

    def test_error_outranks_warn_when_both_apply(self):
        # Stale polling (error) plus zero raw events (warn) -> error wins,
        # and both reasons are still collected.
        stale_hours = 24 * _STALE_POLL_MULTIPLIER
        row = make_row(
            last_polled_dt=NOW - timedelta(hours=stale_hours + 1),
            raw_count=0,
            published=0,
        )
        result = source_health(row, [make_run("ok")], NOW)
        self.assertEqual(result["level"], "error")
        self.assertTrue(any("last polled" in r for r in result["reasons"]))
        self.assertIn("polling but zero new raw events in window", result["reasons"])

    def test_no_recent_runs_and_never_polled_is_not_error(self):
        # No run history and no poll is the emptiest a row can be. It reports
        # `unknown` — nothing here is evidence of a failure.
        row = make_row(last_polled_dt=None, raw_count=0, published=0)
        result = source_health(row, [], NOW)
        self.assertEqual(result["level"], "unknown")
        self.assertTrue(any("never polled" in r for r in result["reasons"]))

    def test_run_failure_still_outranks_never_polled(self):
        # A never-polled source whose runs recorded a failure is evidenced
        # failure — `unknown` must not mask it.
        row = make_row(last_polled_dt=None, raw_count=0, published=0)
        result = source_health(row, [make_run("failed", "boom")], NOW)
        self.assertEqual(result["level"], "error")
