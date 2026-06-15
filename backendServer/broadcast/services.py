"""Persistence for broadcast submissions. Views stay thin; logic lives here."""
from django.conf import settings
from django.db import transaction

from broadcast.models import BroadcastSubmission, BroadcastTarget
from broadcast.schema import CanonicalEvent, event_from_submission


def _maybe_autospawn_worker() -> None:
    """Kick a one-shot worker after commit, if auto-spawn is enabled (dev/single
    box). Prod leaves this off and relies on the systemd broadcast-worker."""
    if not getattr(settings, "BROADCAST_AUTOSPAWN_WORKER", False):
        return
    from broadcast.worker import spawn_worker_once

    transaction.on_commit(spawn_worker_once)


@transaction.atomic
def create_submission(
    client_label: str,
    event: CanonicalEvent,
    site_keys: list[str],
    dry_run: bool,
) -> BroadcastSubmission:
    submission = BroadcastSubmission.objects.create(
        client_label=client_label,
        title=event.title,
        description=event.description,
        start_datetime=event.start_datetime,
        end_datetime=event.end_datetime,
        all_day=event.all_day,
        venue_name=event.venue_name,
        address_line1=event.address_line1,
        city=event.city,
        state=event.state,
        zip=event.zip,
        locality=event.locality,
        categories=event.categories,
        event_url=event.event_url,
        ticket_url=event.ticket_url,
        price=event.price,
        is_free=event.is_free,
        image_url=event.image_url,
        organizer_name=event.organizer_name,
        contact_email=event.contact_email,
        contact_phone=event.contact_phone,
        status="queued",
    )
    # Unique (submission, site_key) holds because keys are deduped here and
    # the DB constraint backstops any race.
    for site_key in dict.fromkeys(site_keys):
        BroadcastTarget.objects.create(
            submission=submission, site_key=site_key, dry_run=dry_run
        )
    _maybe_autospawn_worker()
    return submission


@transaction.atomic
def retry_targets(submission: BroadcastSubmission, site_keys: list[str]) -> int:
    """Reset the given targets to pending and re-queue the submission.

    Reuses existing rows (idempotency) — never creates a second target for
    the same (submission, site_key).
    """
    updated = (
        submission.targets
        .filter(site_key__in=site_keys)
        .exclude(status__in=["pending", "in_progress"])
        .update(status="pending", error="", external_url="", screenshot_path="")
    )
    if updated:
        submission.status = "queued"
        submission.finished_at = None
        submission.save(update_fields=["status", "finished_at"])
        _maybe_autospawn_worker()
    return updated


def manual_recipe(submission: BroadcastSubmission, site_key: str) -> dict:
    """Declarative recipe the manual-review extension fills for one target."""
    from broadcast.adapters import get_adapter

    adapter = get_adapter(site_key)
    return adapter.recipe(event_from_submission(submission))


def job_payload(submission: BroadcastSubmission) -> dict:
    from broadcast.adapters import get_adapter

    targets = []
    for t in submission.targets.all().order_by("site_key"):
        adapter = get_adapter(t.site_key)
        targets.append({
            "site_key": t.site_key,
            "name": adapter.name if adapter else t.site_key,
            "status": t.status,
            "attempts": t.attempts,
            "dry_run": t.dry_run,
            "error": t.error,
            "external_url": t.external_url,
            "screenshot_url": (
                f"/broadcast/jobs/{submission.id}/screenshots/{t.site_key}"
                if t.screenshot_path else ""
            ),
        })
    return {
        "job_id": str(submission.id),
        "status": submission.status,
        "created_at": submission.created_at.isoformat(),
        "started_at": submission.started_at.isoformat() if submission.started_at else None,
        "finished_at": submission.finished_at.isoformat() if submission.finished_at else None,
        "targets": targets,
    }
