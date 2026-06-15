"""DB-backed queue worker: claims queued submissions with SKIP LOCKED.

Runs as its own systemd service (broadcast-worker) via the
run_broadcast_worker management command — never inside gunicorn.
"""
import logging
import os
import subprocess
import sys
import time

from django.conf import settings
from django.db import transaction

from broadcast.models import BroadcastSubmission
from broadcast.runner import run_submission

logger = logging.getLogger("broadcast")

POLL_INTERVAL_S = 3


def spawn_worker_once() -> None:
    """Detach a `run_broadcast_worker --once` process to drain the queue.

    For single-box / dev setups with no long-running worker. Safe to call from
    a gunicorn request handler: it's a *separate* process (Playwright never runs
    in-process), and claim_next uses SKIP LOCKED so it can't collide with a
    systemd worker or another spawn. Call via transaction.on_commit so the
    spawned process sees the committed submission.
    """
    manage_py = str(settings.BASE_DIR / "manage.py")
    try:
        subprocess.Popen(
            [sys.executable, manage_py, "run_broadcast_worker", "--once"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            cwd=str(settings.BASE_DIR),
            env=os.environ.copy(),
        )
    except Exception:
        logger.exception("failed to spawn broadcast worker")


def claim_next() -> BroadcastSubmission | None:
    """Atomically claim the oldest queued submission, or None."""
    with transaction.atomic():
        submission = (
            BroadcastSubmission.objects
            .select_for_update(skip_locked=True)
            .filter(status="queued")
            .order_by("created_at")
            .first()
        )
        if submission is None:
            return None
        submission.status = "running"
        submission.save(update_fields=["status"])
        return submission


def recover_orphans() -> int:
    """Re-queue submissions stranded by a crashed/killed worker.

    Safe only because v1 runs a single worker (systemd unit, concurrency 1):
    any 'running' submission at startup is necessarily orphaned. Targets
    stuck 'in_progress' go back to 'pending'; their attempts count is kept.
    """
    with transaction.atomic():
        orphans = list(
            BroadcastSubmission.objects
            .select_for_update(skip_locked=True)
            .filter(status="running")
        )
        for submission in orphans:
            submission.targets.filter(status="in_progress").update(status="pending")
            submission.status = "queued"
            submission.save(update_fields=["status"])
            logger.warning("re-queued orphaned submission %s", submission.id)
    return len(orphans)


def run_forever() -> None:
    logger.info("broadcast worker started")
    recover_orphans()
    while True:
        processed = run_once()
        if not processed:
            time.sleep(POLL_INTERVAL_S)


def run_once() -> bool:
    """Process at most one submission. Returns True if one was processed."""
    submission = claim_next()
    if submission is None:
        return False
    try:
        run_submission(submission)
    except Exception:
        logger.exception("submission %s crashed", submission.id)
        submission.refresh_from_db()
        submission.status = "failed"
        submission.save(update_fields=["status"])
    return True
