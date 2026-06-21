from django.test import TestCase, tag
from django.urls import reverse

from events.models import NewsletterSubscriber


@tag('db')
class NewsletterSubscribeTests(TestCase):
    def test_subscribe_creates_subscriber(self):
        resp = self.client.post(
            reverse('subscribe'),
            {'email': 'Reader@Example.com', 'frequency': 'MONTHLY'},
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()['email'], 'reader@example.com')
        self.assertEqual(resp.json()['frequency'], 'MONTHLY')
        self.assertEqual(NewsletterSubscriber.objects.count(), 1)

    def test_resubscribe_is_idempotent_and_updates_frequency(self):
        first = self.client.post(
            reverse('subscribe'),
            {'email': 'reader@example.com', 'frequency': 'WEEKLY'},
            content_type='application/json',
        )
        self.assertEqual(first.status_code, 201)

        second = self.client.post(
            reverse('subscribe'),
            {'email': 'reader@example.com', 'frequency': 'MONTHLY'},
            content_type='application/json',
        )
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()['frequency'], 'MONTHLY')
        self.assertEqual(NewsletterSubscriber.objects.count(), 1)
        self.assertEqual(
            NewsletterSubscriber.objects.get(email='reader@example.com').frequency,
            'MONTHLY',
        )

    def test_missing_email_is_400(self):
        resp = self.client.post(
            reverse('subscribe'), {'frequency': 'WEEKLY'}, content_type='application/json'
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()['error'], 'email is required')
