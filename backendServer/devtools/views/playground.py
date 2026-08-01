import queue
import threading

from django.conf import settings
from django.db import transaction
from django.http import HttpResponseBadRequest, JsonResponse, StreamingHttpResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_protect

from events.models import Event, Town
from ingestion.deduplicator import dedup_all_pending
from ingestion.importers.ics_importer import fetch_ics_feed
from ingestion.importers.scraper_importer import fetch_http_source, fetch_scraper_source
from ingestion.models import EventSource, RawEvent, StagedEvent
from ingestion.safety_scorer import score_all_unscored
from ingestion.scraping.scrapers import list_scrapers
from ingestion.services import auto_publish_safe_events
from ingestion.standardizer import standardize_all_unprocessed

from ..pipeline_runner import _event_dict, _resolve_source_name, run_pipeline_into_queue
from ..sse import sse_frame
from ._shared import _debug_only, _validate_url


def _apply_limit(source, limit):
    if limit is None:
        return
    keep_ids = list(RawEvent.objects.filter(source=source).values_list("id", flat=True)[:limit])
    RawEvent.objects.filter(source=source).exclude(id__in=keep_ids).delete()


def _ingest_and_publish(source, town, source_type, limit, prompt_suffix, skip_dedup):
    if source_type == "scraper":
        fetch_scraper_source(source, limit=limit)
    elif source_type == "http":
        fetch_http_source(source, limit=limit)
    else:
        fetch_ics_feed(source)
    _apply_limit(source, limit)
    standardize_all_unprocessed(source=source, prompt_suffix=prompt_suffix)

    for staged in StagedEvent.objects.filter(raw_event__source=source):
        staged.town = town.name
        staged.save(update_fields=["town"])

    if not skip_dedup:
        dedup_all_pending(source=source)
    score_all_unscored(source=source, prompt_suffix=prompt_suffix)
    counts = auto_publish_safe_events(source=source, force_town=town)

    published = [
        _event_dict(e)
        for e in Event.objects.filter(
            town=town,
            staged_source__raw_event__source=source,
        ).distinct()
    ]
    return published, counts


# ── Views ─────────────────────────────────────────────────────────────────────


@_debug_only
def index(request):
    return render(request, "devtools/index.html")


@_debug_only
def playground(request):
    towns = list(Town.objects.order_by("name").values("slug", "name"))
    sources = list(
        EventSource.objects.order_by("name").values(
            "id", "name", "url", "source_type", "scraper_key", "prompt_suffix", "active"
        )
    )
    return render(
        request,
        "devtools/playground.html",
        {"towns": towns, "scrapers": list_scrapers(), "sources": sources},
    )


@_debug_only
def run_stream(request):
    city = request.GET.get("city", "").strip()
    ics_url = request.GET.get("ics_url", "").strip()
    source_name = request.GET.get("source_name", "").strip()
    limit_raw = request.GET.get("limit", "").strip()
    limit = int(limit_raw) if limit_raw.isdigit() else None
    prompt_suffix = request.GET.get("prompt_suffix", "").strip()
    source_type = request.GET.get("source_type", "ics").strip()
    scraper_key = request.GET.get("scraper_key", "").strip()
    skip_dedup = request.GET.get("skip_dedup", "").strip() == "1"

    def _error_stream(message):
        yield sse_frame("error", {"message": message, "traceback": ""})

    try:
        _validate_url(ics_url)
    except ValueError as exc:
        return StreamingHttpResponse(
            _error_stream(str(exc)),
            content_type="text/event-stream",
        )

    q = queue.Queue()
    t = threading.Thread(
        target=run_pipeline_into_queue,
        args=(q,),
        kwargs={
            "city_slug": city,
            "ics_url": ics_url,
            "source_name": source_name,
            "dry_run": True,
            "limit": limit,
            "prompt_suffix": prompt_suffix,
            "source_type": source_type,
            "scraper_key": scraper_key,
            "skip_dedup": skip_dedup,
        },
        daemon=True,
    )
    t.start()

    def stream():
        while True:
            kind, payload = q.get()
            if kind == "__end__":
                break
            yield sse_frame(kind, payload)

    resp = StreamingHttpResponse(stream(), content_type="text/event-stream")
    resp["Cache-Control"] = "no-cache"
    resp["X-Accel-Buffering"] = "no"
    return resp


@csrf_protect
@_debug_only
def save_and_publish(request):
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")

    city = request.POST.get("city", "").strip()
    ics_url = request.POST.get("ics_url", "").strip()
    source_name = request.POST.get("source_name", "").strip()
    prompt_suffix = request.POST.get("prompt_suffix", "").strip()
    source_type = request.POST.get("source_type", "ics").strip()
    scraper_key = request.POST.get("scraper_key", "").strip()
    limit_raw = request.POST.get("limit", "").strip()
    limit = int(limit_raw) if limit_raw.isdigit() else None
    skip_dedup = request.POST.get("skip_dedup", "").strip() == "1"

    try:
        _validate_url(ics_url)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    try:
        town = Town.objects.get(slug=city)

        with transaction.atomic():
            effective_name = _resolve_source_name(source_name, source_type, scraper_key, ics_url)
            source, _ = EventSource.objects.get_or_create(
                url=ics_url,
                defaults={
                    "name": effective_name,
                    "source_type": source_type,
                    "active": True,
                    "prompt_suffix": prompt_suffix,
                    "scraper_key": scraper_key if source_type in ("scraper", "http") else "",
                },
            )

            # Always refresh these fields so updates on existing rows take effect
            source.name = effective_name
            source.prompt_suffix = prompt_suffix
            source.source_type = source_type
            source.scraper_key = scraper_key if source_type in ("scraper", "http") else ""
            source.save(update_fields=["name", "prompt_suffix", "source_type", "scraper_key"])

            published, counts = _ingest_and_publish(
                source, town, source_type, limit, prompt_suffix, skip_dedup
            )

        return JsonResponse({"published": published, "counts": counts})

    except Town.DoesNotExist:
        return JsonResponse({"error": f"Town '{city}' not found"}, status=400)
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=400)


@csrf_protect
@_debug_only
def publish_events_only(request):
    """Publish events now without registering the source for daily cron (active=False)."""
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")

    city = request.POST.get("city", "").strip()
    ics_url = request.POST.get("ics_url", "").strip()
    source_name = request.POST.get("source_name", "").strip()
    prompt_suffix = request.POST.get("prompt_suffix", "").strip()
    source_type = request.POST.get("source_type", "ics").strip()
    scraper_key = request.POST.get("scraper_key", "").strip()
    limit_raw = request.POST.get("limit", "").strip()
    limit = int(limit_raw) if limit_raw.isdigit() else None
    skip_dedup = request.POST.get("skip_dedup", "").strip() == "1"

    try:
        _validate_url(ics_url)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    try:
        town = Town.objects.get(slug=city)

        with transaction.atomic():
            effective_name = _resolve_source_name(source_name, source_type, scraper_key, ics_url)
            # get_or_create but never flip an existing source to active=False
            source, created = EventSource.objects.get_or_create(
                url=ics_url,
                defaults={
                    "name": effective_name,
                    "source_type": source_type,
                    "active": False,
                    "prompt_suffix": prompt_suffix,
                    "scraper_key": scraper_key if source_type in ("scraper", "http") else "",
                },
            )
            if not created:
                source.name = effective_name
                source.prompt_suffix = prompt_suffix
                source.source_type = source_type
                source.scraper_key = scraper_key if source_type in ("scraper", "http") else ""
                source.save(update_fields=["name", "prompt_suffix", "source_type", "scraper_key"])

            published, counts = _ingest_and_publish(
                source, town, source_type, limit, prompt_suffix, skip_dedup
            )

        return JsonResponse({"published": published, "counts": counts})

    except Town.DoesNotExist:
        return JsonResponse({"error": f"Town '{city}' not found"}, status=400)
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=400)


@_debug_only
def sources_api(request):
    db = request.GET.get("db", "default")
    available_dbs = settings.DATABASES
    if db not in ("default", "prod_readonly") or db not in available_dbs:
        db = "default"
    sources = list(
        EventSource.objects.using(db)
        .order_by("name")
        .values("id", "name", "url", "source_type", "scraper_key", "prompt_suffix", "active")
    )
    return JsonResponse({"sources": sources, "db": db})


@csrf_protect
@_debug_only
def add_source(request):
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")

    ics_url = request.POST.get("ics_url", "").strip()
    source_name = request.POST.get("source_name", "").strip()
    prompt_suffix = request.POST.get("prompt_suffix", "").strip()
    source_type = request.POST.get("source_type", "ics").strip()
    scraper_key = request.POST.get("scraper_key", "").strip()

    try:
        _validate_url(ics_url)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    effective_name = _resolve_source_name(source_name, source_type, scraper_key, ics_url)
    source, created = EventSource.objects.update_or_create(
        url=ics_url,
        defaults={
            "name": effective_name,
            "source_type": source_type,
            "active": True,
            "prompt_suffix": prompt_suffix,
            "scraper_key": scraper_key if source_type in ("scraper", "http") else "",
        },
    )
    return JsonResponse(
        {
            "created": created,
            "source_id": source.id,
            "name": source.name,
        }
    )
