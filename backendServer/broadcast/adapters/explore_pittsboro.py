"""Explore Pittsboro events.

explorepittsboro.com is a Wix build; the configured URL
(explorepittsboro.com/events) is an events LISTING page, not a submission
form. The scaffold capture (scaffold_adapter explore_pittsboro) found only a
Wix search box and a newsletter email signup — no event-submission controls.
Explore Pittsboro has no public self-serve event form, so this adapter does
not submit automatically: it loads the page, screenshots it, and returns
needs_manual so a human can add the event through the site's listing/contact
process. recipe_fields is intentionally left unset so check_recipes skips it.
"""
from broadcast.adapters import _helpers as h
from broadcast.adapters.base import SiteAdapter, TargetResult
from broadcast.routing import Eligibility


class ExplorePittsboroAdapter(SiteAdapter):
    key = "explore_pittsboro"
    name = "Explore Pittsboro"
    # Wix listing page — no public submission form (see module docstring).
    submission_url = "https://www.explorepittsboro.com/events"
    requires_auth = False
    eligibility = Eligibility(
        localities=frozenset({"pittsboro", "chatham"}), categories=frozenset()
    )
    # recipe_fields intentionally absent: no public form to fill.

    def fill_and_submit(self, page, ev, ctx):
        try:
            page.goto(self.submission_url, timeout=ctx.timeout_ms)
            page.wait_for_load_state("domcontentloaded", timeout=ctx.timeout_ms)
        except Exception as exc:
            return TargetResult(status="needs_manual",
                                error=f"could not load events page: {exc}")
        h.dismiss_consent(page)
        shot = h.take_screenshot(page, ctx, self.key)
        if h.has_captcha(page):
            return TargetResult(status="needs_manual", error="captcha/bot-check present",
                                screenshot_path=shot)
        return TargetResult(
            status="needs_manual",
            error="Explore Pittsboro has no public event-submission form (Wix "
                  "listing page); add the event via the site's listing/contact "
                  "process manually.",
            screenshot_path=shot,
        )
