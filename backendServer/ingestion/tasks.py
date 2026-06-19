import logging
import os
from datetime import date

from celery import shared_task
from django.core.management import call_command

from ingestion.importers.ics_importer import poll_all_ics_sources
from ingestion.standardizer import standardize_all_unprocessed
from ingestion.deduplicator import dedup_all_pending
from ingestion.safety_scorer import score_all_unscored
from ingestion.services import auto_publish_safe_events, publish_all_approved

logger = logging.getLogger(__name__)


def _resolve_env_shard():
    """Compute (n, m) from INGEST_SHARD_COUNT, or None if unset/disabled.

    Mirrors the env branch of the ingest_events command's --shard handling:
    n rotates daily as (day_of_year % m) so each day polls a different slice.
    """
    m_env = os.environ.get('INGEST_SHARD_COUNT')
    if not m_env:
        return None
    try:
        m = int(m_env)
    except ValueError:
        logger.warning("INGEST_SHARD_COUNT must be an integer (got %r) — ignoring.", m_env)
        return None
    if m <= 1:
        return None
    n = date.today().timetuple().tm_yday % m
    return (n, m)


@shared_task(bind=True, max_retries=3, default_retry_delay=300)
def run_ingestion_pipeline(self):
    """Run the full ingestion pipeline as one task.

    Each step is wrapped so one failure logs and lets the rest proceed (mirroring
    the ingest_events command). If any step raised, the whole task retries — up to
    3 times, 5-min backoff. Steps are idempotent, so re-running is safe.
    """
    logger.info("run_ingestion_pipeline: starting")
    first_error = None

    def step(name, fn):
        nonlocal first_error
        try:
            return fn()
        except Exception as e:  # noqa: BLE001 — log and continue; retry decided at the end
            logger.error("run_ingestion_pipeline step %s failed: %s", name, e)
            if first_error is None:
                first_error = e
            return None

    step("cleanup", lambda: call_command('cleanup_old_events'))

    shard = _resolve_env_shard()
    new_count = step("poll", lambda: poll_all_ics_sources(shard=shard))
    if new_count is not None:
        logger.info("run_ingestion_pipeline: %s new raw events", new_count)

    std_count = step("standardize", standardize_all_unprocessed)
    if std_count is not None:
        logger.info("run_ingestion_pipeline: %s events standardized", std_count)

    dupe_count = step("dedup", dedup_all_pending)
    if dupe_count is not None:
        logger.info("run_ingestion_pipeline: %s duplicates found", dupe_count)

    scored_count = step("safety", score_all_unscored)
    if scored_count is not None:
        logger.info("run_ingestion_pipeline: %s events scored", scored_count)

    result = step("autopublish", auto_publish_safe_events)
    if result is not None:
        logger.info(
            "run_ingestion_pipeline: %s auto-published, %s held for review",
            result['auto_approved'], result['held_for_review'],
        )

    if first_error is not None:
        logger.warning("run_ingestion_pipeline: a step failed — retrying whole pipeline")
        raise self.retry(exc=first_error)

    logger.info("run_ingestion_pipeline: complete")


@shared_task
def publish_all_approved_task():
    """Background wrapper for the bulk publish (called from admin/API)."""
    return publish_all_approved()
