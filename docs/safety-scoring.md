# Safety Scoring

Safety scoring is step 4 of the ingestion pipeline. It sends each staged event to Gemini and gets back a 0.0–1.0 safety score, which is then used in step 5 to auto-publish clean events or hold borderline ones for manual review.

## How it fits in the pipeline

```
poll → standardize → dedup → [safety score] → auto-publish / hold for review
```

`score_all_unscored()` queries `StagedEvent` rows where `status='pending'` and `safety_score IS NULL`, then calls Gemini once per event. Results are written back to `safety_score` (float) and `safety_notes` (text) on the model.

The `auto_publish_safe_events()` function in `services.py` then checks: if `safety_score <= SAFETY_SCORE_THRESHOLD`, auto-approve and publish; otherwise leave as `pending` for admin review.

## Threshold

`SAFETY_SCORE_THRESHOLD = 0.3` — configurable via the `SAFETY_SCORE_THRESHOLD` env var.

- score ≤ 0.3 → auto-published
- score > 0.3 → held for manual admin review in Django admin

The threshold intentionally errs toward publishing. Community content that is merely unusual, political, or religious should score well below 0.3.

## The prompt

```
You are a content moderator for The Commons, a local community events platform
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
Event description: {description}   ← truncated to 2000 chars
Event location: {location_name}
```

## What it flags vs. permits

**Should flag (score > 0.3):**
- Spam / mass-marketing / multi-level marketing recruitment
- Scams (fake prizes, advance-fee schemes, phishing)
- Hate speech, slurs, or content targeting a protected group
- Explicit sexual content
- Events promoting illegal activity

**Should permit (score ≤ 0.3):**
- Political events, candidate rallies, petition drives
- Religious services, revivals, church gatherings
- Niche or unconventional hobbies
- Anything charged or commercial (a concert with a ticket price is fine)
- Mildly adult content (a brewery event, a cigar bar meetup)

## Model selection and retries

Tries models in order: `gemini-2.5-flash-lite` → `gemini-2.5-flash` → `gemini-2.5-pro`. For each model it retries up to 3 times on 503/UNAVAILABLE with exponential backoff (1s, 2s, 4s). If all three models fail, `score_event()` raises `RuntimeError` and `score_all_unscored()` logs the error and continues to the next event.

## Known limitations

- **No score clamping.** If Gemini returns a value outside [0.0, 1.0], it is stored and used as-is. In practice this hasn't occurred because the prompt is explicit, but a `-0.1` would cause an event to auto-publish when it shouldn't.
- **Only `pending` events are scored.** Events already marked `rejected` or `duplicate` by the deduplicator are skipped — intentional, since they won't be published anyway.
- **Description truncated at 2000 chars.** Long event descriptions are cut. This is usually fine; the most important content is in the title and opening sentences.
