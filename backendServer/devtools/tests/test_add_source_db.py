import json
from unittest import mock

from django.http import Http404
from django.test import RequestFactory, TestCase, override_settings, tag

from devtools.views import add_source
from events.models import Event
from ingestion.models import EventSource, RawEvent, StagedEvent


@tag("db")
class AddSourceViewTests(TestCase):
    """Exercises the add_source view directly via RequestFactory.

    The `devtools/` URLs are only mounted when settings.DEBUG is True
    (backend/urls.py), and override_settings does not reload the URLConf,
    so routing through the test client can't reach the view under the
    test settings. Calling the view function directly sidesteps that and
    keeps the test focused on the view's own logic.
    """

    def setUp(self):
        self.factory = RequestFactory()

    def _request(self, data):
        req = self.factory.post("/devtools/add-source", data)
        # RequestFactory (unlike the test client) doesn't disable CSRF, and
        # add_source is @csrf_protect — opt out explicitly.
        req._dont_enforce_csrf_checks = True
        return req

    @override_settings(DEBUG=True)
    @mock.patch("devtools.views._validate_url")
    def test_create_registers_source_no_pipeline(self, mock_validate):
        """Posting a new URL creates exactly one EventSource and zero pipeline rows."""
        resp = add_source(
            self._request(
                {
                    "ics_url": "https://example.com/events.ics",
                    "source_name": "Example Cal",
                    "prompt_suffix": "",
                }
            )
        )
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertTrue(data["created"])
        self.assertEqual(data["name"], "Example Cal")

        self.assertEqual(EventSource.objects.count(), 1)
        self.assertEqual(RawEvent.objects.count(), 0)
        self.assertEqual(StagedEvent.objects.count(), 0)
        self.assertEqual(Event.objects.count(), 0)

    @override_settings(DEBUG=True)
    @mock.patch("devtools.views._validate_url")
    def test_idempotent_same_url_no_duplicate(self, mock_validate):
        """Posting the same URL twice returns created=False on the second call and leaves one row."""
        url = "https://example.com/events.ics"
        add_source(self._request({"ics_url": url, "source_name": "Cal", "prompt_suffix": ""}))

        resp = add_source(
            self._request({"ics_url": url, "source_name": "Cal", "prompt_suffix": ""})
        )
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertFalse(data["created"])
        self.assertEqual(EventSource.objects.count(), 1)

    @override_settings(DEBUG=True)
    @mock.patch("devtools.views._validate_url")
    def test_update_fields_on_repost(self, mock_validate):
        """Re-posting the same URL with a different prompt_suffix/source_name updates the row."""
        url = "https://example.com/events.ics"
        add_source(
            self._request(
                {"ics_url": url, "source_name": "Old Name", "prompt_suffix": "old suffix"}
            )
        )

        add_source(
            self._request(
                {"ics_url": url, "source_name": "New Name", "prompt_suffix": "new suffix"}
            )
        )

        source = EventSource.objects.get(url=url)
        self.assertEqual(source.name, "New Name")
        self.assertEqual(source.prompt_suffix, "new suffix")

    @override_settings(DEBUG=True)
    @mock.patch("devtools.views._validate_url")
    def test_source_name_falls_back_to_hostname(self, mock_validate):
        """When source_name is omitted, the hostname is used as the name."""
        resp = add_source(
            self._request(
                {
                    "ics_url": "https://mycalendar.org/feed.ics",
                    "source_name": "",
                    "prompt_suffix": "",
                }
            )
        )
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertEqual(data["name"], "mycalendar.org")
        source = EventSource.objects.get()
        self.assertEqual(source.name, "mycalendar.org")

    @override_settings(DEBUG=False)
    def test_prod_guard_returns_404(self):
        """The view raises Http404 when DEBUG is False."""
        with self.assertRaises(Http404):
            add_source(
                self._request(
                    {
                        "ics_url": "https://example.com/events.ics",
                        "source_name": "",
                        "prompt_suffix": "",
                    }
                )
            )
