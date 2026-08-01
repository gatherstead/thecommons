from datetime import timedelta

from django.conf import settings
from django.db import OperationalError
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone

from ..monitoring import (
    RUNS_UNREACHABLE,
    broadcast_inbound_summary,
    broadcast_outbound_summary,
    collector_summary,
    drilldown,
    resolve_source_runs_state,
    summarize_sources,
)
from ._shared import _debug_only, _resolve_db

# ── Monitoring ────────────────────────────────────────────────────────────────

_WINDOW_DAYS = {"7d": 7, "30d": 30, "90d": 90}


def _resolve_window(request):
    window = request.GET.get("window", "30d")
    if window not in _WINDOW_DAYS:
        window = "30d"
    end = timezone.now()
    start = end - timedelta(days=_WINDOW_DAYS[window])
    return window, start, end


@_debug_only
def monitor(request):
    db = _resolve_db(request)
    window, start, end = _resolve_window(request)

    # Resolve SourceRun availability once and thread it through both summaries
    # and the template. It used to be re-resolved four times per render, each
    # an uncached round trip to Neon on the prod path, all answering the same
    # question. Doubles as this page's reachability probe: it's the first
    # statement issued, so an unreachable database surfaces here.
    runs_state = resolve_source_runs_state(db)

    collectors, inbound, outbound = [], [], {}
    if runs_state != RUNS_UNREACHABLE:
        try:
            collectors = collector_summary(db, start, end, runs_state=runs_state)
            inbound = broadcast_inbound_summary(db, start, end, runs_state=runs_state)
            outbound = broadcast_outbound_summary(db, start, end)
        except OperationalError:
            # Connection was live for the probe and died mid-render. Degrade to
            # the same banner the rest of the page is built around rather than
            # handing the operator a raw traceback.
            runs_state = RUNS_UNREACHABLE
            collectors, inbound, outbound = [], [], {}

    # Ticket 40.6: the KPI tiles are a pure reduction over the rows already
    # fetched above — no new queries. Computed from `collectors + inbound`
    # regardless of `runs_state`, so an unreachable database still yields the
    # all-zero/empty shape `summarize_sources([])` returns rather than a
    # missing context key.
    summary = summarize_sources(collectors + inbound)

    return render(
        request,
        "devtools/monitor.html",
        {
            "collectors": collectors,
            "inbound": inbound,
            "outbound": outbound,
            "summary": summary,
            "db": db,
            "window": window,
            "prod_readonly_configured": "prod_readonly" in settings.DATABASES,
            "source_runs_state": runs_state,
        },
    )


@_debug_only
def monitor_data(request):
    kind = request.GET.get("kind", "")
    if kind not in ("collector", "inbound", "outbound", "runs"):
        return JsonResponse({"error": f"invalid kind '{kind}'"}, status=400)

    db = _resolve_db(request)
    _, start, end = _resolve_window(request)

    key = request.GET.get("key", "")
    if kind != "outbound":
        # Empty/absent key used to coerce to `None` and then filter
        # `source_id=None` in `_drilldown_source`, silently matching nothing.
        # Ticket 40.5: `None` now means "every source of this kind" for
        # collector/inbound (see `_drilldown_source`); `runs` still requires a
        # numeric key and degrades to empty without one (per-source only).
        key = int(key) if key.isdigit() else None
    else:
        key = key or None

    limit_raw = request.GET.get("limit", "").strip()
    limit = min(int(limit_raw), 100) if limit_raw.isdigit() else 100

    offset_raw = request.GET.get("offset", "").strip()
    offset = int(offset_raw) if offset_raw.isdigit() else 0

    rows, total = drilldown(db, kind, key, start, end, limit=limit, offset=offset)
    return JsonResponse({"rows": rows, "total": total, "offset": offset, "limit": limit, "db": db})
