"""AI autofill — extract broadcast event fields from free text via Gemini.

Self-contained module: no imports from events/ or ingestion/ (isolation contract).
"""
import json
import logging
import time

from google import genai

from django.conf import settings

from broadcast.routing import CATEGORIES, LOCALITIES

logger = logging.getLogger(__name__)

_MODELS = ["gemini-2.5-flash-lite", "gemini-2.5-flash"]
_MAX_RETRIES = 3

_DEFAULTS = {
    "title": "",
    "description": "",
    "start_datetime": "",
    "end_datetime": "",
    "all_day": False,
    "venue_name": "",
    "address_line1": "",
    "state": "NC",
    "zip": "",
    "locality": [],
    "categories": [],
    "event_url": "",
    "ticket_url": "",
    "price": "",
    "is_free": False,
    "image_url": "",
    "organizer_name": "",
    "contact_email": "",
    "contact_phone": "",
}

_PROMPT_TEMPLATE = """\
You are a data-entry assistant for The Commons, a local events platform serving \
the NC Triangle area (Chapel Hill, Carrboro, Durham, Pittsboro, Raleigh, Cary, \
Wake County, and the broader Triangle region).

Given the raw event text below, extract structured data and return ONLY a JSON \
object — no markdown, no backticks, no explanation.

REQUIRED JSON KEYS (return all of them, use "" or [] for unknowns):
- "title"          : string — clean, concise event title
- "description"    : string — 2-3 sentence warm, factual summary
- "start_datetime" : string — "YYYY-MM-DDTHH:MM" (24h, no timezone, no seconds) \
or "" if unknown. Assume America/New_York wall-clock; do not convert.
- "end_datetime"   : string — same format as start_datetime, or ""
- "all_day"        : boolean — true only if explicitly an all-day event
- "venue_name"     : string — venue/location name
- "address_line1"  : string — street address (number + street), no city/state/zip
- "state"          : string — 2-letter US state abbreviation (default "NC")
- "zip"            : string — 5-digit ZIP code or ""
- "locality"       : array of strings — choose ONLY slugs from this list: {localities}
- "categories"     : array of strings — choose ONLY slugs from this list: {categories}
- "event_url"      : string — full URL to the event page, or ""
- "ticket_url"     : string — full URL to purchase tickets, or ""
- "price"          : string — human-readable price (e.g. "$10", "Free", "$5-$15"), or ""
- "is_free"        : boolean — true if the event is explicitly free or $0
- "image_url"      : string — full URL to an event image, or ""
- "organizer_name" : string — name of the organizing group/person, or ""
- "contact_email"  : string — contact email, or ""
- "contact_phone"  : string — contact phone, or ""

RULES:
- locality and categories MUST contain only slugs from the lists above. \
Return [] if none apply.
- Do not invent details not present in the raw text.
- Respond with ONLY the JSON object.

Raw event text:
{text}
"""


def _build_prompt(text: str) -> str:
    return _PROMPT_TEMPLATE.format(
        localities=json.dumps(sorted(LOCALITIES)),
        categories=json.dumps(sorted(CATEGORIES)),
        text=text,
    )


def _strip_fences(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        raw = raw.rsplit("```", 1)[0]
    return raw.strip()


def _coerce(data: dict) -> dict:
    result = dict(_DEFAULTS)

    result["title"] = str(data.get("title") or "")
    result["description"] = str(data.get("description") or "")

    for key in ("start_datetime", "end_datetime"):
        val = data.get(key)
        result[key] = str(val) if isinstance(val, str) and val.strip() else ""

    result["all_day"] = bool(data.get("all_day", False))
    result["venue_name"] = str(data.get("venue_name") or "")
    result["address_line1"] = str(data.get("address_line1") or "")
    result["state"] = str(data.get("state") or "NC")[:2] or "NC"
    result["zip"] = str(data.get("zip") or "")

    raw_locality = data.get("locality") or []
    result["locality"] = [s for s in raw_locality if s in LOCALITIES]

    raw_categories = data.get("categories") or []
    result["categories"] = [s for s in raw_categories if s in CATEGORIES]

    result["event_url"] = str(data.get("event_url") or "")
    result["ticket_url"] = str(data.get("ticket_url") or "")
    result["price"] = str(data.get("price") or "")
    result["is_free"] = bool(data.get("is_free", False))
    result["image_url"] = str(data.get("image_url") or "")
    result["organizer_name"] = str(data.get("organizer_name") or "")
    result["contact_email"] = str(data.get("contact_email") or "")
    result["contact_phone"] = str(data.get("contact_phone") or "")

    return result


def extract_event_fields(text: str) -> dict:
    """Call Gemini to extract EventDraft fields from free-form event text.

    Returns a dict with all EventDraft keys populated (defaults for unknowns).
    Raises RuntimeError if every model/retry attempt fails.
    Raises json.JSONDecodeError (wrapped in RuntimeError) if the response is
    unparseable after fence stripping.
    """
    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    prompt = _build_prompt(text)

    response = None
    for model in _MODELS:
        for attempt in range(_MAX_RETRIES):
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                )
                break
            except Exception as exc:
                if "503" in str(exc) or "UNAVAILABLE" in str(exc):
                    wait = 2 ** attempt
                    logger.warning(
                        "[autofill][%s] 503 on attempt %d/%d, retrying in %ds…",
                        model, attempt + 1, _MAX_RETRIES, wait,
                    )
                    time.sleep(wait)
                else:
                    logger.error("[autofill][%s] unexpected error: %s", model, exc)
                    raise
        if response is not None:
            break
        logger.warning("[autofill][%s] exhausted retries, trying next model…", model)

    if response is None:
        raise RuntimeError("AI autofill: all models/retries exhausted")

    raw_text = response.text.strip()
    clean = _strip_fences(raw_text)

    try:
        data = json.loads(clean)
    except json.JSONDecodeError as exc:
        logger.error("[autofill] JSON parse failed: %s\nRaw response: %s", exc, raw_text)
        raise RuntimeError(f"AI autofill: unparseable response — {exc}") from exc

    result = _coerce(data)
    logger.info("[autofill] extracted fields for title=%r", result.get("title"))
    return result
