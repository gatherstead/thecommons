import json
import logging
import re
import time

import requests
from bs4 import BeautifulSoup
from google import genai

from django.conf import settings

from ingestion.models import RawEvent, StagedEvent

logger = logging.getLogger(__name__)

VALID_TAGS = [
    "weekends-only",
    "evenings-only",
    "daytime-only",
    "free",
    "family-friendly",
    "nature",
    "small-business",
    "lgbtq-friendly",
    "speaks-spanish",
    "wheelchair-accessible",
    "live-music",
    "food-and-drink",
    "arts-and-culture",
    "fitness-and-wellness",
    "community-meetup",
    "fundraiser",
    "market-or-fair",
    "workshop-or-class",
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
- "price": IMPORTANT — search ALL provided text (raw description AND the scraped webpage text) very carefully for price/cost indicators. Look for: "Cost: $X", "Cost: FREE", "Fee: $X", "cost: $X", "$X per person", "admission: $X", "tickets: $X", "free", "FREE", "$0", "no cost", "no charge". Return the dollar amount as a number. If the event says "free", "FREE", or "$0", return 0. If a range like "$10-$20", return the average. Only return -1 if there is absolutely NO price info anywhere in the raw data or scraped webpage and if it doesn't say free.

Rules:
- Only use tags from the provided list. Choose all that apply.
- If the event is free or price is 0, include "free" in tags.
- If the event time is evening (after 5pm), include "evenings-only". If daytime (before 5pm), include "daytime-only".
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


def fetch_page_text(url: str, max_chars: int = 6000) -> str:
    """Fetch a webpage and extract its visible text. Returns empty string on failure."""
    if not url or not url.startswith(('http://', 'https://')):
        return ''
    try:
        resp = requests.get(url, timeout=10, headers={
            'User-Agent': 'Mozilla/5.0 (compatible; TheCommons/1.0)'
        })
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')
        # Remove script/style elements
        for tag in soup(['script', 'style', 'nav']):
            tag.decompose()
        text = soup.get_text(separator='\n', strip=True)
        # Collapse blank lines but keep structure
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text[:max_chars]
    except Exception as e:
        logger.debug(f"Could not fetch {url}: {e}")
        return ''


def standardize_event(raw_event: RawEvent) -> StagedEvent:
    """
    Send a RawEvent through Gemini to produce a standardized StagedEvent.
    """
    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    models_to_try = ['gemini-2.5-flash-lite', 'gemini-2.5-flash', 'gemini-2.5-pro']
    max_retries = 3

    # Fetch the event webpage for additional context (price, details, etc.)
    page_text = fetch_page_text(raw_event.source_url)
    if page_text:
        logger.info(f"Fetched {len(page_text)} chars from {raw_event.source_url}")

    prompt = STANDARDIZATION_PROMPT.format(
        tags=json.dumps(VALID_TAGS),
        title=raw_event.raw_title,
        description=raw_event.raw_description,
        location=raw_event.raw_location,
        start=raw_event.raw_start.isoformat(),
        end=raw_event.raw_end.isoformat() if raw_event.raw_end else "Not specified",
        page_text=page_text or "No webpage available",
    )

    response = None
    for model in models_to_try:
        for attempt in range(max_retries):
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                )
                break  # success
            except Exception as e:
                if '503' in str(e) or 'UNAVAILABLE' in str(e):
                    wait = 2 ** attempt  # 1s, 2s, 4s
                    logger.warning(
                        f"[{model}] 503 on attempt {attempt + 1}/{max_retries}, "
                        f"retrying in {wait}s..."
                    )
                    time.sleep(wait)
                else:
                    raise
        if response is not None:
            break
        logger.warning(f"[{model}] exhausted retries, trying next model...")

    if response is None:
        raise RuntimeError(f"All models failed for '{raw_event.raw_title}'")

    try:
        text = response.text.strip()
        if text.startswith('```'):
            text = text.split('\n', 1)[1]
            text = text.rsplit('```', 1)[0]

        data = json.loads(text)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Gemini response for '{raw_event.raw_title}': {e}")
        logger.error(f"Raw response: {response.text}")
        raise

    valid_tags = [t for t in data.get('tags', []) if t in VALID_TAGS]

    # Parse price: -1 means N/A (displayed as "N/A" on frontend)
    price = data.get('price', -1)

    # Prefer the ICS source URL if it's a real webpage, fall back to Gemini's extraction
    if raw_event.source_url and raw_event.source_url.startswith(('http://', 'https://')):
        link = raw_event.source_url
    else:
        link = data.get('link', '') or ''
        if not link.startswith(('http://', 'https://')):
            link = ''

    staged = StagedEvent.objects.create(
        raw_event=raw_event,
        title=data.get('title', raw_event.raw_title)[:500],
        description=data.get('description', ''),
        location_name=data.get('location_name', raw_event.raw_location)[:255],
        town=data.get('town', '')[:100],
        start_datetime=raw_event.raw_start,
        end_datetime=raw_event.raw_end,
        tags=valid_tags,
        price=price,
        link=link[:500],
        status='pending',
    )

    raw_event.processed = True
    raw_event.save(update_fields=['processed'])

    logger.info(f"Standardized: {staged.title}")
    return staged


def standardize_all_unprocessed():
    """Process all RawEvents that haven't been standardized yet."""
    unprocessed = RawEvent.objects.filter(processed=False)
    count = 0

    for raw_event in unprocessed:
        try:
            standardize_event(raw_event)
            count += 1
        except Exception as e:
            logger.error(f"Failed to standardize '{raw_event.raw_title}': {e}")

    logger.info(f"Standardized {count} events")
    return count
