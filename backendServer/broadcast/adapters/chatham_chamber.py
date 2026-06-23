"""Chatham Chamber events — ChamberMaster / GrowthZone public "Submit Event"
form (business.ccucc.net/ap/Event/Submit/yr4lawrl). Selectors picked from a
captured form dump (scaffold_adapter chatham_chamber).

The form carries a reCAPTCHA (a `g-recaptcha-response` widget is present), so a
real submission always defers to a human: we fill the fields we could verify
(the before-submit screenshot shows the completed form), then return
needs_manual instead of clicking — exactly like triangle_on_the_cheap. Dry runs
fill + screenshot the same way so the mapping can be reviewed.

Capture notes / honesty:
- Verified name-based controls: eventTitle (req), eventStartDate (req, date),
  eventContactEmailAddress (req, email), and the locationDescription /
  contactDescription textareas (by id).
- The end date/time controls came back ambiguous in the capture (GrowthZone's
  combined date/time pickers reuse the `eventEndDate` name) so they are
  deliberately omitted rather than guessed.
- The submit selector is a best-guess GrowthZone primary button; it is never
  clicked here (reCAPTCHA → always needs_manual), so it only documents intent
  for the manual-review extension.
"""
from broadcast.adapters import _helpers as h
from broadcast.adapters.base import RecipeField, SiteAdapter, TargetResult
from broadcast.routing import Eligibility


def _iso_date(dt) -> str:
    return dt.strftime("%Y-%m-%d")  # GrowthZone uses <input type="date"> (ISO)


def _location(ev) -> str:
    parts = [p for p in (ev.venue_name, h.full_address(ev)) if p and p.strip(", ")]
    return "\n".join(parts)


def _contact(ev) -> str:
    parts = [p for p in (ev.organizer_name, ev.contact_phone, ev.event_url) if p]
    return " · ".join(parts)


_RECIPE_FIELDS = [
    RecipeField("input[name='eventTitle']", "text", lambda ev: ev.title, required=True,
                label="Event title"),
    RecipeField("input[name='eventStartDate']", "date", lambda ev: _iso_date(ev.start_datetime),
                required=True, label="Start date"),
    RecipeField("#locationDescription", "textarea", _location, label="Location"),
    RecipeField("#contactDescription", "textarea", _contact, label="Contact details"),
    RecipeField("input[name='eventContactEmailAddress']", "text", lambda ev: ev.contact_email,
                required=True, label="Contact email"),
]


def _has_login_wall(page) -> bool:
    try:
        return page.locator("input[type='password']").first.is_visible(timeout=500)
    except Exception:
        return False


class ChathamChamberAdapter(SiteAdapter):
    key = "chatham_chamber"
    name = "Chatham Chamber Events"
    submission_url = "https://business.ccucc.net/ap/Event/Submit/yr4lawrl"
    requires_auth = False
    eligibility = Eligibility(
        localities=frozenset({"pittsboro", "chatham"}), categories=frozenset()
    )
    recipe_fields = _RECIPE_FIELDS
    captcha_hint = "reCAPTCHA — solve it, then click Submit."
    # Best-guess GrowthZone primary submit; never clicked (always needs_manual).
    submit_selector = "button[type='submit']"

    def fill_and_submit(self, page, ev, ctx):
        try:
            page.goto(self.submission_url, timeout=ctx.timeout_ms)
            page.wait_for_load_state("domcontentloaded", timeout=ctx.timeout_ms)
        except Exception as exc:
            return TargetResult(status="needs_manual",
                                error=f"could not load chamber submit form: {exc}")
        h.dismiss_consent(page)

        if _has_login_wall(page):
            return TargetResult(status="needs_manual", error="member login wall present",
                                screenshot_path=h.take_screenshot(page, ctx, self.key))

        missing = h.apply_specs(page, self.recipe_fields, ev, ctx.timeout_ms)
        if missing:
            return TargetResult(status="needs_manual",
                                error="required fields unfilled: " + "; ".join(missing),
                                screenshot_path=h.take_screenshot(page, ctx, self.key))

        shot = h.take_screenshot(page, ctx, self.key, "before-submit")
        # reCAPTCHA is structural on this form, so there is no automated submit
        # to suppress — dry run and real run alike defer to a human via manual
        # review. Always needs_manual (never "succeeded").
        note = "[DRY RUN] " if ctx.dry_run else ""
        return TargetResult(status="needs_manual",
                            error=note + "reCAPTCHA present; submit manually",
                            screenshot_path=shot)
