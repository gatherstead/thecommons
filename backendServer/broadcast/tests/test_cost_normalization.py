"""Ticket 46.5: broadcast Price is free text on The Commons but destination
sites (Triangle Weekender, ABC11) want a bare number in their Cost field — a
range like "5-10" got forwarded verbatim and was rejected/mis-rendered. These
cover the shared `_helpers.format_cost` normalizer and confirm both adapters'
recipes route the Cost field through it. No DB — pure adapter logic."""

from datetime import datetime

from django.test import SimpleTestCase, tag

from broadcast.adapters import _helpers as h
from broadcast.adapters import get_adapter
from broadcast.schema import CanonicalEvent


@tag("fast")
class FormatCostTest(SimpleTestCase):
    def test_free_flag_wins_regardless_of_price_text(self):
        self.assertEqual(h.format_cost(True, "5-10"), "0")
        self.assertEqual(h.format_cost(True, ""), "0")

    def test_free_text_without_flag(self):
        self.assertEqual(h.format_cost(False, "This event is free"), "0")
        self.assertEqual(h.format_cost(False, "Free"), "0")
        self.assertEqual(h.format_cost(False, "FREE!"), "0")

    def test_range_takes_the_low_value(self):
        self.assertEqual(h.format_cost(False, "5-10"), "5")
        self.assertEqual(h.format_cost(False, "$5 - $10"), "5")
        self.assertEqual(h.format_cost(False, "5–10"), "5")  # en dash
        self.assertEqual(h.format_cost(False, "  5 - 10  "), "5")

    def test_single_value(self):
        self.assertEqual(h.format_cost(False, "$12"), "12")
        self.assertEqual(h.format_cost(False, "12"), "12")
        self.assertEqual(h.format_cost(False, "  $12.50 "), "12.50")

    def test_empty_input_passes_through_as_empty(self):
        self.assertEqual(h.format_cost(False, ""), "")
        self.assertEqual(h.format_cost(False, "   "), "")

    def test_non_numeric_junk_passes_through_unchanged(self):
        self.assertEqual(h.format_cost(False, "TBD"), "TBD")
        self.assertEqual(h.format_cost(False, "call for pricing"), "call for pricing")


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
    )
    base.update(over)
    return CanonicalEvent(**base)


@tag("fast")
class AdapterCostFieldTest(SimpleTestCase):
    """Confirm both in-scope adapters' recipes emit the normalized value, not
    the raw price string — and that CanonicalEvent.price itself is untouched."""

    def _cost_value(self, site_key, selector, ev):
        recipe = get_adapter(site_key).recipe(ev)
        field = next(f for f in recipe["fields"] if f["selector"] == selector)
        return field["value"]

    def test_triangle_weekender_range_emits_low_value(self):
        ev = _event(price="5-10", is_free=False)
        self.assertEqual(self._cost_value("triangle_weekender", "#EventCost", ev), "5")
        self.assertEqual(ev.price, "5-10")  # raw string untouched

    def test_abc11_range_emits_low_value(self):
        ev = _event(price="5-10", is_free=False)
        self.assertEqual(self._cost_value("abc11_community", "#cf33293", ev), "5")
        self.assertEqual(ev.price, "5-10")

    def test_triangle_weekender_free_emits_zero(self):
        ev = _event(price="", is_free=True)
        self.assertEqual(self._cost_value("triangle_weekender", "#EventCost", ev), "0")

    def test_abc11_free_emits_zero(self):
        ev = _event(price="", is_free=True)
        self.assertEqual(self._cost_value("abc11_community", "#cf33293", ev), "0")

    def test_triangle_weekender_dollar_amount_emits_bare_number(self):
        ev = _event(price="$12", is_free=False)
        self.assertEqual(self._cost_value("triangle_weekender", "#EventCost", ev), "12")

    def test_abc11_dollar_amount_emits_bare_number(self):
        ev = _event(price="$12", is_free=False)
        self.assertEqual(self._cost_value("abc11_community", "#cf33293", ev), "12")
