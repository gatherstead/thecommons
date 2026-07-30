"""Guards the beat-freshness logic in `manage.py healthcheck`.

Motivating bug (2026-07-21 -> 2026-07-29 scheduler outage): `scrape-sources-daily`
had no entry in DEFAULT_STALENESS_HOURS, so a task that had *never run* in its
entire life reported OK/WARN forever instead of failing the healthcheck. Two
fixes are pinned down here:

1. scrape-sources-daily has a staleness window, same as the other daily task.
2. A seeded task with NO configured window no longer silently passes at any
   age — it reports WARN with an explicit "add it" message, not OK.
3. Staleness for a *configured* task is now FAIL, not WARN, so a dead schedule
   trips deploy/healthcheck.sh's non-zero exit.

Ticket 36.3: freshness for a crontab-backed task is no longer judged against a
hand-tuned window (which always has a blind spot at least one period wide —
e.g. a missed Sunday digest wouldn't FAIL for ~8 days). Instead we derive the
*expected* next fire time from the task's own crontab
(`crontab.remaining_estimate`) and FAIL as soon as that time has passed.
DEFAULT_STALENESS_HOURS keeps its must-exist role (dict keys = tasks that must
be seeded) and now serves only as a fallback window for interval-backed or
schedule-less tasks, which have no crontab to derive an expected fire time
from.
"""

import unittest
from datetime import timedelta
from types import SimpleNamespace

from django.test import TestCase, override_settings, tag
from django.utils import timezone
from django_celery_beat.models import CrontabSchedule, PeriodicTask

from events.management.commands.healthcheck import (
    DEFAULT_STALENESS_HOURS,
    FAIL,
    OK,
    WARN,
    Command,
    crontab_grace_seconds,
)


def _fake_task(name: str, last_run_at, crontab=None):
    return SimpleNamespace(name=name, last_run_at=last_run_at, crontab=crontab)


def _fake_crontab(minute="0", hour="*", day_of_week="*", tz="UTC"):
    # An unsaved CrontabSchedule — .schedule is a pure property, so this never
    # touches the DB. Safe to use in the no-DB fast tier.
    return CrontabSchedule(
        minute=minute,
        hour=hour,
        day_of_week=day_of_week,
        day_of_month="*",
        month_of_year="*",
        timezone=tz,
    )


@tag("fast")
class TaskFreshnessUnitTests(unittest.TestCase):
    """Exercise _task_freshness directly against fake task objects — no DB."""

    def setUp(self):
        self.cmd = Command()
        self.now = timezone.now()

    def test_scrape_sources_daily_has_a_configured_window(self):
        # The exact defect: this key was missing entirely.
        self.assertIn("scrape-sources-daily", DEFAULT_STALENESS_HOURS)
        self.assertEqual(DEFAULT_STALENESS_HOURS["scrape-sources-daily"], 25)

    def test_broadcast_orphan_recovery_still_in_must_exist_set(self):
        # DEFAULT_STALENESS_HOURS now only needs to carry this key for the
        # must-exist guard (see _check_periodic_tasks) — crontab-backed
        # freshness no longer reads the associated hour value at all.
        self.assertIn("broadcast-orphan-recovery", DEFAULT_STALENESS_HOURS)

    def test_configured_task_never_run_fails(self):
        task = _fake_task("scrape-sources-daily", None)
        status, _, detail = self.cmd._task_freshness(task, "beat:scrape-sources-daily", self.now)
        self.assertEqual(status, FAIL)
        self.assertIn("never run", detail)

    def test_unlisted_task_does_not_silently_pass(self):
        # A task with no entry in DEFAULT_STALENESS_HOURS at all, and no
        # crontab — e.g. the next task someone adds to the schedule and
        # forgets to configure.
        task = _fake_task("some-new-task-nobody-configured", self.now - timedelta(days=400))
        status, _, detail = self.cmd._task_freshness(task, "beat:some-new-task", self.now)
        self.assertNotEqual(status, OK)
        self.assertEqual(status, WARN)
        self.assertIn("DEFAULT_STALENESS_HOURS", detail)

    def test_unlisted_task_recently_run_also_does_not_pass(self):
        # Recency must not mask the missing-window gap either.
        task = _fake_task("some-new-task-nobody-configured", self.now)
        status, _, _ = self.cmd._task_freshness(task, "beat:some-new-task", self.now)
        self.assertNotEqual(status, OK)

    def test_interval_style_task_falls_back_to_window(self):
        # No crontab attached (interval-backed, or schedule-less) — the
        # hand-tuned window is still the right fallback since there is no
        # crontab to derive an expected fire time from.
        task = _fake_task("ingest-events-daily", self.now - timedelta(hours=5), crontab=None)
        status, _, detail = self.cmd._task_freshness(task, "beat:ingest-events-daily", self.now)
        self.assertEqual(status, OK)
        self.assertIn("last run", detail)

    def test_interval_style_task_stale_fails_not_warns(self):
        task = _fake_task("ingest-events-daily", self.now - timedelta(hours=30), crontab=None)
        status, _, detail = self.cmd._task_freshness(task, "beat:ingest-events-daily", self.now)
        self.assertEqual(status, FAIL)
        self.assertIn("STALE", detail)

    def test_crontab_task_on_schedule_is_ok(self):
        # `0 */6 * * *` UTC, last run just after 12:00Z, now 18:00Z + 1s —
        # the 18:00 fire hasn't come due relative to `now` yet... use a `now`
        # still inside the 12:00-18:00 window so no fire has been missed.
        crontab = _fake_crontab(minute="0", hour="*/6", tz="UTC")
        last_run_at = self.now.replace(hour=12, minute=0, second=1, microsecond=0)
        now = last_run_at.replace(hour=17, minute=0, second=0)
        task = _fake_task("broadcast-orphan-recovery", last_run_at, crontab=crontab)
        status, _, detail = self.cmd._task_freshness(task, "beat:broadcast-orphan-recovery", now)
        self.assertEqual(status, OK)
        self.assertIn("next expected fire", detail)

    @override_settings(CELERY_BEAT_SYNC_EVERY=1)
    def test_crontab_task_overdue_within_tight_grace_warns(self):
        # `0 */6 * * *` UTC, last_run_at 12:00:01Z, now 18:04:00Z -> expected
        # fire 18:00:00Z, overdue ~4m. CELERY_BEAT_SYNC_EVERY=1 forces a
        # post-send flush, so the tight 5-minute jitter buffer applies (see
        # crontab_grace_seconds()) — this is plausibly just scheduler/task
        # jitter, not a real miss. WARN, not a silent OK and not a FAIL we
        # can't actually justify.
        crontab = _fake_crontab(minute="0", hour="*/6", tz="UTC")
        last_run_at = self.now.replace(hour=12, minute=0, second=1, microsecond=0)
        now = last_run_at.replace(hour=18, minute=4, second=0)
        task = _fake_task("broadcast-orphan-recovery", last_run_at, crontab=crontab)
        status, _, detail = self.cmd._task_freshness(task, "beat:broadcast-orphan-recovery", now)
        self.assertEqual(status, WARN)
        self.assertIn("18:00:00", detail)
        self.assertIn("04m", detail)
        self.assertIn("grace", detail)

    @override_settings(CELERY_BEAT_SYNC_EVERY=1)
    def test_crontab_task_overdue_past_tight_grace_fails(self):
        # Same schedule, pushed past the tight 5-minute grace — e.g. beat has
        # been down long enough that this is no longer explainable as jitter.
        # `0 */6 * * *` UTC, last_run_at 12:00:01Z, now 18:07:00Z -> expected
        # fire 18:00:00Z, overdue ~7m (> 5m tight grace).
        crontab = _fake_crontab(minute="0", hour="*/6", tz="UTC")
        last_run_at = self.now.replace(hour=12, minute=0, second=1, microsecond=0)
        now = last_run_at.replace(hour=18, minute=7, second=0)
        task = _fake_task("broadcast-orphan-recovery", last_run_at, crontab=crontab)
        status, _, detail = self.cmd._task_freshness(task, "beat:broadcast-orphan-recovery", now)
        self.assertEqual(status, FAIL)
        self.assertIn("MISSED", detail)
        self.assertIn("18:00:00", detail)

    @override_settings(CELERY_BEAT_SYNC_EVERY=0)
    def test_crontab_task_overdue_within_wide_grace_warns_when_sync_every_disabled(self):
        # If CELERY_BEAT_SYNC_EVERY is disabled (0), crontab_grace_seconds()
        # must fall back to the wide 7h grace (6h CELERY_BEAT_MAX_LOOP_INTERVAL
        # + 1h buffer) — the persistence lag this setting guards against comes
        # back, so the healthcheck must automatically re-widen rather than
        # keep using the tight number and start missing real WARN cases.
        # `0 */6 * * *` UTC, last_run_at 12:00:01Z, now 22:07Z -> expected
        # fire 18:00:00Z, overdue ~4h07m, within the 7h wide grace.
        crontab = _fake_crontab(minute="0", hour="*/6", tz="UTC")
        last_run_at = self.now.replace(hour=12, minute=0, second=1, microsecond=0)
        now = last_run_at.replace(hour=22, minute=7, second=0)
        task = _fake_task("broadcast-orphan-recovery", last_run_at, crontab=crontab)
        status, _, detail = self.cmd._task_freshness(task, "beat:broadcast-orphan-recovery", now)
        self.assertEqual(status, WARN)
        self.assertIn("18:00:00", detail)
        self.assertIn("4h07m", detail)
        self.assertIn("grace", detail)

    @override_settings(CELERY_BEAT_SYNC_EVERY=0)
    def test_crontab_task_overdue_past_wide_grace_fails_when_sync_every_disabled(self):
        # Same disabled-setting fallback, pushed past the 7h wide grace —
        # e.g. beat has been down long enough that this is no longer
        # explainable as persistence lag even under the wide bound.
        # `0 */6 * * *` UTC, last_run_at 12:00:01Z, now 01:30:00Z next day ->
        # expected fire 18:00:00Z, overdue ~7h30m (> 7h wide grace).
        crontab = _fake_crontab(minute="0", hour="*/6", tz="UTC")
        last_run_at = self.now.replace(hour=12, minute=0, second=1, microsecond=0)
        now = last_run_at.replace(hour=23, minute=0, second=0) + timedelta(hours=2, minutes=30)
        task = _fake_task("broadcast-orphan-recovery", last_run_at, crontab=crontab)
        status, _, detail = self.cmd._task_freshness(task, "beat:broadcast-orphan-recovery", now)
        self.assertEqual(status, FAIL)
        self.assertIn("MISSED", detail)
        self.assertIn("18:00:00", detail)

    @override_settings(CELERY_BEAT_SYNC_EVERY=1)
    def test_crontab_grace_seconds_tight_when_sync_every_positive(self):
        self.assertEqual(crontab_grace_seconds(), 5 * 60)

    @override_settings(CELERY_BEAT_SYNC_EVERY=0)
    def test_crontab_grace_seconds_wide_when_sync_every_disabled(self):
        self.assertEqual(crontab_grace_seconds(), 6 * 60 * 60 + 60 * 60)

    @override_settings(CELERY_BEAT_SYNC_EVERY=None)
    def test_crontab_grace_seconds_wide_when_sync_every_none(self):
        self.assertEqual(crontab_grace_seconds(), 6 * 60 * 60 + 60 * 60)

    def test_do_not_mask_weekly_digest_missed_sunday_fails(self):
        # "Do not mask" case #1: weekly-digest-sunday, last_run_at 2026-07-20
        # (a Monday-ish run timestamp per the ground truth table), beat dead
        # through Sunday 2026-07-26 -> that week's digest genuinely never
        # went out. Must still FAIL, even though the next scheduled send
        # (2026-08-02) hasn't arrived yet.
        crontab = _fake_crontab(minute="0", hour="9", day_of_week="sun", tz="America/New_York")
        last_run_at = timezone.datetime(
            2026, 7, 20, 13, 0, 2, tzinfo=timezone.get_fixed_timezone(0)
        )
        now = timezone.datetime(2026, 7, 29, 22, 7, 0, tzinfo=timezone.get_fixed_timezone(0))
        task = _fake_task("weekly-digest-sunday", last_run_at, crontab=crontab)
        status, _, detail = self.cmd._task_freshness(task, "beat:weekly-digest-sunday", now)
        self.assertEqual(status, FAIL)
        self.assertIn("MISSED", detail)
        self.assertIn("2026-07-26", detail)

    def test_orphan_recovery_missed_18h_slot_past_tight_grace_now_fails(self):
        # "Do not mask" case #2, revisited now that the persistence lag this
        # grace exists for has been fixed at its source: CELERY_BEAT_SYNC_EVERY
        # = 1 (backend/settings/base.py, inherited unmodified by the test
        # settings) forces a DB flush after every task send, so last_run_at
        # lags reality by roughly one task execution, not up to
        # CELERY_BEAT_MAX_LOOP_INTERVAL (6h) as it used to.
        #
        # broadcast-orphan-recovery, last_run_at 2026-07-29 12:00:01Z, now
        # 2026-07-29 19:00:00Z: ~1h overdue against the 6h period. Under the
        # old 7h wide grace this landed in WARN (renamed test, see git log:
        # test_orphan_recovery_missed_18h_slot_within_grace_warns_not_fails).
        # Under the new tight 5-minute grace (crontab_grace_seconds(), no
        # override needed — CELERY_BEAT_SYNC_EVERY=1 is already the real
        # setting), 1h overdue is far past grace and correctly surfaces as
        # FAIL — this is the intended consequence of closing the
        # persistence-lag gap, not a regression: a 1h-overdue 6h-period task
        # should be caught well before its next scheduled fire.
        crontab = _fake_crontab(minute="0", hour="*/6", tz="UTC")
        last_run_at = timezone.datetime(
            2026, 7, 29, 12, 0, 1, tzinfo=timezone.get_fixed_timezone(0)
        )
        now = timezone.datetime(2026, 7, 29, 19, 0, 0, tzinfo=timezone.get_fixed_timezone(0))
        task = _fake_task("broadcast-orphan-recovery", last_run_at, crontab=crontab)
        status, _, detail = self.cmd._task_freshness(task, "beat:broadcast-orphan-recovery", now)
        self.assertEqual(status, FAIL)
        self.assertIn("MISSED", detail)

    def test_orphan_recovery_overdue_past_grace_fails(self):
        # Same schedule, overdue well beyond even the old 7h wide grace —
        # grace must not become a second staleness window regardless of
        # which branch of crontab_grace_seconds() is active. Must still FAIL.
        crontab = _fake_crontab(minute="0", hour="*/6", tz="UTC")
        last_run_at = timezone.datetime(
            2026, 7, 29, 12, 0, 1, tzinfo=timezone.get_fixed_timezone(0)
        )
        now = timezone.datetime(2026, 7, 30, 1, 30, 0, tzinfo=timezone.get_fixed_timezone(0))
        task = _fake_task("broadcast-orphan-recovery", last_run_at, crontab=crontab)
        status, _, detail = self.cmd._task_freshness(task, "beat:broadcast-orphan-recovery", now)
        self.assertEqual(status, FAIL)
        self.assertIn("MISSED", detail)


@tag("fast")
class CrontabDstTransitionTests(unittest.TestCase):
    """Pin down remaining_estimate()/expected_fire across both 2026 US DST
    transitions for the three America/New_York-seeded beat tasks, plus the
    UTC-seeded broadcast-orphan-recovery as a control.

    TzAwareCrontab (what CrontabSchedule.schedule actually returns whenever
    DJANGO_CELERY_BEAT_TZ_AWARE is left at its True default — verified via
    CrontabSchedule.schedule's source, not assumed) overrides is_due() to
    convert last_run_at into schedule.tz before delegating, and its own
    nowfunc() already returns datetime.now(schedule.tz) — so real beat
    operation reads crontab hour/minute/day-of-week fields against local wall
    time. remaining_estimate() has no such override: it's inherited unchanged
    from celery.schedules.crontab and reads last_run_at.hour/.minute/
    .isoweekday() directly off whatever tzinfo the datetime already carries.
    _crontab_freshness calls remaining_estimate() directly (not is_due()) and
    pins nowfun to a plain UTC `now` (timezone.now()) for determinism, so
    without converting into schedule.tz first, an America/New_York crontab's
    "04:00" would be read as 04:00 UTC — off by the zone's full UTC offset
    (4-5h), not just the 1h DST delta, and wrong on every single day, not
    just the two transition days. These tests exercise the real fix: both
    last_run_at and the pinned `now` are converted to schedule.tz before
    remaining_estimate() runs.
    """

    def setUp(self):
        self.cmd = Command()

    def _check(self, name, minute, hour, day_of_week, tz, last_run_at, now, expected_fire_iso):
        crontab = _fake_crontab(minute=minute, hour=hour, day_of_week=day_of_week, tz=tz)
        schedule = crontab.schedule
        # Confirms we're exercising TzAwareCrontab, not a plain crontab that
        # would happen to ignore tz entirely.
        self.assertEqual(type(schedule).__name__, "TzAwareCrontab")
        task = _fake_task(name, last_run_at, crontab=crontab)
        status, _, detail = self.cmd._task_freshness(task, f"beat:{name}", now)
        self.assertIn(expected_fire_iso, detail)
        return status, detail

    # Each case below picks `now` strictly between two candidate
    # expected_fire values: the "buggy" one a naive (no schedule.tz
    # conversion) remaining_estimate() call would have produced — which is
    # off by the zone's full UTC offset, not just the 1h DST delta — and the
    # correct one accounting for America/New_York local time across the
    # transition. That window is 4-5h wide here (comfortably more than
    # crontab_grace_seconds()'s tight 5-minute buffer), so asserting OK (not
    # WARN/FAIL) at that `now` directly proves the fix, not just that some
    # timestamp landed in the detail string: under the pre-fix code this
    # `now` reads as hours overdue against the buggy expected_fire and FAILs.

    # ── spring forward: 2026-03-08, America/New_York 02:00 -> 03:00 local ──

    def test_ingest_events_daily_spring_forward(self):
        # 0 4 * * * America/New_York. Fire before transition: 2026-03-07
        # 04:00 EST = 09:00 UTC. Buggy (UTC-misread) expected_fire would be
        # 2026-03-08T04:00:00Z; correct expected_fire is 2026-03-08 04:00
        # EDT = 08:00 UTC (a 23h local interval, crossing the missing
        # 02:00-02:59 hour). now = 06:00Z sits 2h past the buggy value but 2h
        # before the correct one.
        last_run_at = timezone.datetime(2026, 3, 7, 9, 0, 1, tzinfo=timezone.get_fixed_timezone(0))
        now = timezone.datetime(2026, 3, 8, 6, 0, 0, tzinfo=timezone.get_fixed_timezone(0))
        status, detail = self._check(
            "ingest-events-daily",
            "0",
            "4",
            "*",
            "America/New_York",
            last_run_at,
            now,
            "2026-03-08T08:00:00+00:00",
        )
        self.assertEqual(status, OK)

    def test_scrape_sources_daily_spring_forward(self):
        # 30 3 * * * America/New_York. Before: 2026-03-07 03:30 EST = 08:30
        # UTC. Buggy expected_fire: 2026-03-08T03:30:00Z. Correct: 2026-03-08
        # 03:30 EDT = 07:30 UTC. now = 05:30Z sits between the two.
        last_run_at = timezone.datetime(2026, 3, 7, 8, 30, 1, tzinfo=timezone.get_fixed_timezone(0))
        now = timezone.datetime(2026, 3, 8, 5, 30, 0, tzinfo=timezone.get_fixed_timezone(0))
        status, detail = self._check(
            "scrape-sources-daily",
            "30",
            "3",
            "*",
            "America/New_York",
            last_run_at,
            now,
            "2026-03-08T07:30:00+00:00",
        )
        self.assertEqual(status, OK)

    def test_weekly_digest_sunday_spring_forward(self):
        # 0 18 * * 0 America/New_York — fires on Sundays, and 2026-03-08 (the
        # transition day itself) is a Sunday. Before: 2026-03-01 18:00 EST =
        # 23:00 UTC. Buggy expected_fire: 2026-03-08T18:00:00Z. Correct:
        # 2026-03-08 18:00 EDT = 22:00 UTC — both 18:00 and the crontab's own
        # hour sit outside the nonexistent 02:00-02:59 window, but the fire
        # is still on the transition day, so the UTC offset used to compute
        # it must flip from -5 to -4. now = 20:00Z sits between the two.
        last_run_at = timezone.datetime(2026, 3, 1, 23, 0, 1, tzinfo=timezone.get_fixed_timezone(0))
        now = timezone.datetime(2026, 3, 8, 20, 0, 0, tzinfo=timezone.get_fixed_timezone(0))
        status, detail = self._check(
            "weekly-digest-sunday",
            "0",
            "18",
            "sun",
            "America/New_York",
            last_run_at,
            now,
            "2026-03-08T22:00:00+00:00",
        )
        self.assertEqual(status, OK)

    def test_broadcast_orphan_recovery_spring_forward_control(self):
        # 0 */6 * * * UTC — no local tz involved, must be unaffected by the
        # US DST transition happening the same day. now sits before the
        # 06:00Z fire (not yet due), unlike the NY-tz cases above which
        # deliberately probe a `now` between the buggy and correct fire
        # times — there's no such gap to probe here since UTC has none.
        last_run_at = timezone.datetime(2026, 3, 8, 0, 0, 1, tzinfo=timezone.get_fixed_timezone(0))
        now = timezone.datetime(2026, 3, 8, 5, 0, 0, tzinfo=timezone.get_fixed_timezone(0))
        status, detail = self._check(
            "broadcast-orphan-recovery",
            "0",
            "*/6",
            "*",
            "UTC",
            last_run_at,
            now,
            "2026-03-08T06:00:00+00:00",
        )
        self.assertEqual(status, OK)

    # ── fall back: 2026-11-01, America/New_York 01:00-01:59 local occurs twice ──

    def test_ingest_events_daily_fall_back(self):
        # Before: 2026-10-31 04:00 EDT = 08:00 UTC. Buggy expected_fire:
        # 2026-11-01T04:00:00Z. Correct: 2026-11-01 04:00 EST = 09:00 UTC (a
        # 25h local interval). now = 06:00Z sits between the two.
        last_run_at = timezone.datetime(
            2026, 10, 31, 8, 0, 1, tzinfo=timezone.get_fixed_timezone(0)
        )
        now = timezone.datetime(2026, 11, 1, 6, 0, 0, tzinfo=timezone.get_fixed_timezone(0))
        status, detail = self._check(
            "ingest-events-daily",
            "0",
            "4",
            "*",
            "America/New_York",
            last_run_at,
            now,
            "2026-11-01T09:00:00+00:00",
        )
        self.assertEqual(status, OK)

    def test_scrape_sources_daily_fall_back(self):
        # Before: 2026-10-31 03:30 EDT = 07:30 UTC. Buggy expected_fire:
        # 2026-11-01T03:30:00Z. Correct: 2026-11-01 03:30 EST = 08:30 UTC.
        # now = 05:30Z sits between the two.
        last_run_at = timezone.datetime(
            2026, 10, 31, 7, 30, 1, tzinfo=timezone.get_fixed_timezone(0)
        )
        now = timezone.datetime(2026, 11, 1, 5, 30, 0, tzinfo=timezone.get_fixed_timezone(0))
        status, detail = self._check(
            "scrape-sources-daily",
            "30",
            "3",
            "*",
            "America/New_York",
            last_run_at,
            now,
            "2026-11-01T08:30:00+00:00",
        )
        self.assertEqual(status, OK)

    def test_weekly_digest_sunday_fall_back(self):
        # 2026-11-01 (the transition Sunday) is the fire day. Before:
        # 2026-10-25 18:00 EDT = 22:00 UTC. Buggy expected_fire:
        # 2026-11-01T18:00:00Z. Correct: 2026-11-01 18:00 EST = 23:00 UTC —
        # offset flips from -4 to -5. now = 20:00Z sits between the two.
        last_run_at = timezone.datetime(
            2026, 10, 25, 22, 0, 1, tzinfo=timezone.get_fixed_timezone(0)
        )
        now = timezone.datetime(2026, 11, 1, 20, 0, 0, tzinfo=timezone.get_fixed_timezone(0))
        status, detail = self._check(
            "weekly-digest-sunday",
            "0",
            "18",
            "sun",
            "America/New_York",
            last_run_at,
            now,
            "2026-11-01T23:00:00+00:00",
        )
        self.assertEqual(status, OK)

    def test_broadcast_orphan_recovery_fall_back_control(self):
        # Same reasoning as the spring-forward control above.
        last_run_at = timezone.datetime(2026, 11, 1, 0, 0, 1, tzinfo=timezone.get_fixed_timezone(0))
        now = timezone.datetime(2026, 11, 1, 5, 0, 0, tzinfo=timezone.get_fixed_timezone(0))
        status, detail = self._check(
            "broadcast-orphan-recovery",
            "0",
            "*/6",
            "*",
            "UTC",
            last_run_at,
            now,
            "2026-11-01T06:00:00+00:00",
        )
        self.assertEqual(status, OK)

    # ── steady state, no transition nearby: confirms this was never a
    # DST-only bug — before the fix, remaining_estimate() misread
    # America/New_York crontab fields as UTC every single day, not just
    # across the two transition days. ──

    def test_ingest_events_daily_steady_state_not_dst_only(self):
        # 2026-06-01 04:00 EDT = 08:00 UTC -> next correct fire 2026-06-02
        # 04:00 EDT = 08:00 UTC (both days EDT, no transition involved). The
        # buggy (UTC-misread) expected_fire would be 2026-06-02T04:00:00Z;
        # now = 06:00Z sits between the two, same as the transition-day
        # cases above — proves the pre-fix bug wasn't DST-specific at all,
        # since no DST transition falls anywhere near this date.
        last_run_at = timezone.datetime(2026, 6, 1, 8, 0, 1, tzinfo=timezone.get_fixed_timezone(0))
        now = timezone.datetime(2026, 6, 2, 6, 0, 0, tzinfo=timezone.get_fixed_timezone(0))
        status, detail = self._check(
            "ingest-events-daily",
            "0",
            "4",
            "*",
            "America/New_York",
            last_run_at,
            now,
            "2026-06-02T08:00:00+00:00",
        )
        self.assertEqual(status, OK)


@tag("db")
class PeriodicTaskHealthcheckDbTests(TestCase):
    """End-to-end against real PeriodicTask rows, including the migration-seeded
    scrape-sources-daily task."""

    def setUp(self):
        self.cmd = Command()

    def test_scrape_sources_daily_seeded_and_never_run_fails(self):
        # Matches prod as found: seeded by ingestion migration 0012, enabled,
        # last_run_at NULL because beat never survived to fire it.
        pt = PeriodicTask.objects.get(name="scrape-sources-daily")
        self.assertTrue(pt.enabled)
        self.assertIsNone(pt.last_run_at)

        results = self.cmd._check_periodic_tasks()
        matches = [r for r in results if r[1] == "beat:scrape-sources-daily"]
        self.assertEqual(len(matches), 1)
        status, _, detail = matches[0]
        self.assertEqual(status, FAIL)
        self.assertIn("never run", detail)

    def test_missing_seeded_task_fails(self):
        PeriodicTask.objects.filter(name="scrape-sources-daily").delete()
        results = self.cmd._check_periodic_tasks()
        matches = [r for r in results if r[1] == "beat:scrape-sources-daily"]
        self.assertEqual(len(matches), 1)
        status, _, detail = matches[0]
        self.assertEqual(status, FAIL)
        self.assertIn("missing", detail)

    def test_stale_but_previously_run_task_fails_the_whole_check(self):
        # 200h ago is ~8 missed daily fires — this crontab-backed task must
        # FAIL with a missed-fire detail, not ride along as OK.
        schedule, _ = CrontabSchedule.objects.get_or_create(
            minute="0", hour="4", day_of_week="*", day_of_month="*", month_of_year="*"
        )
        pt, _ = PeriodicTask.objects.update_or_create(
            name="scrape-sources-daily",
            defaults={
                "task": "ingestion.tasks.scrape_all_sources_task",
                "crontab": schedule,
                "enabled": True,
                "last_run_at": timezone.now() - timedelta(hours=200),
            },
        )
        results = self.cmd._check_periodic_tasks()
        matches = [r for r in results if r[1] == "beat:scrape-sources-daily"]
        status, _, detail = matches[0]
        self.assertEqual(status, FAIL)
        self.assertIn("MISSED", detail)
