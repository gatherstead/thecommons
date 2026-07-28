# Ingestion & Broadcast Monitor

A dev-only diagnostic dashboard for the ingestion funnel and broadcast queues, plus a
dry-run probe for a single source. Lives in `devtools/` (`monitoring.py`, `views.py`,
`templates/devtools/monitor.html`) — see [`ingestion-pipeline.md`](ingestion-pipeline.md)
for the pipeline it observes and [`devtools-ingestion-playground.md`](devtools-ingestion-playground.md)
for the sibling tool that replays a single feed end-to-end.

**Reaching it:** `/devtools/monitor`, mounted only when `DEBUG` is true. Every devtools
view (`devtools/views.py`) starts with `if not settings.DEBUG: raise Http404` — the whole
`devtools` app is unregistered outside dev in the first place (`backend/settings/dev.py`
appends it to `INSTALLED_APPS`; `backend/urls.py` only includes `devtools.urls` when
`settings.DEBUG`). It is never reachable in prod.

---

## The funnel

`collector_summary` / `broadcast_inbound_summary` (`devtools/monitoring.py` →
`_source_rows`) compute eight counts per `EventSource`, windowed by `?window=7d|30d|90d`
(default 30d). Both entry points call the same query function — `collector_summary`
filters to non-`direct` sources, `broadcast_inbound_summary` filters to `source_type='direct'`
(host submissions arriving via the broadcast SPA — see the ingestion-pipeline.md "Direct
Host Submission" section).

| Bucket | Query | Diagnostic meaning |
|---|---|---|
| `raw` | `RawEvent` created in the window | Total intake for this source |
| `unprocessed` | `RawEvent.processed=False` | Waiting on the standardizer (Gemini) |
| `no_staged` | `RawEvent.processed=True`, no `StagedEvent` | Standardizer ran but never created a staged row |
| `duplicate` | `StagedEvent.status='duplicate'` | Caught by the fuzzy dedup pass |
| `unscored` | `StagedEvent.status='pending'`, `safety_score IS NULL` | Waiting on the safety scorer |
| `held_for_review` | `StagedEvent.status='pending'`, `safety_score IS NOT NULL` | Scored but held — didn't clear the auto-publish safety threshold |
| `rejected` | `StagedEvent.status='rejected'` | Manually rejected in admin review |
| `published` | `StagedEvent.published_event IS NOT NULL` | Made it live |

### Two traps

**The buckets are not mutually exclusive and do not sum to `raw`.** They're independent
slices of different tables/states, not a partition — e.g. a `RawEvent` counted in `raw`
may also be counted in `unprocessed` if it hasn't been standardized yet, and a `duplicate`
StagedEvent is not also counted in `unscored` or `held_for_review`. Don't expect the
columns to add up; read each one as its own diagnostic signal.

**Every bucket is windowed on `RawEvent.created_at`**, including the staged/published
buckets (via `raw_event__created_at`) — not on `StagedEvent.created_at` or
`published_event`'s own timestamp. An event raw-ingested just before a window boundary
but staged or published *inside* the window still counts in the **earlier** window. This
is intentional (`monitoring.py:151-155`): it keeps every bucket keyed to the same
ingestion cohort, so "what happened to the events that came in during this window" stays
a single coherent question, at the cost of a published count that can look off from a
naive "when did this get published" read.

Staleness (used by health, below) is the one thing in this module that is **not** windowed
— it's measured against real wall-clock `now`, never the window's `end`
(`monitoring.py:134–141`). In prod the two coincide (`_resolve_window` sets `end =
timezone.now()`), which is exactly why using `end` there would have looked correct and
still been wrong for anyone diffing against a `prod_readonly` snapshot taken earlier.

---

## Health levels

`source_health()` (`monitoring.py:99`) classifies each source as `inactive`, `ok`, `warn`,
or `error`. Three constants drive the rules:

- `_STALE_POLL_MULTIPLIER = 2` — a source is stale once it's gone `2 ×
  poll_interval_hours` without polling.
- `_CONSECUTIVE_FAILURE_THRESHOLD = 2` — two consecutive non-`ok` runs (after filtering out
  `skipped`) trip the error rule regardless of the latest run's own status.
- `_RECENT_RUNS_PER_SOURCE = 5` — how many recent `SourceRun` rows are pulled per source to
  evaluate the consecutive-failure rule (padded above the threshold so a stray `skipped`
  run doesn't push a real failure out of the window).

Rules, most severe first:

1. **`inactive` short-circuits everything.** `if not source_row["active"]: return
   {"level": "inactive", "reasons": []}`. An inactive source is excluded from alerting
   entirely and never reports `error`, no matter how stale or broken its run history is.
2. **`error` — run-based.** Two independent sub-rules, both evaluated:
   - The latest non-`skipped` run is `failed` or `refused`.
   - `_CONSECUTIVE_FAILURE_THRESHOLD` or more non-`skipped` runs in a row are non-`ok`.

   **`skipped` runs are excluded from the consecutive-failure count entirely** — they
   neither break nor extend a streak. Per the docstring on `_run_based_errors`: a source
   that failed once, then was correctly `skipped` every time since (not due for a poll
   yet), is *not* 2-consecutive — it's one failure with no repeat, so this rule doesn't
   trip (staleness might still catch it if polling has actually stalled). But a source
   that failed, was `skipped` twice while not due, then failed again *is* 2 consecutive
   failures once the `skipped` rows are filtered out of the sequence.
3. **`error` — staleness.** `last_polled` is `None` ("never polled"), or `now - last_polled`
   exceeds `poll_interval_hours × 2`. Measured against real `now`, not the window end (see
   above).
4. **`warn` — only reached when no error fired.** The two warn rules are mutually
   exclusive (`if raw_count == 0 ... elif published == 0`):
   - Zero `raw` events in the window ("polling but zero new raw events in window").
   - Otherwise, zero `published` events in the window ("raw events arriving but none
     published in window").
5. **`ok`** — none of the above.

Every applicable rule contributes its own reason string to `reasons: [...]`; the response
always carries the full list of what fired, not just the first match. The **level**
itself is just the most severe single classification — error beats warn beats ok.

---

## `SourceRun` statuses

`ingestion/models.py:32`. One row per per-source poll attempt, written by
`record_source_run` / `record_skipped_run` (`ingestion/importers/source_run.py`):

| Status | Meaning |
|---|---|
| `ok` | Poll attempted and completed without exception. |
| `failed` | Something threw inside the poll attempt — `error_class`, `error_message`, and `traceback` are populated. |
| `refused` | A guard declined to poll — an expected, named condition, not a crash. `error_message` holds the `REFUSAL_*` reason (see below). |
| `skipped` | The source wasn't due yet (`poll_interval_hours` backoff) — no attempt was made at all. |

**Why `refused` is its own status, not folded into `failed`:** per the `errors.py`
docstring, the scraper/HTTP guard paths (bad URL, unknown scraper key, empty fetch) used
to just `return []` — indistinguishable, to the poll loop, from a legitimate fetch that
found zero new events. `SourceRefused` turns that silent "nothing happened" into a raised,
typed exception that `record_source_run` catches separately from a generic `Exception`,
so the funnel and the health check can tell "this guard correctly declined to run" apart
from "this crashed" and from "this ran cleanly and found nothing."

---

## The probe

`GET /devtools/probe?source_id=<int>&db=<alias>` — an SSE stream (`probe_stream`,
`devtools/views.py:379`) that dry-runs the fetch+parse stage for one `EventSource`.

It is a genuine dry run: it **never writes** `RawEvent`, `StagedEvent`, or `SourceRun`
rows, and **never touches** `source.last_polled`. That's why it's safe to point at
`?db=prod_readonly` — it reuses the same fetch/parse logic as the real importers but
stops before the ORM-write phase entirely (no writes issued against either alias).

### SSE frames (five, not four)

| Frame | Payload | When |
|---|---|---|
| `resolved` | `{source_id, name, source_type, url}` | Always first — confirms which source and DB alias were resolved. |
| `stage` | `{stage: "fetch"\|"parse", status: "start"\|"end", ...}` | Progress through the fetch and parse steps (bytes fetched, item count, up to 3 sample titles). |
| `refused` | `{reason, detail}` | A guard declined the probe — see reason codes below. |
| `error` | `{exception_class, message, traceback}` | Something threw during fetch/parse. |
| `done` | `{}` | Always last (in a `finally`), regardless of outcome. |

### Reason codes (`ingestion/importers/errors.py`)

| Code | Meaning |
|---|---|
| `non_public_url` | The source URL failed the SSRF guard (`_validate_url` — blocked host, private/loopback/link-local/reserved IP, or non-http(s) scheme). |
| `unknown_scraper_key` | `source_type` is `scraper`/`http` but `scraper_key` doesn't resolve via `get_scraper()`. |
| `empty_fetch` | The HTTP/ICS fetch succeeded but returned an empty body. |
| `nothing_to_poll` | Probe-only: `source_type` is `direct` or `email` — no fetch step exists for these types (the real poll loop never reaches this because it pre-filters to pollable types; the probe can be pointed at any source row). |
| `unknown_source_type` | Probe-only: `source_type` doesn't match any of `ics`/`scraper`/`http` (defensive — shouldn't happen given model choices). |

### Launching a probe from the monitor

Every collector and inbound row in the monitor table has a **Probe** button
(`monitor.html`). Clicking it opens that row's drilldown — reusing the same tabbed
drilldown as clicking the row itself, via the `renderTabs()` helper — on a third
**Probe** tab and immediately starts streaming `GET /devtools/probe?source_id=<id>&db=<db>`.
The button calls `e.stopPropagation()` so it doesn't also toggle the drilldown open/closed,
and the currently selected DB toggle (`currentDb()`) is passed through, so probing while
"Prod DB" is checked reads the prod source config.

While the stream is open the Probe tab shows a spinner with a live elapsed-second
counter (no cancel button — a scraper probe launches headless Chromium and can
legitimately run 10–30s) and the triggering button is disabled; both clear on whichever
terminal frame arrives. Each SSE frame renders distinctly in the log pane: `resolved`
names the source, `stage` frames show fetch/parse start and end (with byte counts, item
counts, and sample titles on the end frame), `refused` prints the guard name and detail
prominently (the reason this whole probe exists), and `error` renders the message and, if
present, the traceback. The client mirrors `playground.html`'s `EventSource` handling,
including its `streamDone` flag, so the native `error` event the browser fires on normal
connection close right after `done` is ignored instead of rendering as a spurious failure.

---

## Triage runbook

Symptom in the funnel → likely cause → where to look next:

| Symptom | Likely cause | Next step |
|---|---|---|
| `unprocessed` high, `raw` normal | The standardizer (Gemini) is erroring or backed up | Check `ingestion` logs for standardizer exceptions; run the probe to confirm fetch/parse still work |
| `no_staged` high | Standardizer ran (`processed=True`) but produced no `StagedEvent` | Look for a swallowed exception in `standardize_all_unprocessed` for this source's raw events |
| `duplicate` high | Dedup thresholds (title/location similarity) are matching too aggressively for this source's feed shape | Review recent `StagedEvent.duplicate_of` links; see [`ingestion-pipeline.md`](ingestion-pipeline.md) Phase 3 |
| `held_for_review` high | Safety scores are consistently landing above `SAFETY_SCORE_THRESHOLD` | See [`safety-scoring.md`](safety-scoring.md) for threshold tuning |
| `raw` zero, last run `refused` | A guard is declining every poll attempt | Run the probe (`?source_id=<id>`) — the `refused` frame names the exact guard that's firing |
| `raw` zero, last run `ok` or no recent runs | Source may be inactive, mis-scheduled, or genuinely has nothing new | Check `health.reasons` for staleness; confirm `active=True` and `poll_interval_hours` |
| Health `error`, 2+ consecutive non-ok runs | A real regression, not a blip | Check `error_message`/`traceback` on the most recent non-`skipped` `SourceRun` rows via the `runs` drilldown |

---

## Prod read-only safety

The monitor and probe can be pointed at prod data via `?db=prod_readonly` without ever
writing to prod. Layered defenses, from primary to secondary:

1. **Primary control — the Postgres role.** `prod_readonly` is only wired up at all when
   `PROD_DATABASE_URL` is set (`backend/settings/dev.py:41-52`), and that DSN must use the
   `monitor_readonly` Postgres role, which is granted `SELECT`-only at the database level
   on the prod Neon branch. This is the enforcement that actually matters — Django never
   blocks a write attempt against `prod_readonly` on its own. Setup, verification, and
   rotation are fully documented in
   [`dev-db-isolation.md` § Monitoring Prod Read-Only from Local Dev](dev-db-isolation.md#monitoring-prod-read-only-from-local-dev) —
   this doc doesn't restate that runbook, it cross-links it.
2. **Defense in depth — `monitoring.py`'s no-write contract.** The module docstring states
   it plainly: "Read-only: no `.save()`/`.delete()` anywhere in this module." Every query
   function also calls `_db_ok(db)` first, so an unconfigured `prod_readonly` alias
   degrades to an empty result instead of raising.
3. **Defense in depth — the probe's dry-run guarantee.** `probe_stream` never reaches the
   ORM-write phase of the real importers (see above), so even a probe pointed at
   `prod_readonly` can't write there.

None of layers 2–3 would matter if the role behind `PROD_DATABASE_URL` were read-write —
the Postgres grant is the control that makes pointing dev tooling at prod data safe at all.

### Deploy gotcha: `ALTER DEFAULT PRIVILEGES` doesn't follow the table across roles

`ALTER DEFAULT PRIVILEGES ... GRANT SELECT ON TABLES TO monitor_readonly` (set up per the
dev-db-isolation runbook) only auto-grants `SELECT` on tables created **by the role that
ran that statement**. If prod migrations run as a different Postgres role than the one
that set up the default privileges, a newly migrated table is invisible to
`monitor_readonly` even though the default-privileges statement exists.

Concretely: after migration `0014_sourcerun` runs on prod, confirm `monitor_readonly` can
actually `SELECT` from the new `ingestion_sourcerun` table. If it can't, the monitor will
500 with `permission denied for table ingestion_sourcerun` the moment it tries to render
health for any source (every row touches `SourceRun`). This is unverified in prod as of
this writing — check it after the next deploy that includes migration `0014_sourcerun`.

**Fix** — re-run the grant for that specific table, against the prod branch, as an
owner/admin role:

```sql
GRANT SELECT ON ingestion_sourcerun TO monitor_readonly;
```

If this keeps recurring across future migrations, the more durable fix is running
`ALTER DEFAULT PRIVILEGES` as (or granted by) whatever role prod migrations actually run
as — but that's a role-alignment decision to make deliberately, not a blanket workaround
to apply here.
