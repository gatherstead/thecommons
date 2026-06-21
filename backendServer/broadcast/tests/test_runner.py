"""runner.run_submission state-machine tests with _run_target stubbed, so no
Playwright/browser launches (that heavy path lives in test_mock_adapter.py)."""
from datetime import datetime, timezone as dt_timezone
from unittest import mock

from django.test import TestCase

from broadcast.adapters.base import TargetResult
from broadcast.models import BroadcastSubmission, BroadcastTarget
from broadcast.runner import run_submission


def make_submission(site_keys, status="running", dry_run=False):
    submission = BroadcastSubmission.objects.create(
        client_label="test",
        title="T", description="D",
        start_datetime=datetime(2026, 7, 10, 19, 0, tzinfo=dt_timezone.utc),
        venue_name="V", address_line1="1 Main St", city="Pittsboro",
        zip="27312", locality=["pittsboro"], categories=["music"],
        status=status,
    )
    for key in site_keys:
        BroadcastTarget.objects.create(submission=submission, site_key=key, dry_run=dry_run)
    return submission


class RunSubmissionTests(TestCase):
    def test_all_success_marks_submission_done(self):
        submission = make_submission(["a_site", "b_site"])
        with mock.patch(
            "broadcast.runner._run_target",
            return_value=TargetResult(status="succeeded", external_url="https://x/1"),
        ):
            run_submission(submission)

        submission.refresh_from_db()
        self.assertEqual(submission.status, "done")
        self.assertIsNotNone(submission.finished_at)
        self.assertEqual(
            set(submission.targets.values_list("status", flat=True)), {"succeeded"}
        )

    def test_one_failure_marks_submission_failed(self):
        submission = make_submission(["a_site", "b_site"])

        def per_target(target, ev):
            if target.site_key == "b_site":
                return TargetResult(status="failed", error="boom")
            return TargetResult(status="succeeded")

        with mock.patch("broadcast.runner._run_target", side_effect=per_target):
            run_submission(submission)

        submission.refresh_from_db()
        self.assertEqual(submission.status, "failed")
        self.assertEqual(submission.targets.get(site_key="a_site").status, "succeeded")
        self.assertEqual(submission.targets.get(site_key="b_site").status, "failed")

    def test_cancellation_mid_loop_skips_remaining_targets(self):
        submission = make_submission(["a_site", "b_site"])

        def cancel_after_first(target, ev):
            # Simulate a cancel landing in the DB after the first target runs;
            # the runner re-reads status before each target and should stop.
            BroadcastSubmission.objects.filter(id=submission.id).update(status="canceled")
            return TargetResult(status="succeeded")

        with mock.patch("broadcast.runner._run_target", side_effect=cancel_after_first) as rt:
            run_submission(submission)

        submission.refresh_from_db()
        self.assertEqual(submission.status, "canceled")
        self.assertEqual(rt.call_count, 1)  # second target never ran
        self.assertEqual(submission.targets.get(site_key="a_site").status, "succeeded")
        self.assertEqual(submission.targets.get(site_key="b_site").status, "skipped")
