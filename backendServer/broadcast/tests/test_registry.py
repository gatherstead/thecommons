import os
from unittest import mock

from django.test import SimpleTestCase, tag

from broadcast.adapters import _TIER1, get_adapter, registry
from broadcast.adapters.base import SiteAdapter
from broadcast.routing import CATEGORIES, LOCALITIES


@tag("fast")
class RegistryTest(SimpleTestCase):
    def test_tier1_adapters_registered(self):
        expected = {
            "triangle_on_the_cheap", "triangle_weekender",
            "abc11_community", "visit_raleigh", "fun4raleighkids", "chapelboro",
            "explore_pittsboro", "chatham_chamber", "shop_pittsboro", "chatham_arts",
        }
        self.assertEqual(set(registry()), expected)

    def test_keys_match_and_are_unique(self):
        keys = [a.key for a in _TIER1]
        self.assertEqual(len(keys), len(set(keys)))
        for key, adapter in registry().items():
            self.assertEqual(key, adapter.key)
            self.assertIsInstance(adapter, SiteAdapter)

    def test_eligibility_uses_controlled_vocabulary(self):
        for adapter in _TIER1:
            self.assertTrue(adapter.eligibility.localities <= LOCALITIES,
                            f"{adapter.key}: bad localities")
            self.assertTrue(adapter.eligibility.categories <= CATEGORIES,
                            f"{adapter.key}: bad categories")
            self.assertTrue(adapter.submission_url.startswith("https://"))

    def test_mock_only_when_enabled(self):
        with mock.patch.dict(os.environ, {"BROADCAST_ENABLE_MOCK": ""}):
            self.assertIsNone(get_adapter("mock_site"))
        with mock.patch.dict(os.environ, {"BROADCAST_ENABLE_MOCK": "1"}):
            self.assertIsNotNone(get_adapter("mock_site"))

    def test_no_chrome_channel_anywhere(self):
        import pathlib
        root = pathlib.Path(__file__).resolve().parents[1]
        offenders = [
            str(p) for p in root.rglob("*.py")
            if "tests" not in p.parts
            and ('channel="chrome"' in p.read_text() or "channel='chrome'" in p.read_text())
        ]
        self.assertFalse(offenders, f"branded Chrome is unsupported on arm64: {offenders}")
