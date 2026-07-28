import json
from datetime import timedelta

from django.http import Http404
from django.test import RequestFactory, TestCase, override_settings, tag
from django.utils import timezone

from devtools.views import monitor, monitor_data
from events.tests.factories import make_event
from ingestion.models import EventSource, RawEvent, SourceRun, StagedEvent


@tag("db")
class MonitorViewTests(TestCase):
    """Exercises the monitor/monitor_data views directly via RequestFactory.

    The `devtools/` URLs are only mounted when settings.DEBUG is True
    (backend/urls.py), and override_settings does not reload the URLConf,
    so routing through the test client can't reach the view under the
    test settings. Calling the view function directly sidesteps that,
    mirroring devtools/tests/test_add_source_db.py.
    """

    def setUp(self):
        self.factory = RequestFactory()
        self.now = timezone.now()

        self.source = EventSource.objects.create(
            name="Monitor Test Collector",
            source_type="ics",
            url="https://monitor.example.com/feed.ics",
        )
        raw = RawEvent.objects.create(
            source=self.source, raw_title="Test Raw", raw_start=self.now, source_uid="mt1"
        )
        event = make_event(title="Monitor Published Event")
        StagedEvent.objects.create(
            raw_event=raw,
            title="Test Raw",
            description="d",
            location_name="l",
            town="carrboro",
            start_datetime=self.now,
            status="approved",
            published_event=event,
        )

    def _get(self, path, params=None):
        return self.factory.get(path, params or {})

    @override_settings(DEBUG=True)
    def test_monitor_returns_200_in_debug(self):
        resp = monitor(self._get("/devtools/monitor"))
        self.assertEqual(resp.status_code, 200)

    @override_settings(DEBUG=False)
    def test_monitor_raises_404_when_not_debug(self):
        with self.assertRaises(Http404):
            monitor(self._get("/devtools/monitor"))

    @override_settings(DEBUG=True)
    def test_monitor_renders_real_counts(self):
        resp = monitor(self._get("/devtools/monitor", {"window": "30d"}))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertIn("Monitor Test Collector", content)

    @override_settings(DEBUG=True)
    def test_monitor_data_returns_200_with_rows(self):
        resp = monitor_data(
            self._get(
                "/devtools/monitor/data",
                {"kind": "collector", "key": str(self.source.id), "window": "30d"},
            )
        )
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertIn("rows", data)
        self.assertEqual(len(data["rows"]), 1)
        self.assertEqual(data["rows"][0]["raw_title"], "Test Raw")
        self.assertEqual(data["db"], "default")

    @override_settings(DEBUG=True)
    def test_monitor_data_invalid_kind_returns_400(self):
        resp = monitor_data(self._get("/devtools/monitor/data", {"kind": "bogus"}))
        self.assertEqual(resp.status_code, 400)

    @override_settings(DEBUG=False)
    def test_monitor_data_raises_404_when_not_debug(self):
        with self.assertRaises(Http404):
            monitor_data(self._get("/devtools/monitor/data", {"kind": "collector"}))

    @override_settings(DEBUG=True)
    def test_monitor_data_outbound_all_sites(self):
        resp = monitor_data(
            self._get("/devtools/monitor/data", {"kind": "outbound", "key": "", "window": "30d"})
        )
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertIn("rows", data)

    @override_settings(DEBUG=True)
    def test_monitor_data_bad_db_falls_back_to_default(self):
        resp = monitor_data(
            self._get(
                "/devtools/monitor/data",
                {"kind": "collector", "key": str(self.source.id), "db": "not_a_real_db"},
            )
        )
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertEqual(data["db"], "default")

    @override_settings(DEBUG=True)
    def test_monitor_data_runs_returns_run_history(self):
        SourceRun.objects.create(
            source=self.source,
            started_at=self.now - timedelta(hours=2),
            finished_at=self.now - timedelta(hours=2),
            status="failed",
            trigger="scheduled",
            items_fetched=3,
            items_new=1,
            items_duplicate=2,
            error_message="boom",
        )
        SourceRun.objects.create(
            source=self.source,
            started_at=self.now - timedelta(minutes=5),
            finished_at=self.now - timedelta(minutes=5),
            status="ok",
            trigger="manual",
            items_fetched=5,
            items_new=5,
            items_duplicate=0,
        )
        resp = monitor_data(
            self._get(
                "/devtools/monitor/data",
                {"kind": "runs", "key": str(self.source.id), "window": "30d"},
            )
        )
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        rows = data["rows"]
        self.assertEqual(len(rows), 2)
        # Most recent first.
        self.assertEqual(rows[0]["status"], "ok")
        self.assertEqual(rows[0]["trigger"], "manual")
        self.assertEqual(rows[1]["status"], "failed")
        self.assertEqual(rows[1]["error_message"], "boom")

    @override_settings(DEBUG=True)
    def test_monitor_data_runs_not_windowed_by_start_end(self):
        # Run history is "what has this source been doing", not scoped to
        # the funnel window — an old run outside a narrow window still shows.
        SourceRun.objects.create(
            source=self.source,
            started_at=self.now - timedelta(days=60),
            finished_at=self.now - timedelta(days=60),
            status="ok",
        )
        resp = monitor_data(
            self._get(
                "/devtools/monitor/data",
                {"kind": "runs", "key": str(self.source.id), "window": "7d"},
            )
        )
        data = json.loads(resp.content)
        self.assertEqual(len(data["rows"]), 1)

    @override_settings(DEBUG=True)
    def test_monitor_window_param_narrows_results(self):
        old_raw = RawEvent.objects.create(
            source=self.source,
            raw_title="Old Raw",
            raw_start=self.now,
            source_uid="old1",
        )
        RawEvent.objects.filter(pk=old_raw.pk).update(created_at=self.now - timedelta(days=60))

        resp = monitor_data(
            self._get(
                "/devtools/monitor/data",
                {"kind": "collector", "key": str(self.source.id), "window": "7d"},
            )
        )
        data = json.loads(resp.content)
        titles = [r["raw_title"] for r in data["rows"]]
        self.assertNotIn("Old Raw", titles)
