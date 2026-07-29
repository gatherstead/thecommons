"""Shared `SourceRun` recording for the poll loops.

Lives in its own module (rather than in `ics_importer.py` or
`scraper_importer.py`) so neither importer has to import the other to reuse
this — see the "no circular import" guardrail in ticket 32.4.
"""

import logging
import traceback as traceback_module
from collections.abc import Callable, Iterable
from contextlib import contextmanager

from django.utils import timezone

from ingestion.importers.errors import SourceRefused
from ingestion.models import EventSource, RawEvent, SourceRun

logger = logging.getLogger(__name__)


def _safe_create_run(**kwargs) -> SourceRun | None:
    """Create a SourceRun row, logging (not raising) on failure.

    A DB hiccup while recording observability data must never take down the
    poll loop itself.
    """
    try:
        return SourceRun.objects.create(**kwargs)
    except Exception:
        logger.exception("Failed to create SourceRun row")
        return None


def _safe_finish_run(run: SourceRun | None, **fields) -> None:
    """Apply `fields` to `run` and save the whole row.

    A plain `save()` (not `update_fields=[...fields]`) so that any other
    attribute the caller set on the yielded `run` inside the `with` block
    (e.g. `items_new`) is persisted too, not just the fields finalized here.
    """
    if run is None:
        return
    try:
        for key, value in fields.items():
            setattr(run, key, value)
        run.save()
    except Exception:
        logger.exception("Failed to finalize SourceRun row")


@contextmanager
def record_source_run(source: EventSource, *, trigger: str = SourceRun.TRIGGER_CHOICES[0][0]):
    """Record exactly one `SourceRun` row for a single poll attempt.

    Usage:

        with record_source_run(source) as run:
            new_events = fetch_something(source)
            run.items_new = len(new_events)

    On success the row is left as `status="ok"`. Raise `SourceRefused` inside
    the block for a "refused" row, or let any other exception propagate for a
    "failed" row with `error_class`/`error_message`/`traceback` populated; the
    exception is re-raised afterwards so the caller's `except` still runs.
    Every DB write here is best-effort: a failure to record never masks the
    underlying poll outcome or aborts the caller's loop.
    """
    run = _safe_create_run(source=source, started_at=timezone.now(), status="ok", trigger=trigger)

    try:
        yield run
    except SourceRefused as exc:
        message = f"{exc.reason}: {exc.detail}" if exc.detail else exc.reason
        _safe_finish_run(
            run,
            status="refused",
            error_message=message,
            finished_at=timezone.now(),
        )
        raise
    except Exception as exc:
        _safe_finish_run(
            run,
            status="failed",
            error_class=type(exc).__name__,
            error_message=str(exc),
            traceback=traceback_module.format_exc(),
            finished_at=timezone.now(),
        )
        raise
    else:
        _safe_finish_run(run, status="ok", finished_at=timezone.now())


def record_skipped_run(
    source: EventSource, *, trigger: str = SourceRun.TRIGGER_CHOICES[0][0]
) -> None:
    """Record a `SourceRun` for the poll-interval backoff branch (no attempt made)."""
    now = timezone.now()
    _safe_create_run(
        source=source,
        started_at=now,
        finished_at=now,
        status="skipped",
        trigger=trigger,
    )


def poll_sources_with_run_tracking(
    sources: Iterable[EventSource],
    fetch: Callable[[EventSource], list[RawEvent]],
) -> int:
    """Shared body of `poll_all_ics_sources`/`poll_all_scraper_sources`.

    For each source: skip (recording "skipped") if within the poll-interval
    backoff window, otherwise attempt `fetch(source)` inside `record_source_run`
    so exactly one `SourceRun` row is written per source. Returns the total
    count of newly created events across all sources. Any exception from
    `fetch` (including `SourceRefused`) is logged and swallowed so the loop
    continues to the next source.
    """
    total_new = 0
    for source in sources:
        if source.last_polled:
            hours_since = (timezone.now() - source.last_polled).total_seconds() / 3600
            if hours_since < source.poll_interval_hours:
                logger.debug(f"Skipping {source.name} (polled {hours_since:.1f}h ago)")
                record_skipped_run(source)
                continue

        try:
            with record_source_run(source) as run:
                new_events = fetch(source)
                if run is not None:
                    run.items_new = len(new_events)
                total_new += len(new_events)
        except SourceRefused as exc:
            logger.warning(f"Refused to poll {source.name}: {exc}")
        except Exception as e:
            # exc_info=True: without a traceback, a broken source degrades to a
            # single-line log entry indistinguishable from routine noise, which
            # is how a dead source went unnoticed in prod for weeks.
            logger.error(f"Error polling {source.name}: {e}", exc_info=True)

    return total_new
