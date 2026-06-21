"""The cron ingest endpoint is GET (django.views.decorators.http.require_GET),
not POST as some docs imply — trust the code."""
from unittest import mock

from django.test import TestCase, override_settings, tag
from django.urls import reverse


@tag('db')
@override_settings(CRON_SECRET='cron-secret')
class CronIngestTests(TestCase):
    def test_missing_secret_is_401(self):
        resp = self.client.get(reverse('cron-ingest'))
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.json()['error'], 'unauthorized')

    def test_wrong_secret_is_401(self):
        resp = self.client.get(reverse('cron-ingest'), HTTP_AUTHORIZATION='Bearer nope')
        self.assertEqual(resp.status_code, 401)

    def test_valid_secret_queues_pipeline(self):
        with mock.patch('ingestion.views.run_ingestion_pipeline.delay') as delay:
            delay.return_value = mock.Mock(id='task-123')
            resp = self.client.get(
                reverse('cron-ingest'), HTTP_AUTHORIZATION='Bearer cron-secret'
            )
        self.assertEqual(resp.status_code, 202)
        self.assertEqual(resp.json()['status'], 'queued')
        self.assertEqual(resp.json()['task_id'], 'task-123')
        delay.assert_called_once_with()
