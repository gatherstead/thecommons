from datetime import datetime, timedelta, timezone

from django.test import TestCase, tag

from ingestion.deduplicator import dedup_all_pending, find_duplicate
from ingestion.models import StagedEvent

START = datetime(2099, 6, 1, 18, 0, tzinfo=timezone.utc)


@tag('db')
class DeduplicatorTests(TestCase):
    """find_duplicate/dedup_all_pending query StagedEvent, so these are DB-tier
    (the ticket's 'no ORM' framing isn't achievable against the real code)."""

    def _staged(self, title, location, start=START, status='pending'):
        return StagedEvent.objects.create(
            title=title,
            description='d',
            location_name=location,
            town='Carrboro',
            start_datetime=start,
            status=status,
        )

    def test_near_duplicate_is_collapsed(self):
        first = self._staged('Jazz Night at the Cradle', "Cat's Cradle")
        second = self._staged('Jazz Night at the Cradle', "Cat's Cradle")

        found = dedup_all_pending()

        self.assertEqual(found, 1)
        first.refresh_from_db()
        second.refresh_from_db()
        statuses = {first.status, second.status}
        self.assertEqual(statuses, {'duplicate', 'pending'})
        dup = first if first.status == 'duplicate' else second
        self.assertIsNotNone(dup.duplicate_of_id)

    def test_distinct_events_are_not_duplicates(self):
        anchor = self._staged('Jazz Night', "Cat's Cradle")
        other = self._staged('Farmers Market', 'Town Commons')
        self.assertIsNone(find_duplicate(other))
        self.assertEqual(dedup_all_pending(), 0)
        anchor.refresh_from_db()
        self.assertEqual(anchor.status, 'pending')

    def test_event_outside_time_window_is_not_duplicate(self):
        self._staged('Jazz Night', "Cat's Cradle")
        far = self._staged('Jazz Night', "Cat's Cradle", start=START + timedelta(hours=5))
        self.assertIsNone(find_duplicate(far))
