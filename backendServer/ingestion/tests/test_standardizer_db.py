import json
from datetime import UTC, datetime
from unittest import mock

from django.test import TestCase, tag

from ingestion.models import EventSource, RawEvent, StagedEvent
from ingestion.standardizer import standardize_all_unprocessed, standardize_event


@tag("db")
class StandardizerTests(TestCase):
    def setUp(self):
        self.source = EventSource.objects.create(
            name="Test Feed", source_type="ics", url="https://feed.test/cal.ics"
        )
        self.raw = RawEvent.objects.create(
            source=self.source,
            raw_title="raw concert",
            raw_description="a show",
            raw_location="somewhere",
            raw_start_datetime=datetime(2099, 6, 1, 18, 0, tzinfo=UTC),
            source_url="",  # empty avoids fetch_page_text making a network call
            source_uid="uid-1",
        )

    def _gemini_returning(self, payload):
        client = mock.Mock()
        client.models.generate_content.return_value = mock.Mock(text=json.dumps(payload))
        return mock.patch("ingestion.standardizer.genai.Client", return_value=client)

    def test_standardize_event_creates_staged_event(self):
        payload = {
            "title": "Clean Concert",
            "description": "A lovely evening of music.",
            "location_name": "Cat's Cradle",
            "town": "Carrboro",
            "tags": ["live-music", "not-a-real-tag", "free"],
            "price": 0,
        }
        with self._gemini_returning(payload):
            staged = standardize_event(self.raw)

        self.assertEqual(staged.title, "Clean Concert")
        self.assertEqual(staged.town, "Carrboro")
        self.assertEqual(staged.status, "pending")
        # Invalid tags are dropped against the VALID_TAGS allowlist.
        self.assertEqual(set(staged.tags), {"live-music", "free"})
        self.raw.refresh_from_db()
        self.assertTrue(self.raw.processed)

    def test_gemini_error_leaves_raw_unprocessed(self):
        client = mock.Mock()
        client.models.generate_content.side_effect = ValueError("gemini blew up")
        with mock.patch("ingestion.standardizer.genai.Client", return_value=client):
            processed = standardize_all_unprocessed()

        self.assertEqual(processed, 0)
        self.assertFalse(StagedEvent.objects.exists())
        self.raw.refresh_from_db()
        self.assertFalse(self.raw.processed)

    def _minimal_payload(self):
        return {
            "title": "Test Event",
            "description": "A test.",
            "location_name": "Test Venue",
            "town": "Carrboro",
            "tags": [],
            "price": 0,
        }

    def test_no_suffix_prompt_has_no_instructions_label(self):
        client = mock.Mock()
        client.models.generate_content.return_value = mock.Mock(
            text=json.dumps(self._minimal_payload())
        )
        with mock.patch("ingestion.standardizer.genai.Client", return_value=client):
            standardize_event(self.raw)
        contents = client.models.generate_content.call_args.kwargs["contents"]
        self.assertNotIn("ADDITIONAL SOURCE-SPECIFIC INSTRUCTIONS", contents)

    def test_suffix_appended_to_prompt(self):
        client = mock.Mock()
        client.models.generate_content.return_value = mock.Mock(
            text=json.dumps(self._minimal_payload())
        )
        with mock.patch("ingestion.standardizer.genai.Client", return_value=client):
            standardize_event(self.raw, prompt_suffix="focus on family events")
        contents = client.models.generate_content.call_args.kwargs["contents"]
        self.assertIn("ADDITIONAL SOURCE-SPECIFIC INSTRUCTIONS", contents)
        self.assertIn("focus on family events", contents)

    def test_non_503_error_falls_through_to_next_model(self):
        """A 429/RESOURCE_EXHAUSTED (or any non-503) on one model must not abort
        the whole function — it should fall through to the next model in
        models_to_try rather than hitting the bare `raise`."""
        client = mock.Mock()
        good_response = mock.Mock(text=json.dumps(self._minimal_payload()))
        client.models.generate_content.side_effect = [
            Exception("429 RESOURCE_EXHAUSTED"),
            good_response,
        ]
        with mock.patch("ingestion.standardizer.genai.Client", return_value=client):
            staged = standardize_event(self.raw)

        self.assertEqual(staged.title, "Test Event")
        # First model failed outright (no retry loop for non-503), second model
        # succeeded on its first attempt — exactly two calls total.
        self.assertEqual(client.models.generate_content.call_count, 2)
        self.raw.refresh_from_db()
        self.assertTrue(self.raw.processed)

    def test_none_response_text_falls_through_to_next_model(self):
        """A thinking-model response with text=None (MAX_TOKENS/SAFETY finish)
        must be treated as a failure of that model, not raise AssertionError."""
        client = mock.Mock()
        empty_response = mock.Mock(text=None)
        good_response = mock.Mock(text=json.dumps(self._minimal_payload()))
        client.models.generate_content.side_effect = [empty_response, good_response]
        with mock.patch("ingestion.standardizer.genai.Client", return_value=client):
            staged = standardize_event(self.raw)

        self.assertEqual(staged.title, "Test Event")
        self.raw.refresh_from_db()
        self.assertTrue(self.raw.processed)

    def test_unparseable_json_falls_through_to_next_model(self):
        client = mock.Mock()
        bad_response = mock.Mock(text="not json at all")
        good_response = mock.Mock(text=json.dumps(self._minimal_payload()))
        client.models.generate_content.side_effect = [bad_response, good_response]
        with mock.patch("ingestion.standardizer.genai.Client", return_value=client):
            staged = standardize_event(self.raw)

        self.assertEqual(staged.title, "Test Event")
        self.raw.refresh_from_db()
        self.assertTrue(self.raw.processed)

    def test_all_models_failing_raises_and_leaves_unprocessed(self):
        client = mock.Mock()
        client.models.generate_content.side_effect = Exception("429 RESOURCE_EXHAUSTED")
        with mock.patch("ingestion.standardizer.genai.Client", return_value=client):
            with self.assertRaises(RuntimeError):
                standardize_event(self.raw)

        self.assertFalse(StagedEvent.objects.exists())
        self.raw.refresh_from_db()
        self.assertFalse(self.raw.processed)

    def test_null_fields_fall_back_instead_of_raising(self):
        """Gemini returning JSON null for title/location_name/town/description
        must fall back to raw values instead of raising TypeError on `[:500]`
        or IntegrityError on a non-null TextField."""
        payload = {
            "title": None,
            "description": None,
            "location_name": None,
            "town": None,
            "tags": None,
            "price": None,
        }
        with self._gemini_returning(payload):
            staged = standardize_event(self.raw)

        self.assertEqual(staged.title, self.raw.raw_title)
        self.assertEqual(staged.description, "")
        self.assertEqual(staged.location_name, self.raw.raw_location)
        self.assertEqual(staged.town, "")
        self.assertEqual(staged.tags, [])
        self.assertEqual(staged.price, -1)

    def test_non_numeric_price_falls_back_to_sentinel(self):
        payload = self._minimal_payload()
        payload["price"] = "$10"
        with self._gemini_returning(payload):
            staged = standardize_event(self.raw)

        self.assertEqual(staged.price, -1)


@tag("db")
class CancelledTitleGuardTests(TestCase):
    """45.3: a cancelled title must land in the terminal `cancelled` status
    from *any* source, without ever spending a Gemini call — and the guard
    must only ever look at the title, never the description."""

    def setUp(self):
        self.source = EventSource.objects.create(
            name="Test Feed", source_type="ics", url="https://feed.test/cal.ics"
        )

    def _raw(self, title, description="a show", uid="uid-1"):
        return RawEvent.objects.create(
            source=self.source,
            raw_title=title,
            raw_description=description,
            raw_location="somewhere",
            raw_start_datetime=datetime(2099, 6, 1, 18, 0, tzinfo=UTC),
            source_url="",
            source_uid=uid,
        )

    def test_asterisk_wrapped_title_is_cancelled_without_gemini_call(self):
        raw = self._raw("*CANCELLED* Fall Festival")
        client = mock.Mock()
        with mock.patch("ingestion.standardizer.genai.Client", return_value=client):
            staged = standardize_event(raw)

        self.assertEqual(staged.status, "cancelled")
        self.assertEqual(staged.title, "*CANCELLED* Fall Festival")
        client.models.generate_content.assert_not_called()
        raw.refresh_from_db()
        self.assertTrue(raw.processed)

    def test_en_dash_title_is_cancelled(self):
        raw = self._raw("Canceled – Movie Night")
        client = mock.Mock()
        with mock.patch("ingestion.standardizer.genai.Client", return_value=client):
            staged = standardize_event(raw)

        self.assertEqual(staged.status, "cancelled")
        client.models.generate_content.assert_not_called()

    def test_colon_title_is_cancelled(self):
        raw = self._raw("CANCELED: Movie Night")
        client = mock.Mock()
        with mock.patch("ingestion.standardizer.genai.Client", return_value=client):
            staged = standardize_event(raw)

        self.assertEqual(staged.status, "cancelled")
        client.models.generate_content.assert_not_called()

    def test_description_only_cancellation_still_publishes_normally(self):
        """A clean title with 'cancelled' only in the description ("rain date
        if cancelled") must NOT trip the guard — it should go through Gemini
        and land `pending`, exactly like any other event."""
        raw = self._raw(
            "Fall Festival on the Green",
            description="Rain date if cancelled: same time next Saturday.",
        )
        payload = {
            "title": "Fall Festival on the Green",
            "description": "A festival on the green.",
            "location_name": "Town Green",
            "town": "Carrboro",
            "tags": [],
            "price": 0,
        }
        client = mock.Mock()
        client.models.generate_content.return_value = mock.Mock(text=json.dumps(payload))
        with mock.patch("ingestion.standardizer.genai.Client", return_value=client):
            staged = standardize_event(raw)

        self.assertEqual(staged.status, "pending")
        client.models.generate_content.assert_called_once()

    def test_cancelled_row_never_reprocessed(self):
        """RawEvent.processed=True means `standardize_all_unprocessed` skips it
        on the next run — no repeat Gemini billing for an already-cancelled row."""
        raw = self._raw("Event Cancelled")
        client = mock.Mock()
        with mock.patch("ingestion.standardizer.genai.Client", return_value=client):
            standardize_event(raw)

        raw.refresh_from_db()
        self.assertTrue(raw.processed)
        self.assertEqual(StagedEvent.objects.filter(raw_event=raw, status="cancelled").count(), 1)
