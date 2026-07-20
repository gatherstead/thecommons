"""Pure query service for the devtools monitoring view.

Turns real DB rows into per-collector / per-broadcast counts and drill-down
rows. Every public function takes a `db` alias ("default" or
"prod_readonly") and guards it against `settings.DATABASES` so an
unconfigured `prod_readonly` degrades to an empty result instead of raising.
Read-only: no `.save()`/`.delete()` anywhere in this module.
"""

from django.conf import settings
from django.db.models import Count, Q

from broadcast.models import BroadcastSubmission, BroadcastTarget
from ingestion.models import EventSource, RawEvent, StagedEvent

_STAGED_STATUSES = [choice[0] for choice in StagedEvent.STATUS_CHOICES]
_SUBMISSION_STATUSES = [choice[0] for choice in BroadcastSubmission.STATUS_CHOICES]
_TARGET_STATUSES = [choice[0] for choice in BroadcastTarget.STATUS_CHOICES]


def _db_ok(db):
    return db in settings.DATABASES


def _iso(value):
    return value.isoformat() if value is not None else None


def _source_rows(db, start, end, source_type_filter):
    sources = list(
        EventSource.objects.using(db)
        .filter(source_type_filter)
        .order_by("name")
        .values("id", "name", "source_type", "url", "active", "last_polled")
    )
    if not sources:
        return []

    source_ids = [s["id"] for s in sources]

    raw_counts = {
        row["source"]: row["n"]
        for row in RawEvent.objects.using(db)
        .filter(source_id__in=source_ids, created_at__gte=start, created_at__lt=end)
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

    published_counts = {
        row["raw_event__source_id"]: row["n"]
        for row in StagedEvent.objects.using(db)
        .filter(
            raw_event__source_id__in=source_ids,
            raw_event__created_at__gte=start,
            raw_event__created_at__lt=end,
            published_event__isnull=False,
        )
        .values("raw_event__source_id")
        .annotate(n=Count("id"))
    }

    results = []
    for source in sources:
        source_id = source["id"]
        results.append(
            {
                "id": source_id,
                "name": source["name"],
                "source_type": source["source_type"],
                "url": source["url"],
                "active": source["active"],
                "last_polled": _iso(source["last_polled"]),
                "raw_count": raw_counts.get(source_id, 0),
                "staged_by_status": staged_by_source.get(
                    source_id, dict.fromkeys(_STAGED_STATUSES, 0)
                ),
                "published_count": published_counts.get(source_id, 0),
            }
        )
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


def drilldown(db: str, kind: str, key, start, end, limit: int = 100) -> list[dict]:
    if not _db_ok(db):
        return []

    if kind in ("collector", "inbound"):
        return _drilldown_source(db, key, start, end, limit)
    if kind == "outbound":
        return _drilldown_outbound(db, key, start, end, limit)
    return []
