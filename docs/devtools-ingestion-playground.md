# Plan: Dev-only Ingestion Playground (`devtools/`)

> Hand-off doc for a fresh Claude Code instance implementing with **parallel developer subagents** (claude sonnet 4.6 medium effort).
> Workstreams in §4 are designed so no two agents edit the same file. Contracts in §2 and §6 are frozen — implement against them.

---

## 1. Context — why we're building this

The Commons ingests community events from ICS calendar feeds through a 6-stage pipeline (poll → standardize → dedup → safety-score → auto-publish). Three problems motivate this tool:

1. **Adding new calendars is painful and risky.** Every ICS feed is shaped differently. Today the only way to test a new source is to insert an `EventSource` row, run the whole global pipeline (which processes *all* pending rows), and dig through console logs. There's no fast, isolated, "paste a URL and see what happens" loop.
2. **A real bug:** published events show an empty `source_name`. The feature that displays each event's source only populates on *fresh* ingestion (`ingestion/services.py:41`, set from `staged.raw_event.source.name`), and old events never got backfilled. We need to watch the source flow through the pipeline to see where it drops.
3. **Future goal:** feed structured pipeline output back to an AI (Claude Code) to auto-heal flaky sources. That requires the run to emit machine-readable per-stage JSON, not just human logs.

**The fix:** a dev-only, server-rendered Django page where you pick a city, paste an ICS URL, hit Run, and watch the full pipeline execute **live** (SSE) with verbose stage-by-stage logs — runs **dry (rolled back) by default**, with a **Save** button to commit when the feed looks good. Lives in a new `devtools/` app so it's a home for future non-prod tooling and is unregistered/404 in prod.

**Locked product decisions** (from the user):
- **Dry-run by default** — pipeline runs inside a rolled-back transaction; a separate Save action commits.
- **Force selected city as town** — the user's city overrides Gemini's inferred town so events actually publish (publish currently *silently drops* events whose town doesn't match a `Town.slug`). Warn when Gemini's guess differs.
- **Live streaming via SSE** (`StreamingHttpResponse`) + a final structured JSON payload.
- **Home: a new dev-only `devtools/` Django app** (not React, not theCommonsWeb/broadcastWeb). Server-rendered template + vanilla JS — sits next to the pipeline, no separate build/deploy.

---

## 2. Pipeline facts + frozen function-signature contract

Stages 2–5 are currently **global** (no per-source scoping) — this is the core thing to fix so the tool shows only one feed's output. Add a backwards-compatible `source=None` kwarg (default = current behavior; existing `ingest_events` command unaffected).

| Function | File | Change |
|---|---|---|
| `fetch_ics_feed(source)` | `ingestion/importers/ics_importer.py:15` | none — already per-source. Needs a **persisted** EventSource (uses `get_or_create`). |
| `standardize_all_unprocessed(source=None)` | `ingestion/standardizer.py:190` | `qs = RawEvent.objects.filter(processed=False)`; `if source: qs = qs.filter(source=source)` |
| `dedup_all_pending(source=None)` | `ingestion/deduplicator.py:49` | scope outer loop `qs.filter(raw_event__source=source)`; **keep `find_duplicate()` global** (dedup against all events) |
| `score_all_unscored(source=None)` | `ingestion/safety_scorer.py:84` | `qs.filter(raw_event__source=source)` |
| `auto_publish_safe_events(source=None, force_town=None)` | `ingestion/services.py:84` | scope pending; pass through to publish |
| `publish_all_approved(source=None, force_town=None)` | `ingestion/services.py:12` | scope approved + final DELETE; `force_town` bypasses slug matching; **add town-skip logging** |

**`force_town` (a `Town` instance):** in `publish_all_approved`, when set, use it directly instead of the fragile `town_slug = staged.town.lower().replace(' ','-')` → `Town.objects.filter(slug=...)` round-trip (`services.py:36-39`).

**Town-skip logging fix** (`services.py:36-39`): when no Town matches and the event is about to be dropped via `continue`, add:
```python
logger.warning("Dropping staged event '%s' — no Town matches slug '%s' (gemini town=%r)",
               staged.title, town_slug, staged.town)
```
This makes silent drops visible in both prod logs and the tool's live stream.

**Source-scoped final DELETE** in `publish_all_approved` — the existing `StagedEvent...delete()` (services.py:73-75) must also filter `raw_event__source=source` when scoped.

`source=None, force_town=None` defaults must reproduce current prod behavior byte-for-byte.

---

## 3. Architecture

```
backendServer/devtools/
  __init__.py
  apps.py                     # DevtoolsConfig
  urls.py                     # app urlconf
  views.py                    # playground (page), run_stream (SSE), save_and_publish
  pipeline_runner.py          # orchestrator: runs scoped pipeline in worker thread → queue
  sse.py                      # sse_frame() + QueueLoggingHandler
  templates/devtools/playground.html
```

**Dev-only registration (defense in depth):**
- `backend/settings/dev.py`: append `'devtools.apps.DevtoolsConfig'` to `INSTALLED_APPS` (app + templates load only in dev; `TEMPLATES['APP_DIRS']=True` auto-discovers).
- `backend/urls.py`: `from django.conf import settings`; at end `if settings.DEBUG: urlpatterns += [path("devtools/", include("devtools.urls"))]`.
- Every devtools view starts with `if not settings.DEBUG: raise Http404`.

**URLs** (EventSource is GET-only, so the SSE endpoint is GET):
- `GET  /devtools/` → `playground` (passes `towns=[{slug,name}]` from `Town.objects.order_by('name')`).
- `GET  /devtools/run?city=<slug>&ics_url=<url>&source_name=<str>` → `run_stream` (SSE, dry-run).
- `POST /devtools/save` → `save_and_publish` (commit, returns JSON).

---

## 4. Parallel workstreams (clean file ownership)

WS1, WS3, WS4 start immediately against the frozen contracts (§2, §6). WS2 integrates them.

### WS1 — Pipeline scoping (standardizer / deduplicator / safety_scorer)
- Files: `ingestion/standardizer.py`, `ingestion/deduplicator.py`, `ingestion/safety_scorer.py`.
- Add `source=None` kwarg per §2. `find_duplicate()` stays global.
- **AC:** omitting `source` is unchanged; with `source`, querysets filter `raw_event__source=source` (or `source=` for RawEvent). `ingest_events` command runs unchanged.

### WS4 — Publish scoping + force_town + town-skip logging (services.py only)
- File: `ingestion/services.py`.
- `publish_all_approved(source=None, force_town=None)`, `auto_publish_safe_events(source=None, force_town=None)`, source-scoped final DELETE, `logger.warning` at the town-skip (§2).
- **AC:** scoped call only publishes/deletes that source's approved staged events; `force_town` publishes regardless of `staged.town` string; town-skip emits WARNING on `ingestion` logger; no-arg call reproduces prod behavior (existing tests pass).

### WS2 — devtools app, orchestrator, SSE + save views, wiring
- Files: all of `devtools/*` except the template, plus `backend/urls.py`, `backend/settings/dev.py`.
- Implements `sse.py`, `pipeline_runner.py`, `views.py`, `urls.py`, `apps.py`, dev-only install/route + per-view `DEBUG` guard, `_validate_url` SSRF guard.
- **Contract in:** WS1+WS4 signatures. **Contract out:** URL paths + SSE protocol (§6).
- **AC:** `/devtools/` renders dropdown; `/devtools/run` returns `text/event-stream`, runs pipeline in a worker thread inside one atomic block, rolls back on dry-run, emits §6 frames ending with `done`; prod → 404 and app not installed; `/devtools/save` commits and returns JSON.

### WS3 — Template + vanilla-JS EventSource client
- File: `devtools/templates/devtools/playground.html` (extends `admin/base_site.html`; style after `templates/docs/publish_approved.html`).
- **Contract in:** URL paths + SSE protocol (§6) + `towns` context.
- **AC:** streams logs live, renders stage headers, amber town-mismatch warnings, results table with `source_name` highlighted (red if empty); Save button commits and shows result.

---

## 5. SSE orchestrator — the critical mechanics

**Worker thread + queue.** Gemini calls are slow and per-event, so to stream *live* (not per-stage batches), `run_stream` spawns a daemon thread running `run_pipeline_into_queue(q, ...)`; the request thread drains `q` and yields SSE frames. DB transactions are per-thread, so the worker owns its own atomic block + rollback.

**`sse.py`:**
```python
def sse_frame(event, data): return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"

class QueueLoggingHandler(logging.Handler):
    def __init__(self, q, thread_ident): super().__init__(); self.q=q; self.ident=thread_ident
    def emit(self, record):
        if record.thread != self.ident: return        # isolate concurrent runs
        self.q.put(("log", {"stage": getattr(record,"stage",""), "level": record.levelname,
                            "message": self.format(record), "ts": record.created}))
```
Attach to the `'ingestion'` logger for the run (it has `propagate=False`, so attach there, not root). Remove in `finally`.

**`pipeline_runner.run_pipeline_into_queue`** (worker thread), wrapped in ONE `with transaction.atomic():`
1. Create + `save()` a `EventSource(name=source_name or url-host, source_type='ics', url=ics_url, active=True)` **inside the txn** (so rollback removes it).
2. `fetch` → `fetch_ics_feed(source)`; emit `stage`/`stage_data`.
3. `standardize` → `standardize_all_unprocessed(source=source)`; emit staged records.
4. `force_town` → for each staged: if `slugify(s.town) != town.slug` emit `warning{code:"town_mismatch"}`; set `s.town = town.name; s.save(update_fields=['town'])`.
5. `dedup` → `dedup_all_pending(source=source)`.
6. `safety` → `score_all_unscored(source=source)`; emit scored records.
7. `publish` → **snapshot published Event dicts BEFORE rollback** (publish deletes the StagedEvents and runs its own nested atomic/savepoint): `auto_publish_safe_events(source=source, force_town=town)`, then build `published=[_event_dict(e) for e in Event.objects.filter(town=town, staged_source__raw_event__source=source).distinct()]` while still inside the txn.
8. If `dry_run`: `raise Rollback(final)` (custom exception caught just outside the atomic block) → all rows discarded, but the already-built dicts survive on the queue. Else `q.put(("done", final))`.
9. `finally`: remove log handler, `connection.close()` (release worker DB connection), `q.put(("__end__", None))`.

**Dry-run invariance:** publish's inner `transaction.atomic()` becomes a savepoint; the outer `raise Rollback` rolls back EventSource + RawEvent + StagedEvent + Event. Net persisted rows = 0. Results shown come from pre-rollback dict snapshots.

**`run_stream` view** sets `StreamingHttpResponse(stream(), content_type="text/event-stream")`, `Cache-Control: no-cache`, `X-Accel-Buffering: no`.

**`_validate_url`:** require http(s); block `localhost`/127.0.0.1/169.254.169.254/RFC-1918 (SSRF — the tool fetches an arbitrary pasted URL, and standardizer also page-scrapes per event).

**Save path (`save_and_publish`):** a sibling **synchronous** function (no worker/queue, no Rollback) using `EventSource.objects.get_or_create(url=ics_url, defaults={name, source_type:'ics', active:True})` (idempotent re-saves), then fetch→standardize→force_town→dedup→safety→`auto_publish_safe_events(source, force_town=town)`, commit, return `JsonResponse({'published': [...], 'counts': {...}})`.

---

## 6. SSE event protocol (WS2 ↔ WS3 contract)

Stages: `fetch`, `standardize`, `force_town`, `dedup`, `safety`, `publish`.

| event | data |
|---|---|
| `log` | `{stage, level, message, ts}` |
| `stage` | `{stage, status:"start"\|"end", summary?:{...}}` |
| `stage_data` | `{stage, records:[...]}` |
| `warning` | `{code, message, detail?}` |
| `done` | `{dry_run, town, counts:{auto_approved,held_for_review}, published:[event...]}` |
| `error` | `{message, traceback}` |

Record shapes (`stage_data.records[]`):
- **fetch:** `{id, raw_title, raw_location, raw_start, source_url, source_uid}`
- **standardize:** `{id, title, town, location_name, start_datetime, tags, price, link}`
- **safety:** `{id, title, safety_score, safety_notes, status}`
- **publish:** `{uuid, title, town, date, venue, source_name, price, link}`

JS client:
```js
const es = new EventSource(url);
['log','stage','stage_data','warning'].forEach(t =>
  es.addEventListener(t, e => render(t, JSON.parse(e.data))));
es.addEventListener('done',  e => { renderResults(JSON.parse(e.data)); es.close(); });
es.addEventListener('error', e => { renderError(e); es.close(); });
```

---

## 7. Verification (end-to-end)

```bash
cd backendServer   # DJANGO_ENV unset → dev (DEBUG=True)
# needs DATABASE_URL (the isolated dev branch) + GEMINI_API_KEY in .env
uv run python manage.py runserver
```
1. Open `http://localhost:8000/devtools/` — city dropdown populated from Towns.
2. Baseline: `uv run python manage.py shell -c "from events.models import Event; print(Event.objects.count())"`.
3. Pick a city, paste an ICS URL, click **Run (dry-run)**:
   - live `log` frames ("Imported…", "Standardized…", "Safety scored…: 0.xx"); `stage` headers fetch→…→publish; `warning` on town mismatch; results table; final `done`.
   - **source_name check:** every published row shows a source name (none red/empty). If empty, the live warnings + fallback path reveal why.
4. **Dry-run invariance:** re-run the baseline count — `Event`, `EventSource`, `RawEvent`, `StagedEvent` all unchanged (rollback works).
5. Click **Save source & publish** — counts increase; rows visible in `/admin/events/event/` with populated `source_name`.
6. **Prod guard:** `DJANGO_ENV=prod uv run python manage.py shell -c "from django.conf import settings; print('devtools' in str(settings.INSTALLED_APPS))"` → `False`; `/devtools/` → 404.

---

## 8. Risk callouts
- **DB connection per worker thread:** `connection.close()` in `finally` to avoid leaking it.
- **Log isolation:** `QueueLoggingHandler` filters `record.thread == worker ident` so concurrent requests don't cross-contaminate.
- **Gemini cost/latency:** standardize + safety call Gemini per event; a big feed = many calls. Optional `?limit=N` cap on RawEvents in dry-run.
- **Save idempotency:** `get_or_create(url=ics_url)` so re-publishing the same feed reuses the source.

### Critical files
- `ingestion/services.py`, `ingestion/standardizer.py`, `ingestion/deduplicator.py`, `ingestion/safety_scorer.py`
- `backend/urls.py`, `backend/settings/dev.py`
- `devtools/*` (new), `templates/docs/publish_approved.html` (style reference)
