"""Tests for `manage.py probe_sources` (ticket 45.8).

Every test mocks the network (requests.get / the Chromium fetch helper) --
no real outbound request or DNS lookup should happen here. The load-bearing
assertions are: (1) RawEvent/StagedEvent are never touched, (2) exactly one
SourceRun with trigger="probe" is written per probed source, and (3) the WAF-
identifying response headers make it into the stdout summary.
"""

from io import StringIO
from unittest import mock

import requests
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, tag

from ingestion.models import EventSource, RawEvent, SourceRun, StagedEvent

_ICS_BODY = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:1
DTSTART:20260101T120000Z
SUMMARY:Event One
END:VEVENT
BEGIN:VEVENT
UID:2
DTSTART:20260102T120000Z
SUMMARY:Event Two
END:VEVENT
END:VCALENDAR
"""


def _mock_response(status_code=200, headers=None, text=""):
    return mock.Mock(status_code=status_code, headers=headers or {}, text=text)


@tag("db")
class ProbeSourcesCommandTests(TestCase):
    def setUp(self):
        # SSRF guard (`_is_public_url`) does a real DNS lookup -- irrelevant to
        # what this command is being tested for, and the instruction here is
        # "mock the network", so it's stubbed out for every test.
        self.enterContext(
            mock.patch(
                "ingestion.management.commands.probe_sources._is_public_url",
                return_value=True,
            )
        )

    def _no_side_effect_rows(self):
        self.assertEqual(RawEvent.objects.count(), 0)
        self.assertEqual(StagedEvent.objects.count(), 0)

    def test_ics_source_ok_records_probe_run_with_item_count(self):
        source = EventSource.objects.create(
            name="Test Feed", source_type="ics", url="https://feed.test/cal.ics"
        )
        resp = _mock_response(
            200, headers={"Server": "nginx", "cf-ray": "abc123-ord"}, text=_ICS_BODY
        )
        out = StringIO()
        with mock.patch(
            "ingestion.management.commands.probe_sources.requests.get", return_value=resp
        ):
            call_command("probe_sources", "--source", str(source.pk), stdout=out)

        run = SourceRun.objects.get(source=source)
        self.assertEqual(run.trigger, "probe")
        self.assertEqual(run.status, "ok")
        self.assertEqual(run.items_fetched, 2)
        self._no_side_effect_rows()

        output = out.getvalue()
        self.assertIn("OK", output)
        self.assertIn("cf-ray", output)
        self.assertIn("abc123-ord", output)

    def test_non_2xx_status_is_refused_even_with_nonempty_body(self):
        """A WAF challenge/captcha page usually isn't an empty body -- the
        non-2xx status itself, not an empty-fetch check, must be what trips
        the refusal so a blocked source can't masquerade as "ok, 0 items".
        """
        source = EventSource.objects.create(
            name="Blocked HTTP Source",
            source_type="http",
            url="https://blocked.test/events",
            scraper_key="fake-scraper",
        )
        resp = _mock_response(
            403,
            headers={"x-amzn-waf-action": "challenge", "Server": "AmazonS3"},
            text="<html>are you a robot?</html>",
        )
        fake_scraper = mock.Mock()
        out = StringIO()
        with (
            mock.patch(
                "ingestion.management.commands.probe_sources.requests.get", return_value=resp
            ),
            mock.patch(
                "ingestion.management.commands.probe_sources.get_scraper",
                return_value=fake_scraper,
            ),
        ):
            call_command("probe_sources", "--source", str(source.pk), stdout=out)

        run = SourceRun.objects.get(source=source)
        self.assertEqual(run.status, "refused")
        self.assertIn("403", run.error_message)
        fake_scraper.extract.assert_not_called()
        self._no_side_effect_rows()

        output = out.getvalue()
        self.assertIn("REFUSED", output)
        self.assertIn("x-amzn-waf-action", output)
        self.assertIn("challenge", output)

    def test_scraper_source_uses_chromium_fetch_not_requests(self):
        source = EventSource.objects.create(
            name="JS Site",
            source_type="scraper",
            url="https://js-site.test/events",
            scraper_key="fake-scraper",
        )
        fake_scraper = mock.Mock(wait_selector=".event")
        fake_scraper.extract.return_value = [object(), object(), object()]
        out = StringIO()
        with (
            mock.patch(
                "ingestion.management.commands.probe_sources.get_scraper",
                return_value=fake_scraper,
            ),
            mock.patch(
                "ingestion.management.commands.probe_sources._fetch_via_chromium",
                return_value=(200, {"cf-ray": "def456-lax"}, "<html>rendered</html>", None),
            ) as chromium_fetch,
            mock.patch("ingestion.management.commands.probe_sources.requests.get") as requests_get,
        ):
            call_command("probe_sources", "--source", str(source.pk), stdout=out)

        chromium_fetch.assert_called_once_with(source.url, wait_selector=".event")
        requests_get.assert_not_called()

        run = SourceRun.objects.get(source=source)
        self.assertEqual(run.status, "ok")
        self.assertEqual(run.items_fetched, 3)
        self._no_side_effect_rows()

        output = out.getvalue()
        self.assertIn("cf-ray", output)
        self.assertIn("def456-lax", output)

    def test_direct_source_type_is_skipped_without_any_fetch(self):
        source = EventSource.objects.create(
            name="Direct Submission Host",
            source_type="direct",
            url="https://direct.test/submit",
        )
        out = StringIO()
        with (
            mock.patch("ingestion.management.commands.probe_sources.requests.get") as get,
            mock.patch(
                "ingestion.management.commands.probe_sources._fetch_via_chromium"
            ) as chromium,
        ):
            call_command("probe_sources", "--source", str(source.pk), stdout=out)

        get.assert_not_called()
        chromium.assert_not_called()

        run = SourceRun.objects.get(source=source)
        self.assertEqual(run.status, "skipped")
        self.assertEqual(run.trigger, "probe")
        self._no_side_effect_rows()

    def test_unknown_scraper_key_is_refused_before_any_fetch(self):
        source = EventSource.objects.create(
            name="Bad Config Source",
            source_type="http",
            url="https://misconfigured.test/events",
            scraper_key="does-not-exist",
        )
        out = StringIO()
        with mock.patch("ingestion.management.commands.probe_sources.requests.get") as get:
            call_command("probe_sources", "--source", str(source.pk), stdout=out)

        get.assert_not_called()
        run = SourceRun.objects.get(source=source)
        self.assertEqual(run.status, "refused")
        self.assertIn("unknown_scraper_key", run.error_message)

    def test_unparseable_ics_body_is_recorded_as_failed_not_silently_ok(self):
        source = EventSource.objects.create(
            name="Broken Feed", source_type="ics", url="https://broken.test/cal.ics"
        )
        resp = _mock_response(200, headers={}, text="this is not a calendar")
        with mock.patch(
            "ingestion.management.commands.probe_sources.requests.get", return_value=resp
        ):
            call_command("probe_sources", "--source", str(source.pk), stdout=StringIO())

        run = SourceRun.objects.get(source=source)
        self.assertEqual(run.status, "failed")
        self.assertNotEqual(run.error_class, "")
        self._no_side_effect_rows()

    def test_source_flag_with_unknown_id_raises_command_error(self):
        with self.assertRaises(CommandError):
            call_command("probe_sources", "--source", "999999", stdout=StringIO())

    def test_default_run_probes_only_active_sources(self):
        active = EventSource.objects.create(
            name="Active Feed", source_type="ics", url="https://active.test/cal.ics"
        )
        inactive = EventSource.objects.create(
            name="Inactive Feed",
            source_type="ics",
            url="https://inactive.test/cal.ics",
            active=False,
        )
        resp = _mock_response(200, headers={}, text=_ICS_BODY)
        with mock.patch(
            "ingestion.management.commands.probe_sources.requests.get", return_value=resp
        ):
            call_command("probe_sources", stdout=StringIO())

        self.assertTrue(SourceRun.objects.filter(source=active).exists())
        self.assertFalse(SourceRun.objects.filter(source=inactive).exists())

    def test_include_inactive_flag_probes_inactive_sources_too(self):
        inactive = EventSource.objects.create(
            name="Inactive Feed",
            source_type="ics",
            url="https://inactive.test/cal.ics",
            active=False,
        )
        resp = _mock_response(200, headers={}, text=_ICS_BODY)
        with mock.patch(
            "ingestion.management.commands.probe_sources.requests.get", return_value=resp
        ):
            call_command("probe_sources", "--include-inactive", stdout=StringIO())

        self.assertTrue(SourceRun.objects.filter(source=inactive).exists())

    def test_one_failing_source_does_not_abort_the_batch(self):
        broken = EventSource.objects.create(
            name="Broken Feed", source_type="ics", url="https://broken.test/cal.ics"
        )
        healthy = EventSource.objects.create(
            name="Healthy Feed", source_type="ics", url="https://healthy.test/cal.ics"
        )

        def fake_get(url, **kwargs):
            if url == broken.url:
                raise requests.exceptions.ConnectionError("refused")
            return _mock_response(200, headers={}, text=_ICS_BODY)

        with mock.patch(
            "ingestion.management.commands.probe_sources.requests.get", side_effect=fake_get
        ):
            call_command("probe_sources", stdout=StringIO())

        self.assertEqual(SourceRun.objects.get(source=broken).status, "failed")
        self.assertEqual(SourceRun.objects.get(source=healthy).status, "ok")
        self._no_side_effect_rows()
