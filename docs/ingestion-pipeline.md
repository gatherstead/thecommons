# Event Ingestion Pipeline

How ICS calendar events get from a source URL to a published event on thecommons.town.

---

## Overview

```
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

**Trigger:** Vercel cron job hits `GET /api/cron/ingest` every day at 8 AM UTC.
**Manual trigger:** Django admin → EventSources → select source → "Run ingestion pipeline" action.
**CLI trigger:** `python manage.py ingest_events`

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
| `ingestion_eventsource` | ICS source URLs and polling config |
| `ingestion_rawevent` | Raw parsed ICS data, one row per event per source |
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
| Cron schedule | `vercel.json` | `0 8 * * *` — runs at 8 AM UTC daily |

---

## CLI Flags (for testing/debugging)

```bash
# Full pipeline
python manage.py ingest_events

# Skip individual phases
python manage.py ingest_events --skip-poll          # skip ICS fetch
python manage.py ingest_events --skip-standardize   # skip Gemini LLM step
python manage.py ingest_events --skip-dedup         # skip duplicate detection
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
│   ├── admin.py                      # Admin UI for review + approval
│   ├── views.py                      # Cron + publish endpoints
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
