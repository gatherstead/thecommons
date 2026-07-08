import json
from datetime import datetime, timezone
from unittest import mock

from django.test import TestCase, tag

from events.models import Event
from events.tests.factories import make_town, make_user
from ingestion.models import EventSource, RawEvent, StagedEvent
from ingestion.services import ingest_direct_submission


@tag("db")
class DirectIngestTests(TestCase):
    STD_PAYLOAD = {
        "title": "Test Concert",
        "description": "A great show at the Cradle.",
        "location_name": "Cat's Cradle",
        "town": "Carrboro",
        "tags": ["live-music"],
        "price": 10,
    }

    def setUp(self):
        self.source = EventSource.objects.create(
            name="Direct Feed",
            source_type="ics",
            url="https://feed.test/direct.ics",
        )
        self.raw = RawEvent.objects.create(
            source=self.source,
            raw_title="Raw Concert",
            raw_description="A show",
            raw_location="Cat's Cradle, Carrboro, NC",
            raw_start=datetime(2099, 6, 1, 18, 0, tzinfo=timezone.utc),
            source_url="",  # avoids fetch_page_text network call
            source_uid="direct-uid-1",
        )
        self.town = make_town(slug="carrboro")
        self.user = make_user(user_type="BUSINESS")

    def _gemini_mocks(self, std_payload, score):
        """
        Single patch with side_effect so standardize_event and score_event each
        get their own fake client.

        Both ingestion.standardizer and ingestion.safety_scorer do
        `from google import genai`, making them reference the same google.genai
        module object.  Two independent mock.patch calls on that object fight
        each other (the second overwrites the first).  Using side_effect on one
        patch avoids the conflict: the first genai.Client() call (standardizer)
        gets fake_std; the second call (scorer) gets fake_scorer.
        """
        fake_std = mock.Mock()
        fake_std.models.generate_content.return_value = mock.Mock(text=json.dumps(std_payload))
        fake_scorer = mock.Mock()
        fake_scorer.models.generate_content.return_value = mock.Mock(
            text=json.dumps({"score": score, "notes": ""})
        )
        return mock.patch(
            "ingestion.standardizer.genai.Client",
            side_effect=[fake_std, fake_scorer],
        )

    def test_happy_path_creates_event(self):
        with self._gemini_mocks(self.STD_PAYLOAD, 0.0):
            event = ingest_direct_submission(self.raw.id, self.user.id)

        self.assertIsNotNone(event)
        self.assertEqual(Event.objects.count(), 1)
        self.assertEqual(event.source_name, "Direct submission by host")
        self.assertEqual(event.created_by, self.user)
        self.assertTrue(event.is_verified)
        # Staged row must survive (chain preserved for future edits).
        self.assertTrue(StagedEvent.objects.exists())
        staged = StagedEvent.objects.get()
        self.assertEqual(staged.status, "approved")
        self.assertEqual(staged.published_event, event)

    def test_re_edit_updates_event_in_place(self):
        with self._gemini_mocks(self.STD_PAYLOAD, 0.0):
            ingest_direct_submission(self.raw.id, self.user.id)

        self.assertEqual(Event.objects.count(), 1)

        # Simulate host editing the raw submission and resubmitting.
        self.raw.raw_title = "Updated Raw Concert"
        self.raw.save(update_fields=["raw_title"])
        updated_payload = {**self.STD_PAYLOAD, "title": "Updated Concert"}

        with self._gemini_mocks(updated_payload, 0.0):
            event = ingest_direct_submission(self.raw.id, self.user.id)

        self.assertEqual(Event.objects.count(), 1)
        self.assertEqual(event.title, "Updated Concert")
        # Staged row must still exist after re-edit.
        self.assertEqual(StagedEvent.objects.count(), 1)

    def test_over_threshold_holds_event(self):
        with self._gemini_mocks(self.STD_PAYLOAD, 0.9):
            result = ingest_direct_submission(self.raw.id, self.user.id)

        self.assertIsNone(result)
        self.assertEqual(Event.objects.count(), 0)
        staged = StagedEvent.objects.get()
        self.assertEqual(staged.status, "pending")

    def test_anonymous_submission_no_user_id(self):
        """user_id=None → submitted_by=None, is_verified=False, Event created."""
        with self._gemini_mocks(self.STD_PAYLOAD, 0.0):
            event = ingest_direct_submission(self.raw.id, None)

        self.assertIsNotNone(event)
        self.assertEqual(Event.objects.count(), 1)
        self.assertIsNone(event.created_by)
        self.assertFalse(event.is_verified)
        staged = StagedEvent.objects.get()
        self.assertIsNone(staged.submitted_by)
