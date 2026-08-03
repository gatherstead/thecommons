import hashlib
import queue
import re
import threading
import traceback
from datetime import date, datetime

import requests
from django.conf import settings
from django.db import connections, transaction
from django.http import StreamingHttpResponse
from django.utils import timezone
from icalendar import Calendar

from ingestion.importers.errors import (
    REFUSAL_EMPTY_FETCH,
    REFUSAL_NON_PUBLIC_URL,
    REFUSAL_NOTHING_TO_POLL,
    REFUSAL_UNKNOWN_SCRAPER_KEY,
    REFUSAL_UNKNOWN_SOURCE_TYPE,
)
from ingestion.models import EventSource, RawEvent
from ingestion.scraping.browser import render_page
from ingestion.scraping.scrapers import get_scraper

from ..sse import sse_frame
from ._shared import _debug_only, _resolve_db, _validate_url

# ── Probe (dry-run fetch+parse+write, no ORM writes survive) ──────────────────
#
# Ticket 35.6: an 8-day prod outage had all three collectors probing green
# (200, N items parsed) while the pipeline was completely dead downstream of
# parse. Fetch+parse alone can't catch a write-path regression (bad datetime
# conversion, a broken get_or_create, a migration prod hasn't picked up yet),
# so the probe now dry-runs the write step too: it builds the exact rows the
# real importer would create and issues them against the DB inside a
# transaction that is always rolled back (see _probe_dry_run_write). A failure
# there surfaces as a failing "write" stage frame instead of a silent "Done."

# Probe-only reason code for the write-stage skip on a read-only DB alias.
# Not in ingestion/importers/errors.py's REFUSAL_* set (that module is a
# read-only reference for this ticket) and, unlike those, this isn't a
# refusal — fetch and parse both succeeded, so the probe still reports
# resolved/stage frames normally; only the write stage is unavailable.
PROBE_WRITE_SKIPPED_READONLY_DB = "readonly_db_write_dry_run_unavailable"


def _probe_dry_run_write(q, db, source, raw_events):
    """Dry-run the ORM write phase the real importers do after parse:
    RawEvent.get_or_create per item, then source.last_polled = now().

    Always rolled back — even a fully successful dry run leaves zero rows
    behind. `prod_readonly` is a genuinely read-only Postgres role (SELECT
    only, enforced at the DB level — see docs/ingestion-monitoring.md "Prod
    read-only safety"), so attempting a write there wouldn't even reach the
    rollback; it degrades to an explanatory skipped frame instead of letting
    an opaque InsufficientPrivilege stand in for "can't dry-run this."
    """
    q.put(("stage", {"stage": "write", "status": "start", "item_count": len(raw_events)}))

    if db == "prod_readonly":
        q.put(
            (
                "stage",
                {
                    "stage": "write",
                    "status": "skipped",
                    "reason": PROBE_WRITE_SKIPPED_READONLY_DB,
                    "detail": (
                        "prod_readonly is a read-only Postgres role (SELECT only) — "
                        "the write-path dry run can't run against it. Point the probe "
                        "at the default DB to exercise this stage, or trust the "
                        "fetch/parse result above and check prod's own SourceRun history."
                    ),
                },
            )
        )
        return

    with transaction.atomic(using=db):
        created_count = 0
        for raw in raw_events:
            _, created = RawEvent.objects.using(db).get_or_create(
                source=source,
                source_uid=raw["source_uid"],
                defaults={
                    "raw_title": raw["raw_title"][:500],
                    "raw_description": raw["raw_description"],
                    "raw_location": raw["raw_location"][:500],
                    "raw_start_datetime": raw["raw_start_datetime"],
                    "raw_end_datetime": raw["raw_end_datetime"],
                    "source_url": raw["source_url"][:500] if raw["source_url"] else "",
                },
            )
            if created:
                created_count += 1

        # Mirrors the real importers' last_polled write (ics_importer.py:105,
        # scraper_importer.py:152) so a broken save() surfaces here too.
        source.last_polled = timezone.now()
        source.save(using=db, update_fields=["last_polled"])

        # Force the rollback from inside the block, after every write has been
        # issued and validated by Postgres — set_rollback(True) still lets any
        # IntegrityError/etc. above raise and be caught by the outer handler,
        # but on the success path it guarantees nothing here is ever committed.
        transaction.set_rollback(True, using=db)

    q.put(
        (
            "stage",
            {
                "stage": "write",
                "status": "end",
                "item_count": len(raw_events),
                "would_create": created_count,
                "rolled_back": True,
            },
        )
    )


def _probe_ics(q, url, source, db):  # noqa: C901  # mirrors fetch_ics_feed's datetime handling; complexity is inherent
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
    raw_events = []
    for component in cal.walk():
        if component.name != "VEVENT":
            continue
        count += 1
        if len(titles) < 3:
            titles.append(str(component.get("SUMMARY", "Untitled Event")))

        # Same UID/datetime handling as fetch_ics_feed (ics_importer.py:38-69)
        # — this is the conversion step the outage postmortem found the old
        # probe never exercised, so a feed that parses but breaks here used
        # to report "Done" instead of failing.
        raw_title = str(component.get("SUMMARY", "Untitled Event"))
        raw_description = str(component.get("DESCRIPTION", ""))
        raw_location = str(component.get("LOCATION", ""))

        uid = str(component.get("UID", ""))
        dtstart = component.get("DTSTART")
        dtend = component.get("DTEND")
        if dtstart is None:
            continue
        if not uid:
            uid = hashlib.sha256(f"{raw_title}{dtstart.dt}".encode()).hexdigest()

        raw_start_datetime = dtstart.dt
        raw_end_datetime = dtend.dt if dtend else None

        if isinstance(raw_start_datetime, date) and not isinstance(raw_start_datetime, datetime):
            raw_start_datetime = datetime.combine(raw_start_datetime, datetime.min.time())
            raw_start_datetime = timezone.make_aware(raw_start_datetime)
        elif timezone.is_naive(raw_start_datetime):
            raw_start_datetime = timezone.make_aware(raw_start_datetime)

        if raw_end_datetime:
            if isinstance(raw_end_datetime, date) and not isinstance(raw_end_datetime, datetime):
                raw_end_datetime = datetime.combine(raw_end_datetime, datetime.min.time())
                raw_end_datetime = timezone.make_aware(raw_end_datetime)
            elif timezone.is_naive(raw_end_datetime):
                raw_end_datetime = timezone.make_aware(raw_end_datetime)

        if raw_start_datetime < timezone.now():
            continue

        # Same URL fallback as fetch_ics_feed (ics_importer.py:76-82): prefer
        # the ICS URL property, else the first https URL found in the
        # description.
        raw_url = str(component.get("URL", ""))
        source_url = raw_url if raw_url.startswith(("http://", "https://")) else ""
        if not source_url:
            url_match = re.search(r'https?://[^\s<>"\']+', raw_description)
            if url_match:
                source_url = url_match.group(0)

        raw_events.append(
            {
                "source_uid": uid,
                "raw_title": raw_title,
                "raw_description": raw_description,
                "raw_location": raw_location,
                "raw_start_datetime": raw_start_datetime,
                "raw_end_datetime": raw_end_datetime,
                "source_url": source_url,
            }
        )
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

    _probe_dry_run_write(q, db, source, raw_events)


def _probe_scraper(q, url, scraper_key, source, db):
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

    _probe_extract(q, scraper, html, source, db)


def _probe_http(q, url, scraper_key, source, db):
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

    _probe_extract(q, scraper, html, source, db)


def _probe_extract(q, scraper, html, source, db):
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

    raw_events = [
        {
            "source_uid": item.source_uid,
            "raw_title": item.title,
            "raw_description": item.description,
            "raw_location": item.location,
            "raw_start_datetime": item.start,
            "raw_end_datetime": item.end,
            "source_url": item.source_url,
        }
        for item in items
    ]
    _probe_dry_run_write(q, db, source, raw_events)


def _run_probe_into_queue(q, *, source_id, db):
    try:
        try:
            source = EventSource.objects.using(db).get(pk=source_id)
        except EventSource.DoesNotExist:
            q.put(("error", {"message": f"EventSource {source_id} not found in db '{db}'"}))
            return

        # Read the fields we need for the resolved frame into plain locals now
        # — render_page() opens its own sync_playwright context, and the ORM
        # must not be touched *while that's active* (see CLAUDE.md guardrail).
        # `source` itself is still passed down for the write dry-run below,
        # but that only touches the ORM again after render_page() has already
        # returned, never concurrently with it.
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
            _probe_ics(q, url, source, db)
        elif source_type == "scraper":
            _probe_scraper(q, url, scraper_key, source, db)
        elif source_type == "http":
            _probe_http(q, url, scraper_key, source, db)
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
        # This runs on its own thread, and Django connections are thread-local:
        # the `EventSource` lookup above opened a connection that nothing else
        # will ever close. Leaking it holds a session open on the target
        # database, which in tests makes `DROP DATABASE` fail at teardown with
        # "being accessed by other users". `run_pipeline_into_queue` already
        # does this (pipeline_runner.py) — probe needs it for the same reason.
        # close_all() rather than connection.close() because the lookup may
        # have used the `prod_readonly` alias, not `default`.
        connections.close_all()
        q.put(("done", {}))
        q.put(("__end__", None))


@_debug_only
def probe_stream(request):
    """Dry-run fetch+parse+write of a single EventSource, streamed as SSE.

    Never leaves a row behind — RawEvent/StagedEvent/SourceRun counts and
    source.last_polled are unchanged after the stream ends (see ticket 32.2,
    extended by 35.6) — that's the entire point. This reuses the same
    fetch/parse/write logic as the real importers, including the ORM-write
    phase, but every write is issued inside a transaction that is always
    rolled back (`_probe_dry_run_write`), so it's safe to point at
    `?db=prod_readonly` — which additionally skips the write attempt
    entirely, since that alias is a genuinely read-only Postgres role and
    can't dry-run a write at all (see PROBE_WRITE_SKIPPED_READONLY_DB).

    Client-IP caveat: this runs from the operator's machine, not the prod
    poller, so it structurally cannot reproduce IP- or User-Agent-based
    blocking by the source's own WAF — a probe here proves the write path
    works from here, not that prod's poller can reach the source at all.
    Surfaced in monitor.html's Probe tab, not just here.
    """
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
