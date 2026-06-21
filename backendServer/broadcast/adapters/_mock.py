"""Mock site adapter — drives the local static form so the runner/worker
pipeline can be exercised end-to-end (CI and dev) without hitting real sites.
"""
import pathlib

from broadcast.adapters import _helpers as h
from broadcast.adapters.base import RunContext, SiteAdapter, TargetResult
from broadcast.routing import Eligibility

MOCK_FORM_PATH = pathlib.Path(__file__).resolve().parent / "_mock_form.html"

_CAT_MAP = {
    "music": "Music",
    "arts": "Arts & Culture",
    "family-kids": "Family",
    "food-drink": "Food & Drink",
    "festival": "Festivals",
    "market": "Markets",
    "literary": "Arts & Culture",
    "community": "Community",
    "nightlife": "Nightlife",
    "wellness": "Health & Wellness",
    "education": "Classes & Workshops",
}


class MockSiteAdapter(SiteAdapter):
    key = "mock_site"
    name = "Mock Community Calendar (local)"
    submission_url = MOCK_FORM_PATH.as_uri()
    requires_auth = False
    eligibility = Eligibility(localities=frozenset(), categories=frozenset())

    def fill_and_submit(self, page, ev, ctx: RunContext) -> TargetResult:
        page.goto(self.submission_url, timeout=ctx.timeout_ms)

        page.get_by_label("Event Title").fill(ev.title)
        page.get_by_label("Description").fill(ev.description)
        page.get_by_label("Start Date").fill(h.format_date(ev.start_datetime))
        page.get_by_label("Start Time").fill(h.format_time(ev.start_datetime))
        if ev.end_datetime:
            page.get_by_label("End Date").fill(h.format_date(ev.end_datetime))
            page.get_by_label("End Time").fill(h.format_time(ev.end_datetime))
        page.get_by_label("Venue Name").fill(ev.venue_name)
        page.get_by_label("Address", exact=True).fill(h.full_address(ev))
        if ev.event_url:
            page.get_by_label("Event Website").fill(ev.event_url)
        if ev.ticket_url:
            page.get_by_label("Ticket URL").fill(ev.ticket_url)
        if ev.price:
            page.get_by_label("Price").fill(ev.price)
        if ev.organizer_name:
            page.get_by_label("Organizer Name").fill(ev.organizer_name)
        if ev.contact_email:
            page.get_by_label("Contact Email").fill(ev.contact_email)
        if ev.contact_phone:
            page.get_by_label("Contact Phone").fill(ev.contact_phone)
        labels = sorted({_CAT_MAP[c] for c in ev.categories if c in _CAT_MAP})
        h.select_categories(page, page.get_by_label("Categories"), labels)
        if ev.image_url:
            local = h.download_image(ev.image_url, ctx.download_dir)
            if local:
                page.get_by_label("Event Image").set_input_files(local)

        if h.has_captcha(page):
            return TargetResult(status="needs_manual", error="captcha present",
                                screenshot_path=h.take_screenshot(page, ctx, self.key))

        shot = h.take_screenshot(page, ctx, self.key)
        if ctx.dry_run:
            return TargetResult(status="succeeded", error="[DRY RUN] not submitted",
                                screenshot_path=shot)

        page.get_by_role("button", name="Submit Event").click()
        page.locator("#confirmation").wait_for(state="visible", timeout=ctx.timeout_ms)
        return TargetResult(status="succeeded", external_url=page.url,
                            screenshot_path=h.take_screenshot(page, ctx, self.key, "after"))
