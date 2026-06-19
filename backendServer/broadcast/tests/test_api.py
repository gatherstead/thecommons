import os
from unittest import mock

from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from broadcast.models import BroadcastSubmission

CODES = {"BROADCAST_ACCESS_CODES": "makrs:SECRET1,theplant:SECRET2"}

EVENT = {
    "title": "International Dance Night @ The Plant",
    "description": "Live international music and social dancing.",
    "start_datetime": "2026-07-10T19:00:00-04:00",
    "venue_name": "The Plant",
    "address_line1": "220 Lorax Ln",
    "city": "Pittsboro",
    "state": "NC",
    "zip": "27312",
    "locality": ["pittsboro"],
    "categories": ["music", "community", "nightlife"],
}


@override_settings(RATELIMIT_ENABLE=False)
class PreviewTest(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_preview_returns_eligible_and_excluded(self):
        with mock.patch.dict(os.environ, CODES):
            resp = self.client.post(
                "/broadcast/preview",
                {"access_code": "SECRET1", "event": EVENT},
                format="json",
            )
        self.assertEqual(resp.status_code, 200)
        eligible = {e["site_key"] for e in resp.json()["eligible"]}
        excluded = {e["site_key"]: e["reason"] for e in resp.json()["excluded"]}
        self.assertIn("explore_pittsboro", eligible)
        self.assertIn("chatham_arts", excluded)
        self.assertIn("visit_raleigh", excluded)

    def test_preview_rejects_bad_code(self):
        with mock.patch.dict(os.environ, CODES):
            resp = self.client.post(
                "/broadcast/preview",
                {"access_code": "WRONG", "event": EVENT},
                format="json",
            )
        self.assertEqual(resp.status_code, 403)

    def test_preview_rejects_missing_code(self):
        with mock.patch.dict(os.environ, CODES):
            resp = self.client.post("/broadcast/preview", {"event": EVENT}, format="json")
        self.assertEqual(resp.status_code, 403)

    def test_preview_validates_event(self):
        bad = dict(EVENT, locality=["asheville"])
        with mock.patch.dict(os.environ, CODES):
            resp = self.client.post(
                "/broadcast/preview",
                {"access_code": "SECRET1", "event": bad},
                format="json",
            )
        self.assertEqual(resp.status_code, 400)

    def test_preview_writes_nothing(self):
        with mock.patch.dict(os.environ, CODES):
            self.client.post(
                "/broadcast/preview",
                {"access_code": "SECRET1", "event": EVENT},
                format="json",
            )
        self.assertEqual(BroadcastSubmission.objects.count(), 0)


@override_settings(RATELIMIT_ENABLE=False)
class SubmitAndJobTest(TestCase):
    def setUp(self):
        self.client = APIClient()

    def _submit(self, site_keys, dry_run=True):
        with mock.patch.dict(os.environ, CODES):
            return self.client.post(
                "/broadcast/submit",
                {"access_code": "SECRET1", "event": EVENT,
                 "site_keys": site_keys, "dry_run": dry_run},
                format="json",
            )

    def test_submit_creates_one_target_per_site(self):
        resp = self._submit(["explore_pittsboro", "triangle_on_the_cheap",
                             "explore_pittsboro"])  # duplicate is deduped
        self.assertEqual(resp.status_code, 201)
        submission = BroadcastSubmission.objects.get(id=resp.json()["job_id"])
        self.assertEqual(submission.status, "queued")
        self.assertEqual(submission.client_label, "makrs")
        self.assertEqual(submission.targets.count(), 2)
        self.assertTrue(all(t.dry_run for t in submission.targets.all()))

    def test_submit_rejects_unknown_site(self):
        resp = self._submit(["not_a_site"])
        self.assertEqual(resp.status_code, 400)

    def test_submit_rejects_empty_sites(self):
        resp = self._submit([])
        self.assertEqual(resp.status_code, 400)

    def test_job_detail_via_header_code(self):
        job_id = self._submit(["explore_pittsboro"]).json()["job_id"]
        with mock.patch.dict(os.environ, CODES):
            resp = self.client.get(
                f"/broadcast/jobs/{job_id}",
                HTTP_X_BROADCAST_ACCESS_CODE="SECRET2",
            )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["status"], "queued")
        self.assertEqual(body["targets"][0]["site_key"], "explore_pittsboro")
        self.assertEqual(body["targets"][0]["status"], "pending")

    def test_retry_reuses_rows(self):
        job_id = self._submit(["explore_pittsboro"]).json()["job_id"]
        submission = BroadcastSubmission.objects.get(id=job_id)
        target = submission.targets.get()
        target.status = "failed"
        target.error = "boom"
        target.save()
        submission.status = "done"
        submission.save()

        with mock.patch.dict(os.environ, CODES):
            resp = self.client.post(
                f"/broadcast/jobs/{job_id}/retry",
                {"access_code": "SECRET1", "site_keys": ["explore_pittsboro"]},
                format="json",
            )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["requeued"], 1)
        submission.refresh_from_db()
        self.assertEqual(submission.status, "queued")
        self.assertEqual(submission.targets.count(), 1)  # unique constraint: no new row
        target.refresh_from_db()
        self.assertEqual(target.status, "pending")
        self.assertEqual(target.error, "")


@override_settings(RATELIMIT_ENABLE=False)
class SubmitRealTest(TestCase):
    def setUp(self):
        self.client = APIClient()

    def _submit(self, site_keys, dry_run=True):
        with mock.patch.dict(os.environ, CODES):
            return self.client.post(
                "/broadcast/submit",
                {"access_code": "SECRET1", "event": EVENT,
                 "site_keys": site_keys, "dry_run": dry_run},
                format="json",
            )

    def _submit_real(self, job_id, site_keys, code="SECRET1"):
        with mock.patch.dict(os.environ, CODES):
            body = {"site_keys": site_keys}
            if code:
                body["access_code"] = code
            return self.client.post(
                f"/broadcast/jobs/{job_id}/submit-real", body, format="json",
            )

    def _finish_dry(self, submission):
        submission.targets.update(status="succeeded")
        submission.status = "done"
        submission.save()

    def test_promotes_dry_target_to_real_and_requeues(self):
        job_id = self._submit(["explore_pittsboro"]).json()["job_id"]
        submission = BroadcastSubmission.objects.get(id=job_id)
        self._finish_dry(submission)

        resp = self._submit_real(job_id, ["explore_pittsboro"])
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["submitted"], 1)
        submission.refresh_from_db()
        self.assertEqual(submission.status, "queued")
        target = submission.targets.get()
        self.assertEqual(target.status, "pending")
        self.assertFalse(target.dry_run)
        self.assertEqual(target.error, "")

    def test_skips_already_real_targets(self):
        job_id = self._submit(["explore_pittsboro"], dry_run=False).json()["job_id"]
        submission = BroadcastSubmission.objects.get(id=job_id)
        self._finish_dry(submission)

        resp = self._submit_real(job_id, ["explore_pittsboro"])
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["submitted"], 0)
        submission.refresh_from_db()
        self.assertEqual(submission.status, "done")

    def test_rejects_empty_sites(self):
        job_id = self._submit(["explore_pittsboro"]).json()["job_id"]
        resp = self._submit_real(job_id, [])
        self.assertEqual(resp.status_code, 400)

    def test_rejects_bad_code(self):
        job_id = self._submit(["explore_pittsboro"]).json()["job_id"]
        resp = self._submit_real(job_id, ["explore_pittsboro"], code=None)
        self.assertEqual(resp.status_code, 403)

    def test_unknown_job_not_found(self):
        resp = self._submit_real(
            "00000000-0000-0000-0000-000000000000", ["explore_pittsboro"]
        )
        self.assertEqual(resp.status_code, 404)


@override_settings(RATELIMIT_ENABLE=False)
class CancelJobTest(TestCase):
    def setUp(self):
        self.client = APIClient()

    def _submit(self, site_keys, dry_run=True):
        with mock.patch.dict(os.environ, CODES):
            return self.client.post(
                "/broadcast/submit",
                {"access_code": "SECRET1", "event": EVENT,
                 "site_keys": site_keys, "dry_run": dry_run},
                format="json",
            )

    def _cancel(self, job_id, code="SECRET1"):
        with mock.patch.dict(os.environ, CODES):
            body = {"access_code": code} if code else {}
            return self.client.post(
                f"/broadcast/jobs/{job_id}/cancel", body, format="json",
            )

    def test_cancel_skips_pending_and_marks_canceled(self):
        job_id = self._submit(["explore_pittsboro", "triangle_on_the_cheap"]).json()["job_id"]
        resp = self._cancel(job_id)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "canceled")
        self.assertEqual(resp.json()["skipped"], 2)
        submission = BroadcastSubmission.objects.get(id=job_id)
        self.assertEqual(submission.status, "canceled")
        self.assertTrue(all(t.status == "skipped" for t in submission.targets.all()))
        self.assertIsNotNone(submission.finished_at)

    def test_cancel_leaves_finished_target_status(self):
        job_id = self._submit(["explore_pittsboro", "triangle_on_the_cheap"]).json()["job_id"]
        submission = BroadcastSubmission.objects.get(id=job_id)
        done = submission.targets.get(site_key="explore_pittsboro")
        done.status = "succeeded"
        done.save()

        self._cancel(job_id)
        done.refresh_from_db()
        self.assertEqual(done.status, "succeeded")  # only pending targets are skipped
        other = submission.targets.get(site_key="triangle_on_the_cheap")
        self.assertEqual(other.status, "skipped")

    def test_cancel_is_noop_on_done_job(self):
        job_id = self._submit(["explore_pittsboro"]).json()["job_id"]
        submission = BroadcastSubmission.objects.get(id=job_id)
        submission.status = "done"
        submission.save()
        resp = self._cancel(job_id)
        self.assertEqual(resp.json()["skipped"], 0)
        self.assertEqual(resp.json()["status"], "done")

    def test_cancel_rejects_bad_code(self):
        job_id = self._submit(["explore_pittsboro"]).json()["job_id"]
        resp = self._cancel(job_id, code=None)
        self.assertEqual(resp.status_code, 403)

    def test_cancel_unknown_job_not_found(self):
        resp = self._cancel("00000000-0000-0000-0000-000000000000")
        self.assertEqual(resp.status_code, 404)


@override_settings(RATELIMIT_ENABLE=False)
class ManualRecipeTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.submission = BroadcastSubmission.objects.create(
            client_label="makrs",
            title="Jazz Night",
            description="An evening of jazz.",
            start_datetime="2026-07-10T19:00:00-04:00",
            venue_name="The Plant",
            address_line1="220 Lorax Ln",
            state="NC",
            zip="27312",
            locality=["pittsboro"],
            categories=["music"],
            event_url="https://example.com/jazz",
            status="running",
        )

    def _target(self, site_key, status):
        return self.submission.targets.create(site_key=site_key, status=status, dry_run=False)

    def _get(self, site_key, code="SECRET1"):
        with mock.patch.dict(os.environ, CODES):
            headers = {"HTTP_X_BROADCAST_ACCESS_CODE": code} if code else {}
            return self.client.get(
                f"/broadcast/jobs/{self.submission.id}/manual/{site_key}", **headers
            )

    def test_needs_manual_returns_recipe(self):
        self._target("triangle_on_the_cheap", "needs_manual")
        resp = self._get("triangle_on_the_cheap")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["site_key"], "triangle_on_the_cheap")
        self.assertTrue(body["submit_selector"])
        self.assertTrue(body["fields"])

    def test_non_manual_status_conflicts(self):
        self._target("triangle_on_the_cheap", "pending")
        resp = self._get("triangle_on_the_cheap")
        self.assertEqual(resp.status_code, 409)

    def test_missing_access_code_forbidden(self):
        self._target("triangle_on_the_cheap", "needs_manual")
        resp = self._get("triangle_on_the_cheap", code=None)
        self.assertEqual(resp.status_code, 403)

    def test_unknown_site_not_found(self):
        resp = self._get("not_a_site")
        self.assertEqual(resp.status_code, 404)

    def test_adapter_without_recipe_not_found(self):
        # visit_raleigh has no recipe_fields, so manual review is unavailable
        # even when the target is awaiting it.
        self._target("visit_raleigh", "needs_manual")
        resp = self._get("visit_raleigh")
        self.assertEqual(resp.status_code, 404)

    def test_no_target_for_site_not_found(self):
        resp = self._get("triangle_weekender")
        self.assertEqual(resp.status_code, 404)


class RateLimitTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_preview_rate_limit_trips(self):
        with mock.patch.dict(os.environ, CODES):
            for _ in range(10):
                resp = self.client.post(
                    "/broadcast/preview",
                    {"access_code": "SECRET1", "event": EVENT},
                    format="json",
                )
                self.assertEqual(resp.status_code, 200)
            resp = self.client.post(
                "/broadcast/preview",
                {"access_code": "SECRET1", "event": EVENT},
                format="json",
            )
        self.assertEqual(resp.status_code, 403)
