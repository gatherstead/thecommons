import json
import logging
import math
import re
import time

import requests
from bs4 import BeautifulSoup
from django.conf import settings
from google import genai

from events.categories import CATEGORY_SLUGS
from ingestion.models import RawEvent, StagedEvent
from ingestion.scraping.browser import render_page

logger = logging.getLogger(__name__)

# The public post form is single-select, but `Event.categories` is a
# ManyToMany and plenty of ingested events genuinely straddle two categories
# (a brewery's live-music night is both "food-drink" and "music"; a farmers
# market with a band is "markets-fairs" and "music"). Capping at 2 rather than
# 1 lets the pipeline capture that without turning the field into a tag dump —
# the sidebar filters read best when a category means "this is one of the
# event's *main* things", not "this is tangentially related".
MAX_CATEGORIES = 2

VALID_TAGS = [
    "free",
    "family-friendly",
    "nature",
    "small-business",
    "wheelchair-accessible",
    "live-music",
    "food-and-drink",
    "arts-and-culture",
    "fitness-and-wellness",
    "community-meetup",
    "fundraiser",
    "market-or-fair",
    "workshop-or-class",
    "summer-camp",
]

STANDARDIZATION_PROMPT = """You are a data processor for a local community events platform called The Commons.
Your job is to take raw event data and standardize it into a clean, consistent format.

Given the following raw event data, produce a JSON object with these fields:
- "title": A clean, concise event title
- "description": Write a 2-3 sentence description. IMPORTANT: Each event MUST have a unique opening. Use these styles randomly:
  * Start with what makes the event special ("This weekly gathering...", "A hands-on workshop where...")
  * Start with the experience ("Enjoy live music at...", "Explore local art at...")
  * Start with the setting ("At the heart of downtown Carrboro...", "Every Tuesday evening...")
  * Start with the audience ("Perfect for families...", "Whether you're a beginner or...")
  * Start with action ("Drop in for...", "Grab your friends and head to...")
  NEVER use "Join us" or "Come out" as an opening. Summarize the raw description if available. Keep it warm and factual.
- "location_name": The venue or location name, cleaned up
- "town": The city or town where this event takes place (e.g. "Chapel Hill", "Durham", "Carrboro"). Infer from the location/address if possible. If unclear, use an empty string.
- "tags": An array of applicable tags from this list ONLY: {tags}
- "categories": An array of at most {max_categories} categories from this list ONLY: {categories}. Pick the category (or two, if it genuinely spans both) that best describes what the event IS, not just its setting or vibe. Return an empty array if nothing fits well — do not force a bad match.
- "price": IMPORTANT — search ALL provided text (raw description AND the scraped webpage text) very carefully for price/cost indicators. Look for: "Cost: $X", "Cost: FREE", "Fee: $X", "cost: $X", "$X per person", "admission: $X", "tickets: $X", "free", "FREE", "$0", "no cost", "no charge". Return the dollar amount as a number. If the event says "free", "FREE", or "$0", return 0. If a narrow, official-looking range like "$10-$20" is given, return the average. Only return -1 if there is absolutely NO price info anywhere in the raw data or scraped webpage and if it doesn't say free.
  * DO NOT trust pricing from ticket resale/secondary marketplaces (e.g. StubHub, Vivid Seats, SeatGeek, TicketSmarter, EventTicketsCenter, viagogo, or any page that says "resale", "secondary market", "prices may be above face value", or similar). Those prices are marked up and unreliable, not the face-value ticket price.
  * If the only price info comes from such a resale page, or the page shows a very wide price spread (e.g. spanning more than roughly 3x from low to high) with no single clearly-labeled face-value price, that is not usable price data — return -1 rather than guessing or averaging.

Rules:
- Only use tags from the provided list. Choose all that apply.
- Only use categories from the provided list, at most {max_categories}.
- If the event is free or price is 0, include "free" in tags.
- Keep descriptions factual — don't invent details that aren't in the raw data.
- Respond with ONLY the JSON object. No markdown, no backticks, no explanation.

Raw event data:
Title: {title}
Description: {description}
Location: {location}
Start: {start}
End: {end}

Additional context scraped from the event webpage (use this to find price, cost, fee info and other details):
{page_text}
"""

# Slimmed-down sibling of STANDARDIZATION_PROMPT for `infer_categories`, which
# only has a title/description to work with (no raw source data, no scraped
# webpage) — used by the backfill path for events that predate this ticket.
CATEGORY_INFERENCE_PROMPT = """You are a data processor for a local community events platform called The Commons.
Classify the following event into categories.

Respond with a JSON object with one field:
- "categories": An array of at most {max_categories} categories from this list ONLY: {categories}. Pick the category (or two, if it genuinely spans both) that best describes what the event IS, not just its setting or vibe. Return an empty array if nothing fits well — do not force a bad match.

Respond with ONLY the JSON object. No markdown, no backticks, no explanation.

Event title: {title}
Event description: {description}
"""

# Matches "cancelled"/"canceled" (either spelling) anywhere in a title, so
# *CANCELLED*, "Canceled – Fall Festival", and "CANCELED: Movie Night" all
# hit — the surrounding asterisks/dashes/colons are just substring context,
# not part of the pattern. Title only, deliberately: a description like "rain
# date if cancelled" must not trip this (see standardize_event below).
CANCELLED_TITLE_RE = re.compile(r"cancell?ed", re.IGNORECASE)


def _coerce_str(value, fallback: str) -> str:
    """Return `value` as a string, falling back when it's null/missing/blank.

    Gemini can legitimately emit JSON `null` for a key; `dict.get(key, fallback)`
    only applies `fallback` when the key is *absent*, not when it's present with
    a null value, so callers need this instead of a bare `.get(...)`.
    """
    if value is None:
        return fallback
    value = str(value).strip()
    return value or fallback


def _coerce_price(value):
    """Coerce a Gemini price value to a number for the `price` DecimalField.

    Accepts int/float/numeric-strings (e.g. "$10" -> not numeric -> falls back).
    Returns -1 (the existing "N/A" sentinel) on anything non-numeric, null, or
    large enough to overflow `max_digits=10, decimal_places=2`.

    NaN/Infinity need an explicit guard: `json.loads` accepts those as bare
    literals, and a NaN slips past a plain magnitude check (every comparison
    against NaN is False) only to blow up at the DecimalField write.
    """
    if value is None:
        return -1
    try:
        price = float(value)
    except (TypeError, ValueError):
        return -1
    if not math.isfinite(price):
        return -1
    if abs(price) >= 10**8:  # max_digits=10, decimal_places=2 -> 8 integer digits
        return -1
    return price


def fetch_page_text(url: str, max_chars: int = 6000, *, use_browser: bool = False) -> str:
    """Fetch a webpage and extract its visible text. Returns empty string on failure.

    By default fetches via `requests`. When `use_browser` is True, renders the
    page with Playwright (via `render_page`) first — for JS-heavy detail pages
    that come back empty over plain HTTP.
    """
    if not url or not url.startswith(("http://", "https://")):
        return ""
    try:
        if use_browser:
            html = render_page(url)
            if not html:
                return ""
        else:
            resp = requests.get(
                url,
                timeout=10,
                headers={"User-Agent": "Mozilla/5.0 (compatible; TheCommons/1.0)"},
            )
            resp.raise_for_status()
            html = resp.text
        soup = BeautifulSoup(html, "html.parser")
        # Remove script/style elements
        for tag in soup(["script", "style", "nav"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        # Collapse blank lines but keep structure
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text[:max_chars]
    except Exception as e:
        logger.debug(f"Could not fetch {url}: {e}")
        return ""


def _generate_json(client, prompt: str, *, log_label: str = "") -> dict:
    """Send `prompt` to Gemini, trying each model in the flash-lite -> flash ->
    pro fallback chain in turn (with 503 retries) until one returns parseable
    JSON.

    Extracted from `standardize_event` so `infer_categories` can reuse the same
    fallback/retry machinery instead of standing up a second Gemini client path.
    `log_label` is folded into log lines to identify the caller (e.g. a raw
    event title) — purely cosmetic, doesn't affect behavior.

    Raises RuntimeError (chained from the last underlying error) if every
    model fails — callers that need a never-raise contract (`infer_categories`)
    catch this themselves rather than this function swallowing it, so that
    `standardize_event`'s existing raise-on-total-failure behavior is
    unchanged.
    """
    models_to_try = ["gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-2.5-pro"]
    max_retries = 3

    # `data` is only set once a model produces a usable (non-empty, parseable)
    # response. A model that errors out, returns no text, or returns unparseable
    # JSON is treated as failed and we fall through to the next model — the JSON
    # parsing has to live inside this loop for that fallthrough to work.
    data = None
    last_error = None
    for model in models_to_try:
        response = None
        for attempt in range(max_retries):
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                )
                break  # success
            except Exception as e:
                last_error = e
                if "503" in str(e) or "UNAVAILABLE" in str(e):
                    wait = 2**attempt  # 1s, 2s, 4s
                    logger.warning(
                        f"[{model}] 503 on attempt {attempt + 1}/{max_retries}, "
                        f"retrying in {wait}s..."
                    )
                    time.sleep(wait)
                else:
                    # Non-503 (429/RESOURCE_EXHAUSTED, safety block, 400, ...):
                    # this model can't serve the request — stop retrying it and
                    # move on to the next model instead of aborting the function.
                    logger.warning(f"[{model}] non-retryable error, trying next model: {e}")
                    break

        if response is None:
            logger.warning(f"[{model}] exhausted retries, trying next model...")
            continue

        if not response.text:
            last_error = RuntimeError(f"[{model}] returned no text")
            logger.error(f"[{model}] Gemini returned a response with no text, trying next model")
            continue

        text = response.text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
            text = text.rsplit("```", 1)[0]

        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            last_error = e
            logger.error(f"Failed to parse Gemini response for '{log_label}': {e}")
            logger.error(f"Raw response: {response.text}")
            continue

        break  # success

    if data is None:
        raise RuntimeError(f"All models failed for '{log_label}'") from last_error

    return data


def _extract_categories(data: dict) -> list[str]:
    """Validate Gemini's `categories` array against CATEGORY_SLUGS and cap it
    at MAX_CATEGORIES — mirrors the VALID_TAGS filtering below. Never trust the
    model's spelling or its adherence to the "at most N" prompt instruction.
    """
    categories = [c for c in (data.get("categories") or []) if c in CATEGORY_SLUGS]
    return categories[:MAX_CATEGORIES]


def infer_categories(title: str, description: str) -> list[str]:
    """Classify an event into 0-MAX_CATEGORIES canonical category slugs via Gemini.

    Standalone entry point (title/description only, no RawEvent) for the later
    backfill ticket that needs to categorize events which already went through
    the pipeline before this ticket existed — `standardize_event` below covers
    the ingestion-time path. Reuses `_generate_json`'s model-fallback/retry
    loop rather than a second Gemini client path.

    Never raises: an unparseable/failed Gemini response (all models exhausted,
    bad JSON, etc.) is logged and treated as "no categories" rather than
    aborting whatever backfill loop is calling this per-event.
    """
    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    prompt = CATEGORY_INFERENCE_PROMPT.format(
        categories=json.dumps(CATEGORY_SLUGS),
        max_categories=MAX_CATEGORIES,
        title=title,
        description=description,
    )
    try:
        data = _generate_json(client, prompt, log_label=title)
    except Exception as e:
        logger.error(f"infer_categories failed for '{title}': {e}")
        return []

    return _extract_categories(data)


def standardize_event(raw_event: RawEvent, prompt_suffix: str = "") -> StagedEvent:  # noqa: C901  # LLM standardization with fallbacks; complexity is inherent
    """
    Send a RawEvent through Gemini to produce a standardized StagedEvent.
    """
    # Central chokepoint for the cancellation guard — every source passes
    # through here, unlike the two per-scraper guards (morrisvillechamber,
    # eventbriteraleigh) that only cover their own source. Checked against
    # `raw_title` (pre-standardization) and placed before the Gemini call so a
    # cancelled event never costs an API call — the title is already available
    # off the RawEvent, so there's nothing gained by waiting for standardized
    # output (which could even reword "CANCELLED" out of the title). Lands the
    # row in the terminal `cancelled` status rather than deleting it or
    # reusing `rejected`, mirroring the `skipped_no_town` precedent: visible
    # in the monitor, and RawEvent is still marked processed so it isn't
    # re-billed to Gemini on every subsequent run.
    if CANCELLED_TITLE_RE.search(raw_event.raw_title or ""):
        staged = StagedEvent.objects.create(
            raw_event=raw_event,
            title=raw_event.raw_title[:500],
            description=raw_event.raw_description,
            location_name=raw_event.raw_location[:255],
            town="",
            start_datetime=raw_event.raw_start_datetime,
            end_datetime=raw_event.raw_end_datetime,
            tags=[],
            categories=[],
            price=-1,
            link=raw_event.source_url[:500] if raw_event.source_url else "",
            status="cancelled",
        )
        raw_event.processed = True
        raw_event.save(update_fields=["processed"])
        logger.info(f"Cancelled (title match): {staged.title}")
        return staged

    client = genai.Client(api_key=settings.GEMINI_API_KEY)

    # Fetch the event webpage for additional context (price, details, etc.)
    # Scraper-type sources are JS-heavy, so render them with Playwright instead
    # of a plain requests.get (ICS/direct submissions never launch a browser).
    use_browser = bool(raw_event.source and raw_event.source.source_type == "scraper")
    page_text = fetch_page_text(raw_event.source_url, use_browser=use_browser)
    if page_text:
        logger.info(f"Fetched {len(page_text)} chars from {raw_event.source_url}")

    prompt = STANDARDIZATION_PROMPT.format(
        tags=json.dumps(VALID_TAGS),
        categories=json.dumps(CATEGORY_SLUGS),
        max_categories=MAX_CATEGORIES,
        title=raw_event.raw_title,
        description=raw_event.raw_description,
        location=raw_event.raw_location,
        start=raw_event.raw_start_datetime.isoformat(),
        end=raw_event.raw_end_datetime.isoformat()
        if raw_event.raw_end_datetime
        else "Not specified",
        page_text=page_text or "No webpage available",
    )
    if prompt_suffix:
        prompt += f"\n\nADDITIONAL SOURCE-SPECIFIC INSTRUCTIONS:\n{prompt_suffix}\n"

    data = _generate_json(client, prompt, log_label=raw_event.raw_title)

    valid_tags = [t for t in (data.get("tags") or []) if t in VALID_TAGS]
    valid_categories = _extract_categories(data)

    # Parse price: -1 means N/A (displayed as "N/A" on frontend)
    price = _coerce_price(data.get("price", -1))

    # Prefer the ICS source URL if it's a real webpage, fall back to Gemini's extraction
    if raw_event.source_url and raw_event.source_url.startswith(("http://", "https://")):
        link = raw_event.source_url
    else:
        link = data.get("link", "") or ""
        if not link.startswith(("http://", "https://")):
            link = ""

    staged = StagedEvent.objects.create(
        raw_event=raw_event,
        title=_coerce_str(data.get("title"), raw_event.raw_title)[:500],
        description=_coerce_str(data.get("description"), ""),
        location_name=_coerce_str(data.get("location_name"), raw_event.raw_location)[:255],
        town=_coerce_str(data.get("town"), "")[:100],
        start_datetime=raw_event.raw_start_datetime,
        end_datetime=raw_event.raw_end_datetime,
        tags=valid_tags,
        categories=valid_categories,
        price=price,
        link=link[:500],
        status="pending",
    )

    raw_event.processed = True
    raw_event.save(update_fields=["processed"])

    logger.info(f"Standardized: {staged.title}")
    return staged


def standardize_all_unprocessed(source=None, prompt_suffix=None):
    """Process all RawEvents that haven't been standardized yet."""
    if prompt_suffix is None and source is not None:
        prompt_suffix = source.prompt_suffix
    prompt_suffix = prompt_suffix or ""

    unprocessed = RawEvent.objects.filter(processed=False)
    if source:
        unprocessed = unprocessed.filter(source=source)
    count = 0

    for raw_event in unprocessed:
        try:
            standardize_event(raw_event, prompt_suffix=prompt_suffix)
            count += 1
        except Exception as e:
            logger.error(f"Failed to standardize '{raw_event.raw_title}': {e}")

    logger.info(f"Standardized {count} events")
    return count
