"""Tests for AI autofill endpoint and extract_event_fields helper.

Fast tier: StripFencesTest, CoerceTest, ExtractEventFieldsTest (no DB).
DB tier: AutofillViewTest (permission layer requires DB for access resolution).
All Gemini network calls are mocked.
"""

import json
from types import SimpleNamespace
from unittest import mock
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, TestCase, override_settings
from django.test import tag
from rest_framework.test import APIClient

from broadcast.access import hash_code
from broadcast.autofill import _coerce, _strip_fences, extract_event_fields
from broadcast.models import AccessCode, BroadcastAccess

_GOOD_RESPONSE = {
    "title": "Jazz Night at The Plant",
    "description": "Live jazz in a beautiful venue.",
    "start_datetime": "2026-08-15T19:30",
    "end_datetime": "2026-08-15T22:00",
    "all_day": False,
    "venue_name": "The Plant",
    "address_line1": "220 Lorax Ln",
    "state": "NC",
    "zip": "27312",
    "locality": ["pittsboro"],
    "categories": ["music", "nightlife"],
    "event_url": "https://example.com/jazz",
    "ticket_url": "",
    "price": "$10",
    "is_free": False,
    "image_url": "",
    "organizer_name": "Makrs Events",
    "contact_email": "info@example.com",
    "contact_phone": "",
}


def _make_genai_response(payload: dict):
    return SimpleNamespace(text=json.dumps(payload))


def _make_genai_response_text(text: str):
    return SimpleNamespace(text=text)


def _patch_jwt(email):
    return mock.patch("broadcast.access.verify_better_auth_jwt", return_value={"email": email})


@tag("fast")
class StripFencesTest(SimpleTestCase):
    def test_no_fences(self):
        self.assertEqual(_strip_fences('{"a": 1}'), '{"a": 1}')

    def test_json_fences(self):
        raw = '```json\n{"a": 1}\n```'
        self.assertEqual(_strip_fences(raw), '{"a": 1}')

    def test_plain_fences(self):
        raw = '```\n{"a": 1}\n```'
        self.assertEqual(_strip_fences(raw), '{"a": 1}')

    def test_leading_trailing_whitespace(self):
        raw = '  ```json\n{"a": 1}\n```  '
        self.assertEqual(_strip_fences(raw), '{"a": 1}')


@tag("fast")
class CoerceTest(SimpleTestCase):
    def test_all_keys_present_with_defaults_on_empty(self):
        result = _coerce({})
        for key in (
            "title",
            "description",
            "start_datetime",
            "end_datetime",
            "all_day",
            "venue_name",
            "address_line1",
            "state",
            "zip",
            "locality",
            "categories",
            "event_url",
            "ticket_url",
            "price",
            "is_free",
            "image_url",
            "organizer_name",
            "contact_email",
            "contact_phone",
        ):
            self.assertIn(key, result)

    def test_invalid_locality_slugs_filtered(self):
        result = _coerce({"locality": ["pittsboro", "asheville", "invalid-place"]})
        self.assertEqual(result["locality"], ["pittsboro"])

    def test_invalid_category_slugs_filtered(self):
        result = _coerce({"categories": ["music", "notacategory", "xyz"]})
        self.assertEqual(result["categories"], ["music"])

    def test_all_day_coerced_to_bool(self):
        self.assertTrue(_coerce({"all_day": 1})["all_day"])
        self.assertFalse(_coerce({"all_day": 0})["all_day"])

    def test_is_free_coerced_to_bool(self):
        self.assertTrue(_coerce({"is_free": True})["is_free"])
        self.assertFalse(_coerce({"is_free": False})["is_free"])

    def test_state_defaults_to_nc(self):
        self.assertEqual(_coerce({})["state"], "NC")

    def test_state_truncated_to_2_chars(self):
        # Shouldn't happen in practice but we guard it
        result = _coerce({"state": "NCX"})
        self.assertEqual(result["state"], "NC")

    def test_empty_string_datetime_preserved(self):
        result = _coerce({"start_datetime": "", "end_datetime": None})
        self.assertEqual(result["start_datetime"], "")
        self.assertEqual(result["end_datetime"], "")

    def test_valid_datetime_string_preserved(self):
        result = _coerce({"start_datetime": "2026-08-15T19:30"})
        self.assertEqual(result["start_datetime"], "2026-08-15T19:30")


@tag("fast")
class ExtractEventFieldsTest(SimpleTestCase):
    def _mock_client(self, response_payload):
        fake_response = _make_genai_response(response_payload)
        mock_client_instance = MagicMock()
        mock_client_instance.models.generate_content.return_value = fake_response
        return mock_client_instance

    @override_settings(GEMINI_API_KEY="test")
    def test_happy_path_maps_fields(self):
        client_inst = self._mock_client(_GOOD_RESPONSE)
        with patch("broadcast.autofill.genai.Client", return_value=client_inst):
            result = extract_event_fields("Jazz night this Saturday at The Plant")
        self.assertEqual(result["title"], "Jazz Night at The Plant")
        self.assertEqual(result["locality"], ["pittsboro"])
        self.assertEqual(result["categories"], ["music", "nightlife"])
        self.assertEqual(result["start_datetime"], "2026-08-15T19:30")
        self.assertEqual(result["state"], "NC")
        self.assertFalse(result["is_free"])

    @override_settings(GEMINI_API_KEY="test")
    def test_invalid_locality_slugs_filtered(self):
        payload = dict(_GOOD_RESPONSE, locality=["pittsboro", "nowhere", "bogus"])
        client_inst = self._mock_client(payload)
        with patch("broadcast.autofill.genai.Client", return_value=client_inst):
            result = extract_event_fields("some event text")
        self.assertEqual(result["locality"], ["pittsboro"])

    @override_settings(GEMINI_API_KEY="test")
    def test_invalid_category_slugs_filtered(self):
        payload = dict(_GOOD_RESPONSE, categories=["music", "fakecategory"])
        client_inst = self._mock_client(payload)
        with patch("broadcast.autofill.genai.Client", return_value=client_inst):
            result = extract_event_fields("some event text")
        self.assertEqual(result["categories"], ["music"])

    @override_settings(GEMINI_API_KEY="test")
    def test_code_fence_wrapped_json_parses(self):
        fenced = "```json\n" + json.dumps(_GOOD_RESPONSE) + "\n```"
        fake_response = _make_genai_response_text(fenced)
        mock_client_instance = MagicMock()
        mock_client_instance.models.generate_content.return_value = fake_response
        with patch("broadcast.autofill.genai.Client", return_value=mock_client_instance):
            result = extract_event_fields("some event text")
        self.assertEqual(result["title"], _GOOD_RESPONSE["title"])

    @override_settings(GEMINI_API_KEY="test")
    def test_all_keys_present_in_result(self):
        client_inst = self._mock_client(_GOOD_RESPONSE)
        with patch("broadcast.autofill.genai.Client", return_value=client_inst):
            result = extract_event_fields("some event text")
        for key in (
            "title",
            "description",
            "start_datetime",
            "end_datetime",
            "all_day",
            "venue_name",
            "address_line1",
            "state",
            "zip",
            "locality",
            "categories",
            "event_url",
            "ticket_url",
            "price",
            "is_free",
            "image_url",
            "organizer_name",
            "contact_email",
            "contact_phone",
        ):
            self.assertIn(key, result, f"missing key: {key}")

    @override_settings(GEMINI_API_KEY="test")
    def test_llm_exception_propagates_as_runtime_error(self):
        mock_client_instance = MagicMock()
        mock_client_instance.models.generate_content.side_effect = RuntimeError("boom")
        with patch("broadcast.autofill.genai.Client", return_value=mock_client_instance):
            with self.assertRaises(RuntimeError):
                extract_event_fields("some event text")

    @override_settings(GEMINI_API_KEY="test")
    def test_unparseable_response_raises_runtime_error(self):
        fake_response = _make_genai_response_text("not json at all")
        mock_client_instance = MagicMock()
        mock_client_instance.models.generate_content.return_value = fake_response
        with patch("broadcast.autofill.genai.Client", return_value=mock_client_instance):
            with self.assertRaises(RuntimeError):
                extract_event_fields("some event text")


@tag("db")
@override_settings(RATELIMIT_ENABLE=False)
class AutofillViewTest(TestCase):
    """View-level tests for ai_autofill — require DB for permission resolution.

    ai_autofill is tier-2 gated. JWT path uses a BroadcastAccess row + mocked
    JWT verification. Code path uses an AccessCode row.
    """

    def setUp(self):
        self.client = APIClient()
        BroadcastAccess.objects.create(email="tier2@example.com", tier=2)
        BroadcastAccess.objects.create(email="tier1@example.com", tier=1)

    def _post_jwt(self, body, email="tier2@example.com"):
        with _patch_jwt(email):
            return self.client.post(
                "/broadcast/ai-autofill",
                body,
                format="json",
                HTTP_AUTHORIZATION="Bearer faketoken",
            )

    def test_blank_text_returns_400(self):
        resp = self._post_jwt({"text": ""})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("text", resp.json())

    def test_whitespace_only_text_returns_400(self):
        resp = self._post_jwt({"text": "   \n\t  "})
        self.assertEqual(resp.status_code, 400)

    def test_missing_text_key_returns_400(self):
        resp = self._post_jwt({})
        self.assertEqual(resp.status_code, 400)

    def test_no_credentials_returns_403(self):
        resp = self.client.post(
            "/broadcast/ai-autofill",
            {"text": "some event"},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_tier1_jwt_denied_on_ai_autofill(self):
        resp = self._post_jwt({"text": "some event"}, email="tier1@example.com")
        self.assertEqual(resp.status_code, 403)

    def test_tier2_jwt_allowed_on_ai_autofill(self):
        with patch("broadcast.views.extract_event_fields", return_value=dict(_GOOD_RESPONSE)):
            resp = self._post_jwt({"text": "Jazz night this Saturday at The Plant"})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("event", resp.json())

    def test_tier2_access_code_allowed_on_ai_autofill(self):
        AccessCode.objects.create(
            code_hash=hash_code("TIER2CODE"),
            label="testop",
            tier=2,
            max_uses=None,
        )
        with patch("broadcast.views.extract_event_fields", return_value=dict(_GOOD_RESPONSE)):
            resp = self.client.post(
                "/broadcast/ai-autofill",
                {"access_code": "TIER2CODE", "text": "Jazz night at The Plant"},
                format="json",
            )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("event", resp.json())

    def test_tier1_access_code_denied_on_ai_autofill(self):
        AccessCode.objects.create(
            code_hash=hash_code("TIER1CODE"),
            label="tier1client",
            tier=1,
            max_uses=None,
        )
        resp = self.client.post(
            "/broadcast/ai-autofill",
            {"access_code": "TIER1CODE", "text": "some event"},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

    @override_settings(GEMINI_API_KEY="test")
    def test_happy_path_returns_event_dict(self):
        with patch("broadcast.views.extract_event_fields", return_value=dict(_GOOD_RESPONSE)):
            resp = self._post_jwt({"text": "Jazz night this Saturday at The Plant"})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("event", body)
        self.assertEqual(body["event"]["title"], "Jazz Night at The Plant")

    @override_settings(GEMINI_API_KEY="test")
    def test_llm_failure_returns_502(self):
        with patch("broadcast.views.extract_event_fields", side_effect=RuntimeError("llm down")):
            resp = self._post_jwt({"text": "Jazz night at The Plant"})
        self.assertEqual(resp.status_code, 502)
        self.assertIn("error", resp.json())

    def test_access_code_via_header(self):
        AccessCode.objects.create(
            code_hash=hash_code("HEADERCODE"),
            label="testop",
            tier=2,
            max_uses=None,
        )
        with patch("broadcast.views.extract_event_fields", return_value=dict(_GOOD_RESPONSE)):
            resp = self.client.post(
                "/broadcast/ai-autofill",
                {"text": "Jazz night this Saturday"},
                format="json",
                HTTP_X_BROADCAST_ACCESS_CODE="HEADERCODE",
            )
        self.assertEqual(resp.status_code, 200)
