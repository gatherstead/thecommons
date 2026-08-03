"""Category terms have to exist verbatim on the target site.

The extension only selects a term on an exact (or, since suite 46.1, prefix)
label match against the destination's real vocabulary — a plausible-but-wrong
term fails silently: no error, no category, nothing in the log. These tests
pin every mapped term against a snapshot of each site's real vocabulary, so
the next edit that guesses a label fails here instead of on a live calendar.

Vocabularies verified live 2026-08-03 (see suite 46.1):
- Triangle Weekender: select2 "AJAX" category dropdown, but the typed search
  term never actually filters it — it always renders the complete 62-term
  vocabulary. Read directly off the rendered dropdown.
- ABC11: Trumba react-select Category box, a fixed 17-option vocabulary that
  renders in full — `[...document.querySelectorAll("[class*='__option']")]
  .map(o => o.textContent)`.
"""

import unittest

from django.test import tag

from broadcast.adapters.abc11_community import _CAT_MAP, _cat_terms
from broadcast.adapters.triangle_weekender import _WK_CATEGORY_MAP, _wk_category_terms

# Note: routing.CATEGORIES is the eligibility-routing vocabulary (11 slugs) and
# is intentionally narrower than the category slugs adapters may map from —
# events.Category is a free-form DB table, so slugs like "sports"/"film"/
# "dance"/"comedy"/"theatre" are legitimate even though routing doesn't use
# them for eligibility. These tests only pin map *values* against each site's
# real vocabulary, not map *keys* against routing.CATEGORIES.

# The complete Triangle Weekender category vocabulary (62 terms), verified
# live 2026-08-03 against the rendered select2 dropdown.
_WEEKENDER_VOCABULARY = frozenset(
    {
        "Arts",
        "Arts & Crafts",
        "Bluegrass",
        "Books & Readings",
        "Career Fair",
        "Celebrate",
        "Comedy",
        "Computers & Tech",
        "Concert",
        "Conference",
        "Create",
        "Dance",
        "Editors' Picks",
        "Educate",
        "Education",
        "Entertain",
        "Explore",
        "Family Fun",
        "Family-Friendly",
        "Fashion",
        "Festivals",
        "Film",
        "Fitness & Health",
        "Food & Drink",
        "Fundraisers",
        "Fundraisers & Charity",
        "Games",
        "Gather",
        "Global",
        "Goldston",
        "Grand Openings",
        "Holiday",
        "Home & Garden",
        "Homes & Tours",
        "Jazz",
        "Kids & Family",
        "LGBTQ+",
        "Live Music",
        "Marathon",
        "Market",
        "Mixer",
        "Move",
        "Music & Concerts",
        "Networking",
        "Nonprofit",
        "Outdoors",
        "Photography",
        "Pittsboro",
        "Play",
        "Pop-Up",
        "Sale",
        "Shopping",
        "Sports",
        "Talks & Meetings",
        "Talks & Readings",
        "Theater",
        "Trail Run",
        "Trivia",
        "Virtual Challenge",
        "Volunteerism",
        "Wellness",
        "Writing",
    }
)

# The complete ABC11 category vocabulary (17 options), verified live
# 2026-08-03 against the rendered react-select menu.
_ABC11_VOCABULARY = frozenset(
    {
        "Art / Photography / Crafts",
        "Community Events / Volunteerism",
        "Conferences",
        "Festivals / Parades",
        "Food and Beverage / Farmer's Market",
        "Fundraisers",
        "Galas / Banquets / Luncheons",
        "Job Fairs / Employment",
        "Meetings / Hearings",
        "Museum / Exhibitions",
        "Reunions",
        "Runs / Walks / Marathons",
        "School / Education",
        "Sports and Recreation",
        "Theater / Concerts",
        "Yard Sales / Garage Sales / Auctions",
        "Misc.",
    }
)


@tag("fast")
class TriangleWeekenderCategoryMapTests(unittest.TestCase):
    def test_every_mapped_label_exists_in_the_real_vocabulary(self):
        for slug, joined in _WK_CATEGORY_MAP.items():
            for label in joined.split(","):
                self.assertIn(
                    label,
                    _WEEKENDER_VOCABULARY,
                    f"{slug!r} maps to {label!r}, which is not a real Triangle "
                    "Weekender category — re-verify the live dropdown before "
                    "changing this map.",
                )

    def test_wk_category_terms_joins_all_labels_for_a_slug(self):
        class _Ev:
            categories = ["music"]

        self.assertEqual(_wk_category_terms(_Ev()), "Music & Concerts,Live Music")

    def test_wk_category_terms_skips_unmapped_slugs(self):
        class _Ev:
            categories = ["not-a-real-slug"]

        self.assertEqual(_wk_category_terms(_Ev()), "")


@tag("fast")
class Abc11CategoryMapTests(unittest.TestCase):
    def test_every_mapped_label_exists_in_the_real_vocabulary(self):
        for slug, label in _CAT_MAP.items():
            self.assertIn(
                label,
                _ABC11_VOCABULARY,
                f"{slug!r} maps to {label!r}, which is not a real ABC11 category "
                "— re-verify the live react-select menu before changing this map.",
            )

    def test_never_falls_back_to_misc(self):
        # A wrong category is worse than none — adapters never invent content.
        self.assertNotIn("Misc.", _CAT_MAP.values())

    def test_known_unmapped_slugs_are_intentionally_left_out(self):
        # No defensible ABC11 match exists for these — confirms the omission
        # is deliberate, not a regression.
        for slug in ("family-kids", "literary", "nightlife", "wellness", "film"):
            self.assertNotIn(slug, _CAT_MAP)

    def test_cat_terms_dedupes_collapsed_labels(self):
        # music/dance/comedy/theatre all collapse to "Theater / Concerts".
        class _Ev:
            categories = ["music", "dance", "comedy", "theatre"]

        self.assertEqual(_cat_terms(_Ev()), "Theater / Concerts")

    def test_cat_terms_skips_unmapped_slugs(self):
        class _Ev:
            categories = ["wellness", "arts"]

        self.assertEqual(_cat_terms(_Ev()), "Art / Photography / Crafts")
