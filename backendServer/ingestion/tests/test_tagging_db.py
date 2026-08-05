"""47.2: weekends/evenings/daytime are computed from Event.date, not the LLM.
Exercises all three write paths that create/update an Event's tags —
publish_all_approved (pipeline bulk publish), ingest_direct_submission
(direct-submission publish), and EventSerializer.create (API POST) — plus the
"computed always wins over supplied" rule shared by all of them.
"""

import json
from datetime import UTC, datetime
from unittest import mock

from django.test import TestCase, tag

from events.models import Event, Town
from events.serializers import EventSerializer
from events.tests.factories import make_town, make_user
from ingestion.models import EventSource, RawEvent, StagedEvent
from ingestion.services import ingest_direct_submission, publish_all_approved

# 2026-08-15T01:00:00Z is Fri Aug 14, 9:00pm America/New_York — the UTC-trap
# case: evening + weekend (Friday >= 5pm), not a UTC-calendar Saturday.
FRIDAY_EVENING_ET_AS_UTC = datetime(2026, 8, 15, 1, 0, tzinfo=UTC)


def _gemini_mocks(std_payload, score=0.0):
    """Same pattern as test_services_db.py / test_direct_submission_db.py: a
    single patch with side_effect so standardize_event and score_event each
    get their own fake genai.Client() (both modules share the `genai` object).
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


@tag("db")
class PublishAllApprovedDayPartTagsTests(TestCase):
    def setUp(self):
        Town.objects.get_or_create(slug="carrboro", defaults={"name": "Carrboro"})

    def test_bulk_publish_computes_day_part_tags(self):
        staged = StagedEvent.objects.create(
            title="Friday Night Show",
            description="d",
            location_name="Venue",
            town="Carrboro",
            start_datetime=FRIDAY_EVENING_ET_AS_UTC,
            tags=["free"],
            status="approved",
        )

        publish_all_approved()

        event = Event.objects.get(title="Friday Night Show")
        tag_names = set(event.tags.values_list("name", flat=True))
        self.assertEqual(tag_names, {"free", "evenings", "weekends"})
        staged.refresh_from_db()
        self.assertEqual(staged.published_event, event)


@tag("db")
class DirectSubmissionDayPartTagsTests(TestCase):
    def setUp(self):
        make_town(slug="carrboro")
        self.user = make_user(user_type="BUSINESS")
        self.source = EventSource.objects.create(
            name="Direct Feed",
            source_type="ics",
            url="https://feed.test/direct.ics",
        )

    def test_direct_submission_create_branch_computes_day_part_tags(self):
        raw = RawEvent.objects.create(
            source=self.source,
            raw_title="Friday Night Show",
            raw_description="A show",
            raw_location="Some Venue, Carrboro, NC",
            raw_start_datetime=FRIDAY_EVENING_ET_AS_UTC,
            source_url="",
            source_uid="direct-uid-friday",
        )
        std_payload = {
            "title": "Friday Night Show",
            "description": "A show in Carrboro.",
            "location_name": "Some Venue",
            "town": "Carrboro",
            "tags": ["live-music"],
            "price": 0,
        }

        with _gemini_mocks(std_payload):
            event = ingest_direct_submission(raw.id, self.user.id)

        self.assertIsNotNone(event)
        tag_names = set(event.tags.values_list("name", flat=True))
        self.assertEqual(tag_names, {"live-music", "evenings", "weekends"})


@tag("db")
class SerializerCreateDayPartTagsTests(TestCase):
    def setUp(self):
        self.town = make_town(slug="carrboro")

    def _create_event(self, tags):
        serializer = EventSerializer(
            data={
                "title": "Friday Night Show",
                "town": self.town.slug,
                "date": FRIDAY_EVENING_ET_AS_UTC.isoformat(),
                "venue": "Venue",
                "description": "desc",
                "tags": tags,
            }
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        return serializer.save()

    def test_api_create_computes_day_part_tags(self):
        event = self._create_event(["free"])
        tag_names = set(event.tags.values_list("name", flat=True))
        self.assertEqual(tag_names, {"free", "evenings", "weekends"})

    def test_supplied_daytime_is_discarded_in_favor_of_computed_evenings(self):
        # Fri 9pm ET is unambiguously evening, not daytime — a user (or
        # stale client) checking "daytime" on this event must not survive.
        event = self._create_event(["daytime"])
        tag_names = set(event.tags.values_list("name", flat=True))
        self.assertNotIn("daytime", tag_names)
        self.assertIn("evenings", tag_names)
