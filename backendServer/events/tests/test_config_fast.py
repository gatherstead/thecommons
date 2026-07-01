"""Fast tier: configuration guardrails. No database.

These encode the misconfigs that have actually bitten (or could plausibly bite)
production, so CI catches them instead of a live outage. The motivating bug:
DJANGO_ENV unset in prod -> dev.py served in production -> localhost-only
ALLOWED_HOSTS -> every request to the public host returned DisallowedHost (400),
which the frontend rendered as "no events to be displayed".
"""
import unittest

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings, tag

from backend.settings import select_settings_env
from events.management.commands.healthcheck import Command, OK, FAIL


@tag('fast')
class SelectSettingsEnvTests(unittest.TestCase):
    def test_unset_defaults_to_dev(self):
        self.assertEqual(select_settings_env({}), "dev")

    def test_empty_or_whitespace_defaults_to_dev(self):
        self.assertEqual(select_settings_env({"DJANGO_ENV": ""}), "dev")
        self.assertEqual(select_settings_env({"DJANGO_ENV": "   "}), "dev")

    def test_prod_is_selected(self):
        self.assertEqual(select_settings_env({"DJANGO_ENV": "prod"}), "prod")

    def test_case_and_surrounding_whitespace_tolerated(self):
        self.assertEqual(select_settings_env({"DJANGO_ENV": " PROD "}), "prod")
        self.assertEqual(select_settings_env({"DJANGO_ENV": "Dev"}), "dev")

    def test_unrecognized_value_fails_loud(self):
        for bad in ("production", "staging", "PRD", "true"):
            with self.assertRaises(ImproperlyConfigured):
                select_settings_env({"DJANGO_ENV": bad})


@tag('fast')
class HealthcheckConfigProbeTests(SimpleTestCase):
    def _probe(self, require_prod):
        return Command()._check_config(require_prod)

    @override_settings(DEBUG=False, ALLOWED_HOSTS=["api.thecommons.town", "localhost"])
    def test_prod_ok_with_debug_off_and_public_host(self):
        status, name, _ = self._probe(require_prod=True)
        self.assertEqual((status, name), (OK, "config"))

    @override_settings(DEBUG=True, ALLOWED_HOSTS=["localhost", "127.0.0.1"])
    def test_prod_fails_when_dev_settings_leak(self):
        status, _, detail = self._probe(require_prod=True)
        self.assertEqual(status, FAIL)
        self.assertIn("DEBUG=True", detail)

    @override_settings(DEBUG=False, ALLOWED_HOSTS=["localhost", "127.0.0.1"])
    def test_prod_fails_on_localhost_only_allowed_hosts(self):
        status, _, detail = self._probe(require_prod=True)
        self.assertEqual(status, FAIL)
        self.assertIn("localhost-only", detail)

    @override_settings(DEBUG=False, ALLOWED_HOSTS=[])
    def test_prod_fails_on_empty_allowed_hosts(self):
        status, _, _ = self._probe(require_prod=True)
        self.assertEqual(status, FAIL)

    @override_settings(DEBUG=True, ALLOWED_HOSTS=["localhost", "127.0.0.1"])
    def test_dev_run_never_fails(self):
        status, name, _ = self._probe(require_prod=False)
        self.assertEqual((status, name), (OK, "config"))
