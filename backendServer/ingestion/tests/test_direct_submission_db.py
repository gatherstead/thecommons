"""T0 — Acceptance tests for POST /api/events/direct-submit (R4 contract).

New contract (JWT-based ownership, anonymous allowed):
- Anonymous POST + valid event + draft_id  → 202, submitted_by=None.
- POST with valid Bearer JWT               → 202, submitted_by=user.
- POST with INVALID Bearer token           → 401, no Event created.
- Missing draft_id                         → 400.
- High safety score                        → 202, StagedEvent pending, no live Event.
- Re-post of same draft_id is idempotent.
"""
import json
import uuid
from unittest import mock

from django.test import TestCase, override_settings, tag
from rest_framework.test import APIClient

from events.models import Event
from events.tests.factories import make_town, make_user
from ingestion.models import StagedEvent

# ── Fixtures ──────────────────────────────────────────────────────────────────

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

def _gemini_patch(std_payload, score):
    """Patch google.genai.Client so standardize_event and score_event each get
    their own fake client, in call order.

    Both ``ingestion.standardizer`` and ``ingestion.safety_scorer`` do
    ``from google import genai``, so they reference the *same* ``google.genai``
    module object. Two independent ``mock.patch`` calls on that object clobber
    each other (the second wins), which would feed score-JSON to the
    standardizer. A single patch with ``side_effect`` avoids that: the pipeline
    calls ``genai.Client()`` first in standardize_event (→ fake_std) and then in
    score_event (→ fake_scorer).
    """
    fake_std = mock.Mock()
    fake_std.models.generate_content.return_value = mock.Mock(
        text=json.dumps(std_payload)
    )
    fake_scorer = mock.Mock()
    fake_scorer.models.generate_content.return_value = mock.Mock(
        text=json.dumps({"score": score, "notes": ""})
    )
    return mock.patch(
        "ingestion.standardizer.genai.Client",
        side_effect=[fake_std, fake_scorer],
    )


# ── Test class ────────────────────────────────────────────────────────────────

@override_settings(RATELIMIT_ENABLE=False)
@tag("db")
class DirectSubmissionTest(TestCase):
    """End-to-end acceptance tests for POST /api/events/direct-submit."""

    def setUp(self):
        self.client = APIClient()
        self.user = make_user()
        make_town(slug="carrboro")

    def _post_anon(self, draft_id, event, *, score=0.0, std_payload=None):
        """POST without auth credentials."""
        if std_payload is None:
            std_payload = STD_PAYLOAD
        with _gemini_patch(std_payload, score):
            return self.client.post(
                "/api/events/direct-submit",
                {"draft_id": draft_id, "event": event},
                format="json",
            )

    def _post_jwt(self, draft_id, event, *, score=0.0, std_payload=None):
        """POST with a valid (mocked) Bearer JWT for self.user."""
        if std_payload is None:
            std_payload = STD_PAYLOAD
        jwt_claims = {"sub": self.user.id, "email": self.user.email}
        with mock.patch("backend.jwt_auth.verify_better_auth_jwt", return_value=jwt_claims):
            with _gemini_patch(std_payload, score):
                return self.client.post(
                    "/api/events/direct-submit",
                    {"draft_id": draft_id, "event": event},
                    format="json",
                    HTTP_AUTHORIZATION="Bearer fake-jwt-token",
                )

    # 1. Anonymous submission → 202 + one Event with no owner.
    def test_anonymous_submission_returns_202_and_creates_event(self):
        resp = self._post_anon(DRAFT_ID, EVENT)
        self.assertEqual(resp.status_code, 202)
        self.assertEqual(Event.objects.count(), 1)

    def test_anonymous_submission_submitted_by_is_none(self):
        self._post_anon(DRAFT_ID, EVENT)
        staged = StagedEvent.objects.get()
        self.assertIsNone(staged.submitted_by)

    # 2. Authenticated (JWT) submission → 202, attributed to that user.
    def test_jwt_submission_returns_202_and_attributes_user(self):
        resp = self._post_jwt(DRAFT_ID, EVENT)
        self.assertEqual(resp.status_code, 202)
        event = Event.objects.get()
        self.assertEqual(event.source_name, "Direct submission by host")
        self.assertEqual(event.created_by, self.user)

    # 3. Invalid Bearer token → 401, no Event persisted.
    def test_invalid_bearer_token_returns_401(self):
        with mock.patch("backend.jwt_auth.verify_better_auth_jwt", return_value=None):
            resp = self.client.post(
                "/api/events/direct-submit",
                {"draft_id": DRAFT_ID, "event": EVENT},
                format="json",
                HTTP_AUTHORIZATION="Bearer bad-token",
            )
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(Event.objects.count(), 0)

    # 4. Re-posting the same draft_id is idempotent (one Event, updated title).
    def test_repost_same_draft_id_updates_event_without_duplicating(self):
        self._post_jwt(DRAFT_ID, EVENT)
        self.assertEqual(Event.objects.count(), 1)

        updated_event = dict(EVENT, title="Updated Jazz Night")
        updated_std = dict(STD_PAYLOAD, title="Updated Jazz Night")
        self._post_jwt(DRAFT_ID, updated_event, std_payload=updated_std)

        self.assertEqual(Event.objects.count(), 1)
        self.assertEqual(Event.objects.get().title, "Updated Jazz Night")

    # 5. Missing draft_id → 400.
    def test_missing_draft_id_returns_400(self):
        resp = self.client.post(
            "/api/events/direct-submit",
            {"event": EVENT},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

    # 6. Safety score above threshold → StagedEvent(status='pending') held for
    #    review; no live Event created.
    def test_high_safety_score_creates_pending_staged_event_not_live_event(self):
        resp = self._post_jwt(DRAFT_ID, EVENT, score=0.9)
        self.assertEqual(resp.status_code, 202)
        self.assertEqual(Event.objects.count(), 0)
        self.assertEqual(
            StagedEvent.objects.filter(submitted_by=self.user, status="pending").count(),
            1,
        )
