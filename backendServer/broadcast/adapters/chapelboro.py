"""Chapelboro community calendar (chapelboro.com/calendar/add).

Chapelboro (a Learfield/Townsquare local-news property) bot-blocks headless
Chromium: scaffold_adapter's page.goto timed out repeatedly and a plain GET
returns no body, so no deterministic selectors could be captured. This adapter
therefore defers to manual review: it attempts to load the add form and, on
any navigation failure / login wall / captcha, returns needs_manual with a
clear error. recipe_fields is intentionally left unset (no captured selectors)
so check_recipes stays green; it can become a full recipe adapter once the
live form is capturable.
"""
from broadcast.adapters import _helpers as h
from broadcast.adapters.base import SiteAdapter, TargetResult
from broadcast.routing import Eligibility


def _has_login_wall(page) -> bool:
    try:
        return page.locator("input[type='password']").first.is_visible(timeout=500)
    except Exception:
        return False


class ChapelboroAdapter(SiteAdapter):
    key = "chapelboro"
    name = "Chapelboro Calendar"
    submission_url = "https://chapelboro.com/calendar/add"
    requires_auth = False
    eligibility = Eligibility(
        localities=frozenset({"chapel-hill", "carrboro"}), categories=frozenset()
    )
    # recipe_fields intentionally absent: the site blocks headless capture.

    def fill_and_submit(self, page, ev, ctx):
        try:
            page.goto(self.submission_url, timeout=ctx.timeout_ms)
            page.wait_for_load_state("domcontentloaded", timeout=ctx.timeout_ms)
        except Exception as exc:
            return TargetResult(
                status="needs_manual",
                error=f"chapelboro.com blocks automated access ({exc}); submit manually.",
            )
        h.dismiss_consent(page)
        shot = h.take_screenshot(page, ctx, self.key)
        if h.has_captcha(page):
            return TargetResult(status="needs_manual", error="captcha/bot-check present",
                                screenshot_path=shot)
        if _has_login_wall(page):
            return TargetResult(status="needs_manual", error="login wall present",
                                screenshot_path=shot)
        return TargetResult(
            status="needs_manual",
            error="chapelboro.com bot-blocks headless submission and no form "
                  "selectors are captured yet; submit manually.",
            screenshot_path=shot,
        )
