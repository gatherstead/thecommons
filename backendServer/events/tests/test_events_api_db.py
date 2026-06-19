from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase, override_settings, tag
from django.urls import reverse
from rest_framework.test import APIClient

from ingestion.models import StagedEvent

from .factories import make_event, make_town, make_user


@tag('db')
class EventsListTests(TestCase):
    def setUp(self):
        cache.clear()
        self.town = make_town('carrboro', 'Carrboro')
        self.past = make_event('Past Show', town=self.town, days_offset=-3)
        self.future = make_event('Future Show', town=self.town, days_offset=3)

    def test_default_window_excludes_past(self):
        resp = self.client.get(reverse('events'))
        self.assertEqual(resp.status_code, 200)
        uuids = [e['uuid'] for e in resp.data['results']]
        self.assertIn(str(self.future.uuid), uuids)
        self.assertNotIn(str(self.past.uuid), uuids)

    def test_include_past_includes_past(self):
        resp = self.client.get(reverse('events'), {'include_past': 'true'})
        self.assertEqual(resp.status_code, 200)
        uuids = [e['uuid'] for e in resp.data['results']]
        self.assertIn(str(self.past.uuid), uuids)
        self.assertIn(str(self.future.uuid), uuids)

    def test_after_filter_lower_bounds_results(self):
        far = make_event('Far Show', town=self.town, days_offset=30)
        resp = self.client.get(
            reverse('events'),
            {'after': (far.date - timedelta(days=1)).isoformat()},
        )
        self.assertEqual(resp.status_code, 200)
        uuids = [e['uuid'] for e in resp.data['results']]
        self.assertIn(str(far.uuid), uuids)
        self.assertNotIn(str(self.future.uuid), uuids)

    def test_before_filter_upper_bounds_results(self):
        far = make_event('Far Show', town=self.town, days_offset=30)
        resp = self.client.get(
            reverse('events'),
            {'before': (self.future.date + timedelta(days=1)).isoformat()},
        )
        self.assertEqual(resp.status_code, 200)
        uuids = [e['uuid'] for e in resp.data['results']]
        self.assertIn(str(self.future.uuid), uuids)
        self.assertNotIn(str(far.uuid), uuids)

    def test_serialized_event_carries_expected_fields(self):
        resp = self.client.get(reverse('events'))
        row = next(e for e in resp.data['results'] if e['uuid'] == str(self.future.uuid))
        self.assertEqual(row['title'], 'Future Show')
        self.assertEqual(row['town'], 'carrboro')


@tag('db')
@override_settings(THE_COMMONS_API_KEY='test-api-key')
class EventCreateTests(TestCase):
    def setUp(self):
        cache.clear()
        make_town('carrboro', 'Carrboro')

    def _payload(self):
        return {
            'title': 'New Concert',
            'town': 'carrboro',
            'venue': 'Cat\'s Cradle',
            'date': '2026-09-01T19:00:00Z',
            'description': 'A show',
        }

    def test_create_with_api_key_stages_event(self):
        resp = self.client.post(
            reverse('create-event'),
            self._payload(),
            format='json',
            HTTP_AUTHORIZATION='Bearer test-api-key',
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data['status'], 'pending')
        staged = StagedEvent.objects.get(id=resp.data['id'])
        self.assertEqual(staged.title, 'New Concert')
        self.assertIsNone(staged.submitted_by)

    def test_create_without_key_is_401(self):
        resp = self.client.post(reverse('create-event'), self._payload(), format='json')
        self.assertEqual(resp.status_code, 401)
        self.assertFalse(StagedEvent.objects.exists())

    def test_create_missing_fields_is_400(self):
        resp = self.client.post(
            reverse('create-event'),
            {'title': 'Only title'},
            format='json',
            HTTP_AUTHORIZATION='Bearer test-api-key',
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn('Missing fields', resp.data['error'])


@tag('db')
class EventDetailDeleteTests(TestCase):
    def setUp(self):
        cache.clear()
        self.town = make_town('carrboro', 'Carrboro')
        self.owner = make_user('LOCAL')
        self.event = make_event('My Event', town=self.town, created_by=self.owner)

    def _client_for(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def test_get_one_returns_event(self):
        resp = self.client.get(reverse('one-event', args=[self.event.uuid]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['uuid'], str(self.event.uuid))
        self.assertEqual(resp.data['title'], 'My Event')

    def test_get_one_missing_is_404(self):
        resp = self.client.get(
            reverse('one-event', args=['00000000-0000-0000-0000-000000000000'])
        )
        self.assertEqual(resp.status_code, 404)

    def test_owner_can_delete(self):
        resp = self._client_for(self.owner).delete(
            reverse('one-event', args=[self.event.uuid])
        )
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(self.event.__class__.objects.filter(uuid=self.event.uuid).exists())

    def test_non_owner_cannot_delete(self):
        other = make_user('LOCAL')
        resp = self._client_for(other).delete(
            reverse('one-event', args=[self.event.uuid])
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.data['error'], 'You can only delete your own events.')

    def test_anonymous_delete_is_401(self):
        resp = self.client.delete(reverse('one-event', args=[self.event.uuid]))
        self.assertEqual(resp.status_code, 401)
