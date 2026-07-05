"""T0 — Acceptance test for the direct host submission endpoint.

POST /api/events/direct-submit
  body: {access_code, draft_id, event}

This test is intentionally RED: the endpoint does not exist yet.
It encodes the full feature contract so that once the endpoint and any
supporting task/service code are implemented, this file passes unchanged.
"""
import hashlib
import json
import uuid
from unittest import mock

from django.test import TestCase, override_settings, tag
from rest_framework.test import APIClient

from events.models import Event
from events.tests.factories import make_town, make_user
from ingestion.models import HostAccessGrant, StagedEvent

# ── Fixtures ──────────────────────────────────────────────────────────────────

ACCESS_CODE = "HOSTCODE-T0-TEST"

# Fixed draft_id so idempotency tests can re-use it across POSTs.
DRAFT_ID = str(uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"))

# Broadcast canonical event payload (§4 schema). event_url="" avoids any
# requests.get call inside the standardizer's fetch_page_text.
EVENT = {
    "title": "Live Jazz at Cat's Cradle",
    "description": "An evening of live jazz music in Carrboro.",
    "start_datetime": "2026-08-15T19:00:00-04:00",
    "venue_name": "Cat's Cradle",
    "address_line1": "300 E Main St",
    "city": "Carrboro",
    "state": "NC",
    "zip": "27510",
    "locality": ["carrboro"],
    "categories": ["music"],
    "event_url": "",
}

# What the mocked Gemini standardizer returns for EVENT.
# town="Carrboro" is required so publish_all_approved resolves the seeded Town.
STD_PAYLOAD = {
    "title": "Live Jazz at Cat's Cradle",
    "description": "An evening of live jazz music in Carrboro.",
    "location_name": "Cat's Cradle",
    "town": "Carrboro",
    "tags": ["live-music", "evenings-only"],
    "price": 0,
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _gemini_fake(payload):
    """Return a mock genai.Client whose generate_content yields *payload*."""
    fake = mock.Mock()
    fake.models.generate_content.return_value = mock.Mock(text=json.dumps(payload))
    return fake


def _scorer_fake(score):
    """Return a mock safety-scorer genai.Client yielding *score*."""
    fake = mock.Mock()
    fake.models.generate_content.return_value = mock.Mock(
        text=json.dumps({"score": score, "notes": ""})
    )
    return fake


# ── Test class ────────────────────────────────────────────────────────────────

@override_settings(RATELIMIT_ENABLE=False)
@tag("db")
class DirectSubmissionTest(TestCase):
    """End-to-end acceptance tests for POST /api/events/direct-submit."""

    def setUp(self):
        self.client = APIClient()
        self.user = make_user()
        make_town(slug="carrboro")
        HostAccessGrant.objects.create(
            user=self.user,
            code_hash=hashlib.sha256(ACCESS_CODE.encode()).hexdigest(),
            is_active=True,
        )

    def _post(self, access_code, draft_id, event, *, score=0.0, std_payload=None):
        """POST to the direct-submit endpoint with both Gemini mocks active."""
        if std_payload is None:
            std_payload = STD_PAYLOAD
        with mock.patch(
            "ingestion.standardizer.genai.Client", return_value=_gemini_fake(std_payload)
        ), mock.patch(
            "ingestion.safety_scorer.genai.Client", return_value=_scorer_fake(score)
        ):
            return self.client.post(
                "/api/events/direct-submit",
                {"access_code": access_code, "draft_id": draft_id, "event": event},
                format="json",
            )

    # 1. Valid submission → 202 + exactly one Event exists after the pipeline.
    def test_valid_submission_returns_202_and_creates_one_event(self):
        resp = self._post(ACCESS_CODE, DRAFT_ID, EVENT)
        self.assertEqual(resp.status_code, 202)
        self.assertEqual(Event.objects.count(), 1)

    # 2. That Event has the correct source_name and owner.
    def test_event_has_correct_source_name_and_created_by(self):
        self._post(ACCESS_CODE, DRAFT_ID, EVENT)
        event = Event.objects.get()
        self.assertEqual(event.source_name, "Direct submission by host")
        self.assertEqual(event.created_by, self.user)

    # 3. Re-posting the same draft_id with a changed title is idempotent: still
    #    one Event, and its title reflects the second submission.
    def test_repost_same_draft_id_updates_event_without_duplicating(self):
        self._post(ACCESS_CODE, DRAFT_ID, EVENT)
        self.assertEqual(Event.objects.count(), 1)

        updated_event = dict(EVENT, title="Updated Jazz Night")
        updated_std = dict(STD_PAYLOAD, title="Updated Jazz Night")
        self._post(ACCESS_CODE, DRAFT_ID, updated_event, std_payload=updated_std)

        self.assertEqual(Event.objects.count(), 1)
        event = Event.objects.get()
        self.assertEqual(event.title, "Updated Jazz Night")

    # 4. Invalid access_code → 403, no Event persisted.
    def test_invalid_access_code_returns_403_and_no_event(self):
        resp = self._post("WRONG-CODE", DRAFT_ID, EVENT)
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(Event.objects.count(), 0)

    # 5. Safety score above threshold → StagedEvent(status='pending') held for
    #    review; no live Event created.
    def test_high_safety_score_creates_pending_staged_event_not_live_event(self):
        resp = self._post(ACCESS_CODE, DRAFT_ID, EVENT, score=0.9)
        self.assertEqual(resp.status_code, 202)
        self.assertEqual(Event.objects.count(), 0)
        self.assertEqual(
            StagedEvent.objects.filter(submitted_by=self.user, status="pending").count(),
            1,
        )
