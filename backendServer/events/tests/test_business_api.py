from django.test import TestCase, tag
from django.urls import reverse
from rest_framework.test import APIClient

from events.models import BusinessProfile, Tag

from .factories import make_town, make_user


@tag('db')
class BusinessAPITestCase(TestCase):
    """neon_auth `user` is built once by NeonAuthTestRunner (backend/test_runner.py),
    so no per-class schema setup is needed here.
    """

    def _client_for(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def setUp(self):
        self.carrboro = make_town('carrboro', 'Carrboro')
        self.chapelhill = make_town('chapel-hill', 'Chapel Hill')

        self.business_user = make_user('BUSINESS')
        self.venue_user = make_user('VENUE')
        self.local_user = make_user('LOCAL')

    # ── listing ────────────────────────────────────────────────────────────

    def test_venue_lists_published_only(self):
        published = BusinessProfile.objects.create(
            user=self.business_user, business_name='Open Cafe', is_published=True
        )
        BusinessProfile.objects.create(
            user=make_user('BUSINESS'), business_name='Hidden Co', is_published=False
        )

        resp = self._client_for(self.venue_user).get(reverse('businesses'))
        self.assertEqual(resp.status_code, 200)
        names = [b['business_name'] for b in resp.data]
        self.assertEqual(names, ['Open Cafe'])
        self.assertEqual(resp.data[0]['uuid'], str(published.uuid))

    def test_business_cannot_list(self):
        resp = self._client_for(self.business_user).get(reverse('businesses'))
        self.assertEqual(resp.status_code, 403)

    def test_local_cannot_list(self):
        resp = self._client_for(self.local_user).get(reverse('businesses'))
        self.assertEqual(resp.status_code, 403)

    # ── creation ─────────────────────────────────────────────────────────────

    def test_business_can_create(self):
        payload = {
            'business_name': 'Acme Plumbing',
            'description': 'Pipes',
            'tags': ['Repair', 'plumbing'],
            'service_area': ['carrboro'],
            'contact_email': 'hi@acme.test',
        }
        resp = self._client_for(self.business_user).post(
            reverse('businesses'), payload, format='json'
        )
        self.assertEqual(resp.status_code, 201)
        business = BusinessProfile.objects.get(user_id=self.business_user.id)
        self.assertEqual(business.business_name, 'Acme Plumbing')
        self.assertEqual(set(business.tags.values_list('name', flat=True)), {'repair', 'plumbing'})
        self.assertEqual(list(business.service_area.values_list('slug', flat=True)), ['carrboro'])

    def test_duplicate_create_is_400(self):
        client = self._client_for(self.business_user)
        first = client.post(reverse('businesses'), {'business_name': 'One'}, format='json')
        self.assertEqual(first.status_code, 201)
        second = client.post(reverse('businesses'), {'business_name': 'Two'}, format='json')
        self.assertEqual(second.status_code, 400)

    def test_venue_cannot_create(self):
        resp = self._client_for(self.venue_user).post(
            reverse('businesses'), {'business_name': 'Nope'}, format='json'
        )
        self.assertEqual(resp.status_code, 403)

    # ── detail / mutation ──────────────────────────────────────────────────

    def test_owner_can_patch_and_delete(self):
        business = BusinessProfile.objects.create(
            user=self.business_user, business_name='Old Name'
        )
        client = self._client_for(self.business_user)
        url = reverse('business-detail', args=[business.uuid])

        patch = client.patch(url, {'business_name': 'New Name'}, format='json')
        self.assertEqual(patch.status_code, 200)
        business.refresh_from_db()
        self.assertEqual(business.business_name, 'New Name')

        delete = client.delete(url)
        self.assertEqual(delete.status_code, 204)
        self.assertFalse(BusinessProfile.objects.filter(uuid=business.uuid).exists())

    def test_non_owner_cannot_patch_or_delete(self):
        business = BusinessProfile.objects.create(
            user=self.business_user, business_name='Mine'
        )
        url = reverse('business-detail', args=[business.uuid])

        # Another business user, and a venue, are both non-owners for writes.
        other = self._client_for(make_user('BUSINESS'))
        self.assertEqual(other.patch(url, {'business_name': 'x'}, format='json').status_code, 403)
        venue = self._client_for(self.venue_user)
        self.assertEqual(venue.delete(url).status_code, 403)

    def test_detail_get_owner_and_venue_allowed_others_denied(self):
        business = BusinessProfile.objects.create(
            user=self.business_user, business_name='Visible'
        )
        url = reverse('business-detail', args=[business.uuid])

        self.assertEqual(self._client_for(self.business_user).get(url).status_code, 200)
        self.assertEqual(self._client_for(self.venue_user).get(url).status_code, 200)
        self.assertEqual(self._client_for(self.local_user).get(url).status_code, 403)

    # ── filters ──────────────────────────────────────────────────────────────

    def test_filters(self):
        repair = Tag.objects.create(name='repair')
        food = Tag.objects.create(name='food')

        a = BusinessProfile.objects.create(
            user=self.business_user, business_name='Carrboro Repairs', is_published=True
        )
        a.tags.add(repair)
        a.service_area.add(self.carrboro)

        b = BusinessProfile.objects.create(
            user=make_user('BUSINESS'), business_name='Chapel Eats', is_published=True
        )
        b.tags.add(food)
        b.service_area.add(self.chapelhill)

        client = self._client_for(self.venue_user)

        by_tag = client.get(reverse('businesses'), {'tag': 'repair'})
        self.assertEqual([x['business_name'] for x in by_tag.data], ['Carrboro Repairs'])

        by_area = client.get(reverse('businesses'), {'service_area': 'chapel-hill'})
        self.assertEqual([x['business_name'] for x in by_area.data], ['Chapel Eats'])

        by_q = client.get(reverse('businesses'), {'q': 'eats'})
        self.assertEqual([x['business_name'] for x in by_q.data], ['Chapel Eats'])
