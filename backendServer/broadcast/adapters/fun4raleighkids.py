"""Fun 4 Raleigh Kids — Joomla/JEvents site.

The scaffold capture (capture_broadcast_form fun4raleighkids) targeted the
/calendar/ listing page and returned only 5 controls:

  1. input[name='keyword']  — calendar search box
  2. input[name='push']     — search submit button
  3. Email field            — newsletter signup
  4. First Name field       — newsletter signup
  5. Last Name field        — newsletter signup

There is NO public event-submission form.  The real "add your event" entry
point on Joomla/JEvents is always behind a Joomla user login (the standard
com_users login form).  Attempting to automate it without valid credentials
would be guessing at selectors that were never captured.

Decision: honest needs_manual adapter.  fill_and_submit() navigates to the
site, checks for a Joomla login wall (visible password input or
`/index.php?option=com_users` in the URL), screenshots, and returns
needs_manual with a clear error.  recipe_fields is intentionally left unset
so check_recipes stays green.
"""
from broadcast.adapters import _helpers as h
from broadcast.adapters.base import SiteAdapter, TargetResult
from broadcast.routing import Eligibility

# The calendar listing page is the closest public URL; the actual add-event
# URL requires a Joomla login so we keep this as the human starting point.
_CALENDAR_URL = "https://fun4raleighkids.com/calendar/"

# Joomla com_users login markers — any of these present → login wall.
_JOOMLA_LOGIN_SELECTORS = [
    "input[type='password']",
    "form[action*='com_users']",
    "#user-registration",
    ".com-users-login",
]


def _has_login_wall(page) -> bool:
    for sel in _JOOMLA_LOGIN_SELECTORS:
        try:
            if page.locator(sel).first.is_visible(timeout=500):
                return True
        except Exception:
            continue
    # Also catch a redirect to a login URL (Joomla default).
    return "com_users" in page.url


class Fun4RaleighKidsAdapter(SiteAdapter):
    key = "fun4raleighkids"
    name = "Fun 4 Raleigh Kids"
    submission_url = _CALENDAR_URL
    requires_auth = False
    eligibility = Eligibility(
        localities=frozenset({"raleigh", "wake", "cary", "triangle"}),
        categories=frozenset({"family-kids"}),
    )
    # recipe_fields intentionally absent: no public form → check_recipes skips.

    def fill_and_submit(self, page, ev, ctx):
        """Navigate to the calendar and detect the Joomla login wall.

        The site's event-submission form is gated behind a Joomla user account.
        We cannot fill or submit it without real credentials, so we always
        return needs_manual after documenting what we found.  A human reviewer
        should log into fun4raleighkids.com, navigate to Events → Add Event,
        and submit manually.
        """
        page.goto(self.submission_url, timeout=ctx.timeout_ms)
        page.wait_for_load_state("domcontentloaded", timeout=ctx.timeout_ms)
        h.dismiss_consent(page)

        if h.has_captcha(page):
            return TargetResult(
                status="needs_manual",
                error="captcha/bot-check present on calendar page",
                screenshot_path=h.take_screenshot(page, ctx, self.key),
            )

        if _has_login_wall(page):
            return TargetResult(
                status="needs_manual",
                error=(
                    "Joomla login wall detected — event submission requires a "
                    "registered fun4raleighkids.com account; submit manually"
                ),
                screenshot_path=h.take_screenshot(page, ctx, self.key),
            )

        # The capture showed only a search box + newsletter form on /calendar/.
        # If we somehow land without a visible login wall (e.g. a new layout)
        # we still cannot locate an add-event form from captured data alone.
        return TargetResult(
            status="needs_manual",
            error=(
                "No public event-submission form found on the calendar page. "
                "The captured form dump (schema.json) contained only a search "
                "box and newsletter signup — no add-event controls.  Submit "
                "manually via the Joomla back-end or a logged-in account."
            ),
            screenshot_path=h.take_screenshot(page, ctx, self.key),
        )
