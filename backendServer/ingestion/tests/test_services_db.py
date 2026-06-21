from datetime import datetime, timezone

from django.test import TestCase, tag

from events.models import Event, Town
from ingestion.models import StagedEvent
from ingestion.services import publish_all_approved

START = datetime(2099, 6, 1, 18, 0, tzinfo=timezone.utc)


@tag('db')
class PublishAllApprovedTests(TestCase):
    def setUp(self):
        Town.objects.get_or_create(slug='carrboro', defaults={'name': 'Carrboro'})

    def _staged(self, title, status):
        return StagedEvent.objects.create(
            title=title,
            description='d',
            location_name='Venue',
            town='Carrboro',
            start_datetime=START,
            status=status,
        )

    def test_only_approved_events_are_published(self):
        self._staged('Approved Show', 'approved')
        self._staged('Pending Show', 'pending')
        self._staged('Rejected Show', 'rejected')
        self._staged('Duplicate Show', 'duplicate')

        result = publish_all_approved()

        self.assertEqual(result['published'], 1)
        self.assertEqual(result['removed'], 1)
        self.assertEqual(
            list(Event.objects.values_list('title', flat=True)), ['Approved Show']
        )
        # The published staged row is removed; the others remain untouched.
        self.assertFalse(StagedEvent.objects.filter(title='Approved Show').exists())
        self.assertEqual(StagedEvent.objects.count(), 3)

    def test_no_approved_events_is_noop(self):
        self._staged('Pending Show', 'pending')
        result = publish_all_approved()
        self.assertEqual(result, {'published': 0, 'already_published': 0, 'removed': 0})
        self.assertFalse(Event.objects.exists())
