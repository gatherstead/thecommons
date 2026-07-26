"""Regression: fill_and_submit must drive the *computed* recipe_field_specs(ev),
not the static recipe_fields list — otherwise event-dependent fields (e.g.
ABC11's Duration, derived from start/end) are silently dropped on the headless
path. No DB, no real browser — a stub Playwright page records fill() calls."""

import tempfile
from datetime import UTC, datetime

from django.test import SimpleTestCase, tag

from broadcast.adapters.abc11_community import Abc11CommunityAdapter
from broadcast.adapters.base import RunContext
from broadcast.schema import CanonicalEvent


class _StubLocator:
    """Records fill() calls; everything else is inert so has_captcha()/
    dismiss_consent()/_login_wall() (all wrapped in try/except in the
    adapter/helpers) treat this as "nothing there" and move on."""

    def __init__(self, page, selector):
        self._page = page
        self._selector = selector

    @property
    def first(self):
        return self

    def is_visible(self, timeout=None):
        return False

    def fill(self, value, timeout=None):
        self._page.filled[self._selector] = value

    def click(self, timeout=None):
        self._page.clicked.append(self._selector)


class _StubPage:
    """Minimal stand-in for playwright.sync_api.Page — just enough surface
    for Abc11CommunityAdapter.fill_and_submit to run to completion."""

    def __init__(self):
        self.filled: dict[str, str] = {}
        self.clicked: list[str] = []
        self.url = "https://example.test/stub"

    def goto(self, url, timeout=None):
        pass

    def wait_for_load_state(self, state, timeout=None):
        pass

    def locator(self, selector):
        return _StubLocator(self, selector)

    def get_by_role(self, role, name=None):
        return _StubLocator(self, f"role:{role}")

    def screenshot(self, path=None, full_page=False):
        # take_screenshot() writes to a real path; an empty file is enough.
        with open(path, "wb"):
            pass


def _make_event():
    return CanonicalEvent(
        title="Jazz Night",
        description="An evening of jazz.",
        start_datetime=datetime(2026, 8, 1, 19, 0, tzinfo=UTC),
        end_datetime=datetime(2026, 8, 1, 21, 30, tzinfo=UTC),
        venue_name="Acme Hall",
        address_line1="1 Main St",
        city="Pittsboro",
        zip="27312",
        locality=["pittsboro"],
        categories=["music"],
        event_url="https://example.com/jazz",
        organizer_name="Acme Org",
    )


@tag("fast")
class Abc11FillUsesComputedSpecsTest(SimpleTestCase):
    def test_duration_fields_are_filled_when_event_has_an_end_time(self):
        """Duration is only present in recipe_field_specs(ev) (computed from
        start/end), never in the static recipe_fields list. If fill_and_submit
        regresses to `self.recipe_fields`, these selectors go unfilled."""
        adapter = Abc11CommunityAdapter()
        ev = _make_event()
        page = _StubPage()

        with tempfile.TemporaryDirectory() as shots, tempfile.TemporaryDirectory() as dl:
            ctx = RunContext(
                dry_run=True, screenshot_dir=shots, download_dir=dl, submission_id="test"
            )
            result = adapter.fill_and_submit(page, ev, ctx)

        self.assertEqual(result.status, "succeeded")
        self.assertIn("#eventDurationHours", page.filled)
        self.assertIn("#eventDurationMinutes", page.filled)
        self.assertEqual(page.filled["#eventDurationHours"], "2")
        self.assertEqual(page.filled["#eventDurationMinutes"], "30")
