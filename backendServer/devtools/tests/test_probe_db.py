from datetime import timedelta
from unittest import mock

from django.http import Http404
from django.test import RequestFactory, TransactionTestCase, override_settings, tag
from django.utils import timezone

from devtools.views import PROBE_WRITE_SKIPPED_READONLY_DB, probe_stream
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

# _probe_ics drops events whose start is already in the past (mirrors
# fetch_ics_feed). Build the fixture ~1 year out at import time so it can never
# expire the way a hardcoded date does — a fixed DTSTART silently turned this
# into a time-bomb that started failing once real-world time passed it.
_ICS_START = (timezone.now() + timedelta(days=365)).strftime("%Y%m%dT120000Z")
_ICS_END = (timezone.now() + timedelta(days=365)).strftime("%Y%m%dT140000Z")
_ICS_BODY = f"""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:1@example.com
SUMMARY:Farmers Market
DTSTART:{_ICS_START}
DTEND:{_ICS_END}
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
    """Mirrors ingestion/scraping/scrapers/base.py's RawEventData shape —
    the probe's write-dry-run stage (ticket 35.6) now reads every field a
    real scraper item carries, not just `.title`, so the fixture needs to
    carry all of them or the write stage would AttributeError silently
    underneath tests that don't specifically assert on write-stage frames.
    """

    def __init__(self, title, source_uid):
        self.title = title
        self.source_uid = source_uid
        self.description = "A fake event for tests."
        self.location = "Fake Venue"
        self.start = timezone.now() + timedelta(days=7)
        self.end = None
        self.source_url = ""


class _FakeScraper:
    key = "fake"
    wait_selector = None

    def extract(self, html):
        return [
            _FakeScraperItem("Concert in the Park", "concert-1"),
            _FakeScraperItem("Art Walk", "art-walk-1"),
        ]


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
    @mock.patch("devtools.views.probe.requests.get")
    def test_ics_source_streams_stages_and_terminates(self, mock_get):
        source = EventSource.objects.create(
            name="ICS Test",
            source_type="ics",
            url="https://example.com/feed.ics",
        )
        mock_get.return_value = _FakeResponse(text=_ICS_BODY, status_code=200)

        with mock.patch("devtools.views.probe._validate_url"):
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
            "devtools.views.probe._validate_url", side_effect=ValueError("Blocked hostname: localhost")
        ):
            resp = probe_stream(self._get({"source_id": str(source.id)}))
            frames = self._consume(resp)

        refusals = [d for k, d in frames if k == "refused"]
        self.assertEqual(len(refusals), 1)
        self.assertEqual(refusals[0]["reason"], REFUSAL_NON_PUBLIC_URL)

        self._assert_no_writes(source)

    @override_settings(DEBUG=True)
    @mock.patch("devtools.views.probe.get_scraper", return_value=None)
    def test_unknown_scraper_key_yields_named_refusal(self, mock_get_scraper):
        source = EventSource.objects.create(
            name="Scraper Test",
            source_type="scraper",
            url="https://example.com/events",
            scraper_key="does_not_exist",
        )
        with mock.patch("devtools.views.probe._validate_url"):
            resp = probe_stream(self._get({"source_id": str(source.id)}))
            frames = self._consume(resp)

        refusals = [d for k, d in frames if k == "refused"]
        self.assertEqual(len(refusals), 1)
        self.assertEqual(refusals[0]["reason"], REFUSAL_UNKNOWN_SCRAPER_KEY)

        self._assert_no_writes(source)

    @override_settings(DEBUG=True)
    @mock.patch("devtools.views.probe.render_page", return_value="")
    @mock.patch("devtools.views.probe.get_scraper", return_value=_FakeScraper())
    def test_scraper_empty_fetch_yields_named_refusal(self, mock_get_scraper, mock_render):
        source = EventSource.objects.create(
            name="Scraper Test",
            source_type="scraper",
            url="https://example.com/events",
            scraper_key="fake",
        )
        with mock.patch("devtools.views.probe._validate_url"):
            resp = probe_stream(self._get({"source_id": str(source.id)}))
            frames = self._consume(resp)

        refusals = [d for k, d in frames if k == "refused"]
        self.assertEqual(len(refusals), 1)
        self.assertEqual(refusals[0]["reason"], REFUSAL_EMPTY_FETCH)

        self._assert_no_writes(source)

    @override_settings(DEBUG=True)
    @mock.patch("devtools.views.probe.render_page", return_value="<html>fake page</html>")
    @mock.patch("devtools.views.probe.get_scraper", return_value=_FakeScraper())
    def test_scraper_source_streams_parsed_titles(self, mock_get_scraper, mock_render):
        source = EventSource.objects.create(
            name="Scraper Test",
            source_type="scraper",
            url="https://example.com/events",
            scraper_key="fake",
        )
        with mock.patch("devtools.views.probe._validate_url"):
            resp = probe_stream(self._get({"source_id": str(source.id)}))
            frames = self._consume(resp)

        parse_end = next(
            d
            for k, d in frames
            if k == "stage" and d.get("stage") == "parse" and d.get("status") == "end"
        )
        self.assertEqual(parse_end["item_count"], 2)
        self.assertEqual(parse_end["sample_titles"], ["Concert in the Park", "Art Walk"])

        write_end = next(
            d
            for k, d in frames
            if k == "stage" and d.get("stage") == "write" and d.get("status") == "end"
        )
        self.assertEqual(write_end["would_create"], 2)
        self.assertNotIn("error", [k for k, _ in frames])

        self._assert_no_writes(source)

    @override_settings(DEBUG=True)
    @mock.patch("devtools.views.probe.requests.get")
    def test_http_source_uses_requests_not_browser(self, mock_get):
        mock_get.return_value = _FakeResponse(text="<html>fake page</html>", status_code=200)
        source = EventSource.objects.create(
            name="HTTP Test",
            source_type="http",
            url="https://example.com/events",
            scraper_key="fake",
        )
        with (
            mock.patch("devtools.views.probe._validate_url"),
            mock.patch("devtools.views.probe.get_scraper", return_value=_FakeScraper()),
            mock.patch("devtools.views.probe.render_page") as mock_render,
        ):
            resp = probe_stream(self._get({"source_id": str(source.id)}))
            frames = self._consume(resp)
            mock_render.assert_not_called()

        self.assertNotIn("error", [k for k, _ in frames])
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
    @mock.patch("devtools.views.probe.requests.get", side_effect=Exception("boom"))
    def test_unexpected_exception_yields_error_frame_with_traceback(self, mock_get):
        source = EventSource.objects.create(
            name="ICS Test",
            source_type="ics",
            url="https://example.com/feed.ics",
        )
        with mock.patch("devtools.views.probe._validate_url"):
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
            mock.patch("devtools.views.probe.requests.get") as mock_get,
            mock.patch("devtools.views.probe._validate_url"),
        ):
            mock_get.return_value = _FakeResponse(text=_ICS_BODY, status_code=200)
            resp = probe_stream(self._get({"source_id": str(source.id), "db": "not_a_real_db"}))
            frames = self._consume(resp)

        kinds = [k for k, _ in frames]
        self.assertIn("resolved", kinds)
        self.assertNotIn("error", kinds)

    # ── Ticket 35.6: write-path dry run ─────────────────────────────────────

    @override_settings(DEBUG=True)
    @mock.patch("devtools.views.probe.requests.get")
    def test_ics_probe_emits_write_stage_and_leaves_no_rows(self, mock_get):
        """The write stage is new: fetch+parse alone used to be the whole probe,
        which is exactly what let all three collectors probe green during the
        8-day outage while the pipeline was dead downstream of parse. This
        proves the write stage actually runs (not just that no rows survive,
        which the other tests already established) and that DB state is
        provably identical before and after, not merely "assumed empty".
        """
        source = EventSource.objects.create(
            name="ICS Test",
            source_type="ics",
            url="https://example.com/feed.ics",
        )
        mock_get.return_value = _FakeResponse(text=_ICS_BODY, status_code=200)
        raw_count_before = RawEvent.objects.count()
        staged_count_before = StagedEvent.objects.count()

        with mock.patch("devtools.views.probe._validate_url"):
            resp = probe_stream(self._get({"source_id": str(source.id)}))
            frames = self._consume(resp)

        write_frames = [d for k, d in frames if k == "stage" and d.get("stage") == "write"]
        statuses = [d["status"] for d in write_frames]
        self.assertEqual(statuses, ["start", "end"])
        write_end = write_frames[1]
        self.assertEqual(write_end["item_count"], 1)
        self.assertEqual(write_end["would_create"], 1)
        self.assertTrue(write_end["rolled_back"])

        kinds = [k for k, _ in frames]
        self.assertIn("done", kinds)
        self.assertNotIn("error", kinds)

        self.assertEqual(RawEvent.objects.count(), raw_count_before)
        self.assertEqual(StagedEvent.objects.count(), staged_count_before)
        self._assert_no_writes(source)

    @override_settings(DEBUG=True)
    @mock.patch("devtools.views.probe.requests.get")
    def test_write_stage_failure_yields_error_frame_not_done(self, mock_get):
        """A source whose fetch+parse succeed but whose write step fails must
        render a failing frame, not "Done" — that's the entire point of this
        ticket. Patches RawEvent.get_or_create to blow up, standing in for a
        real write-path regression (bad conversion, broken migration, etc.)
        that the old fetch+parse-only probe could never have caught.
        """
        source = EventSource.objects.create(
            name="ICS Test",
            source_type="ics",
            url="https://example.com/feed.ics",
        )
        mock_get.return_value = _FakeResponse(text=_ICS_BODY, status_code=200)

        # RawEvent.objects.using(db) resolves get_or_create fresh on the bound
        # QuerySet each call, so patching the manager's own attribute wouldn't
        # intercept it — patch it at the QuerySet class instead.
        with (
            mock.patch("devtools.views.probe._validate_url"),
            mock.patch(
                "django.db.models.query.QuerySet.get_or_create",
                side_effect=Exception("write boom"),
            ),
        ):
            resp = probe_stream(self._get({"source_id": str(source.id)}))
            frames = self._consume(resp)

        # No successful "write end" frame — the write step raised instead of completing.
        write_end_frames = [
            d
            for k, d in frames
            if k == "stage" and d.get("stage") == "write" and d.get("status") == "end"
        ]
        self.assertEqual(write_end_frames, [])

        errors = [d for k, d in frames if k == "error"]
        self.assertEqual(len(errors), 1)
        self.assertIn("write boom", errors[0]["message"])

        # A write failure still must not leave anything behind.
        self._assert_no_writes(source)

    @override_settings(DEBUG=True)
    @mock.patch("devtools.views.probe._resolve_db", return_value="prod_readonly")
    def test_prod_readonly_skips_write_stage_with_explanatory_frame(self, mock_resolve_db):
        """`prod_readonly` is a genuinely read-only Postgres role — attempting
        a write there wouldn't even reach the rollback, it would just raise
        InsufficientPrivilege. The probe must recognize the alias up front and
        degrade to a clear explanatory frame instead of crashing.

        Patches `_resolve_db` directly rather than actually registering a
        second `prod_readonly` alias: `DATABASES` is one of Django's
        COMPLEX_OVERRIDE_SETTINGS, so `override_settings(DATABASES=...)`
        doesn't reliably rebuild the live `connections` handler mid-test, and
        the thing under test here is the probe's own alias check
        (`db == "prod_readonly"` in `_probe_dry_run_write`), not Django's
        multi-database routing — the source lookup itself still resolves
        against the real (default) test DB, exactly as `_resolve_db` would
        continue to route every other query for this "prod_readonly" value.
        """
        source = EventSource.objects.create(
            name="ICS Test",
            source_type="ics",
            url="https://example.com/feed.ics",
        )

        # `prod_readonly` isn't a registered alias in the test settings (it's
        # popped in backend/settings/test.py), so `EventSource.objects.using(
        # "prod_readonly")` would hit a real ConnectionDoesNotExist before the
        # probe ever reaches the write stage this test is about. Route the
        # source lookup back to the real (default) test DB regardless of the
        # `db` argument it's called with — `_resolve_db` is already mocked
        # above to force "prod_readonly" through, which is what actually
        # drives `_probe_dry_run_write`'s read-only-alias check.
        with (
            mock.patch("devtools.views.probe.requests.get") as mock_get,
            mock.patch("devtools.views.probe._validate_url"),
            mock.patch.object(EventSource.objects, "using", return_value=EventSource.objects),
        ):
            mock_get.return_value = _FakeResponse(text=_ICS_BODY, status_code=200)
            resp = probe_stream(self._get({"source_id": str(source.id)}))
            frames = self._consume(resp)

        write_frames = [d for k, d in frames if k == "stage" and d.get("stage") == "write"]
        statuses = [d["status"] for d in write_frames]
        self.assertEqual(statuses, ["start", "skipped"])
        skipped = write_frames[1]
        self.assertEqual(skipped["reason"], PROBE_WRITE_SKIPPED_READONLY_DB)
        self.assertIn("read-only", skipped["detail"])

        kinds = [k for k, _ in frames]
        self.assertNotIn("error", kinds)
        self.assertIn("done", kinds)
        self._assert_no_writes(source)
