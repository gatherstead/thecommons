from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from django.template.loader import render_to_string
from django.test import SimpleTestCase, tag

# 9:00 PM America/New_York on Wednesday Aug 5 is 1:00 AM UTC on Thursday Aug 6 —
# the UTC instant crosses midnight, so this also catches a weekday mislocalization
# (TIME_ZONE="UTC" would render "Thursday" and "1:00 AM"), not just the hour.
EVENING_EVENT_ET = datetime(2026, 8, 5, 21, 0, tzinfo=ZoneInfo("America/New_York"))


def _fake_event(date):
    return SimpleNamespace(
        date=date,
        title="Porch Show",
        link="",
        venue="The Cave",
        town=None,
        price="",
        description="",
    )


@tag("fast")
class DigestTemplateLocalizationTest(SimpleTestCase):
    """`{{ event.date|date }}` / `|time` localize to settings.TIME_ZONE. With
    TIME_ZONE="UTC" a 9 PM ET event renders as 1 AM the next day; it must
    render as 9:00 PM on the correct weekday instead (ticket 45.2).
    """

    def test_evening_event_renders_in_eastern_time(self):
        html = render_to_string(
            "email/digest.html",
            {
                "events": [_fake_event(EVENING_EVENT_ET)],
                "frequency": "WEEKLY",
                "subject": "This Week in The Commons",
                "site_url": "https://www.thecommons.town",
                "manage_url": "",
            },
        )

        self.assertIn("Wednesday, August 5", html)
        self.assertIn("9:00 PM", html)
        self.assertNotIn("Thursday, August 6", html)
        self.assertNotIn("1:00 AM", html)
