import json
from datetime import datetime
from pathlib import Path
from unittest import mock

from celery.exceptions import Retry
from django.test import TestCase, override_settings, tag
from django.utils import timezone

from events.models import Event, Town
from ingestion.importers.scraper_importer import fetch_scraper_source
from ingestion.models import EventSource, RawEvent, StagedEvent
from ingestion.safety_scorer import score_all_unscored
from ingestion.services import auto_publish_safe_events
from ingestion.standardizer import standardize_all_unprocessed
from ingestion.tasks import run_ingestion_pipeline

SCRAPER_FIXTURE = Path(__file__).parent / "fixtures" / "visitpittsboro_month.html"

# Fixed "now" the fixture's 3 events (07-12, 07-17, 07-19) were built to be
# future-dated against — see test_scraper_extract_fast.py for the same fix.
_FIXTURE_BUILD_TIME = timezone.make_aware(datetime(2026, 7, 11))


@tag("db")
@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
class RunIngestionPipelineTests(TestCase):
    def test_runs_all_steps_once(self):
        with (
            mock.patch("ingestion.tasks.call_command") as cleanup,
            mock.patch("ingestion.tasks.poll_all_ics_sources", return_value=3) as poll,
            mock.patch(
                "ingestion.tasks.standardize_all_unprocessed", return_value=2
            ) as standardize,
            mock.patch("ingestion.tasks.dedup_all_pending", return_value=1) as dedup,
            mock.patch("ingestion.tasks.score_all_unscored", return_value=2) as score,
            mock.patch(
                "ingestion.tasks.auto_publish_safe_events",
                return_value={"auto_approved": 1, "held_for_review": 1},
            ) as autopublish,
        ):
            run_ingestion_pipeline.delay()

        cleanup.assert_called_once_with("cleanup_old_events")
        poll.assert_called_once()
        standardize.assert_called_once()
        dedup.assert_called_once()
        score.assert_called_once()
        autopublish.assert_called_once()

    def test_failing_step_retries_whole_pipeline(self):
        with (
            mock.patch("ingestion.tasks.call_command"),
            mock.patch("ingestion.tasks.poll_all_ics_sources", return_value=0),
            mock.patch(
                "ingestion.tasks.standardize_all_unprocessed",
                side_effect=RuntimeError("gemini timeout"),
            ) as standardize,
            mock.patch("ingestion.tasks.dedup_all_pending", return_value=0),
            mock.patch("ingestion.tasks.score_all_unscored", return_value=0),
            mock.patch(
                "ingestion.tasks.auto_publish_safe_events",
                return_value={"auto_approved": 0, "held_for_review": 0},
            ),
        ):
            # In eager mode self.retry() raises Retry rather than re-executing inline;
            # this confirms a failed step requests a whole-pipeline retry.
            with self.assertRaises(Retry):
                run_ingestion_pipeline.delay()

        self.assertEqual(standardize.call_count, 1)


@tag("db")
class ScraperToPublishedEventTests(TestCase):
    """Proves a scraped RawEvent flows all the way to a published Event.

    Only the browser render (`render_page`, called from both the scraper
    importer and the standardizer's detail-page fetch) and the Gemini calls
    (standardizer + safety scorer) are mocked — everything else runs for
    real, including the ORM writes.
    """

    def setUp(self):
        self.town, _ = Town.objects.get_or_create(slug="pittsboro", defaults={"name": "Pittsboro"})
        self.source = EventSource.objects.create(
            name="VisitPittsboro",
            source_type="scraper",
            url="https://visitpittsboro.com/events/month/",
            scraper_key="visitpittsboro",
        )
        self.html = SCRAPER_FIXTURE.read_text(encoding="utf-8")
        self.enterContext(
            mock.patch(
                "ingestion.scraping.scrapers.visitpittsboro.timezone.now",
                return_value=_FIXTURE_BUILD_TIME,
            )
        )

    def _standardized_payload(self, raw_event):
        return {
            "title": raw_event.raw_title,
            "description": "A lovely community event in Pittsboro.",
            "location_name": raw_event.raw_location,
            "town": "Pittsboro",
            "tags": ["arts-and-culture"],
            "price": 0,
        }

    def _gemini_standardize_client(self):
        """A genai.Client stand-in whose generate_content echoes back a
        standardized payload keyed off the RawEvent title embedded in the
        prompt, so each of the 3 scraped events gets a distinct StagedEvent.
        """
        client = mock.Mock()

        def _generate_content(*, model, contents):
            raw = next(c for c in RawEvent.objects.all() if c.raw_title in contents)
            payload = self._standardized_payload(raw)
            return mock.Mock(text=json.dumps(payload))

        client.models.generate_content.side_effect = _generate_content
        return client

    def _gemini_safety_client(self, score=0.0):
        client = mock.Mock()
        client.models.generate_content.return_value = mock.Mock(
            text=json.dumps({"score": score, "notes": "looks fine"})
        )
        return client

    def test_scraped_raw_event_reaches_published_event(self):
        # 1. Scrape: render_page mocked, real XPath/JSON-LD extraction runs.
        with mock.patch("ingestion.importers.scraper_importer.render_page", return_value=self.html):
            created = fetch_scraper_source(self.source)
        self.assertEqual(len(created), 3)
        self.assertEqual(RawEvent.objects.count(), 3)

        # 2. Standardize: Gemini mocked; render_page mocked again because the
        # standardizer re-renders each event's detail page (use_browser=True
        # for scraper sources).
        with (
            mock.patch("ingestion.standardizer.render_page", return_value=self.html),
            mock.patch(
                "ingestion.standardizer.genai.Client",
                return_value=self._gemini_standardize_client(),
            ),
        ):
            standardized_count = standardize_all_unprocessed(source=self.source)
        self.assertEqual(standardized_count, 3)
        self.assertEqual(StagedEvent.objects.count(), 3)

        # 3. Safety score: Gemini mocked to a safe score for every event.
        with mock.patch(
            "ingestion.safety_scorer.genai.Client",
            return_value=self._gemini_safety_client(score=0.0),
        ):
            scored_count = score_all_unscored(source=self.source)
        self.assertEqual(scored_count, 3)

        # 4. Auto-publish: all 3 are safe and below threshold, so all publish.
        result = auto_publish_safe_events(source=self.source)
        self.assertEqual(result["auto_approved"], 3)
        self.assertEqual(result["held_for_review"], 0)

        self.assertEqual(Event.objects.count(), 3)
        published_titles = set(
            Event.objects.filter(source_name=self.source.name).values_list("title", flat=True)
        )
        self.assertEqual(
            published_titles,
            {
                "Loose Watercolor Floral Postcards",
                "Live Music: Too Much Fun! at City Tap",
                "The City Tap’s 18th Birthday Party",
            },
        )
        # `publish_all_approved` no longer deletes swept StagedEvents — it flips
        # them to a terminal `status="published"` so they survive as permanent
        # dedupe anchors (see ingestion/services.py). Lineage back to the
        # scraped RawEvents is therefore still traceable via the StagedEvent
        # rows themselves, not just `source_name`.
        staged = StagedEvent.objects.filter(raw_event__source=self.source)
        self.assertEqual(staged.count(), 3)
        self.assertTrue(all(s.status == "published" for s in staged))
