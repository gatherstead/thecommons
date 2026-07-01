"""ABC11 Community Calendar. abc11.com/community/submitevent/ is only a splash
page; the real form is a Trumba ESF (third-party React form), so we target the
Trumba URL directly (captured via capture_broadcast_form abc11_community).

The form is submittable anonymously — it collects submitter Name/Email/Phone
(required) instead of requiring a Disney sign-in — so we hardcode a single
"The Commons" submitter identity (_SUBMITTER). Later this becomes a per-client
lookup keyed by an access code — see TODO(per-client-access-codes).

Field ids (cfN) and the submit button (value="save") are verified against the
captured dump. Category (react-select) and image (custom uploader) are
best-effort; everything else maps from canonical fields.
"""
from broadcast.adapters import _helpers as h
from broadcast.adapters.base import RecipeField, SiteAdapter, TargetResult
from broadcast.routing import TRIANGLE, Eligibility

# Trumba ESF form, loaded standalone.
_TRUMBA_URL = (
    "https://www.trumba.com/esf2/index.html?webname=whuzr6myd58044bc52a92byjc7"
    "&esfFrameID=trumbaSubmitEventForm&trumbaServer=https%3A%2F%2Fwww.trumba.com"
)

# TODO(per-client-access-codes): replace with a DB-backed identity lookup.
_SUBMITTER = {
    "name": "The Commons",
    "email": "broadcast@thecommons.org",  # TODO confirm real address
    "phone": "919-000-0000",              # TODO confirm real number
}


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
# react-select Category box; the extension types it and picks the first option.
_CAT_MAP = {
    "music": "Music", "arts": "Arts", "family-kids": "Family",
    "food-drink": "Food", "festival": "Festival", "market": "Market",
    "literary": "Literature", "community": "Community", "nightlife": "Nightlife",
    "wellness": "Health", "education": "Education", "sports": "Sports",
    "film": "Film", "dance": "Dance", "comedy": "Comedy", "theatre": "Theater",
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
# NOTE: #eventStartDate-label is the field's <label>, not the input — the
# content-script date handler must fall back to the label's associated input.
_RECIPE_FIELDS = [
    RecipeField("#cf3", "text", lambda ev: ev.title, required=True, label="Event title"),
    RecipeField("#cf4", "textarea", lambda ev: ev.description, label="Event Details"),
    RecipeField("#cf5", "text", _location, label="Location"),
    RecipeField("#cf6", "text", lambda ev: ev.event_url, label="Web link"),
    RecipeField("#cf33293", "text", lambda ev: "0" if ev.is_free else ev.price, label="Cost"),
    RecipeField("#cf33704", "text", lambda ev: ev.organizer_name or _SUBMITTER["name"],
                label="Contact Name"),
    RecipeField("#cf34384", "text", lambda ev: ev.contact_phone, label="Contact Phone"),
    RecipeField("#cf34385", "text", lambda ev: ev.contact_email, label="Contact Email"),
    RecipeField("#cf35", "text", lambda ev: _SUBMITTER["name"], required=True, label="Submitter Name"),
    RecipeField("#cf37", "text", lambda ev: _SUBMITTER["email"], required=True, label="Submitter Email"),
    RecipeField("#cf36", "text", lambda ev: _SUBMITTER["phone"], required=True, label="Submitter Phone"),
    RecipeField("#eventStartDate-label", "date", lambda ev: _date(ev.start_datetime),
                label="Start date", hint="targets a label — fall back to its input"),
    RecipeField("#eventStartTime", "time",
                lambda ev: "" if ev.all_day else h.format_time(ev.start_datetime).lower(),
                label="Start time"),
]


class Abc11CommunityAdapter(SiteAdapter):
    key = "abc11_community"
    name = "ABC11 Community Calendar"
    submission_url = _TRUMBA_URL
    requires_auth = False
    eligibility = Eligibility(localities=TRIANGLE, categories=frozenset())
    recipe_fields = _RECIPE_FIELDS
    submit_selector = "button[type='submit'].clrCommit"
    captcha_hint = "Solve any captcha or Trumba/Disney sign-in shown before submitting."

    def recipe_field_specs(self, ev):
        """Static fields + computed Duration (hours/minutes) and the Category
        react-select, both event-dependent so only added when we can resolve them."""
        specs = list(_RECIPE_FIELDS)
        dur = _duration(ev)
        if dur:
            hours, minutes = dur
            specs.append(RecipeField("#eventDurationHours", "text",
                                     lambda ev, hh=hours: str(hh), label="Duration (hours)"))
            specs.append(RecipeField("#eventDurationMinutes", "text",
                                     lambda ev, mm=minutes: str(mm), label="Duration (minutes)"))
        cats = _cat_terms(ev)
        if cats:
            specs.append(RecipeField("#cf33292", "react_select", lambda ev, c=cats: c,
                                     recipe_only=True, label="Category",
                                     hint="type each term and pick the first option"))
        return specs

    def fill_and_submit(self, page, ev, ctx):
        page.goto(self.submission_url, timeout=ctx.timeout_ms)
        page.wait_for_load_state("domcontentloaded", timeout=ctx.timeout_ms)
        h.dismiss_consent(page)

        if h.has_captcha(page):
            return TargetResult(status="needs_manual", error="captcha/bot-check present",
                                screenshot_path=h.take_screenshot(page, ctx, self.key))
        if self._login_wall(page):
            return TargetResult(status="needs_manual", error="Trumba/Disney login wall",
                                screenshot_path=h.take_screenshot(page, ctx, self.key))

        missing = h.apply_specs(page, self.recipe_fields, ev, ctx.timeout_ms)
        if missing:
            return TargetResult(status="needs_manual",
                                error="required fields unfilled: " + "; ".join(missing),
                                screenshot_path=h.take_screenshot(page, ctx, self.key))

        if h.has_captcha(page):
            return TargetResult(status="needs_manual", error="captcha/bot-check present",
                                screenshot_path=h.take_screenshot(page, ctx, self.key))

        shot = h.take_screenshot(page, ctx, self.key, "before-submit")
        if ctx.dry_run:
            return TargetResult(status="succeeded", error="[DRY RUN] not submitted",
                                screenshot_path=shot)

        # Single commit button (labelled "Next", value="save").
        page.locator("button[type='submit'].clrCommit").first.click(timeout=ctx.timeout_ms)
        page.wait_for_load_state("load", timeout=ctx.timeout_ms)
        return TargetResult(status="succeeded", external_url=page.url,
                            screenshot_path=h.take_screenshot(page, ctx, self.key, "after-submit"))

    @staticmethod
    def _login_wall(page) -> bool:
        try:
            return page.locator("input[type='password']").first.is_visible(timeout=500)
        except Exception:
            return False
