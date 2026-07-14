import logging

from celery import shared_task

from broadcast.worker import recover_orphans, run_once

logger = logging.getLogger("broadcast")


@shared_task
def process_broadcast_queue():
    """Drain the broadcast queue, processing every currently-queued submission.

    Routed to the dedicated `broadcast` queue so it never runs concurrently
    with recover_broadcast_orphans (see CELERY_TASK_ROUTES).
    """
    processed = 0
    while run_once():
        processed += 1
    logger.info("process_broadcast_queue: processed %s submissions", processed)
    return processed


@shared_task
def recover_broadcast_orphans():
    """Re-queue submissions stranded by a crashed worker. Routed to the same
    `broadcast` queue as process_broadcast_queue (see CELERY_TASK_ROUTES)."""
    count = recover_orphans()
    logger.info("recover_broadcast_orphans: re-queued %s orphaned submissions", count)
    return count
