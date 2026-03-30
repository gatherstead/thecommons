# Admin Backend

The admin dashboard lives at `/admin/` and is built on Django's built-in admin framework styled with **django-unfold**. It is the primary interface for managing the event ingestion pipeline, reviewing staged events, and browsing published content.

---

## Access & Authentication

- **URL:** `/admin/`
- **Login:** Django's built-in username/password auth
- **Who can log in:** Any user with `is_staff=True`
- **Superusers** (`is_superuser=True`) have full access to everything including user management

To create a superuser:
```bash
python manage.py createsuperuser
```

---

## Sidebar Navigation

The sidebar is organized into three sections, configured in `backend/settings.py` under `UNFOLD["SIDEBAR"]`:

| Section | Item | URL |
|---|---|---|
| **Ingestion** | Event Sources | `/admin/ingestion/eventsource/` |
| | Raw Events | `/admin/ingestion/rawevent/` |
| | Staged Events | `/admin/ingestion/stagedevent/` |
| | Pipeline Docs | `/admin/ingestion/pipeline-docs/` |
| **Events** | Published Events | `/admin/events/event/` |
| | Tags | `/admin/events/tag/` |
| **Users** | Users | `/admin/auth/user/` |
| | User Profiles | `/admin/events/userprofile/` |

---

## Ingestion Section

These three models represent the three stages of the ingestion pipeline before an event goes live.

### Event Sources — `/admin/ingestion/eventsource/`

Manages the list of ICS calendar feeds the pipeline polls.

**Columns:** Name, Source Type, Active, Last Polled, # Events (raw event count)

**Fields on each source:**

| Field | Description |
|---|---|
| `name` | Human-readable label (e.g. "Northampton Arts Calendar") |
| `source_type` | `ics`, `scraper`, or `email` |
| `url` | The ICS feed URL to poll |
| `active` | If unchecked, the source is skipped during ingestion |
| `poll_interval_hours` | How often to re-poll (default: 24h) |
| `last_polled` | Read-only, updated automatically after each poll |
| `notes` | Free-text notes for internal use |

**Bulk action:**
- **"Run ingestion pipeline (poll → standardize → dedup)"** — triggers the full pipeline (`ingest_events` management command) across all active sources. Shows a confirmation banner when done.

> To add a new ICS calendar source, create a new Event Source record with its feed URL and set `active=True`.

---

### Raw Events — `/admin/ingestion/rawevent/`

Read-only view of events as they were parsed directly from ICS feeds — no cleaning or LLM processing applied yet.

**Columns:** Title, Source, Start Date, Processed, Created At

**Filters:** Processed (yes/no), Source

**Fields:**

| Field | Description |
|---|---|
| `raw_title` | Title exactly as it appeared in the ICS feed |
| `raw_description` | Description exactly as scraped |
| `raw_location` | Location string from the ICS feed |
| `raw_start` / `raw_end` | Datetime parsed from DTSTART/DTEND |
| `source_url` | URL extracted from the event (for webpage scraping) |
| `source_uid` | Unique ID from the ICS UID field (or SHA256 hash) |
| `processed` | `True` once the Gemini standardization step has run |

Raw events are **never edited here** — they're a permanent record of what was scraped.

---

### Staged Events — `/admin/ingestion/stagedevent/`

The main review queue. These are events that have been cleaned by the LLM and are waiting for an admin to approve or reject them before going live.

**Columns:** Title, Location, Town, Date, Status, Price, Link, Tags, Source

**Filters:** Status (`pending`, `approved`, `rejected`, `duplicate`)

**Status values:**

| Status | Meaning |
|---|---|
| `pending` | Needs admin review |
| `approved` | Admin approved; event is (or will be) published |
| `rejected` | Admin rejected; will not be published |
| `duplicate` | Automatically flagged as a near-duplicate of another staged event |

**How to review events:**

1. Filter by `status = pending`
2. Review each row — check title, description, town, date, price, tags, and the link
3. To approve or reject:
   - **Option A — Inline:** Click the Status dropdown directly in the list row and save
   - **Option B — Bulk action:** Check multiple rows → choose "Approve selected events" or "Reject selected events" → click Go

**What "Approve" does:**
- Creates a new `Event` record in the published events table
- Creates any missing `Tag` objects and attaches them
- Sets `staged.published_event` FK to the new event
- Sets `staged.status = 'approved'`

**What "Reject" does:**
- Sets `staged.status = 'rejected'`
- The staged event stays in the database but is never published

**Fields (read-only on detail page):**

| Field | Description |
|---|---|
| `raw_event` | Link back to the original scraped data |
| `title` | LLM-standardized title |
| `description` | LLM-written 2–3 sentence description |
| `location_name` | Venue or address |
| `town` | Town inferred by LLM |
| `start_datetime` / `end_datetime` | Parsed event times |
| `tags` | JSON list of tag strings |
| `price` | Decimal price (`0` = free, `-1` = N/A, `null` = unknown) |
| `link` | URL to the event's website |
| `duplicate_of` | FK to the earlier staged event it duplicates |
| `reviewer_notes` | Free text for admin comments |

---

## Events Section

### Published Events — `/admin/events/event/`

All events currently live on the website.

**Columns:** Title, Town, Venue, Date

**Filters:** Town

**Fields:**

| Field | Description |
|---|---|
| `title` | Event name |
| `town` | Town/city |
| `date` | Event datetime |
| `venue` | Venue name |
| `description` | Full description |
| `price` | Decimal; `null` = unknown, `0` = free |
| `photo` | Optional image upload |
| `tags` | Many-to-many relationship with Tag |
| `link` | URL to event page |

Events can be created, edited, or deleted directly here. Changes take effect immediately on the website.

### Tags — `/admin/events/tag/`

Simple lookup table of tag strings (e.g. `free`, `live-music`, `family-friendly`). Tags are shared across events and user profiles.

To add a new valid tag: create it here, then reference it in the LLM prompt's allowed tag list in `ingestion/standardizer.py`.

---

## Users Section

### Users — `/admin/auth/user/`

Standard Django user management. Use this to:
- Create new admin/staff accounts
- Reset passwords
- Grant/revoke `is_staff` or `is_superuser` flags

### User Profiles — `/admin/events/userprofile/`

Extended profile data attached to each Django user.

**Fields:**

| Field | Description |
|---|---|
| `user` | FK to Django's built-in User |
| `user_type` | `LOCAL`, `BUSINESS`, or `VENUE` |
| `primary_city` | User's home city |
| `email_preference` | `WEEKLY`, `MONTHLY`, or `NEVER` |
| `tags` | Interest tags for the user |

---

## API Endpoints (not in admin UI)

Two backend endpoints exist outside the admin but are relevant to admin operations:

### `GET /api/cron/ingest`
Triggers the full ingestion pipeline. Called automatically by Vercel's cron at 8 AM UTC daily.
- **Auth:** `Authorization: Bearer <CRON_SECRET>`

### `POST /api/events/publish-approved`
Publishes all staged events with `status='approved'` that haven't been published yet, then deletes them from the staged table. Runs atomically — if anything fails, nothing is committed.
- **Auth:** `Authorization: Bearer <THE_COMMONS_API_KEY>`

---

## Configuration

Admin appearance and sidebar are configured in `backend/settings.py` under the `UNFOLD` dict:

| Key | What it controls |
|---|---|
| `SITE_TITLE` | Browser tab title |
| `SITE_HEADER` | Top bar text |
| `SITE_URL` | Where the header logo links |
| `SHOW_HEADER_SEARCH` | Global search bar visibility |
| `SIDEBAR.navigation` | Sidebar sections and links |
| `COLORS.primary` | Brand color (Tailwind scale, currently default) |

Template directory for custom admin pages: `backendServer/ingestion/templates/ingestion/`

---

## Key Files

```
backendServer/
├── ingestion/
│   ├── admin.py              # EventSource, RawEvent, StagedEvent admin config
│   ├── views.py              # pipeline_docs view + cron/publish endpoints
│   └── templates/ingestion/
│       └── pipeline_docs.html  # Pipeline Docs admin page
├── events/
│   └── admin.py              # Event, Tag, UserProfile admin config
└── backend/
    ├── settings.py           # UNFOLD config, sidebar nav, env vars
    └── urls.py               # URL routing (pipeline-docs must come before admin/)
```
