"""ABC11 Community Calendar. abc11.com/community/submitevent/ is only a splash
page; the real form is a Trumba ESF (third-party React form), so we target the
Trumba URL directly (captured via capture_broadcast_form abc11_community).

The form is submittable anonymously — it collects submitter Name/Email/Phone
(required) instead of requiring a Disney sign-in. Organizer and contact details
are required on the web form, so the Submitter fields resolve straight from the
canonical event (organizer_name / contact_email / contact_phone); an event
missing them yields needs_manual rather than submitting a fabricated identity.

Field ids (cfN) and the submit button (value="save") are verified against the
captured dump. Category (react-select) and image (custom uploader) are
best-effort; everything else maps from canonical fields.

Image: the form has exactly one `input[type=file][accept="image/*"]`, behind a
drag-and-drop skin at `.image-field-esf .image-dropzone` — a real file input,
not a JS-only dropzone, so a programmatic file set works through the normal
Playwright/extension path. Emitted only when `ev.image_url` is set (mirrors
triangle_weekender's image spec). Uploading reveals an alt-text field on
ABC11's form; `CanonicalEvent` has no alt-text field upstream, and per the
"adapters never invent content" rule we do not synthesize one — that field is
left for manual follow-up (see docs/broadcast.md's adapter rules).
"""

from broadcast.adapters import _helpers as h
from broadcast.adapters.base import RecipeField, SiteAdapter, TargetResult
from broadcast.routing import TRIANGLE, Eligibility

# Trumba ESF form, loaded standalone.
_TRUMBA_URL = (
    "https://www.trumba.com/esf2/index.html?webname=whuzr6myd58044bc52a92byjc7"
    "&esfFrameID=trumbaSubmitEventForm&trumbaServer=https%3A%2F%2Fwww.trumba.com"
)


def _date(dt) -> str:
    return f"{dt.month}/{dt.day}/{dt.year}"  # matches the form's n/j/Y


def _location(ev) -> str:
    parts = [p for p in (ev.venue_name, h.full_address(ev)) if p and p.strip(", ")]
    return ", ".join(parts)


def _duration(ev):
    """(hours, minutes) between start and end, or None when not computable.

    The Trumba form has no end-time field — it asks for a Duration as separate
    Hours/Minutes inputs. end - start is a timedelta, so day rollovers and
    am/pm shifts are handled naturally (both datetimes are Eastern-local here)."""
    if ev.all_day or not ev.end_datetime:
        return None
    total = int((ev.end_datetime - ev.start_datetime).total_seconds() // 60)
    if total <= 0:
        return None
    return divmod(total, 60)


# Map our canonical category slugs to a search term to type into ABC11's
# react-select Category box; the extension types it and picks whichever
# rendered option is an exact (else prefix) match, per term. ABC11's
# vocabulary is a fixed 17-term list (verified live 2026-08-03 — see suite
# 46.1) with no "Music"/"Family"/etc. terms, so most of our slugs have no
# defensible match — those are left unmapped rather than guessing (a wrong
# category is worse than none; adapters never invent content).
_CAT_MAP = {
    "music": "Theater / Concerts",
    "dance": "Theater / Concerts",
    "comedy": "Theater / Concerts",
    "theatre": "Theater / Concerts",
    "arts": "Art / Photography / Crafts",
    "food-drink": "Food and Beverage / Farmer's Market",
    "market": "Food and Beverage / Farmer's Market",
    "festival": "Festivals / Parades",
    "community": "Community Events / Volunteerism",
    "education": "School / Education",
    "sports": "Sports and Recreation",
    # Unmapped — no defensible match in ABC11's vocabulary; left out so no
    # category is sent rather than stretching to a nearest neighbour:
    # family-kids, literary, nightlife, wellness, film.
}


def _cat_terms(ev) -> str:
    seen: list[str] = []
    for slug in ev.categories:
        term = _CAT_MAP.get(slug)
        if term and term not in seen:
            seen.append(term)
    return ",".join(seen)


# Declared once; consumed by the server-side fill loop (h.apply_specs) and the
# manual-review recipe export. Date/time are best-effort (optional) as before.
# NOTE: #eventStartDate-label is NOT a <label> — the id just happens to end in
# "-label". It's the Fluent UI (Office UI Fabric) datepicker's own text input
# (role="combobox"), the only date input on the form; the selector is correct
# as-is and needs no fallback. What it does need is the retry handled by the
# content-script date handler (see fillInputVerified) — Trumba's widget
# self-populates the field with a near-current default shortly after load
# (see the ready_selector comment below), so a value written before that
# default fires gets silently overwritten.
_RECIPE_FIELDS = [
    RecipeField("#cf3", "text", lambda ev: ev.title, required=True, label="Event title"),
    RecipeField("#cf4", "textarea", lambda ev: ev.description, label="Event Details"),
    RecipeField("#cf5", "text", _location, label="Location"),
    RecipeField("#cf6", "text", lambda ev: ev.event_url, label="Web link"),
    RecipeField("#cf33293", "text", lambda ev: h.format_cost(ev.is_free, ev.price), label="Cost"),
    RecipeField("#cf33704", "text", lambda ev: ev.organizer_name, label="Contact Name"),
    RecipeField("#cf34384", "text", lambda ev: ev.contact_phone, label="Contact Phone"),
    RecipeField("#cf34385", "text", lambda ev: ev.contact_email, label="Contact Email"),
    RecipeField(
        "#cf35", "text", lambda ev: ev.organizer_name, required=True, label="Submitter Name"
    ),
    RecipeField(
        "#cf37", "text", lambda ev: ev.contact_email, required=True, label="Submitter Email"
    ),
    RecipeField(
        "#cf36", "text", lambda ev: ev.contact_phone, required=True, label="Submitter Phone"
    ),
    RecipeField(
        "#eventStartDate-label",
        "date",
        lambda ev: _date(ev.start_datetime),
        label="Start date",
        hint="Trumba's own widget self-populates a default shortly after load; "
        "the fill must re-read and re-apply if that default overwrites us",
    ),
    RecipeField(
        "#eventStartTime",
        "time",
        lambda ev: "" if ev.all_day else h.format_time(ev.start_datetime).lower(),
        label="Start time",
    ),
]


class Abc11CommunityAdapter(SiteAdapter):
    key = "abc11_community"
    name = "ABC11 Community Calendar"
    submission_url = _TRUMBA_URL
    requires_auth = False
    eligibility = Eligibility(localities=TRIANGLE, categories=frozenset())
    recipe_fields = _RECIPE_FIELDS
    submit_selector = "button[type='submit'].clrCommit"
    # The date/time widgets self-populate with a near-current default shortly
    # after the page "completes" — waiting on the first field (as the default
    # ready_selector does) can fire before that default-setting effect runs,
    # so our fill loses the race on a slow connection. The submit button is
    # the last element Trumba renders, so gating on it instead means the
    # React tree (including the date/time defaults) has already settled by
    # the time we start writing.
    ready_selector = "button[type='submit'].clrCommit"
    captcha_hint = "Solve any captcha or Trumba/Disney sign-in shown before submitting."

    def recipe_field_specs(self, ev):
        """Static fields + computed Duration (hours/minutes) and the Category
        react-select, both event-dependent so only added when we can resolve them."""
        specs = list(_RECIPE_FIELDS)
        dur = _duration(ev)
        if dur:
            hours, minutes = dur
            specs.append(
                RecipeField(
                    "#eventDurationHours",
                    "text",
                    lambda ev, hh=hours: str(hh),
                    label="Duration (hours)",
                )
            )
            specs.append(
                RecipeField(
                    "#eventDurationMinutes",
                    "text",
                    lambda ev, mm=minutes: str(mm),
                    label="Duration (minutes)",
                )
            )
        cats = _cat_terms(ev)
        if cats:
            specs.append(
                RecipeField(
                    "#cf33292",
                    "react_select",
                    lambda ev, c=cats: c,
                    recipe_only=True,
                    label="Category",
                    hint="react-select — extension matches each term exactly (else by "
                    "prefix) and reports any it can't find",
                )
            )
        if ev.image_url:
            specs.append(
                RecipeField(
                    ".image-field-esf input[type=file]",
                    "file",
                    lambda ev: ev.image_url,
                    recipe_only=True,
                    label="Event image",
                    hint="auto-uploaded by the extension; reveals an alt-text field "
                    "on ABC11's form that must be filled in manually",
                )
            )
        return specs

    def fill_and_submit(self, page, ev, ctx):
        page.goto(self.submission_url, timeout=ctx.timeout_ms)
        page.wait_for_load_state("domcontentloaded", timeout=ctx.timeout_ms)
        h.dismiss_consent(page)

        if h.has_captcha(page):
            return TargetResult(
                status="needs_manual",
                error="captcha/bot-check present",
                screenshot_path=h.take_screenshot(page, ctx, self.key),
            )
        if self._login_wall(page):
            return TargetResult(
                status="needs_manual",
                error="Trumba/Disney login wall",
                screenshot_path=h.take_screenshot(page, ctx, self.key),
            )

        specs = self.recipe_field_specs(ev)
        missing = h.apply_specs(page, specs, ev, ctx.timeout_ms)
        if missing:
            return TargetResult(
                status="needs_manual",
                error="required fields unfilled: " + "; ".join(missing),
                screenshot_path=h.take_screenshot(page, ctx, self.key),
            )

        if ev.image_url:
            local = h.download_image(ev.image_url, ctx.download_dir)
            if local:
                _try_fill_file(page, ".image-field-esf input[type=file]", local)

        if h.has_captcha(page):
            return TargetResult(
                status="needs_manual",
                error="captcha/bot-check present",
                screenshot_path=h.take_screenshot(page, ctx, self.key),
            )

        shot = h.take_screenshot(page, ctx, self.key, "before-submit")
        if ctx.dry_run:
            return TargetResult(
                status="succeeded", error="[DRY RUN] not submitted", screenshot_path=shot
            )

        # Single commit button (labelled "Next", value="save").
        page.locator("button[type='submit'].clrCommit").first.click(timeout=ctx.timeout_ms)
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


def _try_fill_file(page, selector: str, path: str) -> None:
    try:
        page.locator(selector).first.set_input_files(path, timeout=5000)
    except Exception:
        pass
