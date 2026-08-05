"""Suite 48.6 — ranked select2 matching for Triangle Weekender venue/organizer
widgets. `_rank_select2_match` is the pure core of `_select2_match_or_create`
(which also drives a real Playwright page, so it isn't unit-tested directly
here) — it decides whether an existing option is reused, and which one, before
the adapter ever considers creating a new venue/organizer on the live site.
"""

import unittest

from django.test import tag

from broadcast.adapters.triangle_weekender import (
    _rank_select2_match,
    _wk_normalize_label,
    _wk_token_set,
)


@tag("fast")
class RankSelect2MatchTests(unittest.TestCase):
    def test_exact_match_wins(self):
        labels = ["Durham Central Park", "Durham Central Park @ 501 Foster St"]
        self.assertEqual(_rank_select2_match(labels, "Durham Central Park"), 0)

    def test_address_suffixed_duplicate_normalizes_to_exact_and_ties_short_wins(self):
        # Both labels normalize to the same bare name once the "@ <address>"
        # suffix is stripped — the tie-break must prefer the shorter one.
        labels = ["Durham Central Park @ 501 Foster St", "Durham Central Park"]
        self.assertEqual(_rank_select2_match(labels, "Durham Central Park"), 1)

    def test_prefix_tier_used_when_no_exact_match(self):
        labels = ["Motorco Music Hall Annex", "Something Unrelated"]
        self.assertEqual(_rank_select2_match(labels, "Motorco Music Hall"), 0)

    def test_token_set_tier_ignores_punctuation_and_case(self):
        labels = ["park, durham central!!"]
        self.assertEqual(_rank_select2_match(labels, "Durham Central Park"), 0)

    def test_anchoring_discipline_short_name_does_not_match_longer_unrelated_option(self):
        # Suite 46's guardrail: a short query must not swallow a longer,
        # unrelated candidate via substring matching. None of exact/prefix/
        # token-set tiers should fire here.
        labels = ["Art Market and Exhibition"]
        self.assertIsNone(_rank_select2_match(labels, "Market"))

    def test_no_match_returns_none(self):
        labels = ["Completely Different Venue"]
        self.assertIsNone(_rank_select2_match(labels, "Durham Central Park"))

    def test_empty_query_returns_none(self):
        self.assertIsNone(_rank_select2_match(["Anything"], ""))

    def test_empty_labels_returns_none(self):
        self.assertIsNone(_rank_select2_match([], "Durham Central Park"))


@tag("fast")
class NormalizeHelpersTests(unittest.TestCase):
    def test_normalize_strips_trailing_address_suffix(self):
        self.assertEqual(
            _wk_normalize_label("Durham Central Park @ 501 Foster St"),
            "durham central park",
        )

    def test_normalize_strips_trailing_result_count(self):
        self.assertEqual(_wk_normalize_label("Music (12)"), "music")

    def test_token_set_is_order_and_punctuation_insensitive(self):
        self.assertEqual(
            _wk_token_set("Park, Central Durham!"),
            _wk_token_set("central park durham"),
        )
