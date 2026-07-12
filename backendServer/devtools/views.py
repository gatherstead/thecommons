import ipaddress
import queue
import socket
import threading
from urllib.parse import urlparse

from django.conf import settings
from django.db import transaction
from django.http import Http404, HttpResponseBadRequest, JsonResponse, StreamingHttpResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_protect

from events.models import Event, Town
from ingestion.deduplicator import dedup_all_pending
from ingestion.importers.ics_importer import fetch_ics_feed
from ingestion.importers.scraper_importer import fetch_scraper_source
from ingestion.models import EventSource, StagedEvent
from ingestion.safety_scorer import score_all_unscored
from ingestion.services import auto_publish_safe_events
from ingestion.standardizer import standardize_all_unprocessed

from .pipeline_runner import _event_dict, run_pipeline_into_queue
from .sse import sse_frame

# ── SSRF guard ────────────────────────────────────────────────────────────────

_BLOCKED_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "169.254.169.254"}


def _validate_url(url):
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"URL scheme must be http or https, got '{parsed.scheme}'")

    hostname = parsed.hostname
    if not hostname:
        raise ValueError("URL has no hostname")

    if hostname in _BLOCKED_HOSTS:
        raise ValueError(f"Blocked hostname: {hostname}")

    try:
        resolved = socket.gethostbyname(hostname)
    except socket.gaierror as exc:
        raise ValueError(f"Cannot resolve hostname '{hostname}': {exc}") from exc

    ip = ipaddress.ip_address(resolved)
    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
        raise ValueError(f"Resolved IP {resolved} is not a public address")


# ── Views ─────────────────────────────────────────────────────────────────────


def index(request):
    if not settings.DEBUG:
        raise Http404
    return render(request, "devtools/index.html")


def playground(request):
    if not settings.DEBUG:
        raise Http404
    towns = list(Town.objects.order_by("name").values("slug", "name"))
    return render(request, "devtools/playground.html", {"towns": towns})


def run_stream(request):
    if not settings.DEBUG:
        raise Http404

    city = request.GET.get("city", "").strip()
    ics_url = request.GET.get("ics_url", "").strip()
    source_name = request.GET.get("source_name", "").strip()
    limit_raw = request.GET.get("limit", "").strip()
    limit = int(limit_raw) if limit_raw.isdigit() else None
    prompt_suffix = request.GET.get("prompt_suffix", "").strip()
    source_type = request.GET.get("source_type", "ics").strip()
    scraper_key = request.GET.get("scraper_key", "").strip()

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
def save_and_publish(request):
    if not settings.DEBUG:
        raise Http404

    if request.method != "POST":
        return HttpResponseBadRequest("POST required")

    city = request.POST.get("city", "").strip()
    ics_url = request.POST.get("ics_url", "").strip()
    source_name = request.POST.get("source_name", "").strip()
    prompt_suffix = request.POST.get("prompt_suffix", "").strip()
    source_type = request.POST.get("source_type", "ics").strip()
    scraper_key = request.POST.get("scraper_key", "").strip()

    try:
        _validate_url(ics_url)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    try:
        town = Town.objects.get(slug=city)

        with transaction.atomic():
            effective_name = source_name or urlparse(ics_url).hostname
            source, _ = EventSource.objects.get_or_create(
                url=ics_url,
                defaults={
                    "name": effective_name,
                    "source_type": source_type,
                    "active": True,
                    "prompt_suffix": prompt_suffix,
                    "scraper_key": scraper_key if source_type == "scraper" else "",
                },
            )

            # Always refresh prompt_suffix so updates on existing rows take effect
            source.prompt_suffix = prompt_suffix
            source.source_type = source_type
            source.scraper_key = scraper_key if source_type == "scraper" else ""
            source.save(update_fields=["prompt_suffix", "source_type", "scraper_key"])

            if source_type == "scraper":
                fetch_scraper_source(source)
            else:
                fetch_ics_feed(source)
            standardize_all_unprocessed(source=source, prompt_suffix=prompt_suffix)

            for staged in StagedEvent.objects.filter(raw_event__source=source):
                staged.town = town.name
                staged.save(update_fields=["town"])

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

        return JsonResponse({"published": published, "counts": counts})

    except Town.DoesNotExist:
        return JsonResponse({"error": f"Town '{city}' not found"}, status=400)
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=400)


@csrf_protect
def add_source(request):
    if not settings.DEBUG:
        raise Http404
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

    effective_name = source_name or urlparse(ics_url).hostname
    source, created = EventSource.objects.update_or_create(
        url=ics_url,
        defaults={
            "name": effective_name,
            "source_type": source_type,
            "active": True,
            "prompt_suffix": prompt_suffix,
            "scraper_key": scraper_key if source_type == "scraper" else "",
        },
    )
    return JsonResponse(
        {
            "created": created,
            "source_id": source.id,
            "name": source.name,
        }
    )
