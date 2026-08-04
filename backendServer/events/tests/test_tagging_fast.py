"""day_part_tags is a pure function of an event's start datetime — no DB, no
model instances required. See events/tagging.py for the tag rules.
"""

import unittest
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from django.test import tag

from events.tagging import day_part_tags

_ET = ZoneInfo("America/New_York")


@tag("fast")
class DayPartTagsTests(unittest.TestCase):
    def test_morning_is_daytime_only(self):
        dt = datetime(2026, 8, 3, 9, 0, tzinfo=_ET)  # Monday 9am
        self.assertEqual(day_part_tags(dt), {"daytime"})

    def test_late_afternoon_is_both_daytime_and_evenings(self):
        # 4-6pm is a deliberate overlap band: events have no end time, so a
        # 4:30pm start plausibly runs into the evening. Err inclusive.
        dt = datetime(2026, 8, 3, 16, 30, tzinfo=_ET)  # Monday 4:30pm
        self.assertEqual(day_part_tags(dt), {"daytime", "evenings"})

    def test_night_is_evenings_only(self):
        dt = datetime(2026, 8, 3, 19, 0, tzinfo=_ET)  # Monday 7pm
        self.assertEqual(day_part_tags(dt), {"evenings"})

    def test_friday_afternoon_is_not_weekend(self):
        dt = datetime(2026, 8, 7, 14, 0, tzinfo=_ET)  # Friday 2pm
        tags = day_part_tags(dt)
        self.assertNotIn("weekends", tags)
        self.assertEqual(tags, {"daytime"})

    def test_friday_evening_is_weekend(self):
        dt = datetime(2026, 8, 7, 19, 0, tzinfo=_ET)  # Friday 7pm
        tags = day_part_tags(dt)
        self.assertIn("weekends", tags)
        self.assertEqual(tags, {"evenings", "weekends"})

    def test_saturday_morning_is_weekend(self):
        dt = datetime(2026, 8, 8, 9, 0, tzinfo=_ET)  # Saturday 9am
        tags = day_part_tags(dt)
        self.assertIn("weekends", tags)
        self.assertEqual(tags, {"daytime", "weekends"})

    def test_naive_datetime_is_treated_as_already_local_not_crashed(self):
        # Defensive handling for a naive dt: don't crash, treat it as ET
        # wall-clock rather than raising on astimezone().
        dt = datetime(2026, 8, 8, 9, 0)  # Saturday 9am, no tzinfo
        self.assertEqual(day_part_tags(dt), {"daytime", "weekends"})

    def test_utc_trap_friday_evening_et_stored_as_utc(self):
        """Regression guard: 2026-08-15T01:00:00Z is Fri Aug 14 9:00pm ET, not
        a UTC-calendar Saturday. Skipping the UTC->ET conversion would land
        this on the wrong day (Saturday daytime) instead of the correct
        Friday-evening/weekend classification.
        """
        dt = datetime(2026, 8, 15, 1, 0, tzinfo=UTC)
        self.assertEqual(day_part_tags(dt), {"evenings", "weekends"})
