import logging
import os
from datetime import date

from celery import shared_task
from django.core.management import call_command

from ingestion.deduplicator import dedup_all_pending
from ingestion.importers.ics_importer import poll_all_ics_sources
from ingestion.importers.scraper_importer import poll_all_scraper_sources
from ingestion.safety_scorer import score_all_unscored
from ingestion.services import (
    auto_publish_safe_events,
    ingest_direct_submission,
    publish_all_approved,
)
from ingestion.standardizer import standardize_all_unprocessed

logger = logging.getLogger(__name__)


def _resolve_env_shard():
    """Compute (n, m) from INGEST_SHARD_COUNT, or None if unset/disabled.

    Mirrors the env branch of the ingest_events command's --shard handling:
    n rotates daily as (day_of_year % m) so each day polls a different slice.
    """
    m_env = os.environ.get("INGEST_SHARD_COUNT")
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
    """Run the ICS-poll leg of the ingestion pipeline as one task.

    Polls ICS sources ONLY (`poll_all_ics_sources`) — http/scraper sources are
    NOT touched here. Those are polled by the separate `scrape_all_sources_task`
    on its own beat schedule (`scrape-sources-daily`), routed to the dedicated
    `scrape` queue. The two are intentionally NOT chained: see ingest_events.py's
    Step 1 vs Step 1b for the command-line equivalent of this split. A prior
    version of this docstring claimed to mirror ingest_events end-to-end, which
    was false and part of why two `http`-type sources went unpolled for weeks
    with nobody noticing — don't repeat that mistake.

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

    step("cleanup", lambda: call_command("cleanup_old_events"))

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
            result["auto_approved"],
            result["held_for_review"],
        )

    if first_error is not None:
        logger.warning("run_ingestion_pipeline: a step failed — retrying whole pipeline")
        raise self.retry(exc=first_error)

    logger.info("run_ingestion_pipeline: complete")


@shared_task(bind=True, max_retries=3, default_retry_delay=300)
def scrape_all_sources_task(self):
    """Poll `http`- and `scraper`-type EventSources. Routed to the dedicated
    `scrape` queue so headless-browser memory stays off the default worker.

    Despite the queue name, most of the critical path here is NOT a browser:
    `poll_all_scraper_sources` covers both `http` and `scraper` source types,
    and `http` sources are fetched with plain `requests` (no Chromium at all —
    see `_fetch_via_http` in scraper_importer.py). Only `scraper`-type sources
    render headless Chromium. Both current production sources in this task's
    remit (Visit Pittsboro, The Plant NC) are `http`, so Chromium isn't in
    their path; don't assume it is when debugging a stall here.

    Retries on any exception, up to 3 times with a 5-min backoff, matching
    run_ingestion_pipeline — this task previously had no retry at all, so a
    transient failure (e.g. a single flaky fetch) just silently dropped the
    day's poll.
    """
    try:
        shard = _resolve_env_shard()
        new_count = poll_all_scraper_sources(shard=shard)
        logger.info("scrape_all_sources_task: %s new raw events", new_count)
        return new_count
    except Exception as e:
        logger.error("scrape_all_sources_task failed: %s", e)
        raise self.retry(exc=e) from e


@shared_task
def publish_all_approved_task():
    """Background wrapper for the bulk publish (called from admin/API)."""
    return publish_all_approved()


@shared_task(bind=True, max_retries=3, default_retry_delay=300, acks_late=True)
def ingest_direct_submission_task(self, raw_event_id, user_id):
    """Background wrapper for direct host submission ingestion.

    acks_late=True (unlike the other tasks in this module): prod runs
    --concurrency=2 under systemd with MemoryMax=1G and is restarted on every
    deploy. Celery's default is at-most-once, so a prefetched message is
    silently dropped if the worker dies (OOM/restart) mid-task — confirmed in
    prod on 2026-07-21 12:46 UTC, when the worker died and a submission
    enqueued 5 minutes later was never consumed. ingest_direct_submission is
    documented as idempotent (see its docstring in services.py), so
    at-least-once redelivery here is safe.
    """
    try:
        return ingest_direct_submission(raw_event_id, user_id)
    except Exception as e:
        logger.error(
            "ingest_direct_submission_task failed for raw_event_id=%s: %s", raw_event_id, e
        )
        raise self.retry(exc=e) from e
