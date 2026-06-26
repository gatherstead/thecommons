"""Triangle on the Cheap — Gravity Forms (form id 5). Selectors verified
against a captured form dump (capture_broadcast_form triangle_on_the_cheap).

The form carries a reCAPTCHA, so a real submission always defers to a human:
we fill every field (the before-submit screenshot shows the completed form),
then return needs_manual instead of clicking. Dry runs still fill + screenshot
so the field mapping can be verified.

Submitter/org identity comes from the user-entered Contact block:
ev.organizer_name feeds both #input_5_1 (Organization name) and #input_5_4
(Your name); ev.contact_email feeds #input_5_5 (Your email).

Two static fields remain: position (#input_5_3) and heard_about (#input_5_22).

Field input_26 ("Email", autocomplete=new-password) is an anti-spam honeypot —
intentionally left blank.
"""
from broadcast.adapters import _helpers as h
from broadcast.adapters.base import RecipeField, SiteAdapter, TargetResult
from broadcast.routing import TRIANGLE, Eligibility

# Static submitter defaults — position and heard_about are not user-entered.
_POSITION = "Editor"
_HEARD_ABOUT = "Word of mouth"


def _dates(ev) -> str:
    start = h.format_date(ev.start_datetime)
    if ev.end_datetime and ev.end_datetime.date() != ev.start_datetime.date():
        return f"{start} - {h.format_date(ev.end_datetime)}"
    return start


def _city(ev) -> str:
    # Per spec, the form's City field is fed from our Locality tag.
    if ev.locality:
        return ev.locality[0].replace("-", " ").title()
    return ev.city


def _end(ev):
    return ev.end_datetime or ev.start_datetime


# Plain fillable fields. The anti-spam honeypot #input_5_26 is intentionally
# absent here (filling it flags the submission as a bot).
_RECIPE_FIELDS = [
    RecipeField("#input_5_1", "text", lambda ev: ev.organizer_name, required=True,
                label="Organization name"),
    RecipeField("#input_5_3", "text", lambda ev: _POSITION, label="Your position"),
    RecipeField("#input_5_4", "text", lambda ev: ev.organizer_name, required=True,
                label="Your name"),
    RecipeField("#input_5_5", "text", lambda ev: ev.contact_email, required=True,
                label="Your email"),
    RecipeField("#input_5_6", "text", lambda ev: ev.title, required=True, label="Event title"),
    RecipeField("#input_5_7", "textarea", lambda ev: ev.description, required=True,
                label="Event description"),
    RecipeField("#input_5_8", "date", _dates, required=True, label="Date(s)"),
    RecipeField("#input_5_10", "time", lambda ev: h.format_time(ev.start_datetime),
                required=True, label="Start time"),
    RecipeField("#input_5_9", "time", lambda ev: h.format_time(_end(ev)), required=True,
                label="End time"),
    RecipeField("#input_5_11", "text", lambda ev: ev.venue_name, required=True, label="Venue"),
    RecipeField("#input_5_13_1", "text", lambda ev: ev.address_line1, label="Address"),
    RecipeField("#input_5_13_3", "text", _city, label="City"),  # City ← Locality (per spec)
    RecipeField("#input_5_13_4", "text", lambda ev: ev.state, label="State"),
    RecipeField("#input_5_14", "text", lambda ev: ev.event_url, required=True, label="Event URL"),
    RecipeField("#input_5_16", "text", lambda ev: "0" if ev.is_free else ev.price, required=True,
                label="Cost"),
    RecipeField("#input_5_22", "text", lambda ev: _HEARD_ABOUT, label="How heard"),
]


class TriangleOnTheCheapAdapter(SiteAdapter):
    key = "triangle_on_the_cheap"
    name = "Triangle on the Cheap"
    submission_url = "https://triangleonthecheap.com/submit-an-event/"
    requires_auth = False
    eligibility = Eligibility(localities=TRIANGLE, categories=frozenset())
    recipe_fields = _RECIPE_FIELDS
    captcha_hint = "reCAPTCHA — solve it, then click Submit."
    # Gravity Forms (form id 5) submit button. TODO verify against the capture
    # (capture_broadcast_form triangle_on_the_cheap).
    submit_selector = "#gform_submit_button_5"

    def recipe_field_specs(self, ev):
        """Add the image-dependent radios + image upload (recipe_only — driven
        imperatively on the server path). Selector bakes in the chosen value."""
        specs = list(_RECIPE_FIELDS)
        has_image = bool(ev.image_url)
        photo = "Yes" if has_image else "I'm not uploading a photo"
        ai = "No" if has_image else "I'm not uploading a photo"
        specs += [
            RecipeField('input[name="input_17"][value="No"]', "radio", lambda ev: "No",
                        recipe_only=True, label="Paid advertising info?"),
            RecipeField(f'input[name="input_20"][value="{photo}"]', "radio",
                        lambda ev, v=photo: v, recipe_only=True, label="Photo permission"),
            RecipeField(f'input[name="input_25"][value="{ai}"]', "radio",
                        lambda ev, v=ai: v, recipe_only=True, label="Was AI used?"),
        ]
        if has_image:
            specs.append(RecipeField(
                "#input_5_19", "file", lambda ev: ev.image_url, recipe_only=True,
                label="Event image",
                hint="upload the image manually — files can't be auto-filled",
            ))
        return specs

    def fill_and_submit(self, page, ev, ctx):
        page.goto(self.submission_url, timeout=ctx.timeout_ms)
        page.wait_for_load_state("domcontentloaded", timeout=ctx.timeout_ms)
        h.dismiss_consent(page)

        missing = h.apply_specs(page, self.recipe_field_specs(ev), ev, ctx.timeout_ms)
        if missing:
            return TargetResult(status="needs_manual",
                                error="required fields unfilled: " + "; ".join(missing),
                                screenshot_path=h.take_screenshot(page, ctx, self.key))

        # Radio: "more info about paid advertising?" → No.
        _check_radio(page, "input_17", "No")

        has_image = bool(ev.image_url)
        if has_image:
            local = h.download_image(ev.image_url, ctx.download_dir)
            if local:
                try:
                    page.locator("#input_5_19").set_input_files(local, timeout=5000)
                except Exception:
                    has_image = False
            else:
                has_image = False
        # Photo-permission + "Was AI used?" radios depend on whether we uploaded.
        _check_radio(page, "input_20", "Yes" if has_image else "I'm not uploading a photo")
        _check_radio(page, "input_25", "No" if has_image else "I'm not uploading a photo")

        shot = h.take_screenshot(page, ctx, self.key, "before-submit")
        # reCAPTCHA is always present on this form, so there is no automated
        # submit to suppress — dry run and real run alike defer to a human via
        # manual review. Always needs_manual (never "succeeded").
        note = "[DRY RUN] " if ctx.dry_run else ""
        return TargetResult(status="needs_manual",
                            error=note + "reCAPTCHA present; submit manually",
                            screenshot_path=shot)


def _check_radio(page, name: str, value: str) -> None:
    # Double-quoted attrs: some option values contain an apostrophe.
    try:
        page.locator(f'input[name="{name}"][value="{value}"]').check(timeout=2000)
    except Exception:
        pass
