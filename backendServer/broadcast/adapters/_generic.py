"""Shared label-driven fill flow for Tier 1 adapters.

Until a site's real selectors are captured (scaffold_adapter), adapters
declare label-based field specs and run this standard flow. Any adapter can
override fill_and_submit entirely once real selectors are known.

The flow enforces the hard rules from the design doc §8: captcha/login wall →
needs_manual; missing required field → needs_manual; dry_run never clicks
final submit; screenshots before and after submit.
"""
from dataclasses import dataclass

from broadcast.adapters import _helpers as h
from broadcast.adapters.base import RunContext, TargetResult
from broadcast.schema import CanonicalEvent


@dataclass(frozen=True)
class FieldSpec:
    label: str            # accessible label / placeholder text to locate by
    required: bool = False
    exact: bool = False


def _field_values(ev: CanonicalEvent) -> dict[str, str]:
    return {
        "title": ev.title,
        "description": ev.description,
        "start_date": h.format_date(ev.start_datetime),
        "start_time": "" if ev.all_day else h.format_time(ev.start_datetime),
        "end_date": h.format_date(ev.end_datetime) if ev.end_datetime else "",
        "end_time": h.format_time(ev.end_datetime) if ev.end_datetime and not ev.all_day else "",
        "venue_name": ev.venue_name,
        "address": h.full_address(ev),
        "address_line1": ev.address_line1,
        "city": ev.city,
        "state": ev.state,
        "zip": ev.zip,
        "event_url": ev.event_url,
        "ticket_url": ev.ticket_url,
        "price": ev.price,
        "organizer_name": ev.organizer_name,
        "contact_email": ev.contact_email,
        "contact_phone": ev.contact_phone,
    }


def _try_fill(page, spec: FieldSpec, value: str, timeout_ms: int) -> bool:
    try:
        locator = page.get_by_label(spec.label, exact=spec.exact).first
        locator.fill(value, timeout=timeout_ms)
        return True
    except Exception:
        try:
            locator = page.get_by_placeholder(spec.label).first
            locator.fill(value, timeout=timeout_ms)
            return True
        except Exception:
            return False


def standard_fill_and_submit(
    adapter,
    page,
    ev: CanonicalEvent,
    ctx: RunContext,
    *,
    fields: dict[str, FieldSpec],
    cat_map: dict[str, str] | None = None,
    categories_label: str | None = None,
    image_label: str | None = None,
    submit_button: str = "Submit",
    success_locator: str | None = None,
) -> TargetResult:
    page.goto(adapter.submission_url, timeout=ctx.timeout_ms)
    page.wait_for_load_state("domcontentloaded", timeout=ctx.timeout_ms)
    h.dismiss_consent(page)

    if h.has_captcha(page):
        return TargetResult(status="needs_manual", error="captcha/bot-check present",
                            screenshot_path=h.take_screenshot(page, ctx, adapter.key))

    values = _field_values(ev)
    missing_required = []
    for field_name, spec in fields.items():
        value = values.get(field_name, "")
        if not value:
            if spec.required:
                missing_required.append(f"{field_name}: no value submitted")
            continue
        filled = _try_fill(page, spec, value, min(ctx.timeout_ms, 5000))
        if not filled and spec.required:
            missing_required.append(f"{field_name}: control '{spec.label}' not found")

    if missing_required:
        return TargetResult(
            status="needs_manual",
            error="required fields unfilled: " + "; ".join(missing_required),
            screenshot_path=h.take_screenshot(page, ctx, adapter.key),
        )

    if cat_map and categories_label:
        labels = sorted({cat_map[c] for c in ev.categories if c in cat_map})
        try:
            h.select_categories(page, page.get_by_label(categories_label).first, labels)
        except Exception:
            pass  # categories are best-effort on sites with non-standard pickers

    if image_label and ev.image_url:
        local = h.download_image(ev.image_url, ctx.download_dir)
        if local:
            try:
                page.get_by_label(image_label).first.set_input_files(local, timeout=5000)
            except Exception:
                pass

    # re-check: some sites inject a captcha after interaction
    if h.has_captcha(page):
        return TargetResult(status="needs_manual", error="captcha/bot-check present",
                            screenshot_path=h.take_screenshot(page, ctx, adapter.key))

    shot = h.take_screenshot(page, ctx, adapter.key)
    if ctx.dry_run:
        return TargetResult(status="succeeded", error="[DRY RUN] not submitted",
                            screenshot_path=shot)

    page.get_by_role("button", name=submit_button).first.click(timeout=ctx.timeout_ms)
    if success_locator:
        page.locator(success_locator).first.wait_for(state="visible", timeout=ctx.timeout_ms)
    else:
        page.wait_for_load_state("load", timeout=ctx.timeout_ms)
    return TargetResult(status="succeeded", external_url=page.url,
                        screenshot_path=h.take_screenshot(page, ctx, adapter.key, "after"))
