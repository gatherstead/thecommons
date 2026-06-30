import json
import logging
import os
import time

from google import genai

from django.conf import settings

from ingestion.models import StagedEvent

logger = logging.getLogger(__name__)

SAFETY_SCORE_THRESHOLD = float(os.environ.get('SAFETY_SCORE_THRESHOLD', '0.3'))

SAFETY_PROMPT = """You are a content moderator for The Commons, a local community events platform
serving small towns in North Carolina. Your job is to evaluate whether an event is problematic.

Score the following event on a scale of 0.0 to 1.0, where:
  0.0 = completely safe, normal community event
  1.0 = definitely problematic (spam, scam, hate speech, explicit content, dangerous activity)

Be permissive. This is a community board — err heavily toward publishing. Only flag content that
is genuinely harmful, explicitly offensive, clearly spam/commercial-only, or likely a scam.
Do NOT flag events just because they are political, religious, niche, or unconventional.

Return a JSON object with exactly these fields:
- "score": a float between 0.0 and 1.0
- "notes": a one or two sentence explanation of your reasoning (especially if score > 0.2)

Respond with ONLY the JSON object. No markdown, no backticks, no explanation.

Event title: {title}
Event description: {description}
Event location: {location}
"""


def score_event(staged: StagedEvent) -> tuple[float, str]:
    """Call Gemini to score a StagedEvent for problematic content. Returns (score, notes)."""
    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    models_to_try = ['gemini-2.5-flash-lite', 'gemini-2.5-flash', 'gemini-2.5-pro']
    max_retries = 3

    prompt = SAFETY_PROMPT.format(
        title=staged.title,
        description=staged.description[:2000],
        location=staged.location_name,
    )

    response = None
    for model in models_to_try:
        for attempt in range(max_retries):
            try:
                response = client.models.generate_content(model=model, contents=prompt)
                break
            except Exception as e:
                if '503' in str(e) or 'UNAVAILABLE' in str(e):
                    wait = 2 ** attempt
                    logger.warning(
                        f"[{model}] 503 on attempt {attempt + 1}/{max_retries}, retrying in {wait}s..."
                    )
                    time.sleep(wait)
                else:
                    raise
        if response is not None:
            break
        logger.warning(f"[{model}] exhausted retries, trying next model...")

    if response is None:
        raise RuntimeError(f"All models failed scoring '{staged.title}'")

    text = response.text.strip()
    if text.startswith('```'):
        text = text.split('\n', 1)[1]
        text = text.rsplit('```', 1)[0]

    data = json.loads(text)
    score = max(0.0, min(1.0, float(data['score'])))
    notes = data.get('notes', '')
    return score, notes


def score_all_unscored(source=None):
    """Score all pending StagedEvents that have not yet been safety-scored."""
    unscored = StagedEvent.objects.filter(status='pending', safety_score__isnull=True)
    if source:
        unscored = unscored.filter(raw_event__source=source)
    count = 0

    for staged in unscored:
        try:
            score, notes = score_event(staged)
            staged.safety_score = score
            staged.safety_notes = notes
            staged.save(update_fields=['safety_score', 'safety_notes'])
            logger.info(f"Safety scored '{staged.title}': {score:.2f}")
            count += 1
        except Exception as e:
            logger.error(f"Failed to safety-score '{staged.title}': {e}")

    logger.info(f"Safety-scored {count} events")
    return count
