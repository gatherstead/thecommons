from datetime import timedelta
from unittest import mock

from celery.exceptions import Retry
from django.test import TestCase, tag
from django.utils import timezone

from events.models import Event
from events.tests.factories import make_town
from newsletter.models import NewsletterSubscriber
from newsletter.tasks import fan_out_monthly_digest, fan_out_weekly_digest, send_one_digest


@tag("db")
class DigestTaskTests(TestCase):
    """Celery runs eagerly via settings.test (CELERY_TASK_ALWAYS_EAGER), and the
    neon_auth `user` table is built by NeonAuthTestRunner — no per-class setup.

    fan_out_* now resolves recipients from NewsletterSubscriber (the single
    source of truth) rather than UserProfile, so subtasks take a resolved
    email/tags/manage_token/frequency instead of a profile id.
    """

    def _make_subscriber(self, frequency="WEEKLY", is_active=True, email=None):
        return NewsletterSubscriber.objects.create(
            email=email or "reader@example.com",
            frequency=frequency,
            is_active=is_active,
        )

    def setUp(self):
        self.carrboro = make_town("carrboro", "Carrboro")
        Event.objects.create(
            title="Weekly Event",
            town=self.carrboro,
            date=timezone.now() + timedelta(days=2),
            venue="V",
            description="d",
        )

    def test_fan_out_weekly_queues_one_subtask_per_weekly_subscriber(self):
        self._make_subscriber("WEEKLY", email="a@example.com")
        self._make_subscriber("WEEKLY", email="b@example.com")
        self._make_subscriber("MONTHLY", email="c@example.com")  # excluded
        self._make_subscriber("WEEKLY", is_active=False, email="d@example.com")  # excluded

        with mock.patch("newsletter.tasks.send_one_digest.delay") as delay:
            count = fan_out_weekly_digest.delay().get()

        self.assertEqual(count, 2)
        self.assertEqual(delay.call_count, 2)

    def test_fan_out_monthly_queues_one_subtask_per_monthly_subscriber(self):
        self._make_subscriber("MONTHLY", email="a@example.com")
        self._make_subscriber("WEEKLY", email="b@example.com")  # excluded

        with mock.patch("newsletter.tasks.send_one_digest.delay") as delay:
            count = fan_out_monthly_digest.delay().get()

        self.assertEqual(count, 1)
        delay.assert_called_once_with("a@example.com", [], mock.ANY, "MONTHLY")

    def test_send_one_digest_sends_for_matching_events(self):
        with mock.patch("newsletter.tasks.send_email", return_value=True) as send:
            send_one_digest.delay("reader@example.com", [], "some-token", "WEEKLY")
        send.assert_called_once()
        self.assertEqual(send.call_args.args[0], "reader@example.com")

    def test_send_one_digest_skips_when_no_events_match_tags(self):
        # The one seeded event has no tags, so a tag-filtered recipient gets nothing.
        with mock.patch("newsletter.tasks.send_email") as send:
            send_one_digest.delay("reader@example.com", ["music"], "some-token", "WEEKLY")
        send.assert_not_called()

    def test_send_one_digest_retries_on_brevo_failure(self):
        with mock.patch("newsletter.tasks.send_email", return_value=False) as send:
            # In eager mode self.retry() raises Retry; confirms a Brevo failure
            # requests a retry of this one subtask.
            with self.assertRaises(Retry):
                send_one_digest.delay("reader@example.com", [], "some-token", "WEEKLY")
        send.assert_called_once()
