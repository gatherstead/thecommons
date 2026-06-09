# The Commons — Broadcast (Event Syndication) — Design Doc

> **Audience:** an implementing agent (Claude Code, "fable") building this in one shot inside the existing `thecommons` monorepo.
> **Status:** proposed. **Owner:** Arya. **Canonical repo docs:** `AGENTS.md`, `ARCHITECTURE.md`, `CODING_STYLE.md`, `DEPLOY.md` — this feature follows all of them. If anything here contradicts those, trust them and flag the drift.

---

## 0. TL;DR for the implementer

Build a new feature that lets a paying client fill out **one** event form on a subdomain and have that event **automatically submitted to many local calendar websites** via headless-browser form-filling (Playwright + Chromium). Access is gated by a **secret code stored in env**. Each destination site gets a **hand-written adapter**. A **tag-based routing layer** decides which sites an event is eligible for (no Pittsboro events on a Durham calendar; no non-art events on an arts calendar). A **dev-time scaffolding agent** speeds up writing new adapters. **No LLM is used at runtime** — every field posted to an external site comes from the form or from static per-site config. Nothing is generated/guessed.

Two new pieces, both **isolated from the existing Commons code** (see §2.1):
- **Backend:** new, self-contained Django app `broadcast/` (intake API + Playwright runner + adapters + worker + dev tooling). No imports to/from `events` or `ingestion`.
- **Frontend:** a **standalone single-page app** (`broadcastWeb/`, its own Vite + React + TS project), built to static files and served directly by nginx on `broadcast.thecommons.town`. It is **not** part of `theCommonsWeb` and shares no code with it — it only copies the design tokens.

---

## 1. Goals & non-goals

### Goals
1. A single, simple, **public form** (one event in → many calendars out).
2. **Access-code gate** — only clients we've given a code to can submit. Code lives in env, validated server-side, never shipped to the browser.
3. **Automated submission** to a predetermined list of sites via Playwright, one site at a time, each with its own adapter/script.
4. **Tag-based routing** so events only go where they belong (location + category eligibility).
5. **No hallucinated data** — adapters may only use (a) fields the user submitted, or (b) deterministic static config defined in the adapter. Never invented per-event content. **No runtime LLM calls.**
6. A **dev tool / agent** to scaffold a new site adapter quickly.
7. Per-site **status + evidence** (success/fail/needs-manual, screenshot, external URL) so the operator can verify.

### Non-goals (v1)
- Solving CAPTCHAs or defeating bot detection. **We never bypass CAPTCHA or bot-checks** — if a site presents one, the adapter halts that target and flags it `needs_manual`. (This is both a hard rule and good engineering.)
- Recurring-event expansion (single occurrence per submission in v1).
- The long-term "calendars subscribe to us" model — out of scope here; this is the interim push model.
- User accounts. The access code is the only identity.

---

## 2. How it fits the existing system

The Broadcast feature lives **alongside** The Commons in the monorepo but is deliberately **decoupled** — it can be built, deployed, broken, or deleted without touching the Commons app.

```
thecommons/
├── backendServer/
│   ├── broadcast/            # NEW — self-contained Django app (API, runner, adapters, worker, dev tools)
│   ├── events/               # UNCHANGED — broadcast never imports from here
│   └── ingestion/            # UNCHANGED — broadcast never imports from here
├── theCommonsWeb/            # UNCHANGED — the Commons frontend; do NOT add broadcast code here
└── broadcastWeb/             # NEW — standalone Vite + React + TS SPA (its own package.json/lockfile)
    ├── index.html
    ├── package.json
    ├── vite.config.ts
    └── src/
        ├── main.tsx
        ├── App.tsx
        ├── styles/tokens.css     # COPIED design tokens (NOT imported from the Commons)
        ├── components/
        ├── services/broadcastApi.ts
        └── models/
```

- Backend: Python 3.13, Django 6 + DRF, `uv`. The `broadcast` app registers in `INSTALLED_APPS` and mounts under its own URL namespace, but is otherwise self-contained.
- Frontend: a **separate** Vite + React 19 + TypeScript SPA. Not Next.js, not part of `theCommonsWeb`. The newspaper look comes from a small **copied** `tokens.css` (the `--color-*` vars + Georgia). **No new fonts, no gradients, no pill buttons, no shadows.**
- DB: Neon Postgres, `public` schema, normal Django migrations. Broadcast tables stand alone — **no FKs into `events`, `ingestion`, or `neon_auth`.** **Do not touch `neon_auth`.**
- Broadcast does **not** use Better Auth and has no logged-in users — the access code is the only gate. Don't wire it into the Commons auth flow.

### 2.1 Isolation contract (what "modular" means here)

Treat Broadcast as a tenant that happens to share a VM and a database server. The rules:

**Frontend (hard separation):**
- `broadcastWeb/` is its **own project** with its own `package.json` and lockfile. It is **not** a workspace package of `theCommonsWeb` and imports nothing from it.
- Design tokens are **copied** into `broadcastWeb/src/styles/tokens.css`, not imported. (Small, intentional duplication — the price of decoupling. If the palette changes, copy the new values over; the two apps aren't meant to stay byte-identical.)
- It builds to **static files** (`vite build` → `dist/`) and is served directly by nginx — **no Node process in production** (one fewer service, less RAM on the 6 GB VM, nothing that can take the Commons down).
- It talks to the backend only over HTTP. No shared client code.

**Backend (self-contained app):**
- `broadcast/` **must not import from `events` or `ingestion`**, and they must not import from it. Enforce with a small test that asserts no such imports exist.
- Own env prefix (`BROADCAST_*`), own URL namespace (`/broadcast/...`), own DB tables with no cross-app FKs.
- The Playwright **worker is its own `systemd` service** regardless of everything else.
- It rides the existing Django project/gunicorn for convenience, but because it shares nothing it's **extraction-ready**: to make it fully separate later, move `broadcast/` into its own Django/ASGI service (optionally on `broadcast-api.thecommons.town`) with no changes to the Commons. The frontend wouldn't notice — just repoint `VITE_BROADCAST_API_BASE_URL`.

> **Why a standalone SPA instead of a route in `theCommonsWeb`:** it's "just a gated form," so it needs no SSR/SEO and gains nothing from Next.js. A static SPA is the most modular option, the lightest on the VM (Chromium already eats the RAM budget), and structurally incapable of breaking the Commons. If you'd rather keep stack-consistency with the rest of the repo, the fallback is a **separate Next.js app** in `broadcastWeb/` on its own port + `systemd` service — still fully isolated, just heavier. Default to the static SPA.

---

## 3. Architecture overview

```
                    broadcast.thecommons.town  (Next.js /broadcast)
                                   │
                 1. POST /broadcast/preview   (code + event draft)
                                   │  ← returns eligible[] + excluded[{site,reason}]
                                   ▼
        ┌──────────────────────────────────────────────────────┐
        │  Django  (api.thecommons.town)  —  broadcast app       │
        │                                                        │
        │  views.py: validate access code (const-time, rate-ltd) │
        │            routing.py: tag eligibility                 │
        │                                                        │
        │  2. POST /broadcast/submit (code + event + site_keys)  │
        │     → create BroadcastSubmission + BroadcastTarget rows │
        │     → mark queued                                      │
        └───────────────┬────────────────────────────────────────┘
                        │ (DB-backed queue; no Redis required)
                        ▼
        ┌──────────────────────────────────────────────────────┐
        │  broadcast-worker  (systemd, separate process)         │
        │  worker.py loop: claim queued submission               │
        │    SELECT ... FOR UPDATE SKIP LOCKED                    │
        │  runner.py: launch Playwright (sync API) Chromium      │
        │    for each target (sequential):                       │
        │      adapter.fill_and_submit(page, event, ctx)         │
        │      capture screenshot + result + external_url        │
        │      update BroadcastTarget status                     │
        └──────────────────────────────────────────────────────┘
                        │
   3. GET /broadcast/jobs/{id}  ← frontend polls; shows per-site progress
```

**Why a separate worker process (not request-thread):** filling 10+ sites takes minutes and Chromium is memory-heavy. gunicorn workers must stay responsive. The worker is its own `systemd` service. We use a **DB-backed queue** (a status column + `FOR UPDATE SKIP LOCKED`) to avoid adding Redis/Celery to the stack. Celery/`django-tasks` can replace it later without changing the API surface.

**Why sync Playwright in the worker:** the worker is a plain process (no asyncio event loop, no async ORM friction). Use `playwright.sync_api`. Keep the Django ORM calls ordinary and synchronous.

**Concurrency:** v1 = **single worker, one submission at a time, targets sequential.** The VM is 1 OCPU / 6 GB RAM (see §11) — Chromium is the memory hog. Make max concurrency an env knob (`BROADCAST_MAX_CONCURRENCY`, default `1`).

---

## 4. Canonical event schema (the form is the source of truth)

The form must collect a **superset** of everything any adapter needs. If a site needs a field no adapter can fill from this schema, the adapter sets a static default it defines, or marks the target `needs_manual` with a reason — it never invents event content.

| Field | Type | Required | Notes |
|---|---|---|---|
| `access_code` | string | yes | gate; never stored in plaintext logs; not persisted on the row |
| `title` | string | yes | |
| `description` | text | yes | plain text; adapters truncate per-site if needed |
| `start_datetime` | ISO 8601 w/ tz | yes | America/New_York assumed if no tz |
| `end_datetime` | ISO 8601 w/ tz | no | |
| `all_day` | bool | no | default false |
| `venue_name` | string | yes | |
| `address_line1` | string | yes | |
| `city` | string | yes | |
| `state` | string | yes | default `NC` |
| `zip` | string | yes | |
| `locality` | enum | yes | **routing** — see §6 controlled list |
| `categories` | enum[] | yes (≥1) | **routing** — see §6 controlled list |
| `event_url` | url | no | source/details page (e.g. theplantnc.com/...) |
| `ticket_url` | url | no | |
| `price` | string | no | e.g. "Free", "$10", "$10–$20" |
| `is_free` | bool | no | derived helper for sites with a free toggle |
| `image_url` | url | no | adapters that need a file **download it to temp** then upload |
| `organizer_name` | string | no | |
| `contact_email` | email | no | |
| `contact_phone` | string | no | |

Represent this as a single `@dataclass CanonicalEvent` in `broadcast/schema.py` **and** a DRF `BroadcastSubmissionSerializer`. The dataclass is what adapters receive (decoupled from the ORM row).

---

## 5. Data model (`broadcast/models.py`)

`public` schema, normal migrations.

```python
class BroadcastSubmission(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    client_label = models.CharField(max_length=64)        # which access code was used (see §7)
    # --- canonical event fields (mirror §4, minus access_code) ---
    title = models.CharField(max_length=300)
    description = models.TextField()
    start_datetime = models.DateTimeField()
    end_datetime = models.DateTimeField(null=True, blank=True)
    all_day = models.BooleanField(default=False)
    venue_name = models.CharField(max_length=200)
    address_line1 = models.CharField(max_length=200)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=2, default="NC")
    zip = models.CharField(max_length=10)
    locality = models.CharField(max_length=40)            # controlled value, §6
    categories = models.JSONField(default=list)           # list[str], controlled, §6
    event_url = models.URLField(blank=True)
    ticket_url = models.URLField(blank=True)
    price = models.CharField(max_length=60, blank=True)
    is_free = models.BooleanField(default=False)
    image_url = models.URLField(blank=True)
    organizer_name = models.CharField(max_length=200, blank=True)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=40, blank=True)
    status = models.CharField(max_length=20, default="queued")  # queued|running|done|failed
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

class BroadcastTarget(models.Model):
    STATUS = ["pending", "in_progress", "succeeded", "failed", "needs_manual", "skipped"]
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    submission = models.ForeignKey(BroadcastSubmission, related_name="targets", on_delete=models.CASCADE)
    site_key = models.CharField(max_length=64)            # matches an adapter in the registry
    status = models.CharField(max_length=20, default="pending")
    attempts = models.PositiveSmallIntegerField(default=0)
    external_url = models.URLField(blank=True)            # confirmation/listing URL if site returns one
    error = models.TextField(blank=True)
    screenshot_path = models.CharField(max_length=300, blank=True)
    dry_run = models.BooleanField(default=False)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["submission", "site_key"], name="uniq_submission_site")]
```

**Idempotency:** the unique `(submission, site_key)` constraint + `attempts` lets retries be safe; never create a second target for the same pair.

Site metadata (URL, accepted localities/categories, tier, auth) lives **in code** in the adapter registry (§8), not the DB — adapters and their rules version together. The DB only holds per-run target rows.

Register both models in `broadcast/admin.py` with django-unfold so the operator can inspect runs, read errors, and view screenshots.

---

## 6. Tag taxonomy & routing (`broadcast/routing.py`)

This is the "no arts events in a music calendar, no Pittsboro events in Durham" logic. **Deterministic, no LLM.**

### Controlled `locality` values (single choice on the form)
`pittsboro`, `chatham` (rest of Chatham County), `chapel-hill`, `carrboro`, `durham`, `raleigh`, `cary`, `wake` (rest of Wake), `triangle` (region-wide / spans multiple).

### Controlled `categories` values (multi-select on the form)
`music`, `arts`, `family-kids`, `wellness`, `food-drink`, `festival`, `market`, `literary`, `community`, `nightlife`, `education`.

### Eligibility rule (per adapter)
```python
@dataclass(frozen=True)
class Eligibility:
    localities: frozenset[str]   # event.locality must be in here (empty = accept any)
    categories: frozenset[str]   # event must have ≥1 category in here (empty = accept any)

    def matches(self, ev: CanonicalEvent) -> tuple[bool, str]:
        if self.localities and ev.locality not in self.localities:
            return False, f"locality '{ev.locality}' not covered"
        if self.categories and not (set(ev.categories) & self.categories):
            return False, f"none of {ev.categories} in accepted categories"
        return True, ""
```

`routing.eligible_targets(ev, enabled_adapters)` returns `(eligible: list[Adapter], excluded: list[(site_key, reason)])`. Region-wide sites simply list all Triangle localities. **The operator can deselect any eligible site before submitting** (see §9 flow), so routing is a safe default, not a hard gate.

### Site rules table (seed these into the adapters)

Localities use these region groups for brevity:
`TRIANGLE = {pittsboro, chatham, chapel-hill, carrboro, durham, raleigh, cary, wake, triangle}`.

| site_key | accepted localities | accepted categories | tier | auth | submission URL |
|---|---|---|---|---|---|
| `triangle_on_the_cheap` | TRIANGLE | any | 1 | no | https://triangleonthecheap.com/submit-an-event/ |
| `triangle_weekender` | TRIANGLE | any | 1 | no | https://thetriangleweekender.com/events/community/add/ |
| `indy_week` | TRIANGLE | any | 1 | maybe | https://indyweek.com/calendar/#/ |
| `abc11_community` | TRIANGLE | any | 1 | no | https://abc11.com/community/calendar/ |
| `visit_raleigh` | {raleigh, wake, cary} | any | 1 | no | https://www.visitraleigh.com/events/submit-an-event/ |
| `fun4raleighkids` | {raleigh, wake, cary, triangle} | **{family-kids}** | 1 | no | https://fun4raleighkids.com/calendar/ |
| `chapelboro` | {chapel-hill, carrboro} | any | 1 | no | https://chapelboro.com/calendar/add |
| `explore_pittsboro` | {pittsboro, chatham} | any | 1 | no | https://www.explorepittsboro.com/events |
| `chatham_chamber` | {pittsboro, chatham} | any | 1 | maybe (member) | https://business.ccucc.net/ap/Event/Submit/yr4lawrl |
| `shop_pittsboro` | {pittsboro} | any | 1 | maybe (member) | https://shoppittsboro.com/member-events/#!event/new |
| `chatham_arts` | {pittsboro, chatham} | **{arts, literary}** | 1 | no | https://www.chathamartscouncil.org/calendar/ |
| `eventbrite` | TRIANGLE | any | 2 | yes | (account) |
| `yelp_events` | TRIANGLE | any | 2 | yes | https://www.yelp.com/events |
| `meetup` | TRIANGLE | any | 2 | yes | (account/group) |
| `nextdoor` | TRIANGLE | any | 2 | yes | https://nextdoor.com/login/ |
| `wral_oot` | TRIANGLE | any | 2 | maybe | https://www.wral.com/entertainment/out-and-about/ |
| `fox8_cityspark` | TRIANGLE | any | 2 | yes | https://login.cityspark.com/login |
| `allevents_raleigh` | {raleigh, triangle} | any | 2 | yes (organizer) | https://allevents.in/raleigh |
| `discover_durham` | {durham} | any | backlog | — | (no submit URL yet) |
| `downtown_durham` | {durham} | any | backlog | — | (no submit URL yet) |
| `third_friday_durham` | {durham} | **{arts}** | backlog | — | (no submit URL yet) |
| `raltoday` | TRIANGLE | any | backlog | — | (no submit URL yet) |
| `raleighnc_gov` | {raleigh} | any | backlog | — | (no submit URL yet) |
| `spectrum_news` | TRIANGLE | any | backlog | — | (no submit URL yet) |
| `this_is_raleigh` | {raleigh} | any | backlog | — | (no submit URL yet) |
| `dra_downtown_raleigh` | {raleigh} | any | backlog | — | (no submit URL yet) |

> Decision: `chatham_arts` accepts only `{arts, literary}` to honor "don't submit a non-art event to an arts calendar." Live music at The Plant is **not** auto-routed there. Operator can override per submission. Tune the table as real-world behavior is learned.

**Implementation phasing:** build the framework + **all Tier 1** adapters first (these are the Pittsboro/Chatham-relevant ones for the first client). Tier 2 (auth/credentials) and backlog (need submission-URL research) come later. Ship Tier 1 end-to-end before touching Tier 2.

---

## 7. Access-code gate (`broadcast/access.py`)

- Codes live in env: `BROADCAST_ACCESS_CODES="makrs:CODE1,theplant:CODE2"` — a comma list of `label:code` pairs so each client gets a distinct, individually-revocable code and we can stamp `client_label` on every submission.
- Parse once at startup into a dict. Validate with a **constant-time compare** (`hmac.compare_digest`) against each code; return the matching label or reject.
- **Rate-limit** the preview/submit endpoints per IP (e.g. simple DB or cache counter) to blunt brute-forcing the code space. Reject early on a missing/blank code.
- **Never** log the code value; never return it; never persist it on the row (only the resolved `client_label`).
- The code is validated **server-side only** and is never present in any client bundle or `NEXT_PUBLIC_*` var.

---

## 8. Adapters (`broadcast/adapters/`)

One module per site. The registry maps `site_key → adapter instance`.

### Base contract (`adapters/base.py`)
```python
from dataclasses import dataclass
from playwright.sync_api import Page

@dataclass
class RunContext:
    dry_run: bool
    screenshot_dir: str
    download_dir: str          # temp dir for image downloads
    timeout_ms: int = 30_000

@dataclass
class TargetResult:
    status: str                # "succeeded" | "failed" | "needs_manual" | "skipped"
    external_url: str = ""
    error: str = ""
    screenshot_path: str = ""

class SiteAdapter:
    key: str
    name: str
    submission_url: str
    requires_auth: bool = False
    eligibility: "Eligibility"

    def fill_and_submit(self, page: Page, ev: "CanonicalEvent", ctx: RunContext) -> TargetResult:
        raise NotImplementedError
```

### Rules every adapter must follow
1. **Only** use `ev` fields or **static constants defined in this adapter**. No generated text. (e.g. mapping our `wellness` tag → a site's "Other" dropdown option is a hardcoded dict — deterministic, fine.)
2. If the site requires a field we can't supply → return `needs_manual` with a clear `error`. **Do not invent it.**
3. If a **CAPTCHA / bot-check / login wall** appears → return `needs_manual`. **Never attempt to bypass it.**
4. Respect `ctx.dry_run`: fill the form but **do not click final submit**; capture a screenshot and return `succeeded` with a `[DRY RUN]` note.
5. Always capture a screenshot just before (and, on success, after) submit → `ctx.screenshot_dir/{submission_id}/{site_key}.png`.
6. Be resilient to slow loads: use Playwright auto-waiting / `expect`, explicit `wait_for`, and `ctx.timeout_ms`. Prefer label/role-based locators (`get_by_label`, `get_by_role`) over brittle CSS where possible.
7. Pace interactions like a human where the site is sensitive (small delays, real typing) — but **no CAPTCHA defeat, no fingerprint spoofing arms race.** If a site can't be done politely, it's `needs_manual`.

### Example adapter (`adapters/triangle_on_the_cheap.py`) — illustrative
```python
class TriangleOnTheCheapAdapter(SiteAdapter):
    key = "triangle_on_the_cheap"
    name = "Triangle on the Cheap"
    submission_url = "https://triangleonthecheap.com/submit-an-event/"
    requires_auth = False
    eligibility = Eligibility(localities=TRIANGLE, categories=frozenset())

    def fill_and_submit(self, page, ev, ctx):
        page.goto(self.submission_url, timeout=ctx.timeout_ms)
        # cookie/consent: choose most privacy-preserving option if present
        _dismiss_consent(page)

        page.get_by_label("Event Title").fill(ev.title)
        page.get_by_label("Description").fill(ev.description)
        page.get_by_label("Start Date").fill(ev.start_datetime.strftime("%m/%d/%Y"))
        page.get_by_label("Start Time").fill(ev.start_datetime.strftime("%I:%M %p"))
        if ev.end_datetime:
            page.get_by_label("End Date").fill(ev.end_datetime.strftime("%m/%d/%Y"))
        page.get_by_label("Venue Name").fill(ev.venue_name)
        page.get_by_label("Address").fill(f"{ev.address_line1}, {ev.city}, {ev.state} {ev.zip}")
        if ev.event_url:
            page.get_by_label("Event Website").fill(ev.event_url)
        if ev.image_url:
            local = _download(ev.image_url, ctx.download_dir)         # download → temp
            page.get_by_label("Event Image").set_input_files(local)   # upload the real file
        # static category mapping — deterministic, not generated:
        _select_categories(page, [_CAT_MAP[c] for c in ev.categories if c in _CAT_MAP])

        if _has_captcha(page):
            return TargetResult(status="needs_manual", error="captcha present",
                                screenshot_path=_shot(page, ctx, self.key))

        shot = _shot(page, ctx, self.key)
        if ctx.dry_run:
            return TargetResult(status="succeeded", error="[DRY RUN] not submitted", screenshot_path=shot)

        page.get_by_role("button", name="Submit Event").click()
        page.wait_for_load_state("networkidle", timeout=ctx.timeout_ms)
        return TargetResult(status="succeeded",
                            external_url=page.url,
                            screenshot_path=_shot(page, ctx, self.key))

_CAT_MAP = {"music": "Music", "arts": "Arts & Culture", "family-kids": "Family",
            "food-drink": "Food & Drink", "festival": "Festivals", "market": "Markets",
            "literary": "Arts & Culture", "community": "Community", "nightlife": "Nightlife",
            "wellness": "Health & Wellness", "education": "Classes & Workshops"}
```
> Selectors above are placeholders — the scaffolding tool (§10) captures the real ones. Shared helpers (`_dismiss_consent`, `_download`, `_shot`, `_has_captcha`, `_select_categories`) live in `adapters/_helpers.py`.

### Tier 2 (auth) adapters — credential handling
- Credentials per site in env (e.g. `EVENTBRITE_EMAIL` / `EVENTBRITE_PASSWORD`), **never** in the repo, **never** in `NEXT_PUBLIC_*`.
- Reuse sessions via Playwright **storage state** (`context.storage_state(path=...)`) so we log in once and refresh only when expired.
- ⚠️ **ToS check required before enabling any Tier 2 site** (see §13). Several explicitly prohibit automation.

---

## 9. API (Django, `broadcast/views.py` + `urls.py`)

Mounted under `api.thecommons.town`. All accept JSON, all validate the access code.

| Method | Path | Body | Returns |
|---|---|---|---|
| POST | `/broadcast/preview` | `{access_code, event}` | `{eligible:[{site_key,name}], excluded:[{site_key,reason}]}` — no DB write |
| POST | `/broadcast/submit` | `{access_code, event, site_keys[], dry_run?}` | `{job_id}` — creates submission + targets, sets `queued` |
| GET | `/broadcast/jobs/{id}` | — | submission status + `targets:[{site_key,name,status,error,external_url,screenshot_url}]` |
| POST | `/broadcast/jobs/{id}/retry` | `{access_code, site_keys[]}` | resets those targets to `pending`, re-queues |

- Use `BearerTokenAuthentication` is **not** appropriate here (no users). Use a tiny custom permission that checks the access code in the body/header, plus per-IP rate limiting. Keep views thin; eligibility logic in `routing.py`, persistence in a small `services.py`.
- `screenshot_url` is served read-only behind the API (operator-only path or signed URL); screenshots can contain the submitted event, nothing sensitive, but don't expose the whole directory publicly.
- CORS/CSRF: add `https://broadcast.thecommons.town` to `CORS_EXTRA_ORIGINS` and `CSRF_TRUSTED_ORIGINS`. The form is JSON POST with the access code, so it's CORS not CSRF-cookie; configure DRF accordingly.

### Frontend (standalone SPA in `broadcastWeb/`)
A single React page, client-only. Flow:
1. User enters access code + fills the event form.
2. "Preview" → `POST /broadcast/preview` → render **eligible sites (checked)** and **excluded sites (greyed, with reason)**. User can uncheck eligible sites.
3. "Broadcast" → `POST /broadcast/submit` with the selected `site_keys` (+ optional dry-run).
4. Poll `GET /broadcast/jobs/{id}` every ~3s → live per-site progress list (pending → in progress → ✓ / ✗ / needs-manual), with screenshot links.

- **"Dry run" toggle** so the operator can test without actually posting.
- **Styling:** newspaper aesthetic from the **copied** `tokens.css` (`var(--color-*)`, Georgia). Masthead header ("THE COMMONS · BROADCAST"), column rules between form sections, dark-red (`--color-accent`) only for the active/submit state. No cards/shadows/pills/new fonts.
- **API layer** in `src/services/broadcastApi.ts`; types in `src/models/`. No raw `fetch` in components. Base URL from `import.meta.env.VITE_BROADCAST_API_BASE_URL`.
- **No router needed** (one page), **no global auth/session** — the access code is a controlled input, sent per request, never stored.
- **Serving:** `vite build` → `dist/`; nginx serves the static `dist/` for `broadcast.thecommons.town` (§11). No Node runtime in prod.

---

## 10. Dev tool: the adapter-scaffolding agent

Goal: "easily generate a new script for a new website." Two-step, dev-time only (LLM allowed here — this is **not** the runtime path).

### Step A — capture (deterministic, `manage.py scaffold_adapter`)
```
uv run python manage.py scaffold_adapter --url <submission_url> --key <site_key> [--headed]
```
Launches Playwright, navigates to the URL, and writes to `broadcast/adapters/_scaffold/<site_key>/`:
- `schema.json` — every form control found: tag, `name`/`id`, `type`, associated label (via `for`/`aria-label`/`placeholder`), `required`, and `<select>` options, plus a best-guess stable locator for each.
- `page.png` — full-page screenshot.
- `adapter.py.draft` — a starter adapter from a Jinja-ish template with the registry boilerplate, eligibility stub, and one TODO-stubbed `fill_and_submit` line per detected field.

### Step B — generate (the "agent")
A Claude Code **skill** (`broadcast/adapters/_scaffold/SKILL.md` + prompt) that takes `schema.json` + `page.png` + the canonical schema (§4) and the category-mapping conventions (§6), and writes the real `fill_and_submit` — mapping canonical fields to detected controls and producing the static `_CAT_MAP` / locality handling for that site. The dev then runs a **dry run** (§9 toggle / command below) to verify before enabling. Deliver this as a documented skill so the workflow is repeatable.

### Dry-run command (verify any adapter without posting)
```
uv run python manage.py broadcast_dry_run --site <site_key> --fixture sample_pittsboro_music.json
```
Runs that one adapter in `dry_run=True` against a fixture and saves a screenshot. Also ship a tiny **local mock submission form** (`adapters/_mock.py` + a static HTML form served by a test view) so adapter integration tests run end-to-end in CI without hitting real sites.

---

## 11. Deployment (extends `DEPLOY.md`)

### Playwright on the Oracle **ARM64** VM — important
- VM is Ubuntu 24.04, **aarch64**. Playwright supports Ubuntu 24.04 arm64, **but on arm64 Linux it uses the bundled Chromium** — the branded-Chrome path (`playwright install chrome` / `channel="chrome"`) is **not supported** on arm64. **Pin to bundled Chromium and never set a Chrome channel.**
```bash
cd backendServer
uv add playwright
uv run playwright install chromium          # bundled Chromium ONLY — not "chrome"
uv run playwright install-deps chromium     # system libs
```
- Memory: 6 GB total. Run Chromium **headless, sequential** (`BROADCAST_MAX_CONCURRENCY=1`). Launch with conservative args (`--disable-dev-shm-usage`, a small `--js-flags` heap if needed). If memory becomes a problem, move the worker to a separate small box; the API/DB don't care where the worker runs.

### New systemd service: `broadcast-worker`
Runs `uv run python manage.py run_broadcast_worker`. Mirrors the gunicorn/nextjs service pattern. Restart-on-failure. Owns its own `RuntimeDirectory` for the screenshot/download temp dirs, or point them at a writable path under `/home/ubuntu`.

### nginx + DNS + TLS
- **Cloudflare DNS:** add `broadcast` record (proxied / orange cloud), like the others.
- **nginx:** new server block `broadcast.thecommons.town` that serves the **static SPA** directly — `root /home/ubuntu/thecommons/broadcastWeb/dist;` with `try_files $uri /index.html;`. **No proxy to a Node process** (the SPA is static). The form POSTs to `api.thecommons.town` (existing Django server block) — add the broadcast routes there; they're just more Django URLs, no new server block needed for the API. (If you take the Next.js fallback instead of the static SPA, this block proxies to its own port, e.g. `http://localhost:3001`, and you add a `broadcast-web` systemd service.)
- **TLS:** the Cloudflare origin cert must cover `broadcast.thecommons.town` — use a **wildcard** origin cert (`*.thecommons.town`) or add the SAN. Verify before enabling the subdomain.
- **Firewall:** no change — same 80/443 already open (mind the iptables REJECT-before-ACCEPT gotcha from `DEPLOY.md`).

### Deploy commands (additions)
```bash
# backend (Commons API + broadcast app share this project)
cd /home/ubuntu/thecommons && git pull
cd backendServer
uv sync
uv run playwright install chromium            # first deploy / version bumps (bundled Chromium only)
uv run python manage.py migrate               # broadcast app migrations
sudo systemctl restart gunicorn
sudo systemctl restart broadcast-worker       # NEW — the Playwright worker

# broadcast frontend (separate static SPA — independent of theCommonsWeb)
cd ../broadcastWeb
pnpm install            # its own lockfile
pnpm run build          # → broadcastWeb/dist/, served straight by nginx; no service to restart

# the Commons frontend (theCommonsWeb) is built/deployed exactly as before — untouched
```

---

## 12. Environment variables

### `backendServer/.env` (add)
```
BROADCAST_ACCESS_CODES=            # "makrs:XXXX,theplant:YYYY"  (label:code, comma-sep)
BROADCAST_HEADLESS=true
BROADCAST_DRY_RUN_DEFAULT=false
BROADCAST_MAX_CONCURRENCY=1
BROADCAST_SCREENSHOT_DIR=/home/ubuntu/broadcast/screenshots
BROADCAST_DOWNLOAD_DIR=/home/ubuntu/broadcast/downloads
BROADCAST_TIMEOUT_MS=30000
# Tier-2 site credentials (only when those adapters are enabled) — NEVER commit
# EVENTBRITE_EMAIL=   EVENTBRITE_PASSWORD=   ...
```
Also add `https://broadcast.thecommons.town` to `CORS_EXTRA_ORIGINS` and `CSRF_TRUSTED_ORIGINS`. **Update `.env.example`.**

### `broadcastWeb/.env` (its own env — NOT in theCommonsWeb)
```
VITE_BROADCAST_API_BASE_URL=   # https://api.thecommons.town  (or a future broadcast-api host)
```
> `theCommonsWeb` gets **no** new env vars — it's untouched. The access code is never an env var anywhere; it's typed into the form at runtime and sent per request.

---

## 13. Security, privacy & ToS (read before enabling sites)

- **Access code:** constant-time compare, rate-limited, never logged/persisted/shipped to client.
- **No CAPTCHA / bot-check bypass.** Ever. Sites that gate on it become `needs_manual`.
- **Credentials** (Tier 2) in env/secrets only; reuse Playwright storage-state; rotate on the client's instruction.
- **Privacy:** screenshots may show the submitted event only. Keep the screenshot directory non-public; serve via an operator-gated path. Don't put any secret in URLs.
- **Terms of Service / ethics — flag explicitly to the operator:** automating submissions to third-party sites can violate their ToS. Community-calendar submission forms (the Tier 1 set: Triangle on the Cheap, Triangle Weekender, Explore Pittsboro, Chapelboro, Chatham Chamber/Arts, Shop Pittsboro, Visit Raleigh, Fun 4 Raleigh Kids) are *designed* for public event submission and are the right first targets. Several **Tier 2** platforms (Eventbrite, Yelp, Meetup, Nextdoor) likely **prohibit automation** — before enabling those, check each site's ToS and prefer an official API/partner channel or assisted-manual flow. This aligns with the long-term "calendars subscribe to us" vision (Sam/Arya thread): push only where pushing is welcome.
- **Politeness:** one submission at a time, human-paced; honor any `robots`/rate signals; back off on errors. We are a good-faith community tool, not a scraper farm.

---

## 14. Testing

- **Unit:** `routing.eligible_targets` against a fixture matrix (Pittsboro music → Explore Pittsboro/Chatham Chamber/Shop Pittsboro/Triangle-wide ✓, Chatham Arts ✗, Durham/Raleigh sites ✗; book festival → Chatham Arts ✓; yoga → not arts, not kids).
- **Adapter integration:** run each adapter `dry_run=True` against the **local mock form** in CI (no real sites). Real-site dry runs are a manual pre-enable gate.
- **Access code:** valid code → label resolved; wrong/blank → 403; rate limit trips.
- **API:** preview returns correct eligible/excluded; submit creates exactly one target per selected site (unique constraint holds on retry).
- Backend: `uv run python manage.py test broadcast`. Frontend: `pnpm run build` (type-check).

### Seed fixtures (from the sample-event sheet)
- `pittsboro_music`: "International Dance Night @ The Plant" — locality `pittsboro`, categories `[music, community, nightlife]`.
- `pittsboro_literary`: "Plants Read Too Outdoor Book Festival" — `pittsboro`, `[literary, festival, market]` → should reach Chatham Arts.
- `pittsboro_wellness`: "Restorative Yoga @ Pittsboro Yoga" — `pittsboro`, `[wellness]` → must **not** reach arts/kids calendars.
- `pittsboro_festival`: "Eyes Wide Open Juneteenth Festival" — `pittsboro`, `[festival, community, arts]`.

---

## 15. Build order (so it lands in roughly one pass)

1. `broadcast` app skeleton: `schema.py` (CanonicalEvent), `models.py` (+ migration), `serializers.py`, `admin.py`.
2. `routing.py` (taxonomy + Eligibility + `eligible_targets`) + unit tests.
3. `adapters/base.py`, `adapters/_helpers.py`, `adapters/__init__.py` (registry), `adapters/_mock.py` + mock-form test view.
4. `runner.py` (sync Playwright, one submission → its targets) + `worker.py` (claim loop) + `run_broadcast_worker` command. Validate end-to-end against the mock form in dry run.
5. API: `views.py` (preview/submit/jobs/retry), `urls.py`, access-code permission + rate limit; mount in root `urls.py`; CORS/CSRF.
6. **All Tier 1 adapters** (table §6), each verified with `broadcast_dry_run` against the mock form, then a manual real-site dry run.
7. Frontend: scaffold `broadcastWeb/` (Vite + React + TS), copy `tokens.css`, build the single page (form → preview → submit → poll), `broadcastApi.ts` service + types, newspaper styling. Build to `dist/`.
8. Dev tooling: `scaffold_adapter` command + the scaffolding **skill** (§10).
9. Deploy: systemd `broadcast-worker`, `playwright install chromium`, nginx subdomain block, Cloudflare DNS, wildcard TLS, env vars, `.env.example`.
10. (Later) Tier 2 auth adapters after ToS review; backlog sites once submission URLs are found.

---

## 16. Open questions for Arya/Sam

1. Should each client's code map to a **restricted site set** (e.g. The Plant only broadcasts to Chatham-area calendars), or do all codes get the full eligible set? (Easy to add a `client_label → allowed_site_keys` map in env if yes.)
2. Image handling on sites that **require** an upload but the submission has no `image_url` — `needs_manual`, or a per-client default fallback image?
3. For sites where submissions are **moderated** (most community calendars hold for review), "succeeded" means *submitted*, not *live*. Is capturing the confirmation screen + any returned URL enough evidence, or do we need follow-up verification?
4. Tier 2: which platforms are actually worth the ToS/credential cost vs. leaving as assisted-manual?

---

## 17. Guardrails (carry into implementation)

- **Modularity:** `broadcastWeb/` is a standalone SPA sharing nothing with `theCommonsWeb` (tokens are copied). The `broadcast/` Django app imports nothing from `events`/`ingestion` and vice versa. Don't add broadcast code into the Commons frontend or couple the DB tables.
- **No runtime LLM.** Every external field comes from the form or static adapter config.
- **No invented event content.** Missing-required → `needs_manual`.
- **Never bypass CAPTCHA / bot-checks / login walls** → `needs_manual`.
- **Access code:** server-side only, constant-time, rate-limited, never logged or shipped to the client; never an env var (typed at runtime).
- **ARM64:** bundled Chromium only; never a Chrome channel.
- **Newspaper aesthetic** on the form (serif, cream/ink, rules; no gradients/shadows/pills).
- **Don't touch `neon_auth`**; normal migrations for `broadcast` only.
- **Tier 1 first**, fully working end-to-end, before Tier 2.
- **Idempotent targets** (unique `(submission, site_key)`); retries reuse rows.
- Keep each project's `.env.example` current; no secrets in the repo.

---

## Appendix A — Full calendar source list (for adapter work)

Every calendar from the combined MAKRS + Plant/Fair Game list, with the `site_key` and tier assigned in §6. Blank submission URL = needs research before an adapter can be written. **Tier 1** = public submission form (build first); **Tier 2** = requires an account/login (ToS review first, §13); **B** = backlog (no submission URL yet).

| # | site_key | Calendar / Org | Coverage | Main URL | Submission URL | Tier | Source | Notes |
|---|---|---|---|---|---|---|---|---|
| 1 | `triangle_on_the_cheap` | Triangle on the Cheap | Triangle-wide | triangleonthecheap.com | /submit-an-event/ | 1 | MAKRS; Fair Game | |
| 2 | `triangle_weekender` | The Triangle Weekender | Triangle-wide | thetriangleweekender.com | /events/community/add/ | 1 | MAKRS; Fair Game | |
| 3 | `visit_raleigh` | Visit Raleigh | Raleigh / Wake | visitraleigh.com | /events/submit-an-event/ | 1 | MAKRS | |
| 4 | `fun4raleighkids` | Fun 4 Raleigh Kids | Wake / families | fun4raleighkids.com | /calendar/ | 1 | MAKRS | family-kids only; also a Charlotte site |
| 5 | `chapelboro` | Chapelboro Calendar | Chapel Hill / Carrboro | chapelboro.com | /calendar/add | 1 | Fair Game | |
| 6 | `explore_pittsboro` | Explore Pittsboro | Pittsboro / Chatham | explorepittsboro.com | /events | 1 | Fair Game | |
| 7 | `chatham_chamber` | Chatham Chamber Events | Chatham County | business.ccucc.net | /ap/Event/Submit/yr4lawrl | 1 | Fair Game | may be member-gated |
| 8 | `shop_pittsboro` | Shop Pittsboro Events | Pittsboro | shoppittsboro.com | /member-events/#!event/new | 1 | Fair Game | member events |
| 9 | `chatham_arts` | Chatham Arts Council | Chatham County | chathamartscouncil.org | /calendar/ | 1 | Fair Game | arts/literary only |
| 10 | `indy_week` | INDY Week | Triangle | indyweek.com | /calendar/#/ | 1 | MAKRS | |
| 11 | `abc11_community` | ABC11 Community Calendar | Triangle | abc11.com/community/calendar/ | (same) | 1 | MAKRS | |
| 12 | `allevents_raleigh` | AllEvents.in Raleigh | Raleigh / Triangle | allevents.in/raleigh | (account) | 2 | MAKRS | needs Organizer page |
| 13 | `wral_oot` | WRAL Out & About | Triangle | wral.com/entertainment/out-and-about/ | (sign-in) | 2 | MAKRS | may require sign-in |
| 14 | `eventbrite` | Eventbrite | Regional | eventbrite.com | (account) | 2 | MAKRS | ToS: automation likely restricted |
| 15 | `yelp_events` | Yelp Events | Regional | yelp.com/events | (same) | 2 | MAKRS | ToS: automation likely restricted |
| 16 | `meetup` | Meetup | Regional | meetup.com | (account/group) | 2 | MAKRS | ToS: automation likely restricted |
| 17 | `nextdoor` | Nextdoor | Local | nextdoor.com | /login/ | 2 | Fair Game | ToS: automation likely restricted |
| 18 | `fox8_cityspark` | FOX8 / CitySpark | Regional | (syndicated) | login.cityspark.com/login | 2 | Fair Game | CitySpark syndication system |
| 19 | `discover_durham` | Discover Durham | Durham | discoverdurham.com/events/ | — | B | MAKRS | find submit URL |
| 20 | `downtown_durham` | Downtown Durham | Durham | downtowndurham.com/events/ | — | B | MAKRS | find submit URL |
| 21 | `third_friday_durham` | Third Friday Durham | Durham | thirdfridaydurham.org | — | B | MAKRS | arts; "really specific" |
| 22 | `raltoday` | RALtoday (6AM City) | Triangle | raltoday.6amcity.com | — | B | MAKRS | find submit path |
| 23 | `raleighnc_gov` | RaleighNC.gov Events | Raleigh | raleighnc.gov/events/calendar | — | B | MAKRS | gov calendar |
| 24 | `spectrum_news` | Spectrum News Community | Triangle | spectrumlocalnews.com/nc | — | B | MAKRS | find submit URL |
| 25 | `this_is_raleigh` | This Is Raleigh | Raleigh | thisisraleigh.com | — | B | MAKRS | find submit URL |
| 26 | `dra_downtown_raleigh` | Downtown Raleigh Alliance | Raleigh | downtownraleigh.org | — | B | MAKRS | find submit URL |
| 27 | `raleigh_downtown` | Raleigh Downtown (likely ≠ DRA) | Raleigh | — | — | B | MAKRS | confirm it's a distinct org |
| 28 | `cvb` | CVB (Convention & Visitors Bureau) | Raleigh / Wake | — | — | B | Fair Game | identify the actual site — may be the same as Visit Raleigh (#3) |

> **Dedupe before building:** #28 "CVB" (Convention & Visitors Bureau) may *be* Visit Raleigh (#3); #27 "Raleigh Downtown" may duplicate DRA (#26). Resolve during research so we don't double-submit the same event to the same calendar.
