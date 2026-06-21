"""The Triangle Weekender — Tribe Events / "The Events Calendar" community
add form (WordPress). Selectors verified against a captured form dump
(capture_broadcast_form triangle_weekender).

Form notes from the capture:
- Required fields: post_title, post_content, EventURL, and the terms checkbox.
- Venue and Organizer are select2 "Create or Find" widgets: we type the name,
  reuse an existing entry on a close string match, otherwise pick "Create".
  Detail inputs (address/email/…) only populate when we create a new entry.
- Categories are a select2 AJAX dropdown (remote term search) — not drivable
  deterministically, so we skip them. The custom "County" checkboxes map from
  our locality tags, so we set those.
- A newsletter popup is scheduled to appear after a delay and can cover the
  submit button; we dismiss it before submitting.
- No captcha on this form.
"""
import difflib

from broadcast.adapters import _helpers as h
from broadcast.adapters.base import RecipeField, SiteAdapter, TargetResult
from broadcast.routing import TRIANGLE, Eligibility

_MATCH_THRESHOLD = 0.82  # similarity above which we reuse an existing select2 entry

_COUNTY_MAP = {
    "durham": "Durham", "chatham": "Chatham", "pittsboro": "Chatham",
    "chapel-hill": "Orange", "carrboro": "Orange",
    "raleigh": "Wake", "cary": "Wake", "wake": "Wake",
}


def _wk_date(dt) -> str:
    return f"{dt.month}/{dt.day}/{dt.year}"  # matches the datepicker's n/j/Y


def _wk_time(dt) -> str:
    return h.format_time(dt).lower()  # e.g. "7:00 pm"


def _end(ev):
    return ev.end_datetime or ev.start_datetime


# Plain fillable fields. Times, select2 widgets, county checkboxes, image and
# terms are event-dependent or non-fillable — see recipe_field_specs().
_PLAIN_FIELDS = [
    RecipeField("#post_title", "text", lambda ev: ev.title, required=True, label="Event title"),
    RecipeField("#post_content", "textarea", lambda ev: ev.description, required=True,
                label="Description"),
    RecipeField("#EventStartDate", "date", lambda ev: _wk_date(ev.start_datetime), required=True,
                label="Start date"),
    RecipeField("#EventEndDate", "date", lambda ev: _wk_date(_end(ev)), label="End date"),
    RecipeField("#EventURL", "text", lambda ev: ev.event_url, required=True, label="Event URL"),
    RecipeField("#EventCost", "text", lambda ev: "0" if ev.is_free else ev.price, label="Cost"),
]


class TriangleWeekenderAdapter(SiteAdapter):
    key = "triangle_weekender"
    name = "The Triangle Weekender"
    submission_url = "https://thetriangleweekender.com/events/community/add/"
    requires_auth = False
    eligibility = Eligibility(localities=TRIANGLE, categories=frozenset())
    recipe_fields = _PLAIN_FIELDS
    captcha_hint = ""  # no captcha on this form
    submit_selector = "#post"

    def recipe_field_specs(self, ev):
        """Plain fields + event-dependent widgets. Times only when not all_day;
        venue/organizer select2, county checkboxes, image and terms are
        recipe_only (driven imperatively below on the server path)."""
        specs = list(_PLAIN_FIELDS)
        if not ev.all_day:
            specs += [
                RecipeField("#EventStartTime", "time", lambda ev: _wk_time(ev.start_datetime),
                            label="Start time"),
                RecipeField("#EventEndTime", "time", lambda ev: _wk_time(_end(ev)),
                            label="End time"),
            ]
        if ev.venue_name:
            specs.append(RecipeField("#saved_tribe_venue", "select2", lambda ev: ev.venue_name,
                                     recipe_only=True, label="Venue",
                                     hint="pick the match or choose Create"))
        if ev.organizer_name:
            specs.append(RecipeField("#saved_tribe_organizer", "select2",
                                     lambda ev: ev.organizer_name, recipe_only=True,
                                     label="Organizer", hint="pick the match or choose Create"))
        for county in sorted({_COUNTY_MAP[loc] for loc in ev.locality if loc in _COUNTY_MAP}):
            specs.append(RecipeField(
                f"input[name='_ecp_custom_2[]'][value='{county}']", "checkbox",
                lambda ev, c=county: c, recipe_only=True, label=f"County: {county}"))
        if ev.image_url:
            specs.append(RecipeField("#event_image", "file", lambda ev: ev.image_url,
                                     recipe_only=True, label="Event image",
                                     hint="upload the image manually — files can't be auto-filled"))
        specs.append(RecipeField("#terms", "terms", lambda ev: "true", required=True,
                                 recipe_only=True, label="Accept community terms"))
        return specs

    def fill_and_submit(self, page, ev, ctx):
        page.goto(self.submission_url, timeout=ctx.timeout_ms)
        page.wait_for_load_state("domcontentloaded", timeout=ctx.timeout_ms)
        h.dismiss_consent(page)

        if h.has_captcha(page):
            return TargetResult(status="needs_manual", error="captcha/bot-check present",
                                screenshot_path=h.take_screenshot(page, ctx, self.key))

        specs = self.recipe_field_specs(ev)
        missing = h.apply_specs(page, specs, ev, ctx.timeout_ms)
        if missing:
            return TargetResult(status="needs_manual",
                                error="required fields unfilled: " + "; ".join(missing),
                                screenshot_path=h.take_screenshot(page, ctx, self.key))

        # The timepicker leaves its dropdown open, which would intercept the next
        # click — close it before driving the venue/organizer select2 widgets.
        try:
            page.keyboard.press("Escape")
        except Exception:
            pass

        # Venue: reuse an existing venue on a close match, else create. Only fill
        # detail fields when we created a new one (existing venues self-populate).
        if ev.venue_name:
            if _select2_match_or_create(page, "saved_tribe_venue", ev.venue_name) == "created":
                for selector, value in [
                    ("input[name='venue[Address][]']", ev.address_line1),
                    ("input[name='venue[City][]']", ev.city),
                    ("#StateProvinceText", ev.state),
                    ("#EventZip", ev.zip),
                ]:
                    _try_fill(page, selector, value)

        # Organizer: same linked-post select2 pattern.
        if ev.organizer_name:
            if _select2_match_or_create(page, "saved_tribe_organizer", ev.organizer_name) == "created":
                _try_fill(page, "#organizer-email", ev.contact_email)
                _try_fill(page, "#organizer-phone", ev.contact_phone)

        # The scheduled newsletter popup can appear by now and intercept clicks.
        _dismiss_popups(page)

        # Custom "County" checkboxes (name=_ecp_custom_2[]) — drive them from the
        # same specs the recipe exports so the two paths can't drift.
        for spec in specs:
            if spec.type == "checkbox":
                _check_box(page, spec.selector)

        if ev.image_url:
            local = h.download_image(ev.image_url, ctx.download_dir)
            if local:
                _try_fill_file(page, "#event_image", local)

        # Required: agree to the community terms (checkbox is gated on scrolling
        # the terms region to the bottom).
        if not _check_terms(page):
            return TargetResult(status="needs_manual", error="could not accept terms checkbox",
                                screenshot_path=h.take_screenshot(page, ctx, self.key))

        if h.has_captcha(page):
            return TargetResult(status="needs_manual", error="captcha/bot-check present",
                                screenshot_path=h.take_screenshot(page, ctx, self.key))

        # A timed newsletter popup can overlay the submit button — clear it.
        _dismiss_popups(page)

        shot = h.take_screenshot(page, ctx, self.key, "before-submit")
        if ctx.dry_run:
            return TargetResult(status="succeeded", error="[DRY RUN] not submitted",
                                screenshot_path=shot)

        page.locator("#post").click(timeout=ctx.timeout_ms)
        page.wait_for_load_state("networkidle", timeout=ctx.timeout_ms)
        return TargetResult(status="succeeded", external_url=page.url,
                            screenshot_path=h.take_screenshot(page, ctx, self.key, "after-submit"))


def _select2_match_or_create(page, select_id: str, text: str) -> str | None:
    """Open the select2 bound to <select id=select_id>, type the value, and:
    reuse an existing option on a close string match ("matched"), otherwise pick
    the "Create: <text>" option ("created"). Returns None on any failure."""
    try:
        # Open via the select2 jQuery API — a pointer click on the selection can
        # be intercepted by a leftover jQuery-UI date/time overlay. Fall back to
        # clicking the selection element if the API isn't reachable.
        opened = False
        try:
            opened = page.evaluate(
                "(id) => { const $ = window.jQuery;"
                " if ($ && $('#' + id).data('select2')) { $('#' + id).select2('open');"
                " return true; } return false; }",
                select_id,
            )
        except Exception:
            opened = False
        if not opened:
            page.locator(
                f"xpath=//select[@id='{select_id}']"
                f"/following-sibling::span[contains(@class,'select2-container')][1]"
                f"//*[contains(@class,'select2-selection')]"
            ).first.click(timeout=3000)
        # The opened dropdown is a body-appended .select2-dropdown — scope
        # search/results to it so we don't hit the always-visible inline search
        # boxes of the category/tag widgets.
        search = page.locator(".select2-dropdown .select2-search__field").first
        search.fill(text, timeout=3000)
        page.wait_for_timeout(1000)  # let results + the freeform "Create:" render

        options = page.locator(".select2-dropdown li.select2-results__option")
        target, create_opt = None, None
        norm = text.strip().lower()
        best_ratio = 0.0
        for i in range(options.count()):
            opt = options.nth(i)
            label = (opt.inner_text() or "").strip()
            low = label.lower()
            if low.startswith("create"):
                create_opt = opt
                continue
            ratio = difflib.SequenceMatcher(None, low, norm).ratio()
            if norm and (norm in low or low in norm):
                ratio = max(ratio, 0.9)
            if ratio > best_ratio:
                best_ratio, target = ratio, opt

        if target is not None and best_ratio >= _MATCH_THRESHOLD:
            target.click(timeout=3000)
            return "matched"
        chosen = create_opt or options.first
        chosen.click(timeout=3000)
        return "created"
    except Exception:
        return None


# Close buttons used by popup/offcanvas plugins; first visible one wins.
_POPUP_CLOSE_SELECTORS = [
    ".uael-offcanvas-close",
    ".pum-close", ".popmake-close",
    ".dialog-close-button", ".elementor-popup-modal .dialog-close-button",
    "[aria-label='Close']", "[aria-label='close']",
    "button.close",
]


def _dismiss_popups(page) -> None:
    for selector in _POPUP_CLOSE_SELECTORS:
        try:
            el = page.locator(selector).first
            if el.is_visible(timeout=300):
                el.click(timeout=1500)
                return
        except Exception:
            continue
    try:
        page.keyboard.press("Escape")
    except Exception:
        pass


def _check_terms(page) -> bool:
    # Scroll the terms region to the bottom and fire a scroll event so the
    # plugin enables the agreement checkbox.
    try:
        page.locator(".tec-event-terms-description").evaluate(
            "el => { el.scrollTop = el.scrollHeight;"
            " el.dispatchEvent(new Event('scroll', {bubbles: true})); }"
        )
    except Exception:
        pass
    try:
        page.locator("#terms").check(timeout=2000)
        return True
    except Exception:
        pass
    # Fallback: force-enable and check via JS, then confirm it took.
    try:
        page.locator("#terms").evaluate(
            "el => { el.disabled = false; el.checked = true;"
            " el.dispatchEvent(new Event('change', {bubbles: true})); }"
        )
        return page.locator("#terms").is_checked()
    except Exception:
        return False


def _check_box(page, selector: str) -> None:
    """Check a checkbox, forcing through any overlay if a normal click fails."""
    for kwargs in ({"timeout": 2000}, {"timeout": 2000, "force": True}):
        try:
            page.locator(selector).first.check(**kwargs)
            return
        except Exception:
            continue


def _try_fill(page, selector: str, value: str) -> None:
    if not value:
        return
    try:
        page.locator(selector).first.fill(value, timeout=3000)
    except Exception:
        pass


def _try_fill_file(page, selector: str, path: str) -> None:
    try:
        page.locator(selector).first.set_input_files(path, timeout=5000)
    except Exception:
        pass
