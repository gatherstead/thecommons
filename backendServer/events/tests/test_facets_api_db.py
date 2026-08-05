from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase, tag
from django.urls import reverse
from django.utils import timezone

from events.models import Event, Tag

from .factories import make_event, make_town

PAGE_SIZE = 30


@tag("db")
class EventFacetsTests(TestCase):
    def setUp(self):
        cache.clear()
        self.carrboro = make_town("carrboro", "Carrboro")
        self.chapel_hill = make_town("chapel-hill", "Chapel Hill")

    def test_counts_exceed_a_single_page(self):
        # More than PAGE_SIZE events in one town: a client-side count over the
        # paginated list endpoint would cap at 30. The facet endpoint must not.
        total = PAGE_SIZE + 5
        for i in range(total):
            make_event(f"Show {i}", town=self.carrboro, days_offset=1)

        resp = self.client.get(reverse("event-facets"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["towns"]["carrboro"], total)

    def test_response_shape(self):
        tag_free = Tag.objects.create(name="free")
        event = make_event("Free Show", town=self.carrboro, days_offset=1)
        event.tags.add(tag_free)

        resp = self.client.get(reverse("event-facets"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(set(resp.data.keys()), {"towns", "tags"})
        self.assertEqual(resp.data["towns"], {"carrboro": 1})
        self.assertEqual(resp.data["tags"], {"free": 1})

    def test_zero_count_facets_are_omitted(self):
        # chapel-hill and any unused tag should never appear.
        make_event("Carrboro Show", town=self.carrboro, days_offset=1)

        resp = self.client.get(reverse("event-facets"))
        self.assertNotIn("chapel-hill", resp.data["towns"])
        self.assertEqual(resp.data["tags"], {})

    def test_event_with_multiple_tags_counts_once_per_tag(self):
        evenings = Tag.objects.create(name="evenings")
        free = Tag.objects.create(name="free")
        event = make_event("Multi Tag Show", town=self.carrboro, days_offset=1)
        event.tags.add(evenings, free)

        resp = self.client.get(reverse("event-facets"))
        self.assertEqual(resp.data["tags"], {"evenings": 1, "free": 1})

    def test_window_past_narrows_counts(self):
        make_event("Past Show", town=self.carrboro, days_offset=-3)
        make_event("Future Show", town=self.chapel_hill, days_offset=3)

        resp = self.client.get(reverse("event-facets"), {"window": "past"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["towns"], {"carrboro": 1})

    def test_facets_are_cached_and_invalidated_with_list(self):
        make_event("First", town=self.carrboro, days_offset=1)
        first = self.client.get(reverse("event-facets"))
        self.assertEqual(first.data["towns"]["carrboro"], 1)

        # bulk_create bypasses post_save, so the cache is NOT invalidated.
        Event.objects.bulk_create(
            [
                Event(
                    title="Hidden",
                    town=self.carrboro,
                    date=timezone.now() + timedelta(days=1),
                    venue="V",
                    description="d",
                ),
            ]
        )
        cached = self.client.get(reverse("event-facets"))
        self.assertEqual(cached.data["towns"]["carrboro"], 1, "second call should hit the cache")

        # A normal create fires post_save -> invalidates both list and facets caches.
        make_event("Third", town=self.carrboro, days_offset=1)
        fresh = self.client.get(reverse("event-facets"))
        self.assertEqual(fresh.data["towns"]["carrboro"], 3)
