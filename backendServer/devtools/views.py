import ipaddress
import queue
import socket
import threading
import traceback
from datetime import timedelta
from urllib.parse import urlparse

import requests
from django.conf import settings
from django.db import transaction
from django.http import Http404, HttpResponseBadRequest, JsonResponse, StreamingHttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_protect
from icalendar import Calendar

from events.models import Event, Town
from ingestion.deduplicator import dedup_all_pending
from ingestion.importers.errors import (
    REFUSAL_EMPTY_FETCH,
    REFUSAL_NON_PUBLIC_URL,
    REFUSAL_NOTHING_TO_POLL,
    REFUSAL_UNKNOWN_SCRAPER_KEY,
    REFUSAL_UNKNOWN_SOURCE_TYPE,
)
from ingestion.importers.ics_importer import fetch_ics_feed
from ingestion.importers.scraper_importer import fetch_http_source, fetch_scraper_source
from ingestion.models import EventSource, RawEvent, StagedEvent
from ingestion.safety_scorer import score_all_unscored
from ingestion.scraping.browser import render_page
from ingestion.scraping.scrapers import get_scraper, list_scrapers
from ingestion.services import auto_publish_safe_events
from ingestion.standardizer import standardize_all_unprocessed

from .monitoring import (
    broadcast_inbound_summary,
    broadcast_outbound_summary,
    collector_summary,
    drilldown,
)
from .pipeline_runner import _event_dict, _resolve_source_name, run_pipeline_into_queue
from .sse import sse_frame

# ── SSRF guard ────────────────────────────────────────────────────────────────

_BLOCKED_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "169.254.169.254"}

# ── Monitoring ────────────────────────────────────────────────────────────────

_WINDOW_DAYS = {"7d": 7, "30d": 30, "90d": 90}


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


def index(request):
    if not settings.DEBUG:
        raise Http404
    return render(request, "devtools/index.html")


def playground(request):
    if not settings.DEBUG:
        raise Http404
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


# ── Probe (dry-run fetch+parse, no ORM writes) ─────────────────────────────────


def _probe_ics(q, url):
    q.put(("stage", {"stage": "fetch", "status": "start", "url": url}))
    response = requests.get(
        url,
        timeout=30,
        headers={"User-Agent": settings.INGEST_SCRAPER_USER_AGENT},
    )
    response.raise_for_status()
    body = response.text
    q.put(
        (
            "stage",
            {
                "stage": "fetch",
                "status": "end",
                "http_status": response.status_code,
                "bytes": len(response.content),
            },
        )
    )

    if not body:
        q.put(("refused", {"reason": REFUSAL_EMPTY_FETCH, "detail": url}))
        return

    q.put(("stage", {"stage": "parse", "status": "start"}))
    cal = Calendar.from_ical(body)
    titles = []
    count = 0
    for component in cal.walk():
        if component.name != "VEVENT":
            continue
        count += 1
        if len(titles) < 3:
            titles.append(str(component.get("SUMMARY", "Untitled Event")))
    q.put(
        (
            "stage",
            {
                "stage": "parse",
                "status": "end",
                "item_count": count,
                "sample_titles": titles,
            },
        )
    )


def _probe_scraper(q, url, scraper_key):
    scraper = get_scraper(scraper_key)
    if not scraper_key or scraper is None:
        q.put(("refused", {"reason": REFUSAL_UNKNOWN_SCRAPER_KEY, "detail": scraper_key}))
        return

    wait_selector = getattr(scraper, "wait_selector", None)
    q.put(("stage", {"stage": "fetch", "status": "start", "url": url}))
    html = render_page(url, wait_selector=wait_selector)
    q.put(("stage", {"stage": "fetch", "status": "end", "bytes": len(html)}))

    if not html:
        q.put(("refused", {"reason": REFUSAL_EMPTY_FETCH, "detail": url}))
        return

    _probe_extract(q, scraper, html)


def _probe_http(q, url, scraper_key):
    scraper = get_scraper(scraper_key)
    if not scraper_key or scraper is None:
        q.put(("refused", {"reason": REFUSAL_UNKNOWN_SCRAPER_KEY, "detail": scraper_key}))
        return

    q.put(("stage", {"stage": "fetch", "status": "start", "url": url}))
    response = requests.get(
        url,
        timeout=settings.INGEST_SCRAPER_TIMEOUT_MS / 1000,
        headers={"User-Agent": settings.INGEST_SCRAPER_USER_AGENT},
    )
    response.raise_for_status()
    html = response.text
    q.put(
        (
            "stage",
            {
                "stage": "fetch",
                "status": "end",
                "http_status": response.status_code,
                "bytes": len(response.content),
            },
        )
    )

    if not html:
        q.put(("refused", {"reason": REFUSAL_EMPTY_FETCH, "detail": url}))
        return

    _probe_extract(q, scraper, html)


def _probe_extract(q, scraper, html):
    q.put(("stage", {"stage": "parse", "status": "start"}))
    items = scraper.extract(html)
    titles = [item.title for item in items[:3]]
    q.put(
        (
            "stage",
            {
                "stage": "parse",
                "status": "end",
                "item_count": len(items),
                "sample_titles": titles,
            },
        )
    )


def _run_probe_into_queue(q, *, source_id, db):
    try:
        try:
            source = EventSource.objects.using(db).get(pk=source_id)
        except EventSource.DoesNotExist:
            q.put(("error", {"message": f"EventSource {source_id} not found in db '{db}'"}))
            return

        # Read every field we need into plain locals now — render_page() opens
        # its own sync_playwright context, and the ORM must not be touched again
        # once that starts (see CLAUDE.md guardrail).
        url = source.url
        scraper_key = source.scraper_key
        source_type = source.source_type
        name = source.name

        q.put(
            (
                "resolved",
                {"source_id": source_id, "name": name, "source_type": source_type, "url": url},
            )
        )

        if source_type in ("direct", "email"):
            q.put(
                (
                    "refused",
                    {
                        "reason": REFUSAL_NOTHING_TO_POLL,
                        "detail": f"source_type '{source_type}' has no fetch step",
                    },
                )
            )
            return

        try:
            _validate_url(url)
        except ValueError as exc:
            q.put(("refused", {"reason": REFUSAL_NON_PUBLIC_URL, "detail": str(exc)}))
            return

        if source_type == "ics":
            _probe_ics(q, url)
        elif source_type == "scraper":
            _probe_scraper(q, url, scraper_key)
        elif source_type == "http":
            _probe_http(q, url, scraper_key)
        else:
            q.put(("refused", {"reason": REFUSAL_UNKNOWN_SOURCE_TYPE, "detail": source_type}))

    except Exception as exc:
        q.put(
            (
                "error",
                {
                    "exception_class": type(exc).__name__,
                    "message": str(exc),
                    "traceback": traceback.format_exc(),
                },
            )
        )
    finally:
        q.put(("done", {}))
        q.put(("__end__", None))


def probe_stream(request):
    """Dry-run fetch+parse of a single EventSource, streamed as SSE.

    Never writes RawEvent/StagedEvent/SourceRun rows and never touches
    source.last_polled — that's the entire point (see ticket 32.2). This
    reuses the same fetch/parse logic as the real importers but stops before
    the ORM-write phase, so it's safe to point at `?db=prod_readonly`.
    """
    if not settings.DEBUG:
        raise Http404

    source_id_raw = request.GET.get("source_id", "").strip()
    db = _resolve_db(request)

    def _error_stream(message):
        yield sse_frame("error", {"message": message})
        yield sse_frame("done", {})

    if not source_id_raw.isdigit():
        return StreamingHttpResponse(
            _error_stream("source_id is required and must be an integer"),
            content_type="text/event-stream",
        )
    source_id = int(source_id_raw)

    q = queue.Queue()
    t = threading.Thread(
        target=_run_probe_into_queue,
        args=(q,),
        kwargs={"source_id": source_id, "db": db},
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
def publish_events_only(request):
    """Publish events now without registering the source for daily cron (active=False)."""
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


def sources_api(request):
    if not settings.DEBUG:
        raise Http404
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


def _resolve_db(request):
    db = request.GET.get("db", "default")
    if db not in ("default", "prod_readonly") or db not in settings.DATABASES:
        db = "default"
    return db


def _resolve_window(request):
    window = request.GET.get("window", "30d")
    if window not in _WINDOW_DAYS:
        window = "30d"
    end = timezone.now()
    start = end - timedelta(days=_WINDOW_DAYS[window])
    return window, start, end


def monitor(request):
    if not settings.DEBUG:
        raise Http404

    db = _resolve_db(request)
    window, start, end = _resolve_window(request)

    return render(
        request,
        "devtools/monitor.html",
        {
            "collectors": collector_summary(db, start, end),
            "inbound": broadcast_inbound_summary(db, start, end),
            "outbound": broadcast_outbound_summary(db, start, end),
            "db": db,
            "window": window,
            "prod_readonly_configured": "prod_readonly" in settings.DATABASES,
        },
    )


def monitor_data(request):
    if not settings.DEBUG:
        raise Http404

    kind = request.GET.get("kind", "")
    if kind not in ("collector", "inbound", "outbound", "runs"):
        return JsonResponse({"error": f"invalid kind '{kind}'"}, status=400)

    db = _resolve_db(request)
    _, start, end = _resolve_window(request)

    key = request.GET.get("key", "")
    if kind != "outbound":
        key = int(key) if key.isdigit() else None
    else:
        key = key or None

    limit_raw = request.GET.get("limit", "").strip()
    limit = min(int(limit_raw), 100) if limit_raw.isdigit() else 100

    rows = drilldown(db, kind, key, start, end, limit=limit)
    return JsonResponse({"rows": rows, "db": db})
