import json
import logging

import google.generativeai as genai
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
- "title": A clean, concise event title (remove venue name if it's redundant with location)
- "description": A friendly 2-3 sentence description of the event. Keep the tone warm and community-oriented. If the raw description is empty or minimal, write a brief generic description based on the title.
- "location_name": The venue or location name, cleaned up
- "town": The city or town where this event takes place (e.g. "Chapel Hill", "Durham", "Carrboro"). Infer from the location/address if possible. If unclear, use an empty string.
- "tags": An array of applicable tags from this list ONLY: {tags}

Rules:
- Only use tags from the provided list. Choose all that apply.
- If the event is free, include "free".
- If the event time is evening (after 5pm), include "evenings-only". If daytime (before 5pm), include "daytime-only".
- Keep descriptions factual — don't invent details that aren't in the raw data.
- Respond with ONLY the JSON object. No markdown, no backticks, no explanation.

Raw event data:
Title: {title}
Description: {description}
Location: {location}
Start: {start}
End: {end}
"""


def standardize_event(raw_event: RawEvent) -> StagedEvent:
    """
    Send a RawEvent through Gemini to produce a standardized StagedEvent.
    """
    genai.configure(api_key=settings.GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-2.5-flash-lite')

    prompt = STANDARDIZATION_PROMPT.format(
        tags=json.dumps(VALID_TAGS),
        title=raw_event.raw_title,
        description=raw_event.raw_description,
        location=raw_event.raw_location,
        start=raw_event.raw_start.isoformat(),
        end=raw_event.raw_end.isoformat() if raw_event.raw_end else "Not specified",
    )

    response = model.generate_content(prompt)

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

    staged = StagedEvent.objects.create(
        raw_event=raw_event,
        title=data.get('title', raw_event.raw_title)[:500],
        description=data.get('description', ''),
        location_name=data.get('location_name', raw_event.raw_location)[:255],
        town=data.get('town', '')[:100],
        start_datetime=raw_event.raw_start,
        end_datetime=raw_event.raw_end,
        tags=valid_tags,
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
