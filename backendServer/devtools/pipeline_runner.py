import logging
import threading
import traceback
from urllib.parse import urlparse

from django.db import connection, transaction

from events.models import Event, Town
from ingestion.deduplicator import dedup_all_pending
from ingestion.importers.ics_importer import fetch_ics_feed
from ingestion.importers.scraper_importer import fetch_http_source, fetch_scraper_source
from ingestion.models import EventSource, RawEvent, StagedEvent
from ingestion.safety_scorer import score_all_unscored
from ingestion.scraping.scrapers import get_scraper
from ingestion.services import auto_publish_safe_events, resolve_town
from ingestion.standardizer import standardize_all_unprocessed

from .sse import QueueLoggingHandler


class _Rollback(Exception):
    def __init__(self, final):
        self.final = final


def _fetch_source(source, *, limit=None):
    """Dispatch the FETCH stage to the right importer for the source type."""
    if source.source_type == "scraper":
        fetch_scraper_source(source, limit=limit)
    elif source.source_type == "http":
        fetch_http_source(source, limit=limit)
    else:
        fetch_ics_feed(source)


def _resolve_source_name(source_name, source_type, scraper_key, ics_url):
    """Pick the attribution label stored on EventSource.name (→ Event.source_name).

    Prefer an explicit label; else the scraper's English name ("Visit Pittsboro");
    else the raw hostname as a last resort.
    """
    if source_name:
        return source_name
    if source_type in ("scraper", "http"):
        scraper = get_scraper(scraper_key)
        if scraper is not None and scraper.name:
            return scraper.name
    return urlparse(ics_url).hostname


def _event_dict(e):
    return {
        "uuid": str(e.uuid),
        "title": e.title,
        "town": e.town.name if e.town else "",
        "date": e.date.isoformat() if e.date else None,
        "venue": e.venue,
        "description": e.description,
        "source_name": e.source_name,
        "price": str(e.price) if e.price is not None else None,
        "link": e.link,
        "tags": list(e.tags.values_list("name", flat=True)),
        "categories": list(e.categories.values_list("display_name", flat=True)),
        "is_verified": e.is_verified,
        "created_by": str(e.created_by_id) if e.created_by_id else None,
        "photo": bool(e.photo),
    }


def _run_fetch_stage(q, source, limit):
    q.put(("stage", {"stage": "fetch", "status": "start"}))

    _fetch_source(source, limit=limit)

    if limit is not None:
        keep_ids = list(RawEvent.objects.filter(source=source).values_list("id", flat=True)[:limit])
        RawEvent.objects.filter(source=source).exclude(id__in=keep_ids).delete()

    fetch_records = list(
        RawEvent.objects.filter(source=source).values(
            "id", "raw_title", "raw_location", "raw_start", "source_url", "source_uid"
        )
    )
    q.put(("stage_data", {"stage": "fetch", "records": fetch_records}))
    q.put(
        (
            "stage",
            {
                "stage": "fetch",
                "status": "end",
                "summary": {"count": len(fetch_records)},
            },
        )
    )


def _run_standardize_stage(q, source, prompt_suffix):
    q.put(("stage", {"stage": "standardize", "status": "start"}))
    std_count = standardize_all_unprocessed(source=source, prompt_suffix=prompt_suffix)
    std_records = [
        {
            "id": s.id,
            "title": s.title,
            "town": s.town,
            "location_name": s.location_name,
            "start_datetime": s.start_datetime,
            "description": s.description,
            "tags": s.tags,
            "price": s.price,
            "link": s.link,
        }
        for s in StagedEvent.objects.filter(raw_event__source=source)
    ]
    q.put(("stage_data", {"stage": "standardize", "records": std_records}))
    q.put(
        (
            "stage",
            {
                "stage": "standardize",
                "status": "end",
                "summary": {"count": std_count},
            },
        )
    )


def _run_force_town_stage(q, source, town):
    """Backfill the forced town onto staged events, but only where Gemini's own
    guess doesn't resolve to a known `Town` (empty, or a place we don't track).
    A guess that resolves to a *different* known town (e.g. a Raleigh-focused
    source occasionally surfacing a Cary event) is trusted and left alone --
    "force town" is a fallback for what Gemini couldn't determine, not a
    blanket override of what it got right. See `resolve_town` in
    `ingestion/services.py`.
    """
    q.put(("stage", {"stage": "force_town", "status": "start"}))
    for staged in StagedEvent.objects.filter(raw_event__source=source):
        if resolve_town(staged.town, None) is None:
            q.put(
                (
                    "warning",
                    {
                        "code": "town_mismatch",
                        "message": (
                            f"Gemini could not resolve town '{staged.town}' -- "
                            f"used forced '{town.name}'"
                        ),
                        "detail": {
                            "staged_title": staged.title,
                            "gemini_town": staged.town,
                        },
                    },
                )
            )
            staged.town = town.name
            staged.save(update_fields=["town"])
    q.put(("stage", {"stage": "force_town", "status": "end"}))


def _run_dedup_stage(q, source, skip_dedup):
    q.put(("stage", {"stage": "dedup", "status": "start"}))
    dedup_count = 0 if skip_dedup else dedup_all_pending(source=source)
    q.put(
        (
            "stage",
            {
                "stage": "dedup",
                "status": "end",
                "summary": {"count": dedup_count, "skipped": skip_dedup},
            },
        )
    )


def _run_safety_stage(q, source, prompt_suffix):
    q.put(("stage", {"stage": "safety", "status": "start"}))
    safety_count = score_all_unscored(source=source, prompt_suffix=prompt_suffix)
    safety_records = [
        {
            "id": s.id,
            "title": s.title,
            "safety_score": s.safety_score,
            "safety_notes": s.safety_notes,
            "status": s.status,
            "updated_at": s.updated_at.isoformat() if s.updated_at else None,
        }
        for s in StagedEvent.objects.filter(raw_event__source=source)
    ]
    q.put(("stage_data", {"stage": "safety", "records": safety_records}))
    q.put(
        (
            "stage",
            {
                "stage": "safety",
                "status": "end",
                "summary": {"count": safety_count},
            },
        )
    )


def _run_publish_stage(q, source, town):
    q.put(("stage", {"stage": "publish", "status": "start"}))
    counts = auto_publish_safe_events(source=source, force_town=town)

    # Snapshot published events BEFORE rollback may discard them. Filtered by
    # source only, not `town=town` -- `force_town` is a fallback, so some
    # events may have published under a town Gemini correctly guessed instead
    # of the operator's forced selection (see `resolve_town`), and those
    # still belong in this run's results.
    published = [
        _event_dict(e)
        for e in Event.objects.filter(
            staged_source__raw_event__source=source,
        ).distinct()
    ]

    q.put(("stage_data", {"stage": "publish", "records": published}))
    q.put(
        (
            "stage",
            {
                "stage": "publish",
                "status": "end",
                "summary": counts,
            },
        )
    )
    return counts, published


def run_pipeline_into_queue(
    q,
    *,
    city_slug,
    ics_url,
    source_name,
    dry_run=True,
    limit=None,
    prompt_suffix="",
    source_type="ics",
    scraper_key="",
    skip_dedup=False,
):
    ingestion_logger = logging.getLogger("ingestion")
    handler = QueueLoggingHandler(q, threading.get_ident())
    handler.setFormatter(logging.Formatter("%(message)s"))
    ingestion_logger.addHandler(handler)

    try:
        try:
            # Look up town before opening the transaction
            try:
                town = Town.objects.get(slug=city_slug)
            except Town.DoesNotExist:
                q.put(
                    (
                        "error",
                        {
                            "message": f"Town with slug '{city_slug}' not found.",
                            "traceback": "",
                        },
                    )
                )
                return

            with transaction.atomic():
                effective_source_name = _resolve_source_name(
                    source_name, source_type, scraper_key, ics_url
                )
                source = EventSource(
                    name=effective_source_name,
                    source_type=source_type,
                    url=ics_url,
                    active=True,
                    scraper_key=scraper_key if source_type in ("scraper", "http") else "",
                )
                source.save()

                _run_fetch_stage(q, source, limit)
                _run_standardize_stage(q, source, prompt_suffix)
                _run_force_town_stage(q, source, town)
                _run_dedup_stage(q, source, skip_dedup)
                _run_safety_stage(q, source, prompt_suffix)
                counts, published = _run_publish_stage(q, source, town)

                final = {
                    "dry_run": dry_run,
                    "town": town.name,
                    "source_name": effective_source_name,
                    "counts": counts,
                    "published": published,
                }

                if dry_run:
                    raise _Rollback(final)

            # Non-dry-run success (atomic block committed)
            q.put(("done", final))

        except _Rollback as rb:
            # Dry-run: the atomic block rolled back everything, but `final` dict survives
            q.put(("done", rb.final))

    except Exception as e:
        q.put(
            (
                "error",
                {
                    "message": str(e),
                    "traceback": traceback.format_exc(),
                },
            )
        )
    finally:
        ingestion_logger.removeHandler(handler)
        connection.close()
        q.put(("__end__", None))
