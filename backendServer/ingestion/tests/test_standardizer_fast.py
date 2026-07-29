import unittest
from unittest import mock

from django.test import tag

from ingestion.standardizer import _coerce_price, _coerce_str, fetch_page_text


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
