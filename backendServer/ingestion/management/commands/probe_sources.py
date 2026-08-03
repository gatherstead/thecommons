"""Fetch-only reachability probe for ingestion sources (ticket 45.8).

The devtools playground (`devtools/views/probe.py`) is `DEBUG`-gated and only
ever runs from a developer's own machine, over that machine's network. It is
structurally incapable of detecting a source that blocks the *production*
egress IP -- several vendor WAFs do exactly that while returning 200 to any
dev machine, so the playground shows those sources green forever.

This command has no such blind spot: run it inside the real container and it
inherits the real egress path (IP, TLS fingerprint, whatever the container's
network looks like). That's the entire point -- do not "fix" a red probe here
by running it from a laptop instead.

Container matters:
  - `ics` / `http` sources only need plain `requests` -- the `backend`
    container is sufficient.
  - `scraper` sources need headless Chromium, which is only baked into the
    `scrape-worker` image (see `Dockerfile`'s `playwright` stage -- `backend`
    has the `playwright` *package* but no browser binary). Probing a
    scraper-type source from `backend` will report a `failed` SourceRun with
    a "Executable doesn't exist" error, not a real reachability result. Run:

        docker compose exec scrape-worker python manage.py probe_sources

Fetch-only: this never creates or mutates a `RawEvent`/`StagedEvent` row --
it only fetches, optionally parses to get an item count, and records one
`SourceRun` (trigger="probe") per source. Safe to run against prod.
"""

import logging
import traceback

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from icalendar import Calendar
from playwright.sync_api import sync_playwright

from ingestion.importers.scraper_importer import _is_public_url
from ingestion.models import EventSource, SourceRun
from ingestion.scraping.browser import CHROMIUM_ARGS
from ingestion.scraping.scrapers import get_scraper

logger = logging.getLogger("ingestion")

# Response headers that identify a WAF/CDN sitting in front of a source.
# `x-amzn-waf-action` is the whole diagnostic payload for an AWS-WAF-fronted
# source: a "challenge" is a JS/cookie check a headless render can clear, a
# "captcha"/"block" is not -- that distinction drives the remediation call on
# a companion ticket. `server` and `cf-ray` do the same job for
# Cloudflare-fronted sources (Cloudflare doesn't expose an action header the
# way AWS does, but `cf-ray` alone proves Cloudflare terminated the request).
WAF_HEADER_NAMES = ("x-amzn-waf-action", "server", "cf-ray")


def _waf_headers(headers) -> dict:
    """Case-insensitive pick of the WAF_HEADER_NAMES present in `headers`.

    `requests` hands back a `CaseInsensitiveDict`; Playwright's `Response.headers`
    is a plain dict with already-lowercased keys. Lowering everything here makes
    the two fetch paths produce an identically-shaped result.
    """
    lowered = {k.lower(): v for k, v in dict(headers or {}).items()}
    return {name: lowered[name] for name in WAF_HEADER_NAMES if name in lowered}


def _refusal_for_status(http_status):
    """A non-2xx response is itself the "source is blocking us" signal, even
    when the body isn't empty (a WAF captcha page is very much *not* empty).
    Without this check, a 403 challenge page that happens to parse to zero
    events would silently report "ok, 0 items" -- exactly the blind spot this
    command exists to close.
    """
    if http_status is None or 200 <= http_status < 300:
        return None
    return f"non_2xx_status: {http_status}"


def _fetch_via_requests(url, *, timeout):
    """Plain GET, returning (http_status, headers, body, error) -- never raises.

    Unlike `ingestion.importers.scraper_importer._fetch_via_http`, this
    doesn't call `raise_for_status()` and swallow the result to "" -- a 403
    with a WAF header attached is exactly the result this command exists to
    surface, not something to discard.
    """
    try:
        resp = requests.get(
            url, timeout=timeout, headers={"User-Agent": settings.INGEST_SCRAPER_USER_AGENT}
        )
        return resp.status_code, resp.headers, resp.text, None
    except requests.RequestException as exc:
        return None, {}, "", exc


def _fetch_via_chromium(url, *, wait_selector=None):
    """Render via headless Chromium, returning (http_status, headers, html, error).

    Deliberately not `ingestion.scraping.browser.render_page`: that helper
    discards the navigation `Response` object, but the WAF-identifying headers
    this command exists to surface only live on that response. Mirrors
    render_page's launch/context/goto sequence otherwise, including the "never
    touch the ORM while sync_playwright is active" discipline -- this function
    is pure fetch, no ORM calls anywhere inside it.
    """
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=settings.INGEST_SCRAPER_HEADLESS, args=CHROMIUM_ARGS
            )
            try:
                context = browser.new_context(user_agent=settings.INGEST_SCRAPER_USER_AGENT)
                page = context.new_page()
                response = page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=settings.INGEST_SCRAPER_TIMEOUT_MS,
                )
                if wait_selector:
                    page.wait_for_selector(
                        wait_selector, timeout=settings.INGEST_SCRAPER_TIMEOUT_MS
                    )
                html = page.content()
                http_status = response.status if response else None
                headers = dict(response.headers) if response else {}
                return http_status, headers, html, None
            finally:
                browser.close()
    except Exception as exc:
        return None, {}, "", exc


class Command(BaseCommand):
    help = (
        "Fetch-only reachability probe for ingestion sources. Records a SourceRun "
        "(trigger=probe) per source but never writes RawEvent/StagedEvent rows -- "
        "safe to run against prod. Run inside the container whose egress you're "
        "checking: `backend` covers ics/http sources, but scraper-type sources need "
        "headless Chromium and MUST run inside `scrape-worker` (the only image with "
        "the Chromium binary baked in). See this module's docstring for why this has "
        "to be a management command rather than the devtools playground."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--source",
            type=int,
            default=None,
            dest="source_id",
            help="Probe only the EventSource with this id (default: all active sources).",
        )
        parser.add_argument(
            "--include-inactive",
            action="store_true",
            help="Also probe inactive sources (default: active sources only).",
        )

    def handle(self, *args, **options):
        sources = self._resolve_sources(options)
        if not sources:
            self.stdout.write(self.style.WARNING("No matching sources to probe.\n"))
            return

        self.stdout.write(f"Probing {len(sources)} source(s)...\n")
        results = [self._probe_source(source) for source in sources]
        self._print_summary(results)

    def _resolve_sources(self, options):
        source_id = options.get("source_id")
        if source_id is not None:
            try:
                return [EventSource.objects.get(pk=source_id)]
            except EventSource.DoesNotExist as exc:
                raise CommandError(f"EventSource {source_id} does not exist") from exc

        qs = EventSource.objects.all().order_by("id")
        if not options["include_inactive"]:
            qs = qs.filter(active=True)
        return list(qs)

    def _probe_source(self, source):  # noqa: C901  # one dispatch per source_type; complexity is inherent
        """Probe a single source and record a `SourceRun`. Never raises -- any
        failure is caught and recorded as a `failed` run so one bad source can't
        abort the rest of the batch.
        """
        started_at = timezone.now()
        status = "ok"
        http_status = None
        item_count = 0
        waf_headers = {}
        error_class = ""
        error_message = ""
        tb = ""

        try:
            if source.source_type in ("direct", "email"):
                status = "skipped"
                error_message = f"source_type '{source.source_type}' has no fetch step"

            elif not _is_public_url(source.url):
                status = "refused"
                error_message = "non_public_url"

            elif source.source_type == "ics":
                http_status, headers, body, err = _fetch_via_requests(source.url, timeout=30)
                waf_headers = _waf_headers(headers)
                refusal = _refusal_for_status(http_status)
                if err is not None:
                    status, error_class, error_message = "failed", type(err).__name__, str(err)
                elif refusal:
                    status, error_message = "refused", refusal
                elif not body:
                    status, error_message = "refused", f"empty_fetch (http_status={http_status})"
                else:
                    item_count = sum(
                        1 for c in Calendar.from_ical(body).walk() if c.name == "VEVENT"
                    )

            elif source.source_type in ("scraper", "http"):
                scraper = get_scraper(source.scraper_key)
                if scraper is None:
                    status = "refused"
                    error_message = f"unknown_scraper_key: {source.scraper_key!r}"
                else:
                    if source.source_type == "scraper":
                        http_status, headers, html, err = _fetch_via_chromium(
                            source.url, wait_selector=scraper.wait_selector
                        )
                    else:
                        http_status, headers, html, err = _fetch_via_requests(
                            source.url, timeout=settings.INGEST_SCRAPER_TIMEOUT_MS / 1000
                        )
                    waf_headers = _waf_headers(headers)
                    refusal = _refusal_for_status(http_status)
                    if err is not None:
                        status, error_class, error_message = "failed", type(err).__name__, str(err)
                    elif refusal:
                        status, error_message = "refused", refusal
                    elif not html:
                        status, error_message = (
                            "refused",
                            f"empty_fetch (http_status={http_status})",
                        )
                    else:
                        item_count = len(scraper.extract(html))

            else:
                status = "refused"
                error_message = f"unknown_source_type: {source.source_type}"

        except Exception as exc:
            status = "failed"
            error_class = type(exc).__name__
            error_message = str(exc)
            tb = traceback.format_exc()
            logger.exception("probe_sources: unhandled error probing source_id=%s", source.pk)

        SourceRun.objects.create(
            source=source,
            started_at=started_at,
            finished_at=timezone.now(),
            status=status,
            trigger="probe",
            items_fetched=item_count,
            error_class=error_class,
            error_message=error_message,
            traceback=tb,
        )

        return {
            "source": source,
            "status": status,
            "http_status": http_status,
            "item_count": item_count,
            "waf_headers": waf_headers,
            "error_message": error_message,
        }

    def _print_summary(self, results):
        style_by_status = {
            "ok": self.style.SUCCESS,
            "refused": self.style.WARNING,
            "skipped": self.style.WARNING,
            "failed": self.style.ERROR,
        }
        for r in results:
            source = r["source"]
            style = style_by_status.get(r["status"], self.style.NOTICE)
            self.stdout.write(
                style(
                    f"[{r['status'].upper()}] {source.name} (id={source.id}, {source.source_type}) "
                    f"http_status={r['http_status']} items={r['item_count']}"
                )
            )
            if r["waf_headers"]:
                self.stdout.write(f"    waf_headers: {r['waf_headers']}")
            if r["error_message"]:
                self.stdout.write(f"    {r['error_message']}")

        ok_count = sum(1 for r in results if r["status"] == "ok")
        self.stdout.write(self.style.SUCCESS(f"\n{ok_count}/{len(results)} sources reachable.\n"))
