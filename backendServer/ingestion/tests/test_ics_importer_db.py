from pathlib import Path
from unittest import mock

from django.test import TestCase, tag

from ingestion.importers.ics_importer import fetch_ics_feed
from ingestion.models import EventSource, RawEvent

FIXTURE = Path(__file__).parent / 'fixtures' / 'sample.ics'


@tag('db')
class IcsImporterTests(TestCase):
    def setUp(self):
        self.source = EventSource.objects.create(
            name='Test Feed', source_type='ics', url='https://feed.test/cal.ics'
        )
        self.ics_text = FIXTURE.read_text()

    def _patched_fetch(self):
        resp = mock.Mock()
        resp.text = self.ics_text
        resp.raise_for_status.return_value = None
        return mock.patch(
            'ingestion.importers.ics_importer.requests.get', return_value=resp
        )

    def test_parses_feed_into_raw_events(self):
        with self._patched_fetch() as get:
            created = fetch_ics_feed(self.source)
        get.assert_called_once()
        self.assertEqual(len(created), 2)
        titles = set(RawEvent.objects.values_list('raw_title', flat=True))
        self.assertEqual(titles, {'Test Concert', 'Farmers Market'})
        concert = RawEvent.objects.get(raw_title='Test Concert')
        self.assertEqual(concert.source_uid, 'evt-001@test')
        self.assertEqual(concert.source_url, 'https://example.com/concert')

    def test_rerun_dedupes_on_source_uid(self):
        with self._patched_fetch():
            fetch_ics_feed(self.source)
        with self._patched_fetch():
            created_again = fetch_ics_feed(self.source)
        self.assertEqual(created_again, [])
        self.assertEqual(RawEvent.objects.count(), 2)
