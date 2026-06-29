"""Visit Raleigh community event calendar.

The form at https://www.visitraleigh.com/events/submit-an-event/ is a fully
public, server-rendered HTML form — no login, no captcha on page load, and no
third-party widget. Field ids and names were verified against the captured dump
(capture_broadcast_form visit_raleigh) and the page screenshot.

Form structure (notable details):
- "Contact Info" section: postname (submitter), postemail, postphone, postcomments.
- "Event Information" section: title, categories (select-multiple), primarycatId
  (select-one), hostID (select-one of orgs in DB), hostName (free-text fallback),
  listingID (select-one of venues in DB), location (free-text venue name),
  addr1/city/state/zip, admission, email, phone, linkurl, starttime, endtime,
  mediafile (file upload), description, startdate (text, "mm/dd/yyyy").
- Dates: startdate is a plain text field (mm/dd/yyyy). There is no "enddate" for
  one-day events in the main section; enddate lives only in the recurrence widget
  and defaults to start for a one-day event, so we skip it.
- Times: starttime / endtime are plain text fields — free-form (e.g. "7:00 PM").
- Submit: input[name='submitevent'] (type=button).
- No captcha on page load; no password-protected gate.

Submitter identity comes from the user-entered Contact block on the canonical
event: ev.organizer_name / ev.contact_email / ev.contact_phone.
"""
from broadcast.adapters import _helpers as h
from broadcast.adapters.base import RecipeField, SiteAdapter, TargetResult
from broadcast.routing import Eligibility

# Map our canonical category slugs to the site's real option strings.
# Options captured from the select-multiple#categories field.
_CAT_MAP: dict[str, str] = {
    "music":       "Concerts",
    "arts":        "Arts",
    "family-kids": "Family",
    "food-drink":  "Culinary",
    "festival":    "Festival",
    "market":      "Shopping",
    "literary":    "Arts",
    "community":   "Annual Event",
    "nightlife":   "Nightlife",
    "wellness":    "Wellness",
    "education":   "Education Outreach",
    "sports":      "Sports",
    "film":        "Film",
    "dance":       "Dance",
    "comedy":      "Comedy",
    "theatre":     "Theatre",
}

_SUBMIT_SELECTOR = "input[name='submitevent']"


def _vr_date(dt) -> str:
    """mm/dd/yyyy as the site's text startdate field expects."""
    return f"{dt.month:02d}/{dt.day:02d}/{dt.year}"


def _vr_time(dt) -> str:
    """'7:00 PM' — matches the free-form starttime / endtime fields."""
    return h.format_time(dt)


def _map_categories(ev) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for slug in ev.categories:
        label = _CAT_MAP.get(slug)
        if label and label not in seen:
            seen.add(label)
            result.append(label)
    return result


# Plain fillable fields declared once; consumed by both the Playwright server
# path (h.apply_specs) and the manual-review recipe export (recipe_fields).
# Fields driven imperatively (categories select-multiple, image file upload) are
# recipe_only so apply_specs skips them on the server path.
_RECIPE_FIELDS = [
    # --- Contact Info (submitter identity — from ev.organizer_name / contact_email / contact_phone) ---
    RecipeField("#postname", "text", lambda ev: ev.organizer_name,
                required=True, label="Submitter Name"),
    RecipeField("#postemail", "text", lambda ev: ev.contact_email,
                required=True, label="Submitter Email"),
    RecipeField("#postphone", "text", lambda ev: ev.contact_phone,
                label="Submitter Phone"),

    # --- Event core ---
    RecipeField("#title", "text", lambda ev: ev.title,
                required=True, label="Event Title"),
    RecipeField("#description", "textarea", lambda ev: ev.description,
                required=True, label="Event Description"),
    RecipeField("#startdate", "text", lambda ev: _vr_date(ev.start_datetime),
                required=True, label="Start Date",
                hint="plain text field — enter mm/dd/yyyy"),

    # --- Location (free-text venue name; address fields) ---
    RecipeField("#location", "text", lambda ev: ev.venue_name,
                label="Venue / Location"),
    RecipeField("#addr1", "text", lambda ev: ev.address_line1,
                label="Address 1"),
    RecipeField("#city", "text", lambda ev: ev.city,
                label="City"),
    RecipeField("#zip", "text", lambda ev: ev.zip,
                label="Zip"),

    # --- Contact for the event itself ---
    RecipeField("#phone", "text", lambda ev: ev.contact_phone,
                label="Event Phone"),
    RecipeField("#email", "text", lambda ev: ev.contact_email,
                label="Event Email"),

    # --- URLs / admission ---
    RecipeField("#linkurl", "text", lambda ev: ev.event_url,
                label="Event Website"),
    RecipeField("#admission", "text",
                lambda ev: "Free" if ev.is_free else ev.price,
                label="Admission"),

    # --- Category (select-multiple — driven imperatively; recipe_only) ---
    RecipeField("#categories", "select", lambda ev: ", ".join(_map_categories(ev)),
                recipe_only=True, label="Event Category",
                hint="select-multiple; pick matching options from the list"),
    RecipeField("#primarycatId", "select", lambda ev: (_map_categories(ev) or [""])[0],
                recipe_only=True, label="Primary Category",
                hint="select the single best-matching primary category"),

    # --- Image (file upload — recipe_only) ---
    RecipeField("#mediafile", "file", lambda ev: ev.image_url,
                recipe_only=True, label="Upload Image",
                hint="download image from event_url and upload manually"),
]

# Time fields are added conditionally in recipe_field_specs().


class VisitRaleighAdapter(SiteAdapter):
    """Visit Raleigh public event submission form (www.visitraleigh.com)."""

    key = "visit_raleigh"
    name = "Visit Raleigh"
    submission_url = "https://www.visitraleigh.com/events/submit-an-event/"
    requires_auth = False
    eligibility = Eligibility(
        localities=frozenset({"raleigh", "wake", "cary"}), categories=frozenset()
    )
    recipe_fields = _RECIPE_FIELDS
    submit_selector = _SUBMIT_SELECTOR
    # The form markup renders a beat after page load; wait for the description
    # textarea (near the bottom of the form) before autofilling so fields exist.
    ready_selector = "#description"
    captcha_hint = (
        "If a bot-check appears before or after filling the form, "
        "solve it manually then submit."
    )

    def recipe_field_specs(self, ev):
        """Base fields + optional time fields when the event is not all-day."""
        specs = list(_RECIPE_FIELDS)
        if not ev.all_day:
            specs.append(
                RecipeField("#starttime", "text",
                            lambda ev: _vr_time(ev.start_datetime),
                            label="Start Time",
                            hint="free-form text, e.g. '7:00 PM'")
            )
            if ev.end_datetime:
                specs.append(
                    RecipeField("#endtime", "text",
                                lambda ev: _vr_time(ev.end_datetime),
                                label="End Time",
                                hint="free-form text, e.g. '9:00 PM'")
                )
        return specs

    def fill_and_submit(self, page, ev, ctx):
        page.goto(self.submission_url, timeout=ctx.timeout_ms)
        page.wait_for_load_state("domcontentloaded", timeout=ctx.timeout_ms)
        h.dismiss_consent(page)

        # Guard: login wall (password input visible).
        if self._login_wall(page):
            return TargetResult(
                status="needs_manual",
                error="login wall detected — form not publicly accessible",
                screenshot_path=h.take_screenshot(page, ctx, self.key),
            )

        # Guard: captcha before we fill anything.
        if h.has_captcha(page):
            return TargetResult(
                status="needs_manual",
                error="captcha/bot-check present before form fill",
                screenshot_path=h.take_screenshot(page, ctx, self.key),
            )

        # Fill all FILLABLE_TYPES fields via the shared loop.
        specs = self.recipe_field_specs(ev)
        missing = h.apply_specs(page, specs, ev, ctx.timeout_ms)
        if missing:
            return TargetResult(
                status="needs_manual",
                error="required fields unfilled: " + "; ".join(missing),
                screenshot_path=h.take_screenshot(page, ctx, self.key),
            )

        # Drive the category selects imperatively (select-multiple + select-one).
        cats = _map_categories(ev)
        if cats:
            _select_categories(page, "#categories", cats, ctx.timeout_ms)
            _select_option(page, "#primarycatId", cats[0], ctx.timeout_ms)

        # Image: download and set on the file input.
        if ev.image_url:
            local = h.download_image(ev.image_url, ctx.download_dir)
            if local:
                try:
                    page.locator("#mediafile").first.set_input_files(
                        local, timeout=ctx.timeout_ms
                    )
                except Exception:
                    pass

        # Guard: captcha that appeared after JS interaction.
        if h.has_captcha(page):
            return TargetResult(
                status="needs_manual",
                error="captcha/bot-check present after form fill",
                screenshot_path=h.take_screenshot(page, ctx, self.key),
            )

        shot = h.take_screenshot(page, ctx, self.key, "before-submit")
        if ctx.dry_run:
            return TargetResult(
                status="succeeded",
                error="[DRY RUN] not submitted",
                screenshot_path=shot,
            )

        page.locator(_SUBMIT_SELECTOR).first.click(timeout=ctx.timeout_ms)
        page.wait_for_load_state("load", timeout=ctx.timeout_ms)
        return TargetResult(
            status="succeeded",
            external_url=page.url,
            screenshot_path=h.take_screenshot(page, ctx, self.key, "after-submit"),
        )

    @staticmethod
    def _login_wall(page) -> bool:
        try:
            return page.locator("input[type='password']").first.is_visible(timeout=500)
        except Exception:
            return False


# ---------------------------------------------------------------------------
# Widget helpers (imperative, server path only)
# ---------------------------------------------------------------------------

def _select_categories(page, selector: str, labels: list[str], timeout_ms: int) -> None:
    """Select multiple options on a <select multiple> by label, best-effort."""
    if not labels:
        return
    try:
        page.locator(selector).first.select_option(label=labels, timeout=timeout_ms)
    except Exception:
        for label in labels:
            try:
                page.locator(selector).first.select_option(label=label, timeout=2000)
            except Exception:
                continue


def _select_option(page, selector: str, label: str, timeout_ms: int) -> None:
    """Select a single option on a <select> by label, best-effort."""
    if not label:
        return
    try:
        page.locator(selector).first.select_option(label=label, timeout=timeout_ms)
    except Exception:
        pass
