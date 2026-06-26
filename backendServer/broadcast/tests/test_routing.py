from datetime import datetime, timezone

from django.test import SimpleTestCase

from broadcast.adapters import _TIER1
from broadcast.routing import eligible_targets
from broadcast.schema import CanonicalEvent


def make_event(locality, categories):
    # locality is now a list
    locs = locality if isinstance(locality, list) else [locality]
    return CanonicalEvent(
        title="t", description="d",
        start_datetime=datetime(2026, 7, 1, 19, 0, tzinfo=timezone.utc),
        venue_name="v", address_line1="1 Main St", zip="27312",
        locality=locs, categories=categories,
    )


def keys(adapters):
    return {a.key for a in adapters}


class RoutingMatrixTest(SimpleTestCase):
    def test_pittsboro_music(self):
        eligible, excluded = eligible_targets(
            make_event("pittsboro", ["music", "community", "nightlife"]), _TIER1
        )
        ek = keys(eligible)
        self.assertIn("explore_pittsboro", ek)
        self.assertIn("chatham_chamber", ek)
        self.assertIn("shop_pittsboro", ek)
        self.assertIn("triangle_on_the_cheap", ek)
        self.assertIn("triangle_weekender", ek)
        self.assertIn("abc11_community", ek)
        excluded_keys = {k for k, _ in excluded}
        self.assertIn("chatham_arts", excluded_keys)      # not an arts event
        self.assertIn("visit_raleigh", excluded_keys)     # wrong locality
        self.assertIn("chapelboro", excluded_keys)
        self.assertIn("fun4raleighkids", excluded_keys)

    def test_pittsboro_book_festival_reaches_chatham_arts(self):
        eligible, _ = eligible_targets(
            make_event("pittsboro", ["literary", "festival", "market"]), _TIER1
        )
        self.assertIn("chatham_arts", keys(eligible))

    def test_pittsboro_yoga_excluded_from_arts_and_kids(self):
        eligible, excluded = eligible_targets(
            make_event("pittsboro", ["wellness"]), _TIER1
        )
        ek = keys(eligible)
        self.assertNotIn("chatham_arts", ek)
        self.assertNotIn("fun4raleighkids", ek)
        self.assertIn("explore_pittsboro", ek)

    def test_raleigh_kids_event(self):
        eligible, _ = eligible_targets(
            make_event("raleigh", ["family-kids"]), _TIER1
        )
        ek = keys(eligible)
        self.assertIn("fun4raleighkids", ek)
        self.assertIn("visit_raleigh", ek)
        self.assertNotIn("explore_pittsboro", ek)
        self.assertNotIn("chapelboro", ek)

    def test_multi_locality_reaches_both(self):
        eligible, _ = eligible_targets(
            make_event(["durham", "pittsboro"], ["music"]), _TIER1
        )
        ek = keys(eligible)
        self.assertIn("explore_pittsboro", ek)
        self.assertIn("triangle_on_the_cheap", ek)

    def test_excluded_reasons_are_explanatory(self):
        _, excluded = eligible_targets(make_event("durham", ["music"]), _TIER1)
        reasons = dict(excluded)
        # explore_pittsboro only covers pittsboro/chatham — Durham is excluded.
        self.assertIn("Covers", reasons["explore_pittsboro"])
        self.assertIn("Pittsboro", reasons["explore_pittsboro"])
        self.assertIn("check one of those localities", reasons["explore_pittsboro"])
