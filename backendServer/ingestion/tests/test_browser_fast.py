from unittest import mock

from django.test import SimpleTestCase, tag

from ingestion.scraping.browser import render_page

SENTINEL_HTML = "<html><body>rendered</body></html>"


def _mock_sync_playwright(page):
    """Build a MagicMock standing in for `sync_playwright()` whose `with` block
    yields a fake `p` such that `p.chromium.launch(...).new_context(...).new_page()`
    returns `page`.
    """
    browser = mock.MagicMock()
    browser.new_context.return_value.new_page.return_value = page

    p = mock.MagicMock()
    p.chromium.launch.return_value = browser

    sp = mock.MagicMock()
    sp.__enter__.return_value = p
    return mock.MagicMock(return_value=sp), browser


@tag("fast")
class RenderPageTests(SimpleTestCase):
    def test_returns_rendered_html(self):
        page = mock.MagicMock()
        page.content.return_value = SENTINEL_HTML
        sync_playwright_mock, browser = _mock_sync_playwright(page)

        with mock.patch("ingestion.scraping.browser.sync_playwright", sync_playwright_mock):
            result = render_page("https://example.com")

        self.assertEqual(result, SENTINEL_HTML)
        page.goto.assert_called_once()
        browser.close.assert_called_once()

    def test_error_returns_empty_string_and_closes_browser(self):
        page = mock.MagicMock()
        page.goto.side_effect = RuntimeError("boom")
        sync_playwright_mock, browser = _mock_sync_playwright(page)

        with mock.patch("ingestion.scraping.browser.sync_playwright", sync_playwright_mock):
            result = render_page("https://example.com")

        self.assertEqual(result, "")
        browser.close.assert_called_once()
