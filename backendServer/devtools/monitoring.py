"""Pure query service for the devtools monitoring view.

Turns real DB rows into per-collector / per-broadcast counts and drill-down
rows. Every public function takes a `db` alias ("default" or
"prod_readonly") and guards it against `settings.DATABASES` so an
unconfigured `prod_readonly` degrades to an empty result instead of raising.
Read-only: no `.save()`/`.delete()` anywhere in this module.
"""

from django.conf import settings
from django.db.models import Count, Q
from django.utils import timezone

from broadcast.models import BroadcastSubmission, BroadcastTarget
from ingestion.models import EventSource, RawEvent, SourceRun, StagedEvent

_STAGED_STATUSES = [choice[0] for choice in StagedEvent.STATUS_CHOICES]
_SUBMISSION_STATUSES = [choice[0] for choice in BroadcastSubmission.STATUS_CHOICES]
_TARGET_STATUSES = [choice[0] for choice in BroadcastTarget.STATUS_CHOICES]

# How many missed polling intervals before a source is flagged `error` for
# staleness. Chosen, not derived: one missed poll can be a transient blip
# (network hiccup, temporary rate limit); two in a row is a pattern.
_STALE_POLL_MULTIPLIER = 2

# How many consecutive non-`ok` SourceRuns (excluding `skipped`, see
# `source_health`) before a source is flagged `error` regardless of what the
# most recent run says. One failure can be a fluke; two in a row is a trend
# worth surfacing on the triage list.
_CONSECUTIVE_FAILURE_THRESHOLD = 2

# How many recent runs per source we pull to evaluate the consecutive-failure
# rule. Only needs to be >= _CONSECUTIVE_FAILURE_THRESHOLD, padded a bit so a
# `skipped` run or two doesn't push a real failure out of the window.
_RECENT_RUNS_PER_SOURCE = 5

# Sort order for the health column: most severe first, `inactive` last since
# those rows are intentionally excluded from alerting.
_HEALTH_RANK = {"error": 0, "warn": 1, "ok": 2, "inactive": 3}


def _db_ok(db):
    return db in settings.DATABASES


def _iso(value):
    return value.isoformat() if value is not None else None


def _run_based_errors(recent_runs):
    """Evaluate the two run-based `error` rules and return their reason strings.

    `skipped` runs (source correctly throttled by poll_interval_hours) are
    excluded from the consecutive-non-ok count entirely: they neither break
    nor extend a failure streak. A source that ran, failed, then got skipped
    twice because it isn't due yet, then failed again is still 2 consecutive
    failures once `skipped` runs are filtered out — that's the intent. A
    source that failed once and has since been correctly skipped every time
    since (no second failure) is NOT 2-consecutive; it's 1 failure with no
    repeat, so it doesn't trip this rule (though the last-polled-staleness
    rule may still catch it if polling actually stalled).
    """
    non_skipped_runs = [r for r in recent_runs if r["status"] != "skipped"]
    if not non_skipped_runs:
        return []

    reasons = []
    latest = non_skipped_runs[0]
    if latest["status"] in ("failed", "refused"):
        msg = latest.get("error_message") or "(no error message recorded)"
        reasons.append(f"latest run {latest['status']}: {msg}")

    consecutive_non_ok = 0
    for run in non_skipped_runs:
        if run["status"] != "ok":
            consecutive_non_ok += 1
        else:
            break
    if consecutive_non_ok >= _CONSECUTIVE_FAILURE_THRESHOLD:
        msg = latest.get("error_message") or "(no error message recorded)"
        reasons.append(f"{consecutive_non_ok} consecutive non-ok runs, latest: {msg}")

    return reasons


def _staleness_error(source_row, now):
    """Evaluate the last-polled staleness `error` rule; return a reason or None."""
    last_polled_dt = source_row.get("last_polled_dt")
    if last_polled_dt is None:
        return "never polled"

    stale_after_hours = source_row["poll_interval_hours"] * _STALE_POLL_MULTIPLIER
    age_hours = (now - last_polled_dt).total_seconds() / 3600
    if age_hours > stale_after_hours:
        return f"last polled {age_hours:.1f}h ago, expected within {stale_after_hours}h"
    return None


def source_health(source_row, recent_runs, now):
    """Classify a source's health from plain data — no DB access.

    `source_row` is one row as produced by `_source_rows` (dict with `active`,
    `poll_interval_hours`, `last_polled_dt` — a real datetime, not the ISO
    string on the public row shape — `raw_count`, `funnel`). `recent_runs` is
    a list of dicts (most-recent-first) with `status`, `finished_at`,
    `error_message` for one source. `now` is a datetime compared against
    `last_polled_dt`.

    Returns {"level": "ok" | "warn" | "error" | "inactive", "reasons": [str, ...]}.
    Every applicable rule is evaluated and its reason collected; the most
    severe level (error > warn > ok) wins. Inactive sources are excluded from
    alerting entirely and always report "inactive", never "error".
    """
    if not source_row["active"]:
        return {"level": "inactive", "reasons": []}

    reasons = _run_based_errors(recent_runs)
    staleness_reason = _staleness_error(source_row, now)
    if staleness_reason:
        reasons.append(staleness_reason)
    level = "error" if reasons else "ok"

    # Warn signals only add a reason/level when no error already fired for
    # this row's polling health; downstream stalls are still worth surfacing
    # even when polling is fine, so evaluate them regardless of `level`.
    if source_row["raw_count"] == 0:
        reasons.append("polling but zero new raw events in window")
        level = "warn" if level == "ok" else level
    elif source_row["funnel"]["published"] == 0:
        reasons.append("raw events arriving but none published in window")
        level = "warn" if level == "ok" else level

    return {"level": level, "reasons": reasons}


def _source_rows(db, start, end, source_type_filter):
    # Staleness is a wall-clock question ("has this source polled recently?"),
    # so it is measured against real `now`, never the window's `end`. In prod
    # the two coincide (`_resolve_window` sets end = timezone.now()), which is
    # exactly why using `end` here would have looked correct and still been wrong.
    now = timezone.now()
    sources = list(
        EventSource.objects.using(db)
        .filter(source_type_filter)
        .order_by("name")
        .values(
            "id", "name", "source_type", "url", "active", "last_polled", "poll_interval_hours"
        )
    )
    if not sources:
        return []

    source_ids = [s["id"] for s in sources]

    # All windowing below is on RawEvent.created_at (including for the staged/
    # published buckets, via raw_event__created_at), matching the existing
    # raw/staged/published counts. An event raw-ingested just before a window
    # boundary but staged/published inside it still counts in the *earlier*
    # window — intentional, not a bug to "fix".

    raw_rows = (
        RawEvent.objects.using(db)
        .filter(source_id__in=source_ids, created_at__gte=start, created_at__lt=end)
        .values("source")
        .annotate(n=Count("id"), unprocessed=Count("id", filter=Q(processed=False)))
    )
    raw_counts = {row["source"]: row["n"] for row in raw_rows}
    unprocessed_counts = {row["source"]: row["unprocessed"] for row in raw_rows}

    no_staged_counts = {
        row["source"]: row["n"]
        for row in RawEvent.objects.using(db)
        .filter(
            source_id__in=source_ids,
            created_at__gte=start,
            created_at__lt=end,
            processed=True,
            staged__isnull=True,
        )
        .values("source")
        .annotate(n=Count("id"))
    }

    staged_qs = (
        StagedEvent.objects.using(db)
        .filter(
            raw_event__source_id__in=source_ids,
            raw_event__created_at__gte=start,
            raw_event__created_at__lt=end,
        )
        .values("raw_event__source_id", "status")
        .annotate(n=Count("id"))
    )
    staged_by_source = {}
    for row in staged_qs:
        source_id = row["raw_event__source_id"]
        staged_by_source.setdefault(source_id, dict.fromkeys(_STAGED_STATUSES, 0))
        staged_by_source[source_id][row["status"]] = row["n"]

    funnel_staged_qs = (
        StagedEvent.objects.using(db)
        .filter(
            raw_event__source_id__in=source_ids,
            raw_event__created_at__gte=start,
            raw_event__created_at__lt=end,
        )
        .values("raw_event__source_id")
        .annotate(
            unscored=Count(
                "id", filter=Q(status="pending", safety_score__isnull=True)
            ),
            held_for_review=Count(
                "id", filter=Q(status="pending", safety_score__isnull=False)
            ),
            published=Count("id", filter=Q(published_event__isnull=False)),
        )
    )
    funnel_staged_by_source = {
        row["raw_event__source_id"]: row for row in funnel_staged_qs
    }

    # Single query for recent runs across all sources, ordered to match the
    # (source, -started_at) index — no per-source query (no N+1). A bounded
    # number of runs per source is plenty to evaluate the consecutive-failure
    # rule; grouping into a dict keyed by source_id happens in Python.
    runs_by_source: dict[int, list[dict]] = {sid: [] for sid in source_ids}
    for run in (
        SourceRun.objects.using(db)
        .filter(source_id__in=source_ids)
        .order_by("source_id", "-started_at")
        .values("source_id", "status", "started_at", "finished_at", "error_message")
    ):
        bucket = runs_by_source[run["source_id"]]
        if len(bucket) < _RECENT_RUNS_PER_SOURCE:
            bucket.append(run)

    results = []
    for source in sources:
        source_id = source["id"]
        staged_status_counts = staged_by_source.get(
            source_id, dict.fromkeys(_STAGED_STATUSES, 0)
        )
        funnel_staged = funnel_staged_by_source.get(source_id, {})
        recent_runs = runs_by_source.get(source_id, [])
        last_run = (
            {
                "status": recent_runs[0]["status"],
                "finished_at": _iso(recent_runs[0]["finished_at"]),
                "error_message": recent_runs[0]["error_message"],
            }
            if recent_runs
            else None
        )

        row = {
            "id": source_id,
            "name": source["name"],
            "source_type": source["source_type"],
            "url": source["url"],
            "active": source["active"],
            "last_polled": _iso(source["last_polled"]),
            "raw_count": raw_counts.get(source_id, 0),
            "staged_by_status": staged_status_counts,
            "published_count": funnel_staged.get("published", 0),
            "funnel": {
                "raw": raw_counts.get(source_id, 0),
                "unprocessed": unprocessed_counts.get(source_id, 0),
                "no_staged": no_staged_counts.get(source_id, 0),
                "duplicate": staged_status_counts["duplicate"],
                "unscored": funnel_staged.get("unscored", 0),
                "held_for_review": funnel_staged.get("held_for_review", 0),
                "rejected": staged_status_counts["rejected"],
                "published": funnel_staged.get("published", 0),
            },
            "last_run": last_run,
        }
        # source_health needs poll_interval_hours and the raw last_polled
        # datetime (not the ISO string already in `row`), so pass a
        # health-only view rather than mutating the row's public shape.
        health_input = {
            **row,
            "poll_interval_hours": source["poll_interval_hours"],
            "last_polled_dt": source["last_polled"],
        }
        row["health"] = source_health(health_input, recent_runs, now)
        results.append(row)

    # Sort by health severity (error first, inactive last), then by name for
    # a stable secondary order. Sorting happens here, not in the template:
    # Django templates can't sort on a nested dict key, and the drilldown
    # row is interleaved with each source row in the `{% for %}` loop, so
    # reordering client-side would desync them from their drilldowns.
    results.sort(key=lambda row: (_HEALTH_RANK[row["health"]["level"]], row["name"]))
    return results


def collector_summary(db: str, start, end) -> list[dict]:
    if not _db_ok(db):
        return []
    return _source_rows(db, start, end, ~Q(source_type="direct"))


def broadcast_inbound_summary(db: str, start, end) -> list[dict]:
    if not _db_ok(db):
        return []
    return _source_rows(db, start, end, Q(source_type="direct"))


def broadcast_outbound_summary(db: str, start, end) -> dict:
    if not _db_ok(db):
        return {}

    submissions = BroadcastSubmission.objects.using(db).filter(
        created_at__gte=start, created_at__lt=end
    )

    by_status = dict.fromkeys(_SUBMISSION_STATUSES, 0)
    total = 0
    for row in submissions.values("status").annotate(n=Count("id")):
        by_status[row["status"]] = row["n"]
        total += row["n"]

    targets_by_status = dict.fromkeys(_TARGET_STATUSES, 0)
    target_rows = (
        BroadcastTarget.objects.using(db)
        .filter(submission__in=submissions)
        .values("status")
        .annotate(n=Count("id"))
    )
    for row in target_rows:
        targets_by_status[row["status"]] = row["n"]

    return {"by_status": by_status, "total": total, "targets_by_status": targets_by_status}


def _drilldown_source(db, key, start, end, limit):
    raw_events = list(
        RawEvent.objects.using(db)
        .filter(source_id=key, created_at__gte=start, created_at__lt=end)
        .select_related("staged")
        .order_by("-created_at")[:limit]
    )
    rows = []
    for raw in raw_events:
        staged = getattr(raw, "staged", None)
        rows.append(
            {
                "raw_id": raw.id,
                "raw_title": raw.raw_title,
                "raw_created_at": _iso(raw.created_at),
                "processed": raw.processed,
                "staged_status": staged.status if staged else None,
                "published": bool(staged and staged.published_event_id),
            }
        )
    return rows


def _drilldown_outbound(db, key, start, end, limit):
    submissions_qs = BroadcastSubmission.objects.using(db).filter(
        created_at__gte=start, created_at__lt=end
    )
    if key:
        submissions_qs = submissions_qs.filter(targets__site_key=key).distinct()

    submissions = list(submissions_qs.order_by("-created_at").prefetch_related("targets")[:limit])

    rows = []
    for submission in submissions:
        rows.append(
            {
                "submission_id": str(submission.id),
                "title": submission.title,
                "client_label": submission.client_label,
                "status": submission.status,
                "created_at": _iso(submission.created_at),
                "targets": [
                    {"site_key": target.site_key, "status": target.status}
                    for target in submission.targets.all()
                ],
            }
        )
    return rows


def _drilldown_runs(db, key, start, end, limit):
    """Recent SourceRun rows for one source — "what has this source been
    doing", not windowed by `start`/`end` (a source's run history matters
    regardless of the funnel window currently selected). `start`/`end` are
    accepted for signature symmetry with the other drilldown helpers only.
    """
    runs = (
        SourceRun.objects.using(db)
        .filter(source_id=key)
        .order_by("-started_at")[:limit]
    )
    return [
        {
            "started_at": _iso(run.started_at),
            "finished_at": _iso(run.finished_at),
            "status": run.status,
            "trigger": run.trigger,
            "items_fetched": run.items_fetched,
            "items_new": run.items_new,
            "items_duplicate": run.items_duplicate,
            "error_message": run.error_message,
        }
        for run in runs
    ]


def drilldown(db: str, kind: str, key, start, end, limit: int = 100) -> list[dict]:
    if not _db_ok(db):
        return []

    if kind in ("collector", "inbound"):
        return _drilldown_source(db, key, start, end, limit)
    if kind == "outbound":
        return _drilldown_outbound(db, key, start, end, limit)
    if kind == "runs":
        return _drilldown_runs(db, key, start, end, limit)
    return []
