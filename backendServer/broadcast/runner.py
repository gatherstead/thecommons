"""Sync-Playwright runner: executes one submission's targets sequentially.

Runs inside the worker process (plain sync code — no asyncio, ordinary ORM).

ORM calls must never happen inside a `sync_playwright()` block: Playwright
keeps an asyncio loop on the thread, and Django's async-aware connection
locals would silently switch to a second DB connection there. So the browser
is launched per target and all DB writes happen between Playwright sessions.
One Chromium at a time either way — same memory profile on the 6 GB VM.
"""
import logging
import os
import tempfile

from django.conf import settings
from django.utils import timezone
from playwright.sync_api import sync_playwright

from broadcast.adapters import get_adapter
from broadcast.adapters.base import RunContext, TargetResult
from broadcast.models import BroadcastSubmission
from broadcast.schema import event_from_submission

logger = logging.getLogger("broadcast")

# Conservative flags for the 6 GB ARM64 VM. Bundled Chromium only —
# never set a branded Chrome channel (unsupported on arm64 Linux).
CHROMIUM_ARGS = ["--disable-dev-shm-usage"]


def run_submission(submission: BroadcastSubmission) -> None:
    submission.status = "running"  # idempotent if the worker already claimed it
    submission.started_at = timezone.now()
    submission.save(update_fields=["status", "started_at"])

    ev = event_from_submission(submission)
    targets = list(submission.targets.filter(status="pending").order_by("site_key"))
    any_failed = False

    for target in targets:
        # Honor a cancel that arrived mid-run — stop before the next site.
        submission.refresh_from_db(fields=["status"])
        if submission.status == "canceled":
            break

        target.status = "in_progress"
        target.attempts += 1
        target.started_at = timezone.now()
        target.save(update_fields=["status", "attempts", "started_at"])

        result = _run_target(target, ev)

        target.status = result.status
        target.external_url = result.external_url[:200]
        target.error = result.error
        target.screenshot_path = result.screenshot_path
        target.finished_at = timezone.now()
        target.save(update_fields=[
            "status", "external_url", "error", "screenshot_path", "finished_at",
        ])
        if result.status == "failed":
            any_failed = True
        logger.info("broadcast %s → %s: %s", submission.id, target.site_key, result.status)

    submission.refresh_from_db(fields=["status"])
    if submission.status == "canceled":
        # Cancel won the race — leave it canceled, just tidy leftover targets.
        submission.targets.filter(status="pending").update(status="skipped")
        submission.finished_at = timezone.now()
        submission.save(update_fields=["finished_at"])
        return

    submission.status = "failed" if any_failed else "done"
    submission.finished_at = timezone.now()
    submission.save(update_fields=["status", "finished_at"])


def _run_target(target, ev) -> TargetResult:
    """Run one adapter in its own Playwright session. No ORM in here."""
    adapter = get_adapter(target.site_key)
    if adapter is None:
        return TargetResult(status="failed", error=f"no adapter registered for '{target.site_key}'")

    screenshot_dir = settings.BROADCAST_SCREENSHOT_DIR
    os.makedirs(screenshot_dir, exist_ok=True)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=settings.BROADCAST_HEADLESS, args=CHROMIUM_ARGS
            )
            try:
                page = browser.new_context().new_page()
                with tempfile.TemporaryDirectory(dir=_ensure(settings.BROADCAST_DOWNLOAD_DIR)) as tmp:
                    ctx = RunContext(
                        dry_run=target.dry_run,
                        screenshot_dir=screenshot_dir,
                        download_dir=tmp,
                        submission_id=str(target.submission_id),
                        timeout_ms=settings.BROADCAST_TIMEOUT_MS,
                    )
                    return adapter.fill_and_submit(page, ev, ctx)
            finally:
                browser.close()
    except Exception as exc:  # adapter blew up — record, never crash the loop
        logger.exception("adapter %s crashed", target.site_key)
        return TargetResult(status="failed", error=f"{type(exc).__name__}: {exc}")


def _ensure(path: str) -> str:
    os.makedirs(path, exist_ok=True)
    return path
