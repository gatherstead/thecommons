"""Pure UTC → America/New_York conversion (the '4pm→8pm' bug from
docs/broadcast-handoff.md). No DB, no ORM."""
import unittest
from datetime import datetime, timezone as dt_timezone

from django.test import tag

from broadcast.schema import EVENT_TZ, _to_local


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
