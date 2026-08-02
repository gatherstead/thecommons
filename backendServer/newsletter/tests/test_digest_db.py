from datetime import timedelta
from unittest import mock

from django.test import TestCase, tag
from django.utils import timezone
from django_celery_beat.models import PeriodicTask

from events.models import Event, Tag
from events.tests.factories import make_town, make_user
from newsletter.email_service import _build_recipients, send_digest
from newsletter.models import NewsletterSubscriber


@tag("db")
class MonthlyBeatScheduleSeedTests(TestCase):
    """Guards the beat schedule seeded by migration 0020 — mirrors the weekly
    guard in test_beat_schedule_db.py so a future migration can't silently
    drop or disable the monthly digest."""

    def test_monthly_digest_schedule_seeded(self):
        pt = PeriodicTask.objects.get(name="monthly-digest-first")
        self.assertEqual(pt.task, "newsletter.tasks.fan_out_monthly_digest")
        self.assertTrue(pt.enabled)
        self.assertEqual(pt.crontab.minute, "0")
        self.assertEqual(pt.crontab.hour, "18")
        self.assertEqual(pt.crontab.day_of_month, "1")
        self.assertEqual(str(pt.crontab.timezone), "America/New_York")


@tag("db")
class BuildRecipientsTests(TestCase):
    """_build_recipients is the single resolver behind both the Celery fan-out
    and the send_digest command — NewsletterSubscriber is the source of truth,
    so every recipient it produces must carry a manage_token, and an anonymous
    subscriber (no matching UserProfile) must still come through with an empty
    tag filter (i.e. gets every event)."""

    def test_every_recipient_carries_a_manage_token(self):
        NewsletterSubscriber.objects.create(email="a@example.com", frequency="WEEKLY")
        NewsletterSubscriber.objects.create(email="b@example.com", frequency="WEEKLY")

        recipients = _build_recipients("WEEKLY")

        self.assertEqual(len(recipients), 2)
        for r in recipients:
            self.assertIsNotNone(r["manage_token"])

    def test_anonymous_subscriber_included_with_no_tag_filter(self):
        sub = NewsletterSubscriber.objects.create(email="anon@example.com", frequency="WEEKLY")

        recipients = _build_recipients("WEEKLY")

        self.assertEqual(len(recipients), 1)
        self.assertEqual(recipients[0]["email"], "anon@example.com")
        self.assertEqual(recipients[0]["tags"], set())
        self.assertEqual(recipients[0]["manage_token"], sub.manage_token)

    def test_subscriber_matching_a_profile_is_tag_filtered(self):
        music = Tag.objects.create(name="music")
        user = make_user("LOCAL", email="matched@example.com")
        user.profile.tags.add(music)
        NewsletterSubscriber.objects.create(email="matched@example.com", frequency="WEEKLY")

        recipients = _build_recipients("WEEKLY")

        self.assertEqual(len(recipients), 1)
        self.assertEqual(recipients[0]["tags"], {"music"})

    def test_inactive_subscriber_excluded(self):
        NewsletterSubscriber.objects.create(
            email="gone@example.com", frequency="WEEKLY", is_active=False
        )

        self.assertEqual(_build_recipients("WEEKLY"), [])

    def test_wrong_frequency_excluded(self):
        NewsletterSubscriber.objects.create(email="monthly@example.com", frequency="MONTHLY")

        self.assertEqual(_build_recipients("WEEKLY"), [])


@tag("db")
class SendDigestManageLinkTests(TestCase):
    """The rendered digest email must include a working manage/unsubscribe
    link keyed by the recipient's own manage_token, and an anonymous
    subscriber (no account) must still receive a digest."""

    def setUp(self):
        town = make_town("carrboro", "Carrboro")
        Event.objects.create(
            title="Some Event",
            town=town,
            date=timezone.now() + timedelta(days=2),
            venue="V",
            description="d",
        )

    def test_anonymous_subscriber_receives_digest_with_manage_link(self):
        sub = NewsletterSubscriber.objects.create(email="anon@example.com", frequency="WEEKLY")

        captured = {}

        def fake_send_email(to, subject, html, text=None):
            captured["to"] = to
            captured["html"] = html
            return True

        with mock.patch("newsletter.email_service.send_email", side_effect=fake_send_email):
            result = send_digest("WEEKLY")

        self.assertEqual(result, {"sent": 1, "failed": 0})
        self.assertEqual(captured["to"], "anon@example.com")
        self.assertIn(str(sub.manage_token), captured["html"])
        self.assertIn("/newsletter/manage?token=", captured["html"])
        self.assertIn("Manage preferences / Unsubscribe", captured["html"])

    def test_no_subscribers_sends_nothing(self):
        result = send_digest("WEEKLY")
        self.assertEqual(result, {"sent": 0, "failed": 0})
