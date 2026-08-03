"""Per-source dispatch for the Gemini-backed batch pipeline stages.

`standardize_all_unprocessed` and `score_all_unscored` only resolve a
`source.prompt_suffix` when a `source=` argument is actually passed in — the
DEBUG-gated devtools playground (`devtools/pipeline_runner.py`) does this
correctly, but the scheduled paths (`run_ingestion_pipeline`, the
`ingest_events` management command) called them with no arguments at all,
so per-source prompt instructions were silently dropped on every scheduled
run. `run_batch_per_source` fixes that by calling the batch function once
per `EventSource`, so any `prompt_suffix` set on a source actually reaches
Gemini regardless of which entrypoint triggered the run.
"""

import logging

from ingestion.models import EventSource

logger = logging.getLogger(__name__)


def run_batch_per_source(batch_fn, *, step_name):
    """Call `batch_fn(source=source)` once for every `EventSource`, then a
    final sweep call with no source filter for anything left over (rows with
    no source, or created after the loop started).

    Iterates ALL sources — not `filter(active=True)` — because unprocessed
    rows belonging to a deactivated source still need to be standardized/
    scored; otherwise they'd be stranded forever. A single source raising is
    caught and logged so the remaining sources still run, mirroring the
    try/except isolation `run_ingestion_pipeline`'s `step()` helper and the
    `ingest_events` command already use around each pipeline stage.

    Returns the summed count across every source plus the sweep, so
    call sites that log a single total (e.g. "%s events standardized")
    keep meaning what they say.
    """
    total = 0
    for source in EventSource.objects.all():
        try:
            total += batch_fn(source=source)
        except Exception as e:
            logger.error("%s failed for source %s: %s", step_name, source, e)

    total += batch_fn(source=None)
    return total
