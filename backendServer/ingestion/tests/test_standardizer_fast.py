import json
import unittest
from unittest import mock

from django.test import tag

from ingestion.standardizer import (
    CANCELLED_TITLE_RE,
    MAX_CATEGORIES,
    _coerce_price,
    _coerce_str,
    _extract_categories,
    fetch_page_text,
    infer_categories,
)


@tag("fast")
class FetchPageTextTests(unittest.TestCase):
    """fetch_page_text must short-circuit (no network) for empty/non-http URLs."""

    def test_empty_url_returns_empty_without_network(self):
        with mock.patch("ingestion.standardizer.requests.get") as get:
            self.assertEqual(fetch_page_text(""), "")
        get.assert_not_called()

    def test_non_http_url_returns_empty_without_network(self):
        with mock.patch("ingestion.standardizer.requests.get") as get:
            self.assertEqual(fetch_page_text("ftp://example.com/x"), "")
        get.assert_not_called()

    def test_use_browser_true_renders_via_playwright(self):
        html = "<html><body><script>ignored</script><p>Hello world</p></body></html>"
        with (
            mock.patch("ingestion.standardizer.render_page", return_value=html) as render,
            mock.patch("ingestion.standardizer.requests.get") as get,
        ):
            result = fetch_page_text("https://example.com/event", use_browser=True)
        render.assert_called_once_with("https://example.com/event")
        get.assert_not_called()
        self.assertEqual(result, "Hello world")

    def test_use_browser_false_uses_requests_not_playwright(self):
        resp = mock.Mock()
        resp.text = "<html><body><p>Hi there</p></body></html>"
        resp.raise_for_status = mock.Mock()
        with (
            mock.patch("ingestion.standardizer.requests.get", return_value=resp) as get,
            mock.patch("ingestion.standardizer.render_page") as render,
        ):
            result = fetch_page_text("https://example.com/event")
        self.assertEqual(render.call_count, 0)
        get.assert_called_once()
        self.assertEqual(result, "Hi there")


@tag("fast")
class CoerceStrTests(unittest.TestCase):
    """_coerce_str must fall back on null/missing/blank, not just missing."""

    def test_none_falls_back(self):
        self.assertEqual(_coerce_str(None, "fallback"), "fallback")

    def test_blank_string_falls_back(self):
        self.assertEqual(_coerce_str("   ", "fallback"), "fallback")

    def test_real_value_is_kept(self):
        self.assertEqual(_coerce_str("Concert Night", "fallback"), "Concert Night")


@tag("fast")
class CoercePriceTests(unittest.TestCase):
    """_coerce_price must degrade to the -1 'N/A' sentinel instead of raising."""

    def test_none_returns_sentinel(self):
        self.assertEqual(_coerce_price(None), -1)

    def test_non_numeric_string_returns_sentinel(self):
        self.assertEqual(_coerce_price("$10"), -1)

    def test_numeric_string_is_coerced(self):
        self.assertEqual(_coerce_price("15"), 15)

    def test_int_and_float_pass_through(self):
        self.assertEqual(_coerce_price(0), 0)
        self.assertEqual(_coerce_price(12.5), 12.5)

    def test_overflow_value_returns_sentinel(self):
        self.assertEqual(_coerce_price(10**9), -1)


@tag("fast")
class CancelledTitleRegexTests(unittest.TestCase):
    """CANCELLED_TITLE_RE must match both spellings plus common typographic
    variants (asterisks, en/em dash, colon) regardless of surrounding text,
    since it's matched with `.search`, not `.fullmatch`."""

    def test_matches_asterisk_wrapped(self):
        self.assertIsNotNone(CANCELLED_TITLE_RE.search("*CANCELLED*"))

    def test_matches_en_dash_form(self):
        self.assertIsNotNone(CANCELLED_TITLE_RE.search("Canceled – Fall Festival"))

    def test_matches_em_dash_form(self):
        self.assertIsNotNone(CANCELLED_TITLE_RE.search("Canceled — Fall Festival"))

    def test_matches_colon_form(self):
        self.assertIsNotNone(CANCELLED_TITLE_RE.search("CANCELED: Movie Night"))

    def test_matches_double_l_spelling(self):
        self.assertIsNotNone(CANCELLED_TITLE_RE.search("Event Cancelled"))

    def test_matches_single_l_spelling(self):
        self.assertIsNotNone(CANCELLED_TITLE_RE.search("Event Canceled"))

    def test_no_match_on_clean_title(self):
        self.assertIsNone(CANCELLED_TITLE_RE.search("Fall Festival on the Green"))


@tag("fast")
class ExtractCategoriesTests(unittest.TestCase):
    """_extract_categories must never trust the model's spelling or its
    adherence to the "at most MAX_CATEGORIES" prompt instruction."""

    def test_valid_categories_kept(self):
        data = {"categories": ["music", "food-drink"]}
        self.assertEqual(_extract_categories(data), ["music", "food-drink"])

    def test_invalid_categories_dropped(self):
        data = {"categories": ["music", "not-a-real-category"]}
        self.assertEqual(_extract_categories(data), ["music"])

    def test_missing_key_returns_empty_list(self):
        self.assertEqual(_extract_categories({}), [])

    def test_null_value_returns_empty_list(self):
        self.assertEqual(_extract_categories({"categories": None}), [])

    def test_over_cap_list_is_truncated(self):
        # music, art, community are all real slugs; MAX_CATEGORIES caps at 2
        # even though the model returned 3.
        data = {"categories": ["music", "art", "community"]}
        result = _extract_categories(data)
        self.assertEqual(len(result), MAX_CATEGORIES)
        self.assertEqual(result, ["music", "art"])


@tag("fast")
class InferCategoriesFailureTests(unittest.TestCase):
    """infer_categories must never raise — a failed/unparseable Gemini response
    degrades to an empty list so a backfill loop can keep going event-by-event."""

    def test_all_models_failing_returns_empty_list_without_raising(self):
        client = mock.Mock()
        client.models.generate_content.side_effect = Exception("429 RESOURCE_EXHAUSTED")
        with mock.patch("ingestion.standardizer.genai.Client", return_value=client):
            result = infer_categories("Some Event", "Some description")
        self.assertEqual(result, [])

    def test_unparseable_response_returns_empty_list_without_raising(self):
        client = mock.Mock()
        client.models.generate_content.return_value = mock.Mock(text="not json")
        with mock.patch("ingestion.standardizer.genai.Client", return_value=client):
            result = infer_categories("Some Event", "Some description")
        self.assertEqual(result, [])

    def test_successful_response_returns_validated_categories(self):
        client = mock.Mock()
        client.models.generate_content.return_value = mock.Mock(
            text=json.dumps({"categories": ["music", "not-a-real-category"]})
        )
        with mock.patch("ingestion.standardizer.genai.Client", return_value=client):
            result = infer_categories("Jazz Night", "Live jazz downtown.")
        self.assertEqual(result, ["music"])
