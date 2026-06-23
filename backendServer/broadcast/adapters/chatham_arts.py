"""Chatham Arts Council — Tribe Events / "The Events Calendar" community add
form (WordPress), the same platform as The Triangle Weekender. Selectors
verified against a captured form dump (scaffold_adapter chatham_arts).

Form notes from the capture:
- Required: post_title, post_content, EventStartDate.
- Venue and Organizer are select2 "Create or Find" widgets: we type the name,
  reuse an existing entry on a close string match, otherwise pick "Create".
  Detail inputs (address/email/…) only populate when we create a new entry.
- Categories are a select2 AJAX dropdown (tax_input[tribe_events_cat][]) — not
  drivable deterministically, so we skip them (eligibility already restricts
  this calendar to arts/literary events).
- A custom "Please confirm that this event takes place in Chatham County"
  checkbox (_ecp_custom_4[]) gates submission; eligibility is pittsboro/chatham
  only, so we always check it.
- #tribe-not-title is a spam honeypot ("Fake Title") — intentionally left blank.
- No captcha on this form. Submit button is #post (name=community-event).
"""
import difflib

from broadcast.adapters import _helpers as h
from broadcast.adapters.base import RecipeField, SiteAdapter, TargetResult
from broadcast.routing import Eligibility

_MATCH_THRESHOLD = 0.82  # similarity above which we reuse an existing select2 entry

# Chatham-County confirmation checkbox (required to submit).
_CHATHAM_CONFIRM = "#tribe_custom-_ecp_custom_4-PleaseconfirmthatthiseventtakesplaceinChathamCounty-0"


def _ca_date(dt) -> str:
    return f"{dt.month}/{dt.day}/{dt.year}"  # matches the datepicker's n/j/Y


def _ca_time(dt) -> str:
    return h.format_time(dt).lower()  # e.g. "7:00 pm"


def _end(ev):
    return ev.end_datetime or ev.start_datetime


# Plain fillable fields. Times, select2 widgets, the county checkbox and image
# are event-dependent or non-fillable — see recipe_field_specs().
_PLAIN_FIELDS = [
    RecipeField("#post_title", "text", lambda ev: ev.title, required=True, label="Event title"),
    RecipeField("#post_content", "textarea", lambda ev: ev.description, required=True,
                label="Description"),
    RecipeField("#EventStartDate", "date", lambda ev: _ca_date(ev.start_datetime), required=True,
                label="Start date"),
    RecipeField("#EventEndDate", "date", lambda ev: _ca_date(_end(ev)), label="End date"),
    RecipeField("#EventURL", "text", lambda ev: ev.event_url, label="External link"),
    RecipeField("#EventCost", "text", lambda ev: "0" if ev.is_free else ev.price, label="Cost"),
]


class ChathamArtsAdapter(SiteAdapter):
    key = "chatham_arts"
    name = "Chatham Arts Council"
    submission_url = "https://www.chathamartscouncil.org/calendar/community/add/"
    requires_auth = False
    # arts/literary only — "don't submit a non-art event to an arts calendar"
    eligibility = Eligibility(
        localities=frozenset({"pittsboro", "chatham"}),
        categories=frozenset({"arts", "literary"}),
    )
    recipe_fields = _PLAIN_FIELDS
    captcha_hint = ""  # no captcha on this form
    submit_selector = "#post"

    def recipe_field_specs(self, ev):
        """Plain fields + event-dependent widgets. Times only when not all_day;
        venue/organizer select2, the Chatham-County checkbox and image are
        recipe_only (driven imperatively below on the server path)."""
        specs = list(_PLAIN_FIELDS)
        if not ev.all_day:
            specs += [
                RecipeField("#EventStartTime", "time", lambda ev: _ca_time(ev.start_datetime),
                            label="Start time"),
                RecipeField("#EventEndTime", "time", lambda ev: _ca_time(_end(ev)),
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
        specs.append(RecipeField(_CHATHAM_CONFIRM, "checkbox", lambda ev: "Yes",
                                 required=True, recipe_only=True,
                                 label="Confirm event is in Chatham County"))
        if ev.image_url:
            specs.append(RecipeField("#event_image", "file", lambda ev: ev.image_url,
                                     recipe_only=True, label="Event image",
                                     hint="upload the image manually — files can't be auto-filled"))
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

        _dismiss_popups(page)

        # Required: confirm the event takes place in Chatham County.
        _check_box(page, _CHATHAM_CONFIRM)

        if ev.image_url:
            local = h.download_image(ev.image_url, ctx.download_dir)
            if local:
                _try_fill_file(page, "#event_image", local)

        if h.has_captcha(page):
            return TargetResult(status="needs_manual", error="captcha/bot-check present",
                                screenshot_path=h.take_screenshot(page, ctx, self.key))

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
