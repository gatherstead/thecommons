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
    "locality": "pittsboro",
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
        bad = dict(EVENT, locality="asheville")
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
