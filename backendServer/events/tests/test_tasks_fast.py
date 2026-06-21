import unittest

from django.test import tag

from events.tasks import ping, send_one_digest


@tag('fast')
class TaskSmokeTests(unittest.TestCase):
    def test_ping_returns_pong(self):
        self.assertEqual(ping(), 'pong')

    def test_send_one_digest_retry_config(self):
        # The digest send must retry on transient email failures.
        self.assertEqual(send_one_digest.max_retries, 3)
        self.assertEqual(send_one_digest.default_retry_delay, 300)
