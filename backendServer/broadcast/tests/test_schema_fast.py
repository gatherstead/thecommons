"""Pure UTC → America/New_York conversion (the '4pm→8pm' bug from
docs/broadcast-handoff.md). No DB, no ORM."""
import unittest
from datetime import datetime, timezone as dt_timezone

from django.test import tag

from broadcast.adapters._helpers import format_time
from broadcast.schema import EVENT_TZ, _to_local
from broadcast.serializers import CanonicalEventSerializer


@tag('fast')
class ToLocalTests(unittest.TestCase):
    def test_summer_utc_converts_to_edt(self):
        # July → EDT (UTC-4): 20:00 UTC is 16:00 ET.
        dt = datetime(2026, 7, 1, 20, 0, tzinfo=dt_timezone.utc)
        local = _to_local(dt)
        self.assertEqual(local.tzinfo, EVENT_TZ)
        self.assertEqual((local.hour, local.minute), (16, 0))

    def test_winter_utc_converts_to_est(self):
        # January → EST (UTC-5): 20:00 UTC is 15:00 ET.
        dt = datetime(2026, 1, 1, 20, 0, tzinfo=dt_timezone.utc)
        self.assertEqual(_to_local(dt).hour, 15)

    def test_none_passes_through(self):
        self.assertIsNone(_to_local(None))

    def test_naive_datetime_passes_through_unchanged(self):
        naive = datetime(2026, 7, 1, 20, 0)
        self.assertEqual(_to_local(naive), naive)


@tag('fast')
class CanonicalEventSerializerTzTests(unittest.TestCase):
    """Verify that to_canonical() converts aware UTC datetimes to Eastern time."""

    _VALID_BASE = {
        "title": "Summer Test Event",
        "description": "A test event description.",
        "venue_name": "Test Venue",
        "address_line1": "123 Main St",
        "zip": "27514",
        "locality": ["chapel-hill"],
        "categories": ["music"],
    }

    def test_to_canonical_converts_utc_to_eastern(self):
        # 20:00 UTC in July is 16:00 EDT (UTC-4).
        # format_time uses strftime("%I:%M %p") which yields "4:00 AM/PM" (case varies by OS).
        data = {**self._VALID_BASE, "start_datetime": "2026-07-01T20:00:00Z"}
        ser = CanonicalEventSerializer(data=data)
        self.assertTrue(ser.is_valid(), ser.errors)
        ev = ser.to_canonical()
        self.assertIn(format_time(ev.start_datetime).lower(), {"4:00 pm"})
