from datetime import timedelta

from django.core.cache import cache
from django.http import QueryDict
from django.test import TestCase, tag
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from events import cache as events_cache
from events.models import Category, Event

from .factories import make_event, make_town


@tag('db')
class EventCacheTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.town = make_town('carrboro', 'Carrboro')

    def test_list_is_cached_then_invalidated_on_event_write(self):
        make_event('First', town=self.town)

        first = self.client.get(reverse('events'))
        self.assertEqual(first.data['count'], 1)

        # bulk_create bypasses post_save, so the cache is NOT invalidated.
        Event.objects.bulk_create([
            Event(title='Hidden', town=self.town,
                  date=timezone.now() + timedelta(days=1),
                  venue='V', description='d'),
        ])
        cached = self.client.get(reverse('events'))
        self.assertEqual(cached.data['count'], 1, 'second call should be served from cache')

        # A normal create fires post_save -> invalidates the list version.
        make_event('Third', town=self.town)
        fresh = self.client.get(reverse('events'))
        self.assertEqual(fresh.data['count'], 3, 'list should repopulate after invalidation')

    def test_towns_cache_invalidated_on_town_write(self):
        # Migration 0004 seeds some towns, so assert a relative increment: a town
        # write must bust the cache so the next read reflects the new row.
        baseline = len(self.client.get(reverse('towns')).data)
        make_town('a-brand-new-town', 'Brand New Town')
        self.assertEqual(len(self.client.get(reverse('towns')).data), baseline + 1)


@tag('db')
class EventsListKeyTests(TestCase):
    def setUp(self):
        cache.clear()
        self.town = make_town('carrboro', 'Carrboro')

    def test_distinct_query_params_get_distinct_keys(self):
        key_a = events_cache.events_list_key(QueryDict('category=music'))
        key_b = events_cache.events_list_key(QueryDict('category=art'))
        self.assertNotEqual(key_a, key_b)

    def test_event_write_bumps_version_so_prior_key_misses(self):
        empty = QueryDict('')
        before = events_cache.events_list_key(empty)
        make_event('Fresh', town=self.town)  # post_save signal bumps the version
        after = events_cache.events_list_key(empty)
        self.assertNotEqual(before, after)


@tag('db')
class CategoryCacheSignalTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_category_write_invalidates_categories_cache(self):
        cache.set(events_cache.CATEGORIES_CACHE_KEY, [{'slug': 'stale'}], events_cache.STATIC_TTL)
        cat = Category.objects.create(slug='test-cache-cat', display_name='Test Cache Cat')
        self.assertIsNone(cache.get(events_cache.CATEGORIES_CACHE_KEY))

        cache.set(events_cache.CATEGORIES_CACHE_KEY, [{'slug': 'stale'}], events_cache.STATIC_TTL)
        cat.delete()
        self.assertIsNone(cache.get(events_cache.CATEGORIES_CACHE_KEY))
