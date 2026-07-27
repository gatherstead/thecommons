from unittest import mock

from django.http import Http404
from django.test import RequestFactory, TransactionTestCase, override_settings, tag

from devtools.views import probe_stream
from ingestion.importers.errors import (
    REFUSAL_EMPTY_FETCH,
    REFUSAL_NON_PUBLIC_URL,
    REFUSAL_UNKNOWN_SCRAPER_KEY,
)
from ingestion.models import EventSource, RawEvent, StagedEvent

try:
    from ingestion.models import SourceRun

    HAS_SOURCE_RUN = True
except ImportError:  # pragma: no cover - depends on a parallel agent's migration
    HAS_SOURCE_RUN = False

_ICS_BODY = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:1@example.com
SUMMARY:Farmers Market
DTSTART:20260801T120000Z
DTEND:20260801T140000Z
END:VEVENT
END:VCALENDAR
"""


class _FakeResponse:
    def __init__(self, text="", status_code=200):
        self.text = text
        self.content = text.encode()
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")


class _FakeScraperItem:
    def __init__(self, title):
        self.title = title


class _FakeScraper:
    key = "fake"
    wait_selector = None

    def extract(self, html):
        return [_FakeScraperItem("Concert in the Park"), _FakeScraperItem("Art Walk")]


@tag("db")
class ProbeStreamViewTests(TransactionTestCase):
    """Exercises the probe_stream SSE view directly via RequestFactory.

    devtools/ URLs only mount when settings.DEBUG is True, and
    override_settings doesn't reload the URLConf mid-test, so calling the
    view function directly sidesteps routing — same approach as
    test_monitor_view_db.py / test_add_source_db.py.

    TransactionTestCase (not TestCase): probe_stream runs its fetch/parse
    work on a background thread, which opens its own DB connection to look
    up the EventSource. A plain TestCase wraps each test in an outer
    transaction that only the test's own connection can see, so the worker
    thread's `EventSource.objects.using(db).get(...)` would find nothing.
    TransactionTestCase commits real rows that a second connection can read.
    """

    def setUp(self):
        self.factory = RequestFactory()

    def _get(self, params):
        return self.factory.get("/devtools/probe", params)

    def _consume(self, resp):
        """Drain a StreamingHttpResponse into a list of (event, data) frames."""
        import json

        frames = []
        raw = b"".join(resp.streaming_content).decode()
        for block in raw.split("\n\n"):
            if not block.strip():
                continue
            event_line, data_line = block.split("\n", 1)
            event = event_line.removeprefix("event: ")
            data = json.loads(data_line.removeprefix("data: "))
            frames.append((event, data))
        return frames

    def _assert_no_writes(self, source):
        self.assertEqual(RawEvent.objects.filter(source=source).count(), 0)
        self.assertEqual(StagedEvent.objects.filter(raw_event__source=source).count(), 0)
        if HAS_SOURCE_RUN:
            self.assertEqual(SourceRun.objects.filter(source=source).count(), 0)
        source.refresh_from_db()
        self.assertIsNone(source.last_polled)

    @override_settings(DEBUG=False)
    def test_prod_guard_returns_404(self):
        with self.assertRaises(Http404):
            probe_stream(self._get({"source_id": "1"}))

    @override_settings(DEBUG=True)
    def test_missing_source_id_yields_error_frame(self):
        resp = probe_stream(self._get({}))
        frames = self._consume(resp)
        self.assertEqual(frames[0][0], "error")

    @override_settings(DEBUG=True)
    def test_unknown_source_id_yields_error_frame_not_500(self):
        resp = probe_stream(self._get({"source_id": "999999"}))
        frames = self._consume(resp)
        kinds = [k for k, _ in frames]
        self.assertIn("error", kinds)

    @override_settings(DEBUG=True)
    @mock.patch("devtools.views.requests.get")
    def test_ics_source_streams_stages_and_terminates(self, mock_get):
        source = EventSource.objects.create(
            name="ICS Test",
            source_type="ics",
            url="https://example.com/feed.ics",
        )
        mock_get.return_value = _FakeResponse(text=_ICS_BODY, status_code=200)

        with mock.patch("devtools.views._validate_url"):
            resp = probe_stream(self._get({"source_id": str(source.id)}))
            frames = self._consume(resp)

        kinds = [k for k, _ in frames]
        self.assertIn("resolved", kinds)
        self.assertIn("done", kinds)

        parse_end = next(
            d
            for k, d in frames
            if k == "stage" and d.get("stage") == "parse" and d.get("status") == "end"
        )
        self.assertEqual(parse_end["item_count"], 1)
        self.assertIn("Farmers Market", parse_end["sample_titles"])

        self._assert_no_writes(source)

    @override_settings(DEBUG=True)
    def test_non_public_url_yields_named_refusal(self):
        source = EventSource.objects.create(
            name="Private ICS",
            source_type="ics",
            url="https://example.com/feed.ics",
        )
        # _validate_url isn't mocked here: point at a hostname that legitimately
        # fails the public-address check via DNS/private-IP resolution isn't
        # reliable in CI, so instead patch _validate_url to simulate the guard
        # tripping, exactly as it would for a private/loopback host.
        with mock.patch(
            "devtools.views._validate_url", side_effect=ValueError("Blocked hostname: localhost")
        ):
            resp = probe_stream(self._get({"source_id": str(source.id)}))
            frames = self._consume(resp)

        refusals = [d for k, d in frames if k == "refused"]
        self.assertEqual(len(refusals), 1)
        self.assertEqual(refusals[0]["reason"], REFUSAL_NON_PUBLIC_URL)

        self._assert_no_writes(source)

    @override_settings(DEBUG=True)
    @mock.patch("devtools.views.get_scraper", return_value=None)
    def test_unknown_scraper_key_yields_named_refusal(self, mock_get_scraper):
        source = EventSource.objects.create(
            name="Scraper Test",
            source_type="scraper",
            url="https://example.com/events",
            scraper_key="does_not_exist",
        )
        with mock.patch("devtools.views._validate_url"):
            resp = probe_stream(self._get({"source_id": str(source.id)}))
            frames = self._consume(resp)

        refusals = [d for k, d in frames if k == "refused"]
        self.assertEqual(len(refusals), 1)
        self.assertEqual(refusals[0]["reason"], REFUSAL_UNKNOWN_SCRAPER_KEY)

        self._assert_no_writes(source)

    @override_settings(DEBUG=True)
    @mock.patch("devtools.views.render_page", return_value="")
    @mock.patch("devtools.views.get_scraper", return_value=_FakeScraper())
    def test_scraper_empty_fetch_yields_named_refusal(self, mock_get_scraper, mock_render):
        source = EventSource.objects.create(
            name="Scraper Test",
            source_type="scraper",
            url="https://example.com/events",
            scraper_key="fake",
        )
        with mock.patch("devtools.views._validate_url"):
            resp = probe_stream(self._get({"source_id": str(source.id)}))
            frames = self._consume(resp)

        refusals = [d for k, d in frames if k == "refused"]
        self.assertEqual(len(refusals), 1)
        self.assertEqual(refusals[0]["reason"], REFUSAL_EMPTY_FETCH)

        self._assert_no_writes(source)

    @override_settings(DEBUG=True)
    @mock.patch("devtools.views.render_page", return_value="<html>fake page</html>")
    @mock.patch("devtools.views.get_scraper", return_value=_FakeScraper())
    def test_scraper_source_streams_parsed_titles(self, mock_get_scraper, mock_render):
        source = EventSource.objects.create(
            name="Scraper Test",
            source_type="scraper",
            url="https://example.com/events",
            scraper_key="fake",
        )
        with mock.patch("devtools.views._validate_url"):
            resp = probe_stream(self._get({"source_id": str(source.id)}))
            frames = self._consume(resp)

        parse_end = next(
            d
            for k, d in frames
            if k == "stage" and d.get("stage") == "parse" and d.get("status") == "end"
        )
        self.assertEqual(parse_end["item_count"], 2)
        self.assertEqual(parse_end["sample_titles"], ["Concert in the Park", "Art Walk"])

        self._assert_no_writes(source)

    @override_settings(DEBUG=True)
    @mock.patch("devtools.views.requests.get")
    def test_http_source_uses_requests_not_browser(self, mock_get):
        mock_get.return_value = _FakeResponse(text="<html>fake page</html>", status_code=200)
        source = EventSource.objects.create(
            name="HTTP Test",
            source_type="http",
            url="https://example.com/events",
            scraper_key="fake",
        )
        with (
            mock.patch("devtools.views._validate_url"),
            mock.patch("devtools.views.get_scraper", return_value=_FakeScraper()),
            mock.patch("devtools.views.render_page") as mock_render,
        ):
            resp = probe_stream(self._get({"source_id": str(source.id)}))
            self._consume(resp)
            mock_render.assert_not_called()

        self._assert_no_writes(source)

    @override_settings(DEBUG=True)
    def test_direct_source_yields_nothing_to_poll_refusal(self):
        source = EventSource.objects.create(
            name="Direct Test",
            source_type="direct",
            url="https://example.com/submit",
        )
        resp = probe_stream(self._get({"source_id": str(source.id)}))
        frames = self._consume(resp)

        refusals = [d for k, d in frames if k == "refused"]
        self.assertEqual(len(refusals), 1)
        self.assertEqual(refusals[0]["reason"], "nothing_to_poll")

        self._assert_no_writes(source)

    @override_settings(DEBUG=True)
    def test_email_source_yields_nothing_to_poll_refusal(self):
        source = EventSource.objects.create(
            name="Email Test",
            source_type="email",
            url="https://example.com/inbox",
        )
        resp = probe_stream(self._get({"source_id": str(source.id)}))
        frames = self._consume(resp)

        refusals = [d for k, d in frames if k == "refused"]
        self.assertEqual(len(refusals), 1)
        self.assertEqual(refusals[0]["reason"], "nothing_to_poll")

        self._assert_no_writes(source)

    @override_settings(DEBUG=True)
    @mock.patch("devtools.views.requests.get", side_effect=Exception("boom"))
    def test_unexpected_exception_yields_error_frame_with_traceback(self, mock_get):
        source = EventSource.objects.create(
            name="ICS Test",
            source_type="ics",
            url="https://example.com/feed.ics",
        )
        with mock.patch("devtools.views._validate_url"):
            resp = probe_stream(self._get({"source_id": str(source.id)}))
            frames = self._consume(resp)

        errors = [d for k, d in frames if k == "error"]
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]["exception_class"], "Exception")
        self.assertIn("boom", errors[0]["message"])
        self.assertTrue(errors[0]["traceback"])

        self._assert_no_writes(source)

    @override_settings(DEBUG=True)
    def test_bad_db_param_falls_back_to_default(self):
        source = EventSource.objects.create(
            name="ICS Test",
            source_type="ics",
            url="https://example.com/feed.ics",
        )
        with (
            mock.patch("devtools.views.requests.get") as mock_get,
            mock.patch("devtools.views._validate_url"),
        ):
            mock_get.return_value = _FakeResponse(text=_ICS_BODY, status_code=200)
            resp = probe_stream(self._get({"source_id": str(source.id), "db": "not_a_real_db"}))
            frames = self._consume(resp)

        kinds = [k for k, _ in frames]
        self.assertIn("resolved", kinds)
        self.assertNotIn("error", kinds)
