import json
from datetime import UTC, datetime
from unittest import mock

from django.test import TestCase, tag

from ingestion.models import EventSource, RawEvent, StagedEvent
from ingestion.prompt_dispatch import run_batch_per_source
from ingestion.safety_scorer import score_all_unscored
from ingestion.standardizer import standardize_all_unprocessed


@tag("db")
class RunBatchPerSourceStandardizeTests(TestCase):
    """standardize_all_unprocessed only reads source.prompt_suffix when a
    `source=` kwarg is passed. run_ingestion_pipeline and `ingest_events`
    used to call it with none at all, so per-source prompt_suffix never
    reached Gemini on a scheduled run. run_batch_per_source is the fix —
    assert the suffix (or lack of one) actually lands in the prompt text
    handed to Gemini for each source.
    """

    def setUp(self):
        self.with_suffix = EventSource.objects.create(
            name="Visit Raleigh",
            source_type="scraper",
            url="https://visitraleigh.test/events",
            prompt_suffix="Only include events happening downtown.",
        )
        self.without_suffix = EventSource.objects.create(
            name="Plain Feed",
            source_type="ics",
            url="https://plain.test/cal.ics",
        )
        self.raw_with_suffix = RawEvent.objects.create(
            source=self.with_suffix,
            raw_title="Downtown Concert",
            raw_start_datetime=datetime(2099, 6, 1, 18, 0, tzinfo=UTC),
            source_url="",
            source_uid="uid-suffix",
        )
        self.raw_without_suffix = RawEvent.objects.create(
            source=self.without_suffix,
            raw_title="Plain Event",
            raw_start_datetime=datetime(2099, 6, 2, 18, 0, tzinfo=UTC),
            source_url="",
            source_uid="uid-plain",
        )

    def _gemini_client(self):
        client = mock.Mock()
        client.models.generate_content.return_value = mock.Mock(
            text=json.dumps(
                {
                    "title": "Event",
                    "description": "A test.",
                    "location_name": "Somewhere",
                    "town": "Raleigh",
                    "tags": [],
                    "price": 0,
                }
            )
        )
        return client

    def test_per_source_prompt_suffix_reaches_gemini_via_scheduled_path(self):
        client = self._gemini_client()
        with mock.patch("ingestion.standardizer.genai.Client", return_value=client):
            total = run_batch_per_source(standardize_all_unprocessed, step_name="standardize")

        self.assertEqual(total, 2)

        prompts = [
            call.kwargs["contents"] for call in client.models.generate_content.call_args_list
        ]
        suffix_prompt = next(p for p in prompts if "Downtown Concert" in p)
        plain_prompt = next(p for p in prompts if "Plain Event" in p)

        self.assertIn("ADDITIONAL SOURCE-SPECIFIC INSTRUCTIONS", suffix_prompt)
        self.assertIn("Only include events happening downtown.", suffix_prompt)
        self.assertNotIn("ADDITIONAL SOURCE-SPECIFIC INSTRUCTIONS", plain_prompt)

        self.raw_with_suffix.refresh_from_db()
        self.raw_without_suffix.refresh_from_db()
        self.assertTrue(self.raw_with_suffix.processed)
        self.assertTrue(self.raw_without_suffix.processed)

    def test_inactive_source_rows_are_still_standardized(self):
        """Unprocessed rows from a deactivated source must not be stranded --
        run_batch_per_source iterates EventSource.objects.all(), not
        filter(active=True)."""
        self.with_suffix.active = False
        self.with_suffix.save(update_fields=["active"])

        client = self._gemini_client()
        with mock.patch("ingestion.standardizer.genai.Client", return_value=client):
            run_batch_per_source(standardize_all_unprocessed, step_name="standardize")

        self.raw_with_suffix.refresh_from_db()
        self.assertTrue(self.raw_with_suffix.processed)


@tag("db")
class RunBatchPerSourceSafetyTests(TestCase):
    """Same bug, same fix, for score_all_unscored / safety_scorer.py."""

    def setUp(self):
        self.with_suffix = EventSource.objects.create(
            name="Patch Pittsboro",
            source_type="http",
            url="https://patch.test/pittsboro",
            prompt_suffix="Be extra lenient on farmers markets.",
        )
        self.without_suffix = EventSource.objects.create(
            name="Plain Feed",
            source_type="ics",
            url="https://plain.test/cal.ics",
        )
        raw_with_suffix = RawEvent.objects.create(
            source=self.with_suffix,
            raw_title="Farmers Market",
            raw_start_datetime=datetime(2099, 6, 1, 18, 0, tzinfo=UTC),
            source_url="",
            source_uid="uid-1",
            processed=True,
        )
        raw_without_suffix = RawEvent.objects.create(
            source=self.without_suffix,
            raw_title="Book Club",
            raw_start_datetime=datetime(2099, 6, 2, 18, 0, tzinfo=UTC),
            source_url="",
            source_uid="uid-2",
            processed=True,
        )
        self.staged_with_suffix = StagedEvent.objects.create(
            raw_event=raw_with_suffix,
            title="Farmers Market",
            description="Local produce and crafts.",
            location_name="Town Square",
            town="Pittsboro",
            start_datetime=raw_with_suffix.raw_start_datetime,
            status="pending",
        )
        self.staged_without_suffix = StagedEvent.objects.create(
            raw_event=raw_without_suffix,
            title="Book Club",
            description="Monthly meetup at the library.",
            location_name="Library",
            town="Pittsboro",
            start_datetime=raw_without_suffix.raw_start_datetime,
            status="pending",
        )

    def _gemini_client(self):
        client = mock.Mock()
        client.models.generate_content.return_value = mock.Mock(
            text=json.dumps({"score": 0.05, "notes": "fine"})
        )
        return client

    def test_per_source_prompt_suffix_reaches_gemini_via_scheduled_path(self):
        client = self._gemini_client()
        with mock.patch("ingestion.safety_scorer.genai.Client", return_value=client):
            total = run_batch_per_source(score_all_unscored, step_name="safety")

        self.assertEqual(total, 2)

        prompts = [
            call.kwargs["contents"] for call in client.models.generate_content.call_args_list
        ]
        suffix_prompt = next(p for p in prompts if "Farmers Market" in p)
        plain_prompt = next(p for p in prompts if "Book Club" in p)

        self.assertIn("ADDITIONAL SOURCE-SPECIFIC INSTRUCTIONS", suffix_prompt)
        self.assertIn("Be extra lenient on farmers markets.", suffix_prompt)
        self.assertNotIn("ADDITIONAL SOURCE-SPECIFIC INSTRUCTIONS", plain_prompt)

        self.staged_with_suffix.refresh_from_db()
        self.staged_without_suffix.refresh_from_db()
        self.assertIsNotNone(self.staged_with_suffix.safety_score)
        self.assertIsNotNone(self.staged_without_suffix.safety_score)

    def test_inactive_source_rows_are_still_scored(self):
        self.with_suffix.active = False
        self.with_suffix.save(update_fields=["active"])

        client = self._gemini_client()
        with mock.patch("ingestion.safety_scorer.genai.Client", return_value=client):
            run_batch_per_source(score_all_unscored, step_name="safety")

        self.staged_with_suffix.refresh_from_db()
        self.assertIsNotNone(self.staged_with_suffix.safety_score)
