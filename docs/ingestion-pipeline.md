# Event Ingestion Pipeline

How ICS calendar events get from a source URL to a published event on thecommons.town.

---

## Overview

```
(Step 0: Cleanup)  ← delete past RawEvents + StagedEvents
     ↓
ICS Source URL
     ↓  (Phase 1: Poll)
  RawEvent  (stored as-is)
     ↓  (Phase 2: Standardize)
 StagedEvent  (LLM-cleaned, status=pending)
     ↓  (Phase 3: Deduplicate)
 StagedEvent  (duplicates marked, status=duplicate)
     ↓  (Phase 4: Admin Review)
 StagedEvent  (status=approved or rejected)
     ↓  (Phase 5: Publish)
    Event  (live on website)
     ↓
  REST API  →  Frontend
```

**Trigger:** Celery beat runs the pipeline daily at 04:00 America/New_York (schedule `ingest-events-daily`, seeded by migration `ingestion/migrations/0007_seed_ingest_beat.py`). `GET /api/cron/ingest` (Bearer `CRON_SECRET`) queues it on demand.
**Manual trigger:** Django admin → EventSources → select source → "Run ingestion pipeline" action.
**CLI trigger:** `python manage.py ingest_events`

---

## Step 0 — Cleanup (runs first, every time)

**File:** `backendServer/ingestion/management/commands/cleanup_old_events.py`

Runs automatically at the start of every pipeline run before any new events are fetched.

1. Delete all `StagedEvent` records where `start_datetime` is in the past — **except** those with `status='approved'` and no `published_event` yet (approved-but-not-yet-published events are preserved so they don't get lost).
2. Delete all `RawEvent` records where `raw_start` is in the past — **except** those still backing an approved+unpublished staged event (same preservation logic).

**What is preserved:**
- Approved staged events that haven't been pushed to the Events table yet (`status='approved'` + `published_event=null`)
- Their corresponding raw events

**What gets deleted:**
- All past `pending`, `rejected`, and `duplicate` staged events
- All past raw events that are no longer needed

---

## Phase 1 — Poll ICS Sources

**File:** `backendServer/ingestion/importers/ics_importer.py`
**Model:** `RawEvent` (`backendServer/ingestion/models.py`)

1. Load all `EventSource` records where `active=True`.
2. Skip sources polled within the last `poll_interval_hours` (default: 24h).
3. HTTP GET the ICS feed URL (30s timeout).
4. Parse the `.ics` file with the `icalendar` library, extracting each `VEVENT`:
   - `SUMMARY` → raw title
   - `DESCRIPTION` → raw description
   - `LOCATION` → raw location
   - `DTSTART` / `DTEND` → start/end datetimes (converted to UTC-aware)
   - `UID` → unique identifier (or SHA256 hash of title+start if missing)
   - `URL` or regex-extracted URL from description → `source_url`
5. Skip events whose start time is in the past.
6. Save each event as a `RawEvent` with `processed=False`.
   - Unique constraint on `(source, source_uid)` prevents re-importing the same event.
7. Update `EventSource.last_polled = now()`.

---

## Phase 2 — Standardize with LLM

**File:** `backendServer/ingestion/standardizer.py`
**Model:** `StagedEvent` (`backendServer/ingestion/models.py`)

Runs on all `RawEvent` records where `processed=False`.

1. For each raw event, fetch the event's webpage (from `source_url`) using `requests` (10s timeout, Mozilla user-agent).
2. Strip HTML tags with `BeautifulSoup` to get plain visible text (max 6000 chars).
3. Call **Google Gemini API** with the raw event data + scraped webpage text.
   - Primary model: `gemini-2.5-flash-lite`
   - Fallbacks: `gemini-2.5-flash` → `gemini-2.5-pro`
   - Retry logic: 3 attempts with exponential backoff (1s, 2s, 4s) on 503 errors
4. The prompt instructs Gemini to produce:
   - **Title** — clean, standardized event title
   - **Description** — 2–3 sentences, warm and community-focused (never starts with "Join us")
   - **Location name** — venue or address
   - **Town** — inferred from the location
   - **Tags** — selected from the allowed list (see below)
   - **Price** — searches both raw text and scraped webpage for cost indicators (`$X`, "free", "cost:", "fee:", etc.); uses `-1` if not applicable
5. Create a `StagedEvent` record with `status='pending'`.
6. Mark the `RawEvent.processed = True`.

### Allowed Tags (35 total)

| Category | Tags |
|---|---|
| Schedule | `weekends-only`, `evenings-only`, `daytime-only` |
| Cost | `free` |
| Audience | `family-friendly`, `lgbtq-friendly`, `speaks-spanish` |
| Accessibility | `wheelchair-accessible` |
| Activity | `live-music`, `food-and-drink`, `arts-and-culture`, `fitness-and-wellness`, `community-meetup`, `fundraiser`, `market-or-fair`, `workshop-or-class` |
| Business | `small-business`, `nature` |

---

## Phase 3 — Deduplicate

**File:** `backendServer/ingestion/deduplicator.py`

Runs on all `StagedEvent` records with `status='pending'`.

1. For each pending staged event, look for other pending events within a ±3 hour window.
2. Use the `thefuzz` library (Levenshtein distance) to compare:
   - **Title similarity ≥ 80%** AND
   - **Location similarity ≥ 75%**
3. If both thresholds are met, mark the newer event as `status='duplicate'` and set `duplicate_of` FK to the earlier one.

---

## Phase 4 — Admin Review

**URL:** `/admin/` (Django Admin with django-unfold UI)
**File:** `backendServer/ingestion/admin.py`

Admins review `StagedEvent` records in the **Staged Events** list:

- **Columns:** title, location, town, date, status, price, link, tags, source
- **Filter by status:** `pending` / `approved` / `rejected` / `duplicate`
- **Inline edit:** change `status` directly in the list view
- **Bulk actions:**
  - "Approve selected events" — creates an `Event` record + tags, sets `status='approved'`
  - "Reject selected events" — sets `status='rejected'`

Approving a staged event immediately creates the corresponding `Event` in the database.

---

## Phase 5 — Publish to Website

**Endpoint:** `POST /api/events/publish-approved` (also called automatically by the cron job)
**File:** `backendServer/ingestion/views.py` → `publish_approved_events()`

1. Find all `StagedEvent` records with `status='approved'` and no `published_event` yet.
2. Within a single **atomic transaction**:
   - Create an `Event` record for each.
   - Create/get `Tag` objects and attach them via M2M.
3. Delete all approved `StagedEvent` records (cleanup).

---

## Direct Host Submission

**Endpoint:** `POST /api/events/direct-submit`
**Key files:** `backendServer/ingestion/views.py`, `backendServer/ingestion/serializers.py`, `backendServer/ingestion/access.py`, `backendServer/ingestion/services.py`, `backendServer/ingestion/tasks.py`

An alternative entry path that bypasses ICS polling. The broadcast SPA fires this call fire-and-forget when the operator clicks "Preview Destinations" — the same event data going to the preview also enters the pipeline immediately, so the host's event appears in the system without waiting for a cron run.

### Auth — JWT or anonymous

The endpoint is decorated with `BearerTokenAuthentication`. A valid **Better Auth JWT** (`Authorization: Bearer <jwt>`) attributes the submission to the resolved `BetterAuthUser` (`submitted_by`). An invalid token is rejected with 401 before the view body runs. No token → `submitted_by=None` (anonymous submission accepted). The previous grant-based code-to-user model has been removed; ownership is now derived solely from the JWT.

### Request / response

```json
// Request body (JWT optional via Authorization: Bearer header)
{ "draft_id": "<uuid>", "event": { ...broadcast canonical event shape... } }

// 202 on success
{ "status": "queued", "draft_id": "..." }
// 401 — invalid token (rejected by BearerTokenAuthentication before view body)
// 400 — invalid event payload or missing draft_id
```

Rate-limited 10/m by IP. The event serializer (`ingestion/serializers.py`) is a **self-contained copy** of the broadcast canonical-event field set — it does not import from `broadcast/`.

### Idempotency via `draft_id`

The endpoint upserts a singleton `EventSource(name="Direct Host Submission", source_type='direct', active=False)`, then calls `RawEvent.objects.update_or_create(source=source, source_uid=draft_id, defaults=...)`. Re-submitting the same `draft_id` (e.g. the host edits the form and clicks Preview again) refreshes the existing `RawEvent` in place rather than creating a duplicate. `source_type='direct'` is a dedicated `EventSource.source_type` choice.

### Pipeline (`ingestion/services.py::ingest_direct_submission`, Celery task `ingest_direct_submission_task`)

1. Loads the `RawEvent`. If a `StagedEvent` already exists for it, remembers its `published_event` FK, then deletes the staged row so re-standardization starts fresh.
2. `standardize_event` (Gemini) → sets `submitted_by = user`.
3. Safety-scores via `safety_scorer.score_event`.
4. `find_duplicate` — if a pending/approved duplicate exists, marks `status='duplicate'` and stops (no publish).
5. **Safety gate:** `safety_score <= SAFETY_SCORE_THRESHOLD` → publish immediately; otherwise the `StagedEvent` stays `status='pending'` (visible in the host/admin dashboard for manual review) with no live `Event` created.
6. **Publish (create-or-update):** reuses the `publish_all_approved` field mapping but overrides `source_name = "Direct submission by host"`, sets `created_by = user`, and `is_verified = (user.user_type == 'BUSINESS')`. If a prior published `Event` exists (re-edit path), it is updated in place; otherwise a new `Event` is created and linked.
7. **StagedEvent retained** — unlike the bulk `publish_all_approved` flow, the `StagedEvent` row is kept so the edit chain survives future re-submissions.
8. **Town resolution** reuses `Town.objects.filter(slug=...)`. If no matching `Town` exists, the event is logged and the `StagedEvent` is set to the terminal `status='skipped_no_town'` (no `Event` created) — the same terminal status the `publish_all_approved` sweep path uses for out-of-coverage towns, so the row remains a dedupe anchor (`deduplicator.CANDIDATE_STATUSES`) rather than a perpetually-pending dead end. `manage.py reopen_skipped_towns` reopens it (it has no source filter) once coverage is added.

### Isolation

The bridge lives entirely in `ingestion/`. `broadcast/` still imports nothing from `events/` or `ingestion/`; `broadcast/tests/test_isolation.py` remains green. The dependency is one-way: ingestion uses a copied serializer that mirrors the broadcast canonical-event shape, but `broadcast/` is never imported from `ingestion/`.

---

## Frontend Display

**Files:** `theCommonsWeb/src/services/eventService.ts`, `theCommonsWeb/src/components/EventCard.tsx`

1. Frontend calls `GET /events/` on load.
2. `eventService.ts` transforms the API response:
   - `date` string → JS `Date` object
   - `time` formatted as "h:mm AM/PM"
   - `price` formatted as "$X.XX" or "Free Entry" if `0`
3. Events sorted ascending by date; the first event gets a featured (large) card.
4. Users can filter by town and tags.

---

## Database Tables

| Table | Purpose |
|---|---|
| `ingestion_eventsource` | ICS source URLs and polling config; also the singleton `source_type='direct'` row for direct submissions |
| `ingestion_rawevent` | Raw parsed ICS data, one row per event per source; also direct-submission payloads keyed by `draft_id` |
| `ingestion_stagedevent` | LLM-cleaned events awaiting admin review |
| `events_event` | Published events (live on site) |
| `events_tag` | Tag lookup table |

---

## Configuration

| Variable | Where | Purpose |
|---|---|---|
| `GEMINI_API_KEY` | `.env` | Google Gemini API access |
| `CRON_SECRET` | `.env` | Bearer token to authenticate cron endpoint |
| `DATABASE_URL` | `.env` | Neon PostgreSQL connection string |
| Schedule | `django_celery_beat` (DB) | `ingest-events-daily` — 04:00 America/New_York, seeded by `ingestion/migrations/0007` |

---

## CLI Flags (for testing/debugging)

```bash
# Full pipeline (includes cleanup)
python manage.py ingest_events

# Skip individual phases
python manage.py ingest_events --skip-cleanup       # skip past-event deletion
python manage.py ingest_events --skip-poll          # skip ICS fetch
python manage.py ingest_events --skip-standardize   # skip Gemini LLM step
python manage.py ingest_events --skip-dedup         # skip duplicate detection

# Run cleanup standalone
python manage.py cleanup_old_events
```

---

## Key Files

```
backendServer/
├── ingestion/
│   ├── importers/ics_importer.py     # Phase 1: ICS fetch + parse
│   ├── standardizer.py               # Phase 2: Gemini LLM standardization
│   ├── deduplicator.py               # Phase 3: fuzzy duplicate detection
│   ├── models.py                     # EventSource, RawEvent, StagedEvent
│   ├── serializers.py                # DirectSubmitEventSerializer (canonical-event copy)
│   ├── services.py                   # ingest_direct_submission()
│   ├── tasks.py                      # ingest_direct_submission_task (Celery)
│   ├── admin.py                      # Admin UI for review + approval
│   ├── views.py                      # Cron + publish + direct_submit endpoints
│   └── management/commands/
│       └── ingest_events.py          # Django management command (orchestrator)
├── events/
│   ├── models.py                     # Event, Tag, UserProfile
│   ├── views.py                      # GET /events/ API
│   └── serializers.py                # Event → JSON
└── backend/
    ├── settings.py                   # GEMINI_API_KEY, CRON_SECRET, UNFOLD config
    └── urls.py                       # URL routing
theCommonsWeb/
└── src/
    ├── services/eventService.ts      # API client + data transform
    └── components/EventCard.tsx      # Event display component
```
