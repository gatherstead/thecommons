"""DB-tier tests for the broadcast.cache job-status read-through layer (27.5).

broadcastWeb polls GET /broadcast/jobs/{id} every 3s while a job runs; a warm
cache must serve that poll without touching Neon. Uses @tag("db") + TestCase
(real Postgres test DB). Test settings swap CACHES to LocMemCache, so no
Redis is needed here.
"""

from datetime import UTC, datetime
from unittest import mock

from django.core.cache import cache as django_cache
from django.test import TestCase, override_settings, tag
from rest_framework.test import APIClient

from broadcast import cache as broadcast_cache
from broadcast.access import hash_code
from broadcast.models import AccessCode, BroadcastAccess, BroadcastSubmission, BroadcastTarget
from broadcast.services import (
    cancel_submission,
    create_submission,
    job_payload,
    refresh_job_cache,
    retry_targets,
)
from broadcast.schema import CanonicalEvent


def make_submission(status="queued", site_keys=("a_site",)):
    submission = BroadcastSubmission.objects.create(
        client_label="test",
        title="T",
        description="D",
        start_datetime=datetime(2026, 7, 10, 19, 0, tzinfo=UTC),
        venue_name="V",
        address_line1="1 Main St",
        city="Pittsboro",
        zip="27312",
        locality=["pittsboro"],
        categories=["music"],
        status=status,
    )
    for key in site_keys:
        BroadcastTarget.objects.create(submission=submission, site_key=key)
    return submission


def _patch_jwt(email):
    return mock.patch("broadcast.access.verify_better_auth_jwt", return_value={"email": email})


def _make_code(label="makrs", tier=2, max_uses=None, raw="SECRET1"):
    return AccessCode.objects.create(
        code_hash=hash_code(raw),
        label=label,
        tier=tier,
        max_uses=max_uses,
    )


@tag("db")
class RefreshJobCacheTests(TestCase):
    """refresh_job_cache() writes a payload that matches job_payload() and
    stays correct across status transitions."""

    def setUp(self):
        django_cache.clear()

    def test_refresh_writes_payload_matching_job_payload(self):
        submission = make_submission(status="queued")
        refresh_job_cache(submission)

        cached = broadcast_cache.get_job_payload(str(submission.id))
        self.assertEqual(cached, job_payload(submission))
        self.assertEqual(cached["status"], "queued")

    def test_status_transition_is_reflected_after_refresh(self):
        submission = make_submission(status="queued")
        refresh_job_cache(submission)
        self.assertEqual(broadcast_cache.get_job_payload(str(submission.id))["status"], "queued")

        submission.status = "running"
        submission.save(update_fields=["status"])
        refresh_job_cache(submission)

        self.assertEqual(broadcast_cache.get_job_payload(str(submission.id))["status"], "running")

    def test_terminal_states_are_cached_for_end_of_job_reads(self):
        for terminal in ("done", "failed", "canceled"):
            with self.subTest(status=terminal):
                submission = make_submission(status="queued")
                submission.status = terminal
                submission.save(update_fields=["status"])
                refresh_job_cache(submission)

                cached = broadcast_cache.get_job_payload(str(submission.id))
                self.assertIsNotNone(cached)
                self.assertEqual(cached["status"], terminal)

    def test_cancel_submission_updates_cache(self):
        submission = make_submission(status="queued")
        refresh_job_cache(submission)

        cancel_submission(submission)

        cached = broadcast_cache.get_job_payload(str(submission.id))
        self.assertEqual(cached["status"], "canceled")

    def test_retry_targets_requeues_cache(self):
        submission = make_submission(status="failed")
        submission.targets.update(status="failed", error="boom")
        refresh_job_cache(submission)
        self.assertEqual(broadcast_cache.get_job_payload(str(submission.id))["status"], "failed")

        retry_targets(submission, ["a_site"])

        cached = broadcast_cache.get_job_payload(str(submission.id))
        self.assertEqual(cached["status"], "queued")
        self.assertEqual(cached["targets"][0]["status"], "pending")

    def test_create_submission_populates_cache(self):
        event = CanonicalEvent(
            title="T",
            description="D",
            start_datetime=datetime(2026, 7, 10, 19, 0, tzinfo=UTC),
            venue_name="V",
            address_line1="1 Main St",
            city="Pittsboro",
            zip="27312",
            locality=["pittsboro"],
            categories=["music"],
        )
        with mock.patch("broadcast.services._dispatch_worker"):
            submission = create_submission(
                client_label="test",
                event=event,
                site_keys=["a_site"],
                dry_run=True,
            )

        cached = broadcast_cache.get_job_payload(str(submission.id))
        self.assertIsNotNone(cached)
        self.assertEqual(cached["status"], "queued")


@override_settings(RATELIMIT_ENABLE=False)
@tag("db")
class JobDetailCacheReadTest(TestCase):
    """GET /broadcast/jobs/{id} — a warm cache must be served without a
    BroadcastSubmission SELECT."""

    def setUp(self):
        django_cache.clear()
        self.client = APIClient()
        BroadcastAccess.objects.create(email="makrs@example.com", tier=1)

    def _get_job(self, job_id):
        with _patch_jwt("makrs@example.com"):
            return self.client.get(
                f"/broadcast/jobs/{job_id}",
                HTTP_AUTHORIZATION="Bearer faketoken",
            )

    def test_cold_cache_reads_db_and_populates_cache(self):
        submission = make_submission(status="queued")
        # Nothing cached yet.
        self.assertIsNone(broadcast_cache.get_job_payload(str(submission.id)))

        resp = self._get_job(submission.id)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "queued")

        # The read-through populated the cache for the next poll.
        cached = broadcast_cache.get_job_payload(str(submission.id))
        self.assertIsNotNone(cached)
        self.assertEqual(cached["status"], "queued")

    def test_warm_cache_read_skips_submission_select(self):
        submission = make_submission(status="running")
        refresh_job_cache(submission)

        # Deleting the row proves the response cannot have come from the DB —
        # only a cache hit could still return 200 with the right payload.
        BroadcastSubmission.objects.filter(id=submission.id).delete()

        resp = self._get_job(submission.id)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "running")

    def test_unknown_job_still_404s(self):
        resp = self._get_job("00000000-0000-0000-0000-000000000000")
        self.assertEqual(resp.status_code, 404)

    def test_terminal_job_poll_served_from_cache_after_db_delete(self):
        submission = make_submission(status="done")
        submission.targets.update(status="succeeded")
        refresh_job_cache(submission)

        BroadcastSubmission.objects.filter(id=submission.id).delete()

        resp = self._get_job(submission.id)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["status"], "done")
        self.assertEqual(body["targets"][0]["status"], "succeeded")

    def test_submit_then_poll_end_to_end_uses_cache(self):
        """Full flow: POST /submit populates the cache via create_submission's
        refresh_job_cache, then the very first GET poll is a cache hit."""
        _make_code(raw="ENDTOEND")
        submit_resp = self.client.post(
            "/broadcast/submit",
            {
                "access_code": "ENDTOEND",
                "event": {
                    "title": "Dance Night",
                    "description": "Social dancing.",
                    "start_datetime": "2026-07-10T19:00:00-04:00",
                    "venue_name": "The Plant",
                    "address_line1": "220 Lorax Ln",
                    "city": "Pittsboro",
                    "state": "NC",
                    "zip": "27312",
                    "locality": ["pittsboro"],
                    "categories": ["music"],
                },
                "site_keys": ["explore_pittsboro"],
                "dry_run": True,
            },
            format="json",
        )
        self.assertEqual(submit_resp.status_code, 201)
        job_id = submit_resp.json()["job_id"]

        self.assertIsNotNone(broadcast_cache.get_job_payload(job_id))

        # Prove the poll doesn't need the row: delete it, then poll.
        BroadcastSubmission.objects.filter(id=job_id).delete()
        resp = self._get_job(job_id)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "queued")
