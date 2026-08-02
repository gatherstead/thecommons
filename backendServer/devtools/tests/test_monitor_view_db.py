import json
import re
from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.db import OperationalError
from django.http import Http404
from django.test import RequestFactory, TestCase, override_settings, tag
from django.utils import timezone

from devtools.monitoring import (
    RUNS_MISSING_TABLE,
    RUNS_NO_PERMISSION,
    RUNS_UNREACHABLE,
    resolve_source_runs_state,
)
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

    # ── Rendered output: counts, zeros, and the em-dash convention ──────────
    #
    # Nothing rendered `monitor.html` and asserted against it before suite 33,
    # which is how a funnel column that showed every real zero as an em-dash
    # (indistinguishable from a failed page load) shipped unnoticed.

    FUNNEL_CELL_RE = re.compile(r'<td class="num funnel-cell[^"]*">([^<]*)</td>')

    @override_settings(DEBUG=True)
    def test_funnel_counts_are_server_rendered(self):
        # setUp seeds exactly one raw event, unprocessed, with one published
        # staged row — so `raw` is 1, `published` is 1, and the rest are 0.
        # All of it must be in the HTML with no JavaScript run.
        resp = monitor(self._get("/devtools/monitor", {"window": "30d"}))
        cells = self.FUNNEL_CELL_RE.findall(resp.content.decode())

        self.assertTrue(cells, "no funnel cells rendered server-side")
        self.assertIn("1", cells)
        # A blank cell means the template lookup missed entirely — a real bug,
        # and distinguishable from a genuine zero precisely because zeros now
        # render as "0".
        self.assertTrue(all(c.isdigit() for c in cells), cells)

    @override_settings(DEBUG=True)
    def test_zero_counts_render_as_muted_zero_not_a_dash(self):
        content = monitor(self._get("/devtools/monitor", {"window": "30d"})).content.decode()
        self.assertIn('<td class="num funnel-cell zero">0</td>', content)
        self.assertNotIn("—", self.FUNNEL_CELL_RE.findall(content))

    @override_settings(DEBUG=True)
    def test_em_dash_still_marks_a_genuinely_absent_value(self):
        # The seeded source has never polled, so `Last polled` has no value —
        # the one place in these tables the em-dash still belongs.
        content = monitor(self._get("/devtools/monitor", {"window": "30d"})).content.decode()
        self.assertIn("<td>—</td>", content)

    # ── 35.4: zero-in-window vs. zero-ever ──────────────────────────────────

    @override_settings(DEBUG=True)
    def test_never_produced_source_renders_distinct_note(self):
        EventSource.objects.create(
            name="Visit Pittsboro",
            source_type="ics",
            url="https://pittsboro.example.com/feed.ics",
            active=True,
        )
        content = monitor(self._get("/devtools/monitor", {"window": "30d"})).content.decode()
        self.assertIn("never produced a raw event", content)

    @override_settings(DEBUG=True)
    def test_stale_window_source_renders_all_time_count_and_newest_date(self):
        source = EventSource.objects.create(
            name="Carrboro Public Events",
            source_type="ics",
            url="https://carrboro.example.com/feed.ics",
            active=True,
        )
        old = self.now - timedelta(days=75)
        RawEvent.objects.create(source=source, raw_title="Old", raw_start=old, source_uid="old1")
        RawEvent.objects.filter(source=source, source_uid="old1").update(created_at=old)

        content = monitor(self._get("/devtools/monitor", {"window": "30d"})).content.decode()
        self.assertIn("1 all-time", content)
        self.assertIn("widen the window", content)
        self.assertNotIn("never produced a raw event", content)

    # ── 35.10: which database this page is reading must be unambiguous ─────

    # The `.db-banner.db-prod` CSS rule is always present in <style>, so a
    # plain substring check for "db-prod" in the page would pass regardless
    # of which branch rendered — this pulls the class attribute actually
    # applied to the <span class="db-banner ..."> element.
    DB_BANNER_RE = re.compile(r'<span class="db-banner ([^"]*)">')

    @override_settings(DEBUG=True)
    def test_default_db_banner_names_default(self):
        content = monitor(self._get("/devtools/monitor")).content.decode()
        banner_class = self.DB_BANNER_RE.search(content).group(1)
        self.assertEqual(banner_class, "db-default")
        self.assertIn("default (local)", content)

    @override_settings(DEBUG=True)
    def test_prod_readonly_db_banner_names_prod(self):
        content = monitor(self._get("/devtools/monitor", {"db": "prod_readonly"})).content.decode()
        # prod_readonly isn't configured in tests, so `_resolve_db` falls back.
        banner_class = self.DB_BANNER_RE.search(content).group(1)
        self.assertEqual(banner_class, "db-default")

    @override_settings(DEBUG=True)
    def test_prod_readonly_db_banner_when_configured(self):
        # `_resolve_db` only honors `?db=prod_readonly` when that alias is
        # actually configured — simulate configuration by registering the
        # alias (pointed at the same test DB, never actually queried: mocking
        # `resolve_source_runs_state` to `RUNS_UNREACHABLE` short-circuits
        # `monitor()` before either summary query runs, mirroring
        # `_render_with_state` below).
        databases_with_prod = {**settings.DATABASES, "prod_readonly": settings.DATABASES["default"]}
        with (
            override_settings(DATABASES=databases_with_prod),
            patch(
                "devtools.views.monitor.resolve_source_runs_state", return_value=RUNS_UNREACHABLE
            ),
        ):
            content = monitor(
                self._get("/devtools/monitor", {"db": "prod_readonly"})
            ).content.decode()
        banner_class = self.DB_BANNER_RE.search(content).group(1)
        self.assertEqual(banner_class, "db-prod")
        self.assertIn("prod_readonly (read-only)", content)

    # ── Degradation banners ─────────────────────────────────────────────────

    def _render_with_state(self, state):
        with patch("devtools.views.monitor.resolve_source_runs_state", return_value=state):
            resp = monitor(self._get("/devtools/monitor"))
        self.assertEqual(resp.status_code, 200)
        return resp.content.decode()

    @override_settings(DEBUG=True)
    def test_missing_table_banner_names_only_the_migration(self):
        content = self._render_with_state(RUNS_MISSING_TABLE)
        self.assertIn("0014_sourcerun", content)
        self.assertNotIn("GRANT SELECT", content)

    @override_settings(DEBUG=True)
    def test_missing_grant_banner_names_only_the_grant(self):
        # Pre-33.1 this state was undetectable, so the page 500ed instead.
        content = self._render_with_state(RUNS_NO_PERMISSION)
        self.assertIn("GRANT SELECT ON ingestion_sourcerun", content)
        self.assertNotIn("0014_sourcerun", content)

    @override_settings(DEBUG=True)
    def test_unreachable_database_renders_a_banner_not_a_traceback(self):
        content = self._render_with_state(RUNS_UNREACHABLE)
        self.assertIn("reach this database", content)
        # Showing nothing, not zero — the distinction the banner has to make.
        self.assertNotIn('<td class="num funnel-cell zero">0</td>', content)

    @override_settings(DEBUG=True)
    def test_database_dying_mid_render_degrades_to_the_same_banner(self):
        # The probe succeeds, then the connection drops while the summaries
        # run. Previously a raw Django traceback.
        with patch(
            "devtools.views.monitor.collector_summary",
            side_effect=OperationalError("connection closed"),
        ):
            resp = monitor(self._get("/devtools/monitor"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("reach this database", resp.content.decode())

    @override_settings(DEBUG=True)
    def test_availability_is_resolved_once_per_request(self):
        # It used to be resolved four times per render — two summaries, the
        # template context, and the drilldown — each an uncached round trip to
        # Neon on the prod path, all answering the identical question.
        # Both names are patched with the same mock: `views` holds its own
        # reference from the `from .monitoring import ...`, and `_source_rows`
        # resolves through the `monitoring` module global. Patching only one
        # would let a re-resolution through the other go uncounted.
        with (
            patch(
                "devtools.views.monitor.resolve_source_runs_state",
                wraps=resolve_source_runs_state,
            ) as probe,
            patch("devtools.monitoring.resolve_source_runs_state", new=probe),
        ):
            monitor(self._get("/devtools/monitor"))
        self.assertEqual(probe.call_count, 1)

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
        self.assertEqual(data["rows"][0]["source_name"], self.source.name)
        self.assertEqual(data["db"], "default")
        # Ticket 40.5: total/offset/limit ride alongside rows so the client
        # can render "showing X-Y of N".
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["offset"], 0)
        self.assertEqual(data["limit"], 100)

    # ── 40.5: offset + total ────────────────────────────────────────────────

    @override_settings(DEBUG=True)
    def test_monitor_data_offset_and_limit_produce_non_overlapping_pages(self):
        for i in range(4):
            raw = RawEvent.objects.create(
                source=self.source,
                raw_title=f"Extra {i}",
                raw_start=self.now,
                source_uid=f"extra{i}",
            )
            RawEvent.objects.filter(pk=raw.pk).update(created_at=self.now - timedelta(minutes=i))
        # setUp's "Test Raw" plus 4 more here = 5 total in-window rows.
        page_one = json.loads(
            monitor_data(
                self._get(
                    "/devtools/monitor/data",
                    {"kind": "collector", "key": str(self.source.id), "limit": "2", "offset": "0"},
                )
            ).content
        )
        page_two = json.loads(
            monitor_data(
                self._get(
                    "/devtools/monitor/data",
                    {"kind": "collector", "key": str(self.source.id), "limit": "2", "offset": "2"},
                )
            ).content
        )
        self.assertEqual(page_one["total"], 5)
        self.assertEqual(page_two["total"], 5)
        ids_one = {r["raw_id"] for r in page_one["rows"]}
        ids_two = {r["raw_id"] for r in page_two["rows"]}
        self.assertEqual(len(ids_one), 2)
        self.assertEqual(len(ids_two), 2)
        self.assertFalse(ids_one & ids_two)

    @override_settings(DEBUG=True)
    def test_monitor_data_negative_offset_clamps_to_zero(self):
        resp = monitor_data(
            self._get(
                "/devtools/monitor/data",
                {"kind": "collector", "key": str(self.source.id), "offset": "-5"},
            )
        )
        data = json.loads(resp.content)
        # "-5".isdigit() is False, so this falls back to the same 0 default —
        # exercised explicitly since a negative offset must never slice
        # backwards or 500.
        self.assertEqual(data["offset"], 0)
        self.assertEqual(len(data["rows"]), 1)

    # ── 40.5: all-sources mode ───────────────────────────────────────────────

    @override_settings(DEBUG=True)
    def test_monitor_data_collector_empty_key_returns_all_collector_sources(self):
        other = EventSource.objects.create(
            name="Other Collector",
            source_type="scraper",
            url="https://other.example.com/events",
        )
        RawEvent.objects.create(
            source=other, raw_title="Other Raw", raw_start=self.now, source_uid="other1"
        )
        resp = monitor_data(
            self._get("/devtools/monitor/data", {"kind": "collector", "key": "", "window": "30d"})
        )
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        names = {r["source_name"] for r in data["rows"]}
        self.assertEqual(names, {self.source.name, "Other Collector"})
        self.assertEqual(data["total"], 2)

    @override_settings(DEBUG=True)
    def test_monitor_data_inbound_empty_key_excludes_collector_sources(self):
        direct_source = EventSource.objects.create(
            name="Direct Host Submission",
            source_type="direct",
            url="https://commons.local/direct",
            active=False,
        )
        RawEvent.objects.create(
            source=direct_source, raw_title="Direct Raw", raw_start=self.now, source_uid="direct1"
        )
        resp = monitor_data(
            self._get("/devtools/monitor/data", {"kind": "inbound", "key": "", "window": "30d"})
        )
        data = json.loads(resp.content)
        names = {r["source_name"] for r in data["rows"]}
        self.assertEqual(names, {"Direct Host Submission"})
        self.assertNotIn(self.source.name, names)

    @override_settings(DEBUG=True)
    def test_monitor_data_runs_empty_key_returns_empty_not_a_fan_out(self):
        # Run history has no "all sources" mode — it's inherently per-source.
        resp = monitor_data(
            self._get("/devtools/monitor/data", {"kind": "runs", "key": "", "window": "30d"})
        )
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertEqual(data["rows"], [])
        self.assertEqual(data["total"], 0)

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
