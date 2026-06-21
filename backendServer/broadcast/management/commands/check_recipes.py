"""Health check for manual-review recipes: do the hardcoded selectors still
match the live forms?

    uv run python manage.py check_recipes            # offline structural check
    uv run python manage.py check_recipes --live     # also load each live form

Offline mode validates that every recipe-enabled adapter produces a well-formed
recipe (known field types, a submit selector, no empty selectors). --live also
launches Playwright, loads each form, and asserts every recipe selector + the
submit selector resolves to an element. Live mode hits real third-party sites —
only run it when you mean to.

This is a deliberately small, non-scalable monitor: it tells you when a site's
DOM has drifted from the hardcoded recipe so you can fix-on-break.
"""
from datetime import datetime

from django.core.management.base import BaseCommand

from broadcast.adapters import enabled_adapters
from broadcast.schema import CanonicalEvent

VALID_TYPES = {
    "text", "textarea", "date", "time", "select",
    "radio", "checkbox", "file", "select2", "terms", "manual_widget",
}

# A representative event that exercises every conditional field (timed, image,
# venue/organizer, a mapped locality).
SAMPLE_EVENT = CanonicalEvent(
    title="Recipe Healthcheck Event",
    description="Synthetic event used to validate recipe selectors.",
    start_datetime=datetime(2026, 9, 12, 19, 0),
    end_datetime=datetime(2026, 9, 12, 22, 0),
    all_day=False,
    venue_name="Acme Hall",
    address_line1="1 Main St",
    city="Pittsboro",
    zip="27312",
    locality=["pittsboro"],
    categories=["music"],
    event_url="https://example.com/healthcheck",
    price="",
    is_free=True,
    image_url="https://example.com/healthcheck.jpg",
    organizer_name="Acme Org",
    contact_email="hello@example.com",
    contact_phone="919-555-0100",
)


class Command(BaseCommand):
    help = "Audit manual-review recipes against their (optionally live) forms."

    def add_arguments(self, parser):
        parser.add_argument("--live", action="store_true",
                            help="load each live form and check every selector resolves")
        parser.add_argument("--headed", action="store_true", help="show the browser (with --live)")

    def handle(self, *args, **options):
        adapters = [a for a in enabled_adapters() if getattr(a, "recipe_fields", None)]
        if not adapters:
            self.stdout.write("no recipe-enabled adapters found.")
            return

        recipes = {a.key: a.recipe(SAMPLE_EVENT) for a in adapters}

        rows = [self._check_structure(key, recipe) for key, recipe in recipes.items()]
        if options["live"]:
            live = self._check_live(recipes, headed=options["headed"])
            rows = [(k, s_ok, s_msg, live.get(k)) for (k, s_ok, s_msg) in rows]
        else:
            rows = [(k, s_ok, s_msg, None) for (k, s_ok, s_msg) in rows]

        self._print_table(rows, live=options["live"])
        any_fail = any(not s_ok or (live_res is not None and not live_res[0])
                       for (_, s_ok, _, live_res) in rows)
        if any_fail:
            self.stderr.write(self.style.ERROR("one or more recipes FAILED"))
            raise SystemExit(1)
        self.stdout.write(self.style.SUCCESS("all recipes PASS"))

    def _check_structure(self, key, recipe):
        problems = []
        if not recipe.get("submit_selector"):
            problems.append("missing submit_selector")
        if not recipe.get("fields"):
            problems.append("no fields")
        for field in recipe.get("fields", []):
            if not field.get("selector"):
                problems.append("empty selector")
            if field.get("type") not in VALID_TYPES:
                problems.append(f"bad type {field.get('type')!r}")
        return (key, not problems, "; ".join(problems) or "ok")

    def _check_live(self, recipes, headed):
        from playwright.sync_api import sync_playwright

        from broadcast.runner import CHROMIUM_ARGS

        results = {}
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=not headed, args=CHROMIUM_ARGS)
            try:
                for key, recipe in recipes.items():
                    results[key] = self._check_one_live(browser, recipe)
            finally:
                browser.close()
        return results

    def _check_one_live(self, browser, recipe):
        from broadcast.adapters import _helpers as h

        context = browser.new_context()
        page = context.new_page()
        missing = []
        try:
            page.goto(recipe["url"], timeout=60_000, wait_until="domcontentloaded")
            h.dismiss_consent(page)
            page.wait_for_timeout(2000)
            selectors = [f["selector"] for f in recipe["fields"]]
            selectors.append(recipe["submit_selector"])
            for selector in selectors:
                if not self._resolves(page, selector):
                    missing.append(selector)
        except Exception as exc:
            missing.append(f"<load error: {exc}>")
        finally:
            context.close()
        return (not missing, "; ".join(missing) or "all selectors resolved")

    @staticmethod
    def _resolves(page, selector):
        # These forms are often iframe-embedded (Trumba), so search every frame.
        for frame in page.frames:
            try:
                if frame.locator(selector).count() > 0:
                    return True
            except Exception:
                continue
        return False

    def _print_table(self, rows, live):
        width = max((len(k) for (k, *_rest) in rows), default=10)
        for (key, s_ok, s_msg, live_res) in rows:
            status = "PASS" if s_ok else "FAIL"
            line = f"{key:<{width}}  structure={status:<4}"
            if not s_ok:
                line += f" ({s_msg})"
            if live:
                if live_res is None:
                    line += "  live=SKIP"
                else:
                    l_ok, l_msg = live_res
                    line += f"  live={'PASS' if l_ok else 'FAIL'}"
                    if not l_ok:
                        line += f" ({l_msg})"
            styler = self.style.SUCCESS if (s_ok and (live_res is None or live_res[0])) else self.style.ERROR
            self.stdout.write(styler(line))
