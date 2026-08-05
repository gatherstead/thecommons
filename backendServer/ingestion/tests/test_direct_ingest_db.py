import json
from datetime import UTC, datetime
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
            raw_start_datetime=datetime(2099, 6, 1, 18, 0, tzinfo=UTC),
            source_url="",  # avoids fetch_page_text network call
            source_uid="direct-uid-1",
            raw_organizer="The MAKRS Society",
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
        self.assertEqual(event.source_name, "Direct submission by The MAKRS Society")
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
        # No prior Event exists on a first submission — must stay unset.
        self.assertIsNone(staged.published_event)

    def test_blank_organizer_falls_back_to_host(self):
        """No organizer name on the raw row → generic 'by host' attribution."""
        self.raw.raw_organizer = ""
        self.raw.save(update_fields=["raw_organizer"])
        with self._gemini_mocks(self.STD_PAYLOAD, 0.0):
            event = ingest_direct_submission(self.raw.id, self.user.id)

        self.assertEqual(event.source_name, "Direct submission by host")

    def test_host_categories_flow_through_to_staged_event(self):
        """raw_categories set directly on the RawEvent (as direct_submit would
        populate it) must win over STD_PAYLOAD's absent "categories" key —
        confirms the full ingest_direct_submission -> standardize_event path,
        not just standardize_event in isolation."""
        self.raw.raw_categories = ["music", "not-a-real-category"]
        self.raw.save(update_fields=["raw_categories"])

        with self._gemini_mocks(self.STD_PAYLOAD, 0.0):
            ingest_direct_submission(self.raw.id, self.user.id)

        staged = StagedEvent.objects.get()
        self.assertEqual(staged.categories, ["music"])

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


@tag("db")
class DirectIngestOrphanPreventionTests(TestCase):
    """Ticket 40.4: a resubmitted-and-edited direct submission that gets
    gated (duplicate / over-safety-threshold / no-town) must not strand the
    Event a *prior* call to `ingest_direct_submission` already published.
    `events.Event` has no soft-delete or published flag — its existence is
    its publication — so the fix is to keep the terminal `StagedEvent`
    pointed at that prior Event (`published_event`) rather than touch the
    Event at all. Production audit (40.3) found 4 of 4 live direct-submission
    Events orphaned this way.
    """

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
            raw_start_datetime=datetime(2099, 6, 1, 18, 0, tzinfo=UTC),
            source_url="",  # avoids fetch_page_text network call
            source_uid="direct-uid-orphan",
            raw_organizer="The MAKRS Society",
        )
        self.town = make_town(slug="carrboro")
        self.user = make_user(user_type="BUSINESS")

    def _gemini_mocks(self, std_payload, score):
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

    def test_resubmission_that_becomes_a_duplicate_keeps_prior_event_published(self):
        with self._gemini_mocks(self.STD_PAYLOAD, 0.0):
            first_event = ingest_direct_submission(self.raw.id, self.user.id)
        self.assertEqual(Event.objects.count(), 1)

        # A genuine duplicate elsewhere in the system. find_duplicate only
        # matches against a lower pk (see its docstring), and this row is
        # created before the resubmission below, so it qualifies.
        other = StagedEvent.objects.create(
            title=self.STD_PAYLOAD["title"],
            description="d",
            location_name=self.STD_PAYLOAD["location_name"],
            town=self.STD_PAYLOAD["town"],
            start_datetime=self.raw.raw_start_datetime,
            status="published",
        )

        with self._gemini_mocks(self.STD_PAYLOAD, 0.0):
            result = ingest_direct_submission(self.raw.id, self.user.id)

        self.assertIsNone(result)
        # The prior Event stays live and moderatable — not orphaned, not deleted.
        self.assertEqual(Event.objects.count(), 1)
        self.assertTrue(Event.objects.filter(pk=first_event.pk).exists())

        staged = StagedEvent.objects.get(raw_event=self.raw)
        self.assertEqual(staged.status, "duplicate")
        self.assertEqual(staged.duplicate_of, other)
        self.assertEqual(staged.published_event_id, first_event.pk)

    def test_resubmission_over_safety_threshold_keeps_prior_event_published(self):
        with self._gemini_mocks(self.STD_PAYLOAD, 0.0):
            first_event = ingest_direct_submission(self.raw.id, self.user.id)
        self.assertEqual(Event.objects.count(), 1)

        with self._gemini_mocks(self.STD_PAYLOAD, 0.9):
            result = ingest_direct_submission(self.raw.id, self.user.id)

        self.assertIsNone(result)
        self.assertEqual(Event.objects.count(), 1)
        self.assertTrue(Event.objects.filter(pk=first_event.pk).exists())

        staged = StagedEvent.objects.get(raw_event=self.raw)
        # Held for review, same terminal value the automated pipeline uses
        # (see auto_publish_safe_events / monitoring.py's held_for_review
        # bucket) — not silently left at whatever standardize_event defaulted to.
        self.assertEqual(staged.status, "pending")
        self.assertEqual(staged.published_event_id, first_event.pk)

    def test_resubmission_with_no_matching_town_keeps_prior_event_published(self):
        with self._gemini_mocks(self.STD_PAYLOAD, 0.0):
            first_event = ingest_direct_submission(self.raw.id, self.user.id)
        self.assertEqual(Event.objects.count(), 1)

        out_of_coverage_payload = {**self.STD_PAYLOAD, "town": "Greensboro"}
        with self._gemini_mocks(out_of_coverage_payload, 0.0):
            result = ingest_direct_submission(self.raw.id, self.user.id)

        self.assertIsNone(result)
        self.assertEqual(Event.objects.count(), 1)
        staged = StagedEvent.objects.get(raw_event=self.raw)
        self.assertEqual(staged.status, "skipped_no_town")
        self.assertEqual(staged.published_event_id, first_event.pk)

        # The gated resubmission's content must never have touched the Event —
        # only a fully successful re-publish is allowed to mutate it.
        first_event.refresh_from_db()
        self.assertEqual(first_event.town.slug, "carrboro")

    def test_first_submission_duplicate_has_no_published_event(self):
        """No prior_event exists on a first-time duplicate — published_event
        must stay None, not resurrect a reference to a nonexistent Event."""
        other = StagedEvent.objects.create(
            title=self.STD_PAYLOAD["title"],
            description="d",
            location_name=self.STD_PAYLOAD["location_name"],
            town=self.STD_PAYLOAD["town"],
            start_datetime=self.raw.raw_start_datetime,
            status="published",
        )

        with self._gemini_mocks(self.STD_PAYLOAD, 0.0):
            result = ingest_direct_submission(self.raw.id, self.user.id)

        self.assertIsNone(result)
        self.assertFalse(Event.objects.exists())
        staged = StagedEvent.objects.get(raw_event=self.raw)
        self.assertEqual(staged.status, "duplicate")
        self.assertEqual(staged.duplicate_of, other)
        self.assertIsNone(staged.published_event)
