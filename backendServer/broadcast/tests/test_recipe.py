"""Recipe shape + conditional-field tests. No DB — pure adapter logic."""
from datetime import datetime, timezone
from types import SimpleNamespace

from django.test import SimpleTestCase

from broadcast.adapters import _helpers as h
from broadcast.adapters import get_adapter
from broadcast.schema import CanonicalEvent, event_from_submission

RECIPE_KEYS = ["triangle_on_the_cheap", "triangle_weekender", "abc11_community", "chatham_arts"]

VALID_TYPES = {
    "text", "textarea", "date", "time", "select",
    "radio", "checkbox", "file", "select2", "select2_multi", "react_select",
    "terms", "manual_widget",
}


def _event(**over):
    base = dict(
        title="Jazz Night",
        description="An evening of jazz.",
        start_datetime=datetime(2026, 6, 20, 19, 0),
        end_datetime=datetime(2026, 6, 20, 22, 0),
        venue_name="Acme Hall",
        address_line1="1 Main St",
        zip="27312",
        locality=["pittsboro"],
        event_url="https://example.com/jazz",
        organizer_name="Acme Org",
        image_url="https://example.com/jazz.jpg",
    )
    base.update(over)
    return CanonicalEvent(**base)


def _selectors(recipe):
    return {f["selector"] for f in recipe["fields"]}


class RecipeShapeTest(SimpleTestCase):
    def test_recipe_well_formed(self):
        ev = _event()
        for key in RECIPE_KEYS:
            recipe = get_adapter(key).recipe(ev)
            self.assertEqual(recipe["site_key"], key)
            self.assertTrue(recipe["url"])
            self.assertTrue(recipe["submit_selector"], f"{key} missing submit_selector")
            self.assertTrue(recipe["fields"], f"{key} has no fields")
            for field in recipe["fields"]:
                self.assertIn(field["type"], VALID_TYPES)
                self.assertIsInstance(field["selector"], str)
                self.assertIsInstance(field["value"], str)
                self.assertIsInstance(field["required"], bool)
                self.assertTrue(field["selector"])
                self.assertTrue(field["hint"] is None or isinstance(field["hint"], str))

    def test_required_fields_resolved(self):
        recipe = get_adapter("triangle_on_the_cheap").recipe(_event())
        title = next(f for f in recipe["fields"] if f["selector"] == "#input_5_6")
        self.assertTrue(title["required"])
        self.assertEqual(title["value"], "Jazz Night")


class HoneypotTest(SimpleTestCase):
    def test_honeypot_never_in_recipe(self):
        recipe = get_adapter("triangle_on_the_cheap").recipe(_event())
        self.assertNotIn("#input_5_26", _selectors(recipe))


class ConditionalFieldsTest(SimpleTestCase):
    def test_weekender_times_only_when_not_all_day(self):
        timed = _selectors(get_adapter("triangle_weekender").recipe(_event(all_day=False)))
        self.assertIn("#EventStartTime", timed)
        self.assertIn("#EventEndTime", timed)

        all_day = _selectors(get_adapter("triangle_weekender").recipe(_event(all_day=True)))
        self.assertNotIn("#EventStartTime", all_day)
        self.assertNotIn("#EventEndTime", all_day)

    def test_on_the_cheap_image_field_tracks_image_url(self):
        with_img = _selectors(get_adapter("triangle_on_the_cheap").recipe(_event()))
        self.assertIn("#input_5_19", with_img)

        without_img = _selectors(
            get_adapter("triangle_on_the_cheap").recipe(_event(image_url=""))
        )
        self.assertNotIn("#input_5_19", without_img)

    def test_empty_optional_plain_field_dropped(self):
        # No contact phone → abc11's optional Contact Phone field is omitted.
        recipe = get_adapter("abc11_community").recipe(_event(contact_phone=""))
        self.assertNotIn("#cf34384", _selectors(recipe))

    def test_terms_always_emitted_even_though_recipe_only(self):
        recipe = get_adapter("triangle_weekender").recipe(_event())
        terms = next(f for f in recipe["fields"] if f["selector"] == "#terms")
        self.assertEqual(terms["type"], "terms")
        self.assertTrue(terms["required"])

    def test_weekender_category_field_emitted_when_categories_present(self):
        # select2_multi category field must appear when ev.categories has slugs
        # and carry the comma-joined search terms.
        recipe = get_adapter("triangle_weekender").recipe(
            _event(categories=["music", "arts", "festival"])
        )
        cat = next(
            (f for f in recipe["fields"]
             if f["selector"] == "select[name='tax_input[tribe_events_cat][]']"),
            None,
        )
        self.assertIsNotNone(cat, "weekender category select2_multi field missing")
        self.assertEqual(cat["type"], "select2_multi")
        self.assertFalse(cat["required"])
        self.assertIn("Music", cat["value"])
        self.assertIn("Arts", cat["value"])
        self.assertIn("Festival", cat["value"])

    def test_weekender_tag_field_emitted_when_categories_present(self):
        recipe = get_adapter("triangle_weekender").recipe(
            _event(categories=["music"])
        )
        tag = next(
            (f for f in recipe["fields"]
             if f["selector"] == "select[name='tax_input[post_tag][]']"),
            None,
        )
        self.assertIsNotNone(tag, "weekender tag select2_multi field missing")
        self.assertEqual(tag["type"], "select2_multi")
        self.assertIn("Music", tag["value"])

    def test_weekender_category_field_absent_when_no_categories(self):
        # select2_multi with empty value is dropped by recipe() — not required
        # and not in _ALWAYS_EMIT_TYPES.
        recipe = get_adapter("triangle_weekender").recipe(_event(categories=[]))
        selectors = _selectors(recipe)
        self.assertNotIn("select[name='tax_input[tribe_events_cat][]']", selectors)
        self.assertNotIn("select[name='tax_input[post_tag][]']", selectors)

    def test_chatham_arts_category_field_emitted_when_categories_present(self):
        recipe = get_adapter("chatham_arts").recipe(
            _event(categories=["arts", "literary"])
        )
        cat = next(
            (f for f in recipe["fields"]
             if f["selector"] == "select[name='tax_input[tribe_events_cat][]']"),
            None,
        )
        self.assertIsNotNone(cat, "chatham_arts category select2_multi field missing")
        self.assertEqual(cat["type"], "select2_multi")
        self.assertIn("Arts", cat["value"])
        self.assertIn("Literary", cat["value"])


def _submission(start_utc, end_utc=None, all_day=False):
    """Minimal duck-typed submission row for event_from_submission."""
    return SimpleNamespace(
        title="t", description="d",
        start_datetime=start_utc, end_datetime=end_utc, all_day=all_day,
        venue_name="V", address_line1="A", state="NC", zip="27312",
        locality=["pittsboro"], categories=[], event_url="", ticket_url="",
        price="", is_free=True, image_url="", organizer_name="",
        contact_email="", contact_phone="",
    )


class TimezoneTest(SimpleTestCase):
    def test_utc_storage_formats_as_eastern_wall_clock(self):
        # 4pm Eastern (EDT) is stored as 20:00 UTC; it must render as 4:00 PM.
        sub = _submission(datetime(2026, 7, 10, 20, 0, tzinfo=timezone.utc))
        ev = event_from_submission(sub)
        self.assertEqual(h.format_time(ev.start_datetime), "4:00 PM")

    def test_eastern_conversion_can_shift_the_date(self):
        # 11pm Eastern on the 10th is 03:00 UTC on the 11th — the date must
        # follow the local day, not the UTC day.
        sub = _submission(datetime(2026, 7, 11, 3, 0, tzinfo=timezone.utc))
        ev = event_from_submission(sub)
        self.assertEqual(h.format_date(ev.start_datetime), "07/10/2026")
        self.assertEqual(h.format_time(ev.start_datetime), "11:00 PM")

    def test_recipe_time_value_is_local(self):
        sub = _submission(datetime(2026, 7, 10, 20, 0, tzinfo=timezone.utc))
        recipe = get_adapter("triangle_on_the_cheap").recipe(event_from_submission(sub))
        start = next(f for f in recipe["fields"] if f["selector"] == "#input_5_10")
        self.assertEqual(start["value"], "4:00 PM")
