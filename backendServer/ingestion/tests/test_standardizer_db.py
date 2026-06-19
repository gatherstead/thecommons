import json
from datetime import datetime, timezone
from unittest import mock

from django.test import TestCase, tag

from ingestion.models import EventSource, RawEvent, StagedEvent
from ingestion.standardizer import standardize_all_unprocessed, standardize_event


@tag('db')
class StandardizerTests(TestCase):
    def setUp(self):
        self.source = EventSource.objects.create(
            name='Test Feed', source_type='ics', url='https://feed.test/cal.ics'
        )
        self.raw = RawEvent.objects.create(
            source=self.source,
            raw_title='raw concert',
            raw_description='a show',
            raw_location='somewhere',
            raw_start=datetime(2099, 6, 1, 18, 0, tzinfo=timezone.utc),
            source_url='',  # empty avoids fetch_page_text making a network call
            source_uid='uid-1',
        )

    def _gemini_returning(self, payload):
        client = mock.Mock()
        client.models.generate_content.return_value = mock.Mock(text=json.dumps(payload))
        return mock.patch('ingestion.standardizer.genai.Client', return_value=client)

    def test_standardize_event_creates_staged_event(self):
        payload = {
            'title': 'Clean Concert',
            'description': 'A lovely evening of music.',
            'location_name': "Cat's Cradle",
            'town': 'Carrboro',
            'tags': ['live-music', 'not-a-real-tag', 'free'],
            'price': 0,
        }
        with self._gemini_returning(payload):
            staged = standardize_event(self.raw)

        self.assertEqual(staged.title, 'Clean Concert')
        self.assertEqual(staged.town, 'Carrboro')
        self.assertEqual(staged.status, 'pending')
        # Invalid tags are dropped against the VALID_TAGS allowlist.
        self.assertEqual(set(staged.tags), {'live-music', 'free'})
        self.raw.refresh_from_db()
        self.assertTrue(self.raw.processed)

    def test_gemini_error_leaves_raw_unprocessed(self):
        client = mock.Mock()
        client.models.generate_content.side_effect = ValueError('gemini blew up')
        with mock.patch('ingestion.standardizer.genai.Client', return_value=client):
            processed = standardize_all_unprocessed()

        self.assertEqual(processed, 0)
        self.assertFalse(StagedEvent.objects.exists())
        self.raw.refresh_from_db()
        self.assertFalse(self.raw.processed)
