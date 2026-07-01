import os
from unittest import mock

from django.test import SimpleTestCase, tag

from broadcast.access import resolve_client_label


@tag("fast")
class AccessCodeTest(SimpleTestCase):
    CODES = "makrs:CODE1,theplant:CODE2"

    def test_valid_code_resolves_label(self):
        with mock.patch.dict(os.environ, {"BROADCAST_ACCESS_CODES": self.CODES}):
            self.assertEqual(resolve_client_label("CODE1"), "makrs")
            self.assertEqual(resolve_client_label("CODE2"), "theplant")

    def test_invalid_or_blank_code_rejected(self):
        with mock.patch.dict(os.environ, {"BROADCAST_ACCESS_CODES": self.CODES}):
            self.assertIsNone(resolve_client_label("WRONG"))
            self.assertIsNone(resolve_client_label(""))
            self.assertIsNone(resolve_client_label(None))

    def test_no_codes_configured_rejects_everything(self):
        with mock.patch.dict(os.environ, {"BROADCAST_ACCESS_CODES": ""}):
            self.assertIsNone(resolve_client_label("CODE1"))

    def test_malformed_pairs_ignored(self):
        with mock.patch.dict(os.environ, {"BROADCAST_ACCESS_CODES": "nocolon,ok:GOOD, :bad,empty:"}):
            self.assertEqual(resolve_client_label("GOOD"), "ok")
            self.assertIsNone(resolve_client_label("nocolon"))
