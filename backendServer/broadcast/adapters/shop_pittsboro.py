"""Shop Pittsboro member-events widget.

The captured form (scaffold_adapter shop_pittsboro) is a member LOGIN form
(email + password inputs, name='eml'/'pwd'), confirming the "new event" widget
at shoppittsboro.com/member-events/#!event/new is gated behind a member login.
There is no public, anonymous submission form, so this adapter never submits
automatically: it loads the page, confirms the login wall (or any captcha),
screenshots, and returns needs_manual so a human with member credentials can
post the event. recipe_fields is intentionally left unset (no deterministic
public selectors to fill) so check_recipes skips it.
"""
from broadcast.adapters import _helpers as h
from broadcast.adapters.base import SiteAdapter, TargetResult
from broadcast.routing import Eligibility


def _has_login_wall(page) -> bool:
    try:
        return page.locator("input[type='password']").first.is_visible(timeout=500)
    except Exception:
        return False


class ShopPittsboroAdapter(SiteAdapter):
    key = "shop_pittsboro"
    name = "Shop Pittsboro Events"
    # Member-events widget; member-gated — the login wall yields needs_manual.
    submission_url = "https://shoppittsboro.com/member-events/#!event/new"
    requires_auth = False
    eligibility = Eligibility(localities=frozenset({"pittsboro"}), categories=frozenset())
    # recipe_fields intentionally absent: login-gated, no public form to fill.

    def fill_and_submit(self, page, ev, ctx):
        try:
            page.goto(self.submission_url, timeout=ctx.timeout_ms)
            page.wait_for_load_state("domcontentloaded", timeout=ctx.timeout_ms)
        except Exception as exc:
            return TargetResult(status="needs_manual",
                                error=f"could not load member-events page: {exc}")
        h.dismiss_consent(page)
        shot = h.take_screenshot(page, ctx, self.key)
        if h.has_captcha(page):
            return TargetResult(status="needs_manual", error="captcha/bot-check present",
                                screenshot_path=shot)
        reason = (
            "Shop Pittsboro new-event form is behind a member login; sign in "
            "and submit manually."
            if _has_login_wall(page)
            else "No public Shop Pittsboro event form found (member-events widget "
                 "is login-gated); submit manually."
        )
        return TargetResult(status="needs_manual", error=reason, screenshot_path=shot)
