import os
from datetime import UTC, datetime, timedelta
from unittest import mock

from django.test import SimpleTestCase, tag

from devtools.monitoring import (
    _CONSECUTIVE_FAILURE_THRESHOLD,
    _HEALTH_RANK,
    _STALE_POLL_MULTIPLIER,
    source_health,
    summarize_sources,
)

NOW = datetime(2026, 7, 26, 12, 0, 0, tzinfo=UTC)


def make_row(
    *,
    active=True,
    source_type="ics",
    poll_interval_hours=24,
    last_polled_dt=NOW,
    created_at=NOW,
    raw_count=1,
    published=1,
):
    return {
        "active": active,
        "source_type": source_type,
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
    """source_health is pure: plain dicts in, no DB, no I/O.

    None of these fixtures are testing shard-aware staleness (see
    `ShardAwareStalenessTests` below for that) — they're asserting the
    unsharded thresholds documented on each test, so `INGEST_SHARD_COUNT` is
    pinned to unset here rather than left at whatever `.env` happens to have
    (this repo's `.env` sets `INGEST_SHARD_COUNT=3` for prod parity, which
    would otherwise silently widen every stale_after_hours in this class).
    """

    def setUp(self):
        env_without_shard = {k: v for k, v in os.environ.items() if k != "INGEST_SHARD_COUNT"}
        patcher = mock.patch.dict(os.environ, env_without_shard, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_inactive_source_is_never_error(self):
        row = make_row(active=False, last_polled_dt=None, raw_count=0, published=0)
        runs = [make_run("failed", "boom"), make_run("failed", "boom")]
        result = source_health(row, runs, NOW)
        self.assertEqual(result["level"], "inactive")
        self.assertEqual(result["reasons"], [])

    def test_direct_source_is_push_not_inactive(self):
        # 40.2: direct/inbound sources are deliberately active=False (pushed
        # to, never polled) — that must render as the distinct "push" level,
        # not "inactive", which reads as "broken".
        row = make_row(source_type="direct", active=False, last_polled_dt=None, raw_count=0)
        result = source_health(row, [], NOW)
        self.assertEqual(result["level"], "push")
        self.assertIn("direct/push source — not polled", result["reasons"])

    def test_direct_source_is_push_even_when_active_true(self):
        # The direct source is always created active=False in practice
        # (ingestion/views.py), but the check is on source_type, not active —
        # verify it doesn't accidentally depend on active being False.
        row = make_row(source_type="direct", active=True)
        result = source_health(row, [], NOW)
        self.assertEqual(result["level"], "push")

    def test_direct_source_push_outranks_run_failures(self):
        # The push check short-circuits before any other rule runs — a direct
        # source's run/staleness history (it has none, since it's never
        # polled) must never surface as error/warn.
        row = make_row(source_type="direct", active=False, last_polled_dt=None, raw_count=0)
        runs = [make_run("failed", "boom"), make_run("failed", "boom")]
        result = source_health(row, runs, NOW)
        self.assertEqual(result["level"], "push")

    def test_collector_source_with_active_false_stays_inactive(self):
        # Non-direct sources are unaffected by the push check — a collector
        # source with active=False is still "inactive", not "push".
        row = make_row(source_type="ics", active=False, last_polled_dt=None, raw_count=0)
        result = source_health(row, [], NOW)
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

    def test_health_rank_has_an_entry_for_every_level_source_health_returns(self):
        # `_HEALTH_RANK` is read by `_worse()` and by the results sort in
        # `_source_rows` — a level missing from it is a KeyError that takes
        # the whole page down (this is exactly how `push` was almost added:
        # ticket 40.2). `push` is ranked alongside `inactive`, at the end.
        for level in ("error", "warn", "quarantined", "unknown", "ok", "inactive", "push"):
            self.assertIn(level, _HEALTH_RANK)
        self.assertEqual(_HEALTH_RANK["push"], _HEALTH_RANK["inactive"])


@tag("fast")
class QuarantineHealthTests(SimpleTestCase):
    """45.7: `blocked_reason` downgrades an otherwise-"error" result to the
    distinct "quarantined" level, so a known-blocked source's expected
    nightly failure doesn't compete with real regressions for attention or
    inflate the monitor's `error` tile.
    """

    def setUp(self):
        env_without_shard = {k: v for k, v in os.environ.items() if k != "INGEST_SHARD_COUNT"}
        patcher = mock.patch.dict(os.environ, env_without_shard, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_refused_run_on_a_quarantined_source_is_quarantined_not_error(self):
        row = make_row()
        row["blocked_reason"] = "vendor WAF blocks prod egress IP"
        row["blocked_since"] = "2026-07-15"
        runs = [make_run("refused", "empty_fetch"), make_run("refused", "empty_fetch")]
        result = source_health(row, runs, NOW)
        self.assertEqual(result["level"], "quarantined")
        self.assertTrue(any("known-blocked" in r for r in result["reasons"]))
        self.assertTrue(any("vendor WAF blocks prod egress IP" in r for r in result["reasons"]))
        # The underlying run-based reason is still recorded, not replaced —
        # an operator inspecting the row can see both "why quarantined" and
        # "what actually happened last night".
        self.assertTrue(any("empty_fetch" in r for r in result["reasons"]))

    def test_same_failures_without_blocked_reason_are_plain_error(self):
        # Control: identical run history, no `blocked_reason` set -> the
        # ordinary "error" path, unaffected by the quarantine check.
        row = make_row()
        runs = [make_run("refused", "empty_fetch"), make_run("refused", "empty_fetch")]
        result = source_health(row, runs, NOW)
        self.assertEqual(result["level"], "error")

    def test_quarantined_source_that_recovers_reports_ok_not_masked(self):
        # The whole point of quarantine: once the source starts succeeding
        # again, that must be visible as "ok", not hidden behind a permanent
        # "quarantined" badge. This is the refused -> ok signal that tells an
        # operator the egress fix landed.
        row = make_row()
        row["blocked_reason"] = "vendor WAF blocks prod egress IP"
        result = source_health(row, [make_run("ok")], NOW)
        self.assertEqual(result["level"], "ok")

    def test_quarantine_does_not_downgrade_a_warn_level_result(self):
        # Quarantine only intercepts an "error" result. A quarantined source
        # that is merely "warn" (e.g. zero raw events, no run-based failure)
        # is left as "warn", not further muted to "quarantined".
        row = make_row(raw_count=0, published=0)
        row["blocked_reason"] = "vendor WAF blocks prod egress IP"
        result = source_health(row, [make_run("ok")], NOW)
        self.assertEqual(result["level"], "warn")

    def test_quarantine_without_blocked_since_still_downgrades(self):
        # blocked_since is informational only -- an absent value must not
        # prevent the downgrade.
        row = make_row()
        row["blocked_reason"] = "vendor WAF blocks prod egress IP"
        runs = [make_run("refused", "empty_fetch"), make_run("refused", "empty_fetch")]
        result = source_health(row, runs, NOW)
        self.assertEqual(result["level"], "quarantined")

    def test_blank_blocked_reason_does_not_quarantine(self):
        # The model default (`blank=True, default=""`) must not accidentally
        # quarantine every source.
        row = make_row()
        row["blocked_reason"] = ""
        runs = [make_run("refused", "empty_fetch"), make_run("refused", "empty_fetch")]
        result = source_health(row, runs, NOW)
        self.assertEqual(result["level"], "error")

    def test_inactive_quarantined_source_stays_inactive(self):
        # The `active` gate is checked before any run-based evaluation, so a
        # quarantined-but-inactive source still reports "inactive" — the
        # quarantine downgrade never fires because level never reaches
        # "error" in the first place.
        row = make_row(active=False, last_polled_dt=None, raw_count=0, published=0)
        row["blocked_reason"] = "vendor WAF blocks prod egress IP"
        result = source_health(row, [make_run("failed", "boom")], NOW)
        self.assertEqual(result["level"], "inactive")


@tag("fast")
class ShardAwareStalenessTests(SimpleTestCase):
    """35.3: staleness must account for `INGEST_SHARD_COUNT`.

    Prod runs `INGEST_SHARD_COUNT=3` — day-of-year sharding means a source is
    only eligible to poll on one day in three, so its real cadence is
    `poll_interval_hours * 3`, not `poll_interval_hours` alone. Judging a real
    72h cadence against the unsharded 48h threshold (`24h * _STALE_POLL_MULTIPLIER`)
    made a perfectly healthy prod source render a permanent `error` badge.
    """

    def _with_shard(self, value):
        if value is None:
            env = {k: v for k, v in os.environ.items() if k != "INGEST_SHARD_COUNT"}
            return mock.patch.dict(os.environ, env, clear=True)
        return mock.patch.dict(os.environ, {"INGEST_SHARD_COUNT": value})

    def test_60h_since_poll_with_shard_3_is_not_error(self):
        # 24h poll_interval * shard 3 * _STALE_POLL_MULTIPLIER(2) = 144h grace
        # — 60h is well inside it.
        row = make_row(poll_interval_hours=24, last_polled_dt=NOW - timedelta(hours=60))
        with self._with_shard("3"):
            result = source_health(row, [make_run("ok")], NOW)
        self.assertNotEqual(result["level"], "error")

    def test_60h_since_poll_with_shard_1_is_error(self):
        # Same source, sharding disabled: 24h * 1 * 2 = 48h grace, 60h exceeds it.
        row = make_row(poll_interval_hours=24, last_polled_dt=NOW - timedelta(hours=60))
        with self._with_shard("1"):
            result = source_health(row, [make_run("ok")], NOW)
        self.assertEqual(result["level"], "error")

    def test_60h_since_poll_with_shard_unset_is_error(self):
        # Unset must behave identically to shard 1 (sharding disabled),
        # mirroring `ingestion.tasks._resolve_env_shard`.
        row = make_row(poll_interval_hours=24, last_polled_dt=NOW - timedelta(hours=60))
        with self._with_shard(None):
            result = source_health(row, [make_run("ok")], NOW)
        self.assertEqual(result["level"], "error")

    def test_unparseable_shard_count_falls_back_to_unsharded(self):
        row = make_row(poll_interval_hours=24, last_polled_dt=NOW - timedelta(hours=60))
        with self._with_shard("not-a-number"):
            result = source_health(row, [make_run("ok")], NOW)
        self.assertEqual(result["level"], "error")

    def test_assumed_shard_count_is_visible_in_reasons(self):
        row = make_row(
            poll_interval_hours=24,
            last_polled_dt=NOW - timedelta(hours=200),
        )
        with self._with_shard("3"):
            result = source_health(row, [make_run("ok")], NOW)
        self.assertEqual(result["level"], "error")
        self.assertTrue(any("shard count 3" in r for r in result["reasons"]))


def make_source_row(
    *,
    funnel=None,
    health_level="ok",
    last_polled=None,
    latest_raw_created_at=None,
):
    """A `_source_rows`-shaped row, trimmed to the fields `summarize_sources`
    actually reads."""
    base_funnel = {"raw": 0, "published": 0, "held_for_review": 0, "duplicate": 0, "no_town": 0}
    if funnel:
        base_funnel.update(funnel)
    return {
        "funnel": base_funnel,
        "health": {"level": health_level, "reasons": []},
        "last_polled": last_polled,
        "latest_raw_created_at": latest_raw_created_at,
    }


@tag("fast")
class SummarizeSourcesTests(SimpleTestCase):
    """summarize_sources is pure: it reduces already-built collector/inbound
    rows into the monitor page's KPI tile numbers (ticket 40.6) — no DB, no
    I/O, no new queries.
    """

    def test_empty_rows_return_all_zero_and_no_freshness_signal(self):
        result = summarize_sources([], now=NOW)
        self.assertEqual(
            result["funnel"],
            {"raw": 0, "published": 0, "held_for_review": 0, "duplicate": 0, "no_town": 0},
        )
        self.assertEqual(
            result["health"],
            {
                "error": 0,
                "warn": 0,
                "quarantined": 0,
                "unknown": 0,
                "ok": 0,
                "inactive": 0,
                "push": 0,
            },
        )
        self.assertIsNone(result["freshness"]["newest_raw_created_at"])
        self.assertEqual(result["freshness"]["polled_last_24h"], 0)

    def test_funnel_totals_sum_across_rows(self):
        rows = [
            make_source_row(
                funnel={
                    "raw": 3,
                    "published": 1,
                    "held_for_review": 2,
                    "duplicate": 1,
                    "no_town": 0,
                }
            ),
            make_source_row(
                funnel={
                    "raw": 5,
                    "published": 0,
                    "held_for_review": 0,
                    "duplicate": 2,
                    "no_town": 1,
                }
            ),
        ]
        result = summarize_sources(rows, now=NOW)
        self.assertEqual(
            result["funnel"],
            {"raw": 8, "published": 1, "held_for_review": 2, "duplicate": 3, "no_town": 1},
        )

    def test_health_counts_one_row_per_level(self):
        rows = [
            make_source_row(health_level="error"),
            make_source_row(health_level="error"),
            make_source_row(health_level="warn"),
            make_source_row(health_level="quarantined"),
            make_source_row(health_level="ok"),
            make_source_row(health_level="push"),
        ]
        result = summarize_sources(rows, now=NOW)
        self.assertEqual(
            result["health"],
            {
                "error": 2,
                "warn": 1,
                "quarantined": 1,
                "unknown": 0,
                "ok": 1,
                "inactive": 0,
                "push": 1,
            },
        )

    def test_quarantined_sources_do_not_count_toward_the_error_bucket(self):
        # 45.7's headline requirement: a page full of quarantined sources
        # must not report overall pipeline health as degraded via the
        # `error` count -- only genuinely erroring sources land there.
        rows = [
            make_source_row(health_level="quarantined"),
            make_source_row(health_level="quarantined"),
            make_source_row(health_level="quarantined"),
            make_source_row(health_level="ok"),
        ]
        result = summarize_sources(rows, now=NOW)
        self.assertEqual(result["health"]["error"], 0)
        self.assertEqual(result["health"]["quarantined"], 3)

    def test_newest_raw_event_compares_real_datetimes_not_strings(self):
        # The whole point of parsing with fromisoformat instead of comparing
        # strings: these two ISO strings carry different UTC offsets, and
        # lexicographically the *earlier* one sorts larger ("23" > "19"),
        # which would silently pick the wrong "newest" under a naive max().
        earlier_utc_but_lexicographically_larger = "2026-07-26T23:00:00+05:00"  # 18:00 UTC
        later_utc_but_lexicographically_smaller = "2026-07-26T19:00:00+00:00"  # 19:00 UTC
        rows = [
            make_source_row(latest_raw_created_at=earlier_utc_but_lexicographically_larger),
            make_source_row(latest_raw_created_at=later_utc_but_lexicographically_smaller),
        ]
        result = summarize_sources(rows, now=NOW)
        self.assertEqual(
            result["freshness"]["newest_raw_created_at"], later_utc_but_lexicographically_smaller
        )

    def test_newest_raw_event_none_when_no_row_has_one(self):
        rows = [make_source_row(), make_source_row()]
        result = summarize_sources(rows, now=NOW)
        self.assertIsNone(result["freshness"]["newest_raw_created_at"])

    def test_polled_last_24h_counts_only_rows_within_the_window(self):
        rows = [
            make_source_row(last_polled=(NOW - timedelta(hours=1)).isoformat()),
            make_source_row(last_polled=(NOW - timedelta(hours=23, minutes=59)).isoformat()),
            make_source_row(last_polled=(NOW - timedelta(hours=25)).isoformat()),
            make_source_row(last_polled=None),
        ]
        result = summarize_sources(rows, now=NOW)
        self.assertEqual(result["freshness"]["polled_last_24h"], 2)

    def test_now_defaults_to_current_time_when_omitted(self):
        # No `now` kwarg — exercises the `timezone.now()` default path used
        # by the real `monitor()` view, which never passes `now` explicitly.
        result = summarize_sources([make_source_row(last_polled=None)])
        self.assertIn("funnel", result)
        self.assertIn("health", result)
        self.assertIn("freshness", result)
