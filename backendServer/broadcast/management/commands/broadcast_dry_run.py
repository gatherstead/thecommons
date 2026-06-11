"""Run one adapter in dry-run mode against a fixture — verifies the script
fills the form and screenshots without ever clicking submit.

    uv run python manage.py broadcast_dry_run --site triangle_on_the_cheap \
        --fixture pittsboro_music.json
"""
import json
import pathlib
import tempfile
from datetime import datetime

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from playwright.sync_api import sync_playwright

from broadcast.adapters import get_adapter, registry
from broadcast.adapters.base import RunContext
from broadcast.runner import CHROMIUM_ARGS
from broadcast.schema import CanonicalEvent

FIXTURE_DIR = pathlib.Path(__file__).resolve().parents[2] / "fixtures"


class Command(BaseCommand):
    help = "Dry-run a single site adapter against a fixture event (never submits)."

    def add_arguments(self, parser):
        parser.add_argument("--site", required=True, help="site_key of the adapter")
        parser.add_argument("--fixture", required=True,
                            help="fixture filename in broadcast/fixtures/ (or an absolute path)")
        parser.add_argument("--headed", action="store_true", help="show the browser")

    def handle(self, *args, **options):
        adapter = get_adapter(options["site"])
        if adapter is None:
            raise CommandError(
                f"unknown site '{options['site']}'. Known: {sorted(registry())}"
            )

        fixture_path = pathlib.Path(options["fixture"])
        if not fixture_path.is_absolute():
            fixture_path = FIXTURE_DIR / options["fixture"]
        if not fixture_path.exists():
            raise CommandError(f"fixture not found: {fixture_path}")

        data = json.loads(fixture_path.read_text())
        data["start_datetime"] = datetime.fromisoformat(data["start_datetime"])
        if data.get("end_datetime"):
            data["end_datetime"] = datetime.fromisoformat(data["end_datetime"])
        ev = CanonicalEvent(**data)

        ok, reason = adapter.eligibility.matches(ev)
        if not ok:
            self.stdout.write(self.style.WARNING(
                f"note: this event would be excluded by routing ({reason}); running anyway"
            ))

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=not options["headed"], args=CHROMIUM_ARGS
            )
            try:
                page = browser.new_context().new_page()
                with tempfile.TemporaryDirectory() as tmp:
                    ctx = RunContext(
                        dry_run=True,
                        screenshot_dir=settings.BROADCAST_SCREENSHOT_DIR,
                        download_dir=tmp,
                        submission_id=f"dryrun-{options['site']}",
                        timeout_ms=settings.BROADCAST_TIMEOUT_MS,
                    )
                    result = adapter.fill_and_submit(page, ev, ctx)
            finally:
                browser.close()

        style = self.style.SUCCESS if result.status == "succeeded" else self.style.WARNING
        self.stdout.write(style(f"status: {result.status}"))
        if result.error:
            self.stdout.write(f"note: {result.error}")
        if result.screenshot_path:
            self.stdout.write(f"screenshot: {result.screenshot_path}")
