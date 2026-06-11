"""Shared helpers for site adapters. Deterministic only — no generated content."""
import os
import re
from urllib.parse import urlparse

import requests

CAPTCHA_MARKERS = [
    "iframe[src*='recaptcha']",
    "iframe[src*='hcaptcha']",
    "iframe[src*='turnstile']",
    "div.g-recaptcha",
    "div.h-captcha",
    "div.cf-turnstile",
    "#challenge-form",
]

CONSENT_BUTTON_NAMES = [
    re.compile(r"reject all", re.I),
    re.compile(r"decline", re.I),
    re.compile(r"necessary only", re.I),
    re.compile(r"^accept$", re.I),
    re.compile(r"accept all", re.I),
    re.compile(r"^(ok|got it|i agree|agree|close)$", re.I),
]


def has_captcha(page) -> bool:
    for selector in CAPTCHA_MARKERS:
        try:
            if page.locator(selector).first.is_visible(timeout=500):
                return True
        except Exception:
            continue
    return False


def dismiss_consent(page) -> None:
    """Click the most privacy-preserving visible consent button, if any."""
    for pattern in CONSENT_BUTTON_NAMES:
        try:
            btn = page.get_by_role("button", name=pattern).first
            if btn.is_visible(timeout=500):
                btn.click(timeout=2000)
                return
        except Exception:
            continue


def take_screenshot(page, ctx, site_key: str, suffix: str = "") -> str:
    sub_dir = os.path.join(ctx.screenshot_dir, ctx.submission_id or "adhoc")
    os.makedirs(sub_dir, exist_ok=True)
    filename = f"{site_key}{('-' + suffix) if suffix else ''}.png"
    path = os.path.join(sub_dir, filename)
    try:
        page.screenshot(path=path, full_page=True)
    except Exception:
        # Full-page capture can fail on weird layouts; fall back to viewport.
        page.screenshot(path=path)
    return path


def download_image(image_url: str, download_dir: str) -> str | None:
    """Download the submission's image to a temp file for upload. None on failure."""
    if not image_url:
        return None
    try:
        resp = requests.get(image_url, timeout=20)
        resp.raise_for_status()
    except requests.RequestException:
        return None
    name = os.path.basename(urlparse(image_url).path) or "image"
    if "." not in name:
        ext = (resp.headers.get("Content-Type", "").split("/")[-1] or "jpg").split(";")[0]
        name = f"{name}.{ext}"
    os.makedirs(download_dir, exist_ok=True)
    path = os.path.join(download_dir, name)
    with open(path, "wb") as f:
        f.write(resp.content)
    return path


def select_categories(page, locator, values: list[str]) -> None:
    """Select multiple options on a <select multiple>, ignoring missing ones."""
    if not values:
        return
    try:
        locator.select_option(label=values)
    except Exception:
        for value in values:
            try:
                locator.select_option(label=value)
            except Exception:
                continue


def format_date(dt) -> str:
    return dt.strftime("%m/%d/%Y")


def format_time(dt) -> str:
    return dt.strftime("%I:%M %p").lstrip("0")


def full_address(ev) -> str:
    return f"{ev.address_line1}, {ev.city}, {ev.state} {ev.zip}"
