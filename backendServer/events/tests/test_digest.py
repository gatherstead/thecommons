from datetime import timedelta
from unittest import mock

from celery.exceptions import Retry
from django.test import TestCase, tag
from django.utils import timezone

from events.models import Event
from events.tasks import fan_out_weekly_digest, send_one_digest

from .factories import make_town, make_user


@tag('db')
class WeeklyDigestTaskTests(TestCase):
    """Celery runs eagerly via settings.test (CELERY_TASK_ALWAYS_EAGER), and the
    neon_auth `user` table is built by NeonAuthTestRunner — no per-class setup.
    """

    def _make_profile(self, email_preference='WEEKLY', primary_city='carrboro'):
        user = make_user(
            'LOCAL', email_preference=email_preference, primary_city=primary_city
        )
        return user.profile

    def setUp(self):
        self.carrboro = make_town('carrboro', 'Carrboro')
        Event.objects.create(
            title='Weekly Event', town=self.carrboro,
            date=timezone.now() + timedelta(days=2), venue='V', description='d',
        )

    def test_fan_out_queues_one_subtask_per_weekly_profile(self):
        self._make_profile(email_preference='WEEKLY')
        self._make_profile(email_preference='WEEKLY')
        self._make_profile(email_preference='MONTHLY')  # excluded
        self._make_profile(email_preference='NEVER')    # excluded

        with mock.patch('events.tasks.send_one_digest.delay') as delay:
            count = fan_out_weekly_digest.delay().get()

        self.assertEqual(count, 2)
        self.assertEqual(delay.call_count, 2)

    def test_send_one_digest_sends_for_matching_events(self):
        profile = self._make_profile()
        with mock.patch('events.tasks.send_email', return_value=True) as send:
            send_one_digest.delay(profile.id)
        send.assert_called_once()
        self.assertEqual(send.call_args.args[0], profile.user.email)

    def test_send_one_digest_skips_unknown_town(self):
        profile = self._make_profile(primary_city='nowhere')
        with mock.patch('events.tasks.send_email') as send:
            send_one_digest.delay(profile.id)
        send.assert_not_called()

    def test_send_one_digest_retries_on_brevo_failure(self):
        profile = self._make_profile()
        with mock.patch('events.tasks.send_email', return_value=False) as send:
            # In eager mode self.retry() raises Retry; confirms a Brevo failure
            # requests a retry of this one subtask.
            with self.assertRaises(Retry):
                send_one_digest.delay(profile.id)
        send.assert_called_once()
