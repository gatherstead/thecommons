"""Chatham Chamber events — ChamberMaster / GrowthZone public "Submit Event"
form (business.ccucc.net/ap/Event/Submit/yr4lawrl). Selectors verified against a
fresh live capture (capture_broadcast_form chatham_chamber → captures/).

The form carries a reCAPTCHA (a `g-recaptcha-response` widget is present), so a
real submission always defers to a human: we fill the fields we could verify
(the before-submit screenshot shows the completed form), then return
needs_manual instead of clicking — exactly like triangle_on_the_cheap. Dry runs
fill + screenshot the same way so the mapping can be reviewed.

Capture notes / honesty (all confirmed in the live capture):
- Fillable controls: eventTitle (req, text), eventStartDate (req, date),
  eventContactEmailAddress (req, email), eventIsAllDay (checkbox), and the
  locationDescription / contactDescription <textarea>s (by id).
- The main Description (#eventDescription), Date-and-Time Description
  (#hoursDescription) and Fees/Admission (#pricingDescription) are Froala
  rich-text editors (micronet-rich-text-editor) whose editable body lives inside
  an <iframe class="fr-iframe"> — NOT fillable by a content script via .value or
  innerText. We deliberately do not pretend to fill them; the human types the
  description on review. To avoid losing the schedule, _location folds a
  human-readable "When: <date/time>" line into the locationDescription textarea
  we CAN fill — the three native time/end-date inputs all share
  name="eventEndDate" with no unique id, so they are not safely addressable.
- #contactDescription carries ev.organizer_name · ev.contact_phone · ev.event_url.
- IMPORTANT: this form's host (business.ccucc.net) must be in the extension's
  manifest host_permissions or the content script can't inject — that was the
  root cause of "nothing filled" before.
- The submit selector is the GrowthZone primary button; never clicked here
  (reCAPTCHA → always needs_manual), so it only documents intent for the
  manual-review extension.
"""
from broadcast.adapters import _helpers as h
from broadcast.adapters.base import RecipeField, SiteAdapter, TargetResult
from broadcast.routing import Eligibility


def _iso_date(dt) -> str:
    return dt.strftime("%Y-%m-%d")  # GrowthZone uses <input type="date"> (ISO)


def _iso_time(dt) -> str:
    return dt.strftime("%H:%M")  # <input type="time"> wants 24-hour HH:MM


def _contact(ev) -> str:
    parts = [p for p in (ev.organizer_name, ev.contact_phone, ev.event_url) if p]
    return " · ".join(parts)


def _hours(ev) -> str:
    """Human-readable date + time. The native time/end-date inputs share a
    non-unique name and can't be driven, and the dedicated "Date and Time
    Description" field is a Froala iframe editor we can't fill — so we surface the
    schedule inside the one free-text textarea we can (locationDescription)."""
    if ev.all_day:
        return f"{h.format_date(ev.start_datetime)} — All day"
    start = f"{h.format_date(ev.start_datetime)}, {h.format_time(ev.start_datetime)}"
    if ev.end_datetime:
        if ev.end_datetime.date() != ev.start_datetime.date():
            return f"{start} – {h.format_date(ev.end_datetime)}, {h.format_time(ev.end_datetime)}"
        return f"{start} – {h.format_time(ev.end_datetime)}"
    return start


def _location(ev) -> str:
    parts = [ev.venue_name, h.full_address(ev), f"When: {_hours(ev)}"]
    return "\n".join(p for p in parts if p and p.strip(", "))


_RECIPE_FIELDS = [
    RecipeField("input[name='eventTitle']", "text", lambda ev: ev.title, required=True,
                label="Event title"),
    RecipeField("input[name='eventStartDate']", "date", lambda ev: _iso_date(ev.start_datetime),
                required=True, label="Start date"),
    RecipeField("#locationDescription", "textarea", _location, label="Location & schedule"),
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

    def recipe_field_specs(self, ev):
        """Static fields + the now-required End Date and the start/end time
        inputs. The three date/time inputs all share name="eventEndDate", so we
        address them by their distinct ng-model bindings instead. All-day events
        get the checkbox and skip the time fields."""
        specs = list(_RECIPE_FIELDS)
        end = ev.end_datetime or ev.start_datetime
        specs.append(RecipeField(
            "input[ng-model='vm.model.EndDateTime'][type='date']", "date",
            lambda ev, e=end: _iso_date(e), required=True, label="End date"))
        if ev.all_day:
            specs.append(RecipeField("input[name='eventIsAllDay']", "checkbox",
                                     lambda ev: "true", recipe_only=True,
                                     label="All-day event"))
        else:
            specs.append(RecipeField(
                "input[ng-model='vm.model.StartDateTime'][type='time']", "time",
                lambda ev: _iso_time(ev.start_datetime), label="Start time"))
            specs.append(RecipeField(
                "input[ng-model='vm.model.EndDateTime'][type='time']", "time",
                lambda ev, e=end: _iso_time(e), label="End time"))
        return specs

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

        missing = h.apply_specs(page, self.recipe_field_specs(ev), ev, ctx.timeout_ms)
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
