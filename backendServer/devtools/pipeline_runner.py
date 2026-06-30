import logging
import queue
import threading
import traceback
from urllib.parse import urlparse

from django.db import connection, transaction
from django.utils.text import slugify

from events.models import Event, Town
from ingestion.importers.ics_importer import fetch_ics_feed
from ingestion.models import EventSource, RawEvent, StagedEvent
from ingestion.standardizer import standardize_all_unprocessed
from ingestion.deduplicator import dedup_all_pending
from ingestion.safety_scorer import score_all_unscored
from ingestion.services import auto_publish_safe_events

from .sse import QueueLoggingHandler


class _Rollback(Exception):
    def __init__(self, final):
        self.final = final


def _event_dict(e):
    return {
        'uuid': e.uuid,
        'title': e.title,
        'town': e.town.name if e.town else '',
        'date': e.date,
        'venue': e.venue,
        'source_name': e.source_name,
        'price': e.price,
        'link': e.link,
    }


def _slugify(s):
    return slugify(s)


def run_pipeline_into_queue(q, *, city_slug, ics_url, source_name, dry_run=True, limit=None):
    ingestion_logger = logging.getLogger('ingestion')
    handler = QueueLoggingHandler(q, threading.get_ident())
    handler.setFormatter(logging.Formatter('%(message)s'))
    ingestion_logger.addHandler(handler)

    try:
        try:
            # Look up town before opening the transaction
            try:
                town = Town.objects.get(slug=city_slug)
            except Town.DoesNotExist:
                q.put(("error", {
                    "message": f"Town with slug '{city_slug}' not found.",
                    "traceback": "",
                }))
                return

            with transaction.atomic():
                # ── FETCH ─────────────────────────────────────────────────────
                q.put(("stage", {"stage": "fetch", "status": "start"}))

                effective_source_name = source_name or urlparse(ics_url).hostname
                source = EventSource(
                    name=effective_source_name,
                    source_type='ics',
                    url=ics_url,
                    active=True,
                )
                source.save()

                fetch_ics_feed(source)

                if limit is not None:
                    # Cap: keep only the first `limit` RawEvents for this source
                    keep_ids = list(
                        RawEvent.objects.filter(source=source).values_list('id', flat=True)[:limit]
                    )
                    RawEvent.objects.filter(source=source).exclude(id__in=keep_ids).delete()

                fetch_records = list(
                    RawEvent.objects.filter(source=source).values(
                        'id', 'raw_title', 'raw_location', 'raw_start', 'source_url', 'source_uid'
                    )
                )
                q.put(("stage_data", {"stage": "fetch", "records": fetch_records}))
                q.put(("stage", {
                    "stage": "fetch",
                    "status": "end",
                    "summary": {"count": len(fetch_records)},
                }))

                # ── STANDARDIZE ───────────────────────────────────────────────
                q.put(("stage", {"stage": "standardize", "status": "start"}))
                std_count = standardize_all_unprocessed(source=source)
                std_records = []
                for s in StagedEvent.objects.filter(raw_event__source=source):
                    std_records.append({
                        'id': s.id,
                        'title': s.title,
                        'town': s.town,
                        'location_name': s.location_name,
                        'start_datetime': s.start_datetime,
                        'tags': s.tags,
                        'price': s.price,
                        'link': s.link,
                    })
                q.put(("stage_data", {"stage": "standardize", "records": std_records}))
                q.put(("stage", {
                    "stage": "standardize",
                    "status": "end",
                    "summary": {"count": std_count},
                }))

                # ── FORCE_TOWN ────────────────────────────────────────────────
                q.put(("stage", {"stage": "force_town", "status": "start"}))
                for staged in StagedEvent.objects.filter(raw_event__source=source):
                    if _slugify(staged.town) != town.slug:
                        q.put(("warning", {
                            "code": "town_mismatch",
                            "message": f"Gemini guessed town '{staged.town}' but you forced '{town.name}'",
                            "detail": {
                                "staged_title": staged.title,
                                "gemini_town": staged.town,
                            },
                        }))
                    staged.town = town.name
                    staged.save(update_fields=['town'])
                q.put(("stage", {"stage": "force_town", "status": "end"}))

                # ── DEDUP ─────────────────────────────────────────────────────
                q.put(("stage", {"stage": "dedup", "status": "start"}))
                dedup_count = dedup_all_pending(source=source)
                q.put(("stage", {
                    "stage": "dedup",
                    "status": "end",
                    "summary": {"count": dedup_count},
                }))

                # ── SAFETY ────────────────────────────────────────────────────
                q.put(("stage", {"stage": "safety", "status": "start"}))
                safety_count = score_all_unscored(source=source)
                safety_records = []
                for s in StagedEvent.objects.filter(raw_event__source=source):
                    safety_records.append({
                        'id': s.id,
                        'title': s.title,
                        'safety_score': s.safety_score,
                        'safety_notes': s.safety_notes,
                        'status': s.status,
                    })
                q.put(("stage_data", {"stage": "safety", "records": safety_records}))
                q.put(("stage", {
                    "stage": "safety",
                    "status": "end",
                    "summary": {"count": safety_count},
                }))

                # ── PUBLISH ───────────────────────────────────────────────────
                q.put(("stage", {"stage": "publish", "status": "start"}))
                counts = auto_publish_safe_events(source=source, force_town=town)

                # Snapshot published events BEFORE rollback may discard them
                published = [
                    _event_dict(e)
                    for e in Event.objects.filter(
                        town=town,
                        staged_source__raw_event__source=source,
                    ).distinct()
                ]

                pub_records = published  # same shape as _event_dict output
                q.put(("stage_data", {"stage": "publish", "records": pub_records}))
                q.put(("stage", {
                    "stage": "publish",
                    "status": "end",
                    "summary": counts,
                }))

                final = {
                    'dry_run': dry_run,
                    'town': town.name,
                    'counts': counts,
                    'published': published,
                }

                if dry_run:
                    raise _Rollback(final)

            # Non-dry-run success (atomic block committed)
            q.put(("done", final))

        except _Rollback as rb:
            # Dry-run: the atomic block rolled back everything, but `final` dict survives
            q.put(("done", rb.final))

    except Exception as e:
        q.put(("error", {
            "message": str(e),
            "traceback": traceback.format_exc(),
        }))
    finally:
        ingestion_logger.removeHandler(handler)
        connection.close()
        q.put(("__end__", None))
