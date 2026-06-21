"""One-shot capture of a broadcast site's real form HTML, so selectors can be
hand-picked for a direct-locator adapter (broadcast/adapters/<site>.py).

    uv run python manage.py capture_broadcast_form triangle_weekender [--headed]

Writes broadcast/captures/<site_key>.html (every frame's HTML, since these
forms are JS-rendered and often live in iframes) and <site_key>.png.

ABC11 is special: abc11.com/community/submitevent/ is a Trumba splash page
with a "Continue" button. We click through and capture the resulting Trumba
form, logging its final URL so it can be hardcoded as the adapter's
submission_url.

These captures are scratch artifacts (gitignored), not source.
"""
import pathlib

from django.core.management.base import BaseCommand, CommandError
from playwright.sync_api import sync_playwright

from broadcast.adapters import _helpers as h
from broadcast.runner import CHROMIUM_ARGS

CAPTURES_DIR = pathlib.Path(__file__).resolve().parents[2] / "captures"

# site_key → how to reach its live submission form.
#   url:      page to navigate to first
#   continue: accessible name of a button to click before capturing (Trumba splash)
SITES = {
    "triangle_on_the_cheap": {
        "url": "https://triangleonthecheap.com/submit-an-event/",
    },
    "triangle_weekender": {
        "url": "https://thetriangleweekender.com/events/community/add/",
    },
    "abc11_community": {
        "url": "https://abc11.com/community/submitevent/",
        "continue": "Continue",
    },
}


class Command(BaseCommand):
    help = "Capture a broadcast site's real form HTML + screenshot for selector picking."

    def add_arguments(self, parser):
        parser.add_argument("site_key", choices=sorted(SITES), help="which site to capture")
        parser.add_argument("--headed", action="store_true", help="show the browser")
        parser.add_argument("--wait", type=int, default=0,
                            help="extra seconds to wait before dumping (lets timed popups appear)")

    def handle(self, *args, **options):
        key = options["site_key"]
        site = SITES.get(key)
        if site is None:
            raise CommandError(f"unknown site '{key}'. Known: {sorted(SITES)}")

        CAPTURES_DIR.mkdir(parents=True, exist_ok=True)
        html_path = CAPTURES_DIR / f"{key}.html"
        png_path = CAPTURES_DIR / f"{key}.png"

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=not options["headed"], args=CHROMIUM_ARGS)
            try:
                context = browser.new_context()
                page = context.new_page()
                page.goto(site["url"], timeout=60_000, wait_until="domcontentloaded")
                h.dismiss_consent(page)

                if site.get("continue"):
                    label = site["continue"]
                    self.stdout.write(f"clicking '{label}' to leave the splash page…")
                    getters = [
                        lambda: page.get_by_role("button", name=label),
                        lambda: page.get_by_role("link", name=label),
                        lambda: page.get_by_text(label, exact=False),
                    ]
                    for getter in getters:
                        try:
                            getter().first.click(timeout=8_000)
                            break
                        except Exception:
                            continue
                    # These ad-heavy pages never reach networkidle, and Continue
                    # may open the form in a new tab — settle, then take the
                    # newest page.
                    page.wait_for_timeout(6_000)
                    page = context.pages[-1]
                    try:
                        page.wait_for_load_state("domcontentloaded", timeout=15_000)
                    except Exception:
                        pass
                    h.dismiss_consent(page)

                if options["wait"]:
                    page.wait_for_timeout(options["wait"] * 1000)

                final_url = page.url
                frames = page.frames
                sections = []
                for i, frame in enumerate(frames):
                    try:
                        content = frame.content()
                    except Exception as exc:  # detached / cross-origin restricted
                        content = f"<!-- frame content unavailable: {exc} -->"
                    sections.append(
                        f"<!-- ===== frame[{i}] url={frame.url} ===== -->\n{content}"
                    )
                page.screenshot(path=str(png_path), full_page=True)
            finally:
                browser.close()

        html_path.write_text("\n\n".join(sections))

        self.stdout.write(self.style.SUCCESS(
            f"captured {len(frames)} frame(s) → {html_path}\nscreenshot → {png_path}"
        ))
        self.stdout.write(f"final URL: {final_url}")
        if len(frames) > 1:
            self.stdout.write("iframe URLs (a Trumba/embedded form usually lives in one of these):")
            for frame in frames[1:]:
                self.stdout.write(f"  - {frame.url}")
