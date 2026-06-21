import unittest
from unittest import mock

from django.test import tag

from ingestion.standardizer import fetch_page_text


@tag('fast')
class FetchPageTextTests(unittest.TestCase):
    """fetch_page_text must short-circuit (no network) for empty/non-http URLs."""

    def test_empty_url_returns_empty_without_network(self):
        with mock.patch('ingestion.standardizer.requests.get') as get:
            self.assertEqual(fetch_page_text(''), '')
        get.assert_not_called()

    def test_non_http_url_returns_empty_without_network(self):
        with mock.patch('ingestion.standardizer.requests.get') as get:
            self.assertEqual(fetch_page_text('ftp://example.com/x'), '')
        get.assert_not_called()
