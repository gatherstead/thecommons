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

**Which database you're looking at is always visible.** The page header renders a
`Reading: default (local)` / `Reading: prod_readonly (read-only)` badge next to the title,
restating the same `db` query param the window/DB toggle in `.controls` already reflects —
just louder, and unmissable even if the toggle itself is glanced past. This matters because
`?db=default` against a stale local `DATABASE_URL` renders an empty Collectors table that
looks identical, at a glance, to a genuinely-empty prod read — the badge is the one thing on
the page that always answers "which database, unambiguously" regardless of what the tables
below it show.

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

### How a zero is rendered

Funnel counts are **server-rendered** (no JavaScript pass), and a genuine zero renders as a
muted grey `0` — never an em-dash. The em-dash is reserved for genuinely-absent values, of
which `Last polled` on a never-polled source is the only one in these tables. An earlier
version rendered zeros as dashes, which meant a row of eight real zeros looked identical to
a page that had failed to load its data, while the *same glyph* in the same row meant "no
value" under `Last polled`.

That leaves a third state worth knowing: a **blank** funnel cell is diagnostic. `0` means
the server sent integer zero; blank means the template lookup missed and no value was sent
at all — a real bug, not an empty window.

### Zero in this window vs. zero ever

A muted `0` in the `raw` column answers "did this source produce anything in the selected
window", which conflates two very different situations: a source that's just quiet right
now (real rows exist, just older than the window) and a source that has **never** produced
a single `RawEvent`. On a real prod page this showed up as eight identical muted zeros
across three collectors — indistinguishable from a broken page — when the actual story was
one stale-window source and two sources that had never ingested anything at all.

`_source_rows` (`devtools/monitoring.py`) now runs one additional un-windowed grouped query
per `collector_summary` / `broadcast_inbound_summary` call — `raw_all_time` (a plain count)
and `latest_raw_created_at` (`Max(created_at)`) over the same `source_ids`, same shape as
the windowed `raw` query, so it stays O(1) per page render regardless of source count. When
`funnel.raw == 0`, `_raw_zero_note` composes one of two messages, rendered as a subscript
next to the `0` (and as its tooltip):

- Rows exist outside the window: `0 in window; 63 all-time, newest 2026-05-14 (75d ago) —
  widen the window`.
- No rows exist, ever: `never produced a raw event`.

The windowed `funnel.raw` value itself is unchanged — this is purely additional signal, not
a fix to the windowed count (which was verified correct against prod; see the git history
around ticket 35.4 if that assumption ever needs re-checking).

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

`source_health()` classifies each source as `inactive`, `ok`, `unknown`, `warn`, or
`error`. Three constants drive the rules:

- `_STALE_POLL_MULTIPLIER = 2` — a source is stale once it's gone `2 ×
  poll_interval_hours × shard_count` without polling (see shard note below).
- `_CONSECUTIVE_FAILURE_THRESHOLD = 2` — two consecutive non-`ok` runs (after filtering out
  `skipped`) trip the error rule regardless of the latest run's own status.
- `_RECENT_RUNS_PER_SOURCE = 5` — how many recent `SourceRun` rows are pulled per source to
  evaluate the consecutive-failure rule (padded above the threshold so a stray `skipped`
  run doesn't push a real failure out of the window).

**Staleness is shard-aware.** Prod runs `INGEST_SHARD_COUNT=3` — day-of-year sharding means
each source is only *eligible* to poll on one day in three, so the real cadence between
polls is `poll_interval_hours × shard_count`, not `poll_interval_hours` alone. Every
staleness threshold in this module (`_staleness_signal`, `monitoring.py`) multiplies by
`_assumed_shard_count()` before comparing, so a source with `poll_interval_hours=24` under
shard 3 gets a ~144h grace period instead of 48h. Before this, a perfectly healthy sharded
prod rendered a permanent red `error` badge — a false alarm on every single row, all the
time.

`_assumed_shard_count()` parses `INGEST_SHARD_COUNT` from the **local** process's
environment, duplicating (not importing) the same parsing rules as
`ingestion/tasks.py::_resolve_env_shard` (unset, unparseable, or `≤ 1` all mean shard count
1 — sharding disabled). This is a real wart: the devtool is judging a *remote*
`prod_readonly` database's staleness using a *local* env var, and there is no way for it to
ask prod what its own `INGEST_SHARD_COUNT` actually is. The mitigation is visibility, not a
fix — every staleness reason string names the assumed count explicitly, e.g. `last polled
60.0h ago, expected within 144h (assuming shard count 3)`, so a mismatch between local and
prod configuration is something an operator can see and account for, not something silently
wrong.

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
3. **`error` — staleness.** `now - last_polled` exceeds `poll_interval_hours × shard_count ×
   2`. Measured against real `now`, not the window end (see above). This rule requires a
   non-null `last_polled`: **`error` is reserved for evidenced failure**, meaning a source
   that demonstrably polled and then stopped.
4. **`warn` / `unknown` — never polled.** A null `last_polled` is *absence of signal*, not
   evidence of failure, so it never reports `error`. It's judged against the same
   shard-aware grace period (`poll_interval_hours × shard_count × _STALE_POLL_MULTIPLIER`),
   measured from `created_at`:
   - Inside the grace period → **`unknown`**: the source isn't due for a first poll yet.
   - Past it → **`warn`**: something should have polled it and didn't.

   A source added but not yet scheduled must not render the same red badge as one that has
   been hard-failing for weeks; an operator who learns that red sometimes means "nothing
   happened" stops trusting red.
5. **`warn` — funnel stalls.** The two rules are mutually exclusive (`if raw_count == 0 ...
   elif published == 0`):
   - Zero `raw` events in the window ("polling but zero new raw events in window").
   - Otherwise, zero `published` events in the window ("raw events arriving but none
     published in window").

   Both are **suppressed entirely for a never-polled source** — they presuppose polling,
   and without the suppression the badge tooltip contradicts itself ("never polled; polling
   but zero new raw events in window").
6. **`ok`** — none of the above.

Every applicable rule contributes its own reason string to `reasons: [...]`; the response
always carries the full list of what fired, not just the first match. The **level**
itself is just the most severe single classification — error beats warn beats unknown beats
ok, per `_HEALTH_RANK`, which is also the table's sort order.

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
`devtools/views.py:560`) that dry-runs the fetch, parse, **and write** stages for one
`EventSource`.

**Why write is in scope (ticket 35.6):** during an 8-day prod outage, all three
collectors probed green — HTTP 200, dozens of items parsed — while the pipeline was
completely dead. Fetch+parse alone can't catch a write-path regression (a broken
datetime conversion, a `get_or_create` failure, a migration prod hasn't picked up yet),
so a probe that stops at parse can report success on a dead pipeline. The probe now
builds the exact `RawEvent` rows the real importer would create and issues them against
the target database inside a transaction, so a write-path failure surfaces as a failing
`write` stage frame instead of a silent `Done`.

It is still a genuine dry run: it **never leaves a row behind**. Every write goes through
`transaction.atomic()` with `transaction.set_rollback(True, ...)` forced at the end of the
block (`_probe_dry_run_write`), so even a fully successful dry run rolls back —
`RawEvent`/`StagedEvent`/`SourceRun` counts and `source.last_polled` are unchanged after
the stream ends, proven by a test that asserts row counts before/after. Pointed at
`?db=prod_readonly`, the write stage is skipped outright rather than attempted and rolled
back: `prod_readonly` is a genuinely read-only Postgres role (`SELECT` only, enforced at
the DB level — see "Prod read-only safety" below), so an attempted write there wouldn't
even reach the rollback and would instead surface as an opaque `InsufficientPrivilege`.
The probe checks the `db` alias before issuing any write statement and substitutes a
`write` stage frame with `status: "skipped"` and an explanatory `detail` instead.

**Client-IP caveat.** The probe runs from the operator's laptop, not the production VM —
it structurally cannot detect IP- or User-Agent-based blocking by the source's own WAF.
This was a live false hypothesis during the outage investigation (network layer got
blamed while the real fault was downstream of parse). The Probe tab in `monitor.html`
states this caveat directly, not just here: a green probe proves the write path works
*from this machine*, not that prod's poller can reach the source at all.

### SSE frames (still five event types — `write` is a `stage`, not a new type)

| Frame | Payload | When |
|---|---|---|
| `resolved` | `{source_id, name, source_type, url}` | Always first — confirms which source and DB alias were resolved. |
| `stage` | `{stage: "fetch"\|"parse"\|"write", status: "start"\|"end"\|"skipped", ...}` | Progress through fetch, parse, and write. `fetch`/`parse` carry byte counts, item count, up to 3 sample titles on their `end` frame. `write` carries `item_count` and `would_create` on `end`, or `reason`/`detail` on `skipped` (read-only DB — see below). |
| `refused` | `{reason, detail}` | A guard declined the probe before fetch even started — see reason codes below. |
| `error` | `{exception_class, message, traceback}` | Something threw during fetch, parse, or write — including a write-path failure that used to be invisible to this tool. |
| `done` | `{}` | Always last (in a `finally`), regardless of outcome. |

### Reason codes (`ingestion/importers/errors.py`, plus one probe-local code)

| Code | Meaning |
|---|---|
| `non_public_url` | The source URL failed the SSRF guard (`_validate_url` — blocked host, private/loopback/link-local/reserved IP, or non-http(s) scheme). |
| `unknown_scraper_key` | `source_type` is `scraper`/`http` but `scraper_key` doesn't resolve via `get_scraper()`. |
| `empty_fetch` | The HTTP/ICS fetch succeeded but returned an empty body. |
| `nothing_to_poll` | Probe-only: `source_type` is `direct` or `email` — no fetch step exists for these types (the real poll loop never reaches this because it pre-filters to pollable types; the probe can be pointed at any source row). |
| `unknown_source_type` | Probe-only: `source_type` doesn't match any of `ics`/`scraper`/`http` (defensive — shouldn't happen given model choices). |
| `readonly_db_write_dry_run_unavailable` | Probe-only, carried on a `stage`/`write`/`skipped` frame (not a `refused`, since fetch and parse already succeeded) — `db=prod_readonly`, so the write dry-run was skipped rather than attempted. Defined in `devtools/views.py` as `PROBE_WRITE_SKIPPED_READONLY_DB`, not in `ingestion/importers/errors.py`, since it isn't a refusal the real importers can ever hit. |

### Launching a probe from the monitor

Every collector and inbound row in the monitor table has a **Probe** button
(`monitor.html`). Clicking it opens that row's drilldown — reusing the same tabbed
drilldown as clicking the row itself, via the `renderTabs()` helper — on a third
**Probe** tab and immediately starts streaming `GET /devtools/probe?source_id=<id>&db=<db>`.
The button calls `e.stopPropagation()` so it doesn't also toggle the drilldown open/closed,
and the currently selected DB toggle (`currentDb()`) is passed through, so probing while
"Prod DB" is checked reads the prod source config (and skips the write stage, per above).

While the stream is open the Probe tab shows a spinner with a live elapsed-second
counter (no cancel button — a scraper probe launches headless Chromium and can
legitimately run 10–30s) and the triggering button is disabled; both clear on whichever
terminal frame arrives. A caveat line above the log pane states the client-IP limitation
up front, before any frame renders. Each SSE frame renders distinctly in the log pane:
`resolved` names the source, `stage` frames show fetch/parse/write start, end, or skipped
(with byte counts, item counts, sample titles, or the read-only-DB explanation as
applicable), `refused` prints the guard name and detail prominently (the reason this whole
probe exists), and `error` renders the message and, if present, the traceback — now
reachable from a write-path failure, not just fetch/parse. The client mirrors
`playground.html`'s `EventSource` handling, including its `streamDone` flag, so the native
`error` event the browser fires on normal connection close right after `done` is ignored
instead of rendering as a spurious failure.

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
3. **Defense in depth — the probe's dry-run guarantee.** `probe_stream` now does reach the
   ORM-write phase (ticket 35.6 — see "The probe" above), but every write it issues is
   wrapped in `transaction.atomic()` with a forced `set_rollback(True)`, so nothing it
   writes is ever committed. Against `prod_readonly` specifically, the probe skips the
   write attempt outright rather than relying on the rollback — the alias check happens
   before any write statement is issued, so there's no dependency on Postgres rejecting
   the write for this layer to hold.

None of layers 2–3 would matter if the role behind `PROD_DATABASE_URL` were read-write —
the Postgres grant is the control that makes pointing dev tooling at prod data safe at all.

### Deploy gotcha: `ALTER DEFAULT PRIVILEGES` doesn't follow the table across roles

`ALTER DEFAULT PRIVILEGES ... GRANT SELECT ON TABLES TO monitor_readonly` (set up per the
dev-db-isolation runbook) only auto-grants `SELECT` on tables created **by the role that
ran that statement**. If prod migrations run as a different Postgres role than the one
that set up the default privileges, a newly migrated table is invisible to
`monitor_readonly` even though the default-privileges statement exists.

Concretely: after migration `0014_sourcerun` runs on prod, confirm `monitor_readonly` can
actually `SELECT` from the new `ingestion_sourcerun` table.

**Status as of 2026-07-28 (verified against prod, not assumed):** prod is still on
`0013_alter_eventsource_source_type` — `0014_sourcerun` has **not** been deployed, so
`ingestion_sourcerun` does not exist there at all. The first symptom is therefore
`relation "ingestion_sourcerun" does not exist`, not `permission denied`; the grant
question only becomes live once `0014` actually lands. The other prod tables read fine
(`EventSource`, `RawEvent`, `StagedEvent` all return rows as `monitor_readonly`).

This used to take the whole monitor down — `_source_rows` queried `SourceRun`
unconditionally, so *every* `?db=prod_readonly` page load raised `ProgrammingError`. It now
degrades instead: `resolve_source_runs_state()` gates every run-based feature, the page
renders with a banner explaining that run history is unavailable, and health falls back to
the last-polled staleness and warn rules.

That guard distinguishes the two causes by **SQLSTATE**, not by introspection. Django's
PostgreSQL backend builds its table list from `pg_catalog.pg_class`
(`django/db/backends/postgresql/introspection.py`), which has **no privilege predicate** — a
table the role cannot `SELECT` is still listed. An earlier version of this doc claimed
`information_schema.tables` filters by privilege and that introspection therefore covered
the missing-`GRANT` case too; that was wrong, and it is why the permission case went
undetected long enough to become a latent 500. `resolve_source_runs_state()` now issues the
cheapest possible read and branches on the failure's SQLSTATE:

| SQLSTATE | State returned | Meaning |
|---|---|---|
| — (query succeeds) | `available` | Run history readable |
| `42P01` `UndefinedTable` | `missing_table` | Behind on `0014_sourcerun` |
| `42501` `InsufficientPrivilege` | `no_permission` | Table exists, `GRANT SELECT` missing |
| (`OperationalError`) | `unreachable` | Couldn't connect at all |

Catching the error is safe here: `ATOMIC_REQUESTS` is set nowhere in this repo and
`monitor()` opens no `atomic()` block, so Django runs in autocommit and each failed
statement is its own aborted transaction — nothing downstream is poisoned. The stack is
psycopg 3, so the driver error exposes `.sqlstate` (psycopg2 called it `.pgcode`).

**Fix** — re-run the grant for that specific table, against the prod branch, as an
owner/admin role:

```sql
GRANT SELECT ON ingestion_sourcerun TO monitor_readonly;
```

If this keeps recurring across future migrations, the more durable fix is running
`ALTER DEFAULT PRIVILEGES` as (or granted by) whatever role prod migrations actually run
as — but that's a role-alignment decision to make deliberately, not a blanket workaround
to apply here.

---

## Beat scheduler: last_run_at persistence lag

This section is about `manage.py healthcheck` (the systemd-driven prod healthcheck run
by `healthcheck.service`, documented in [DEPLOY.md](../DEPLOY.md#health-check)) and
`django_celery_beat`'s scheduler, not the `/devtools/monitor` dashboard the rest of this
doc covers — it lives here because the incident originates in the same
poll/schedule/freshness family of problems and `backend/settings/base.py` points here for
the writeup.

**Symptom (2026-07-29, ticket 36.4):** `manage.py healthcheck` reported
`beat:broadcast-orphan-recovery STALE — last run 9.7h ago (> 7h window)` every hour on
prod, making `healthcheck.service` a permanently failing systemd unit even though the
task was actually running on schedule.

**Root cause.** `django_celery_beat`'s `DatabaseScheduler` keeps `PeriodicTask.last_run_at`
in memory and only writes it to Postgres when celery's `Scheduler._do_sync()` runs. Both
sync triggers were defeated:

1. `backend/settings/base.py` sets `CELERY_BEAT_MAX_LOOP_INTERVAL = 6 * 60 * 60`. That
   becomes `Scheduler.max_interval` (`celery/beat.py:252-258`), overriding
   django_celery_beat's `DEFAULT_MAX_INTERVAL = 5` (`django_celery_beat/schedulers.py:33`).
   In `Service.start()` (`celery/beat.py:633-655`), `_do_sync()` is only called after
   `time.sleep(interval)`, and only inside `if interval and interval > 0.0` — so beat can
   sleep up to 6 hours between sync opportunities.
2. `Scheduler.apply_async`'s `finally` block (`celery/beat.py:416-418`) is the other
   trigger, gated on `should_sync()` (`celery/beat.py:381-387`). Its task-count clause is
   dead because `app.conf.beat_sync_every` defaults to **0**. Its time clause requires
   `monotonic() - _last_sync > sync_every` where `sync_every = 180` (3 minutes) — so a task
   firing shortly after a prior sync flushes nothing.

**Measured proof on prod** (read-only queries plus one authorized `-l debug` restart):

```
22:24:33  BEFORE   last_run_at = 2026-07-29 12:00:01.808480+00   total_run_count =  9
22:24:35  systemctl restart celerybeat
22:24:37  AFTER    last_run_at = 2026-07-29 18:00:00.021322+00   total_run_count = 10
```

The 18:00 write had been buffered in memory for 4h24m and was flushed only by celery's
shutdown path (`Service.start()`'s `finally: self.sync()`). Beat's journal showed
`Sending due task broadcast-orphan-recovery` at `18:00:00,023`, and the broadcast worker
logged the task `received` and `succeeded in 0.083s` — the task was sent and executed on
time. Only the bookkeeping write was late. Beat had one process, `NRestarts=0`, and no
errors or warnings above DEBUG in `journalctl -u celerybeat`.

**Hypotheses that were disproven** (recorded so nobody re-chases them):

- *A dev/prod database split* — ruled out: `DJANGO_ENV=prod`, DB host
  `ep-late-smoke-...-pooler`, name `neondb`.
- *A swallowed `ObjectDoesNotExist`/`TypeError` in `DatabaseScheduler.sync()`*
  (`django_celery_beat/schedulers.py:459`, which re-adds the failed name to `_dirty` and
  retries forever with no log above DEBUG) — ruled out: `save()` succeeded fine at
  shutdown against the same pk.
- *A stale in-memory `_schedule` overwriting the fresh value* — ruled out: memory held the
  18:00 value, not 12:00.
- *Clock skew.* This one is a trap worth documenting on its own: beat's startup banner
  (`celery beat vX.Y.Z is starting. / LocalTime -> ...`) is flushed at process
  **teardown** and reports that process's own *start* time, so in `journalctl` it looks
  like beat's clock is running behind the system clock. It isn't. Verified across three
  consecutive restarts, where each banner's `LocalTime` matched the previous PID's
  `beat: Starting...` timestamp exactly.

**The fix:** `CELERY_BEAT_SYNC_EVERY = 1` in `backend/settings/base.py`, which maps to
`app.conf.beat_sync_every` → `Scheduler.sync_every_tasks` (`celery/beat.py:262-264`),
forcing a sync after every task send. This costs one UPDATE per task fire and does not
change beat's DB poll rate — deliberately, since `CELERY_BEAT_MAX_LOOP_INTERVAL` exists to
reduce Neon serverless wake-ups, and that trade-off is still worth making. Regression test:
`backendServer/events/tests/test_beat_last_run_persistence.py`.

**Why this matters for monitoring:** before this fix, `last_run_at` could lag reality by
up to `CELERY_BEAT_MAX_LOOP_INTERVAL` (6 hours), so any staleness check reading that
column was measuring a lagging value, not a real one. That's why a 7h window on a 6h-period
task produced false alarms — and why the tempting fix of "just widen the window to 13h"
would have been wrong: it papers over the false alarm but doesn't fix the actual defect
(a real multi-hour outage would then also go undetected for up to 13h). Widening the
window here would have hidden a genuine bug rather than fixed it.

**How to tell a persistence lag from a real outage:** restart `celerybeat` and re-read the
`PeriodicTask` row. Beat's shutdown path always flushes (`Service.start()`'s
`finally: self.sync()`), so a `last_run_at` that jumps forward immediately after the
restart was sitting in memory, not missed — the task fired, the write was just late. If
the value doesn't move after a restart, that's a real gap: the task actually isn't firing.
