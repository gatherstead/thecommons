# Broadcast — Event Syndication

**Single source of truth for everything broadcast.** The broadcast subsystem pushes one event out to multiple third-party community calendars by filling each site's web form, with the browser extension as the primary path so clients can verify what's being submitted before clicking Send.

It spans four places:

| Piece | Path | Role |
|-------|------|------|
| Backend app | `backendServer/broadcast/` | Models, routing, adapters, on-demand Celery worker, API |
| Operator SPA | `broadcastWeb/` | Vite + React console (select sites → extension autofill) |
| Browser extension | `broadcastExtension/` | Primary Chrome MV3 autofill helper — opens each calendar in a tab |
| Worker service | `broadcast-worker` (systemd) | `celery -A backend worker -Q broadcast -c 1` — drains the dedicated `broadcast` Celery queue (oneshot path) |

**Key files:** `broadcast/services.py`, `broadcast/worker.py`, `broadcast/runner.py`, `broadcast/routing.py`, `broadcast/schema.py`, `broadcast/access.py`, `broadcast/adapters/`.

## Design rules (do not break)

- **Isolation from `events/`.** `broadcast/routing.py` must not import from `events` (enforced by `test_isolation.py`). The broadcast app operates on its own denormalized copy of an event (`CanonicalEvent` / `BroadcastSubmission`), never on `events.Event`. The ingestion bridge (`POST /api/events/direct-submit`) that fires alongside preview preserves this contract: its code lives entirely in `ingestion/`, and `broadcast/` still imports nothing from `events/` or `ingestion/`.
- **No Django ORM inside `sync_playwright`.** `runner.py` fetches everything into plain objects first, then drives the browser. Playwright must never run inside gunicorn.
- **Single-concurrency `broadcast` Celery queue.** Both `process_broadcast_queue` and `recover_broadcast_orphans` are routed to a dedicated `broadcast` queue (`CELERY_TASK_ROUTES` in `backend/settings/base.py`), drained by exactly one `-c 1` worker. This is load-bearing, not a tuning default: `recover_orphans()` assumes any `running` submission at startup is orphaned, so a second concurrent worker could race a live queue-drain and re-queue an in-flight target.
- **Adapters never invent content, never call an LLM at runtime, and never solve captchas.** Missing required field / captcha / login wall → the target ends `needs_manual`.

## Submission modes

### Primary: Extension autofill (all recipe-enabled sites)

The browser extension is the default submission path. The SPA requests a recipe per site from the backend, messages the extension, which opens the calendar form in a new tab and fills all fields. The client reviews the prefilled form, solves any captcha, and clicks Submit themselves — giving full visibility into what's being sent.

**Recipe-enabled sites (extension autofill works):** `abc11_community`, `triangle_on_the_cheap`, `triangle_weekender`, `visit_raleigh`, `chatham_arts`, `chatham_chamber`.

**Login-gated sites (coming soon):** `fun4raleighkids`, `chapelboro`, `explore_pittsboro`, `shop_pittsboro`. These require an account login before any form appears; they are greyed out in the SPA with "coming soon". Their adapters carry no recipe.

### Secondary: Oneshot / server-side Playwright (disabled in SPA)

The headless Playwright dry-run → review → real-submit flow exists in the backend and can be re-enabled, but the "Fill & review" button is currently disabled in the SPA. This path is relevant for future automated workflows.

## Flow

```
broadcastWeb (SPA)           Backend (Django)                Extension / Browser
──────────────────           ────────────────                ───────────────────
POST /preview ─────────────▶ CanonicalEvent + routing.eligible_targets()
   ◀──────────────────────── eligible[] / excluded[]

[User selects sites & clicks "Autofill with extension"]

POST /broadcast/direct-recipe ─▶ adapter.recipe(event) ──▶ recipe JSON (no DB write)
   ◀────────────────────────────                         ◀──

SPA.sendFill(extensionId, recipe) ────────────────────────▶ background.js
                                                            opens tab at recipe.url
                                                            injects content.js
                                                            content.js fills fields
                                                            shows banner + green Submit
[Client reviews, solves captcha, clicks Submit]
```

1. **Preview** (`views.preview`) — serializes the event into a `CanonicalEvent` (`schema.py`, ORM-decoupled; converts UTC → `America/New_York`), then `routing.eligible_targets()` matches each adapter's eligibility (locality ∩ category sets) and returns eligible vs excluded-with-reason. Deterministic, no side effects. **The SPA also fires `POST /api/events/direct-submit` (fire-and-forget, non-blocking) on the same click** — this is the ingestion bridge that routes the event into the standardization pipeline without waiting for the next cron run. A failure of the direct-submit call never blocks or affects the preview result.
2. **Direct recipe** (`views.direct_recipe`, `POST /broadcast/direct-recipe`) — takes event data + `site_key`, validates via `CanonicalEventSerializer`, calls `adapter.recipe()`, and returns the recipe JSON. No `BroadcastSubmission` row created; pure read-through. 404 if site unknown or login-gated (no recipe). Rate-limited 30/m.
3. **Extension fill** — SPA calls `sendFill(extensionId, recipe)` for each site. The extension opens a tab at `recipe.url`, injects `content.js`, which fills all non-captcha fields and shows a sticky review banner. Never clicks submit.
4. **Oneshot worker path** (disabled in SPA) — `views.submit` → `services.create_submission` creates `BroadcastSubmission` + `BroadcastTarget` rows, status `queued`, then calls `_dispatch_worker()`, which does `transaction.on_commit(process_broadcast_queue.delay)` — an on-demand Celery task, routed to the dedicated `broadcast` queue, that drains the queue (`worker.claim_next` → `adapter.fill_and_submit`, screenshots, records status) by looping `worker.run_once()` until empty. `retry_targets` and `submit_real_targets` call the same dispatcher. Review & submit-real flow promotes dry-run targets to real. See below for details.

## Models

**Key file:** `broadcast/models.py`

- **`BroadcastSubmission`** — `uuid` PK, `client_label`, a full denormalized copy of the event (title, datetimes, venue/address, locality JSON, categories JSON, urls, price, organizer, contacts), `status` ∈ `queued / running / done / failed / canceled`, timestamps.
- **`BroadcastTarget`** — `uuid` PK, FK→submission, `site_key`, `status` ∈ `pending / in_progress / succeeded / failed / needs_manual / skipped`, `attempts`, `external_url`, `error`, `screenshot_path`, `dry_run`. `UniqueConstraint(submission, site_key)`.
- **`BroadcastAccess`** — `email` (unique, lowercased), `tier` (0/1/2, default 0). Maps a logged-in user's email to a **permanent** feature tier. No row = tier 0. Set via `set_broadcast_access` or by redeeming an UPGRADE code (`POST /broadcast/redeem`).
- **`AccessCode`** — `code_hash` (SHA-256 hex; raw code shown once at generation, never stored), `label`, **`kind`** (`trial` | `upgrade`, default `trial`), `tier` (default 2 — forced to 2 on save for `trial` codes, `AccessCode.save()`), `max_uses` (null = unlimited), `is_active`, `expires_at`. Two independent pools — see [Access control](#access-control).
- **`AccessCodeUse`** — FK→`AccessCode` (`related_name="uses"`), `draft_id`, `unique_together(access_code, draft_id)`. Meters **TRIAL** codes only: one "use" = one distinct `draft_id` at preview time; re-submitting the same `draft_id` (edits) is free.
- **`AccessCodeRedemption`** — FK→`AccessCode` (`related_name="redemptions"`), `email` (lowercased), `unique_together(access_code, email)`. Meters **UPGRADE** codes: one row per distinct account that has redeemed the code.

Lifecycle ops are idempotent and reuse existing target rows: `retry_targets`, `submit_real_targets` (flip dry-run→real, clear error/url/screenshot, re-queue), `cancel_submission` (skip every still-`pending` target, mark submission `canceled` — `claim_next` only picks `queued`, so a canceled job never starts).

## Adapters

**Key files:** `broadcast/adapters/__init__.py` (registry), `broadcast/adapters/base.py` (contract), `broadcast/adapters/_helpers.py` (shared form-fill helpers).

The registry maps `site_key → adapter`. Ten Tier-1 real adapters plus a mock:

```
triangle_on_the_cheap   triangle_weekender   abc11_community   visit_raleigh
fun4raleighkids         chapelboro           explore_pittsboro  chatham_chamber
shop_pittsboro          chatham_arts         _mock (gated by BROADCAST_ENABLE_MOCK)
```

`base.py` defines the `SiteAdapter` contract, `RunContext`, `TargetResult`, and `Eligibility` (locality × category sets). The mock adapter (`_mock.py`) drives a local `_mock_form.html` for CI/dev.

### Declarative recipe layer (manual review)

The imperative `fill_and_submit` is the source of truth for the headless path. A parallel **declarative** recipe shares the same field/selector definitions so the two can't drift, and is consumed by the browser extension for captcha sites.

- `RecipeField(selector, type, resolve, required, label, hint, recipe_only)` — `resolve(ev)` returns a pre-formatted string (using the same `_helpers` formatters as the imperative code). `recipe_only=True` → exported in the recipe but skipped by the shared fill loop.
- `SiteAdapter.recipe_fields`, `submit_selector`, `captcha_hint`, `recipe_field_specs(ev)` (override when the field set depends on the event), and `recipe(ev) -> dict`.
- `FILLABLE_TYPES = {text, textarea, date, time, select}` — what the shared loop (`_helpers.apply_specs`) fills. Widget types (`radio/checkbox/file/select2/terms/manual_widget`) are always emitted by `recipe()` even when empty.
- Recipe-enabled sites so far: `abc11_community`, `triangle_on_the_cheap`, `triangle_weekender`, `visit_raleigh`, `chatham_arts`, `chatham_chamber`. The remaining Tier-1 sites (`fun4raleighkids`, `chapelboro`, `explore_pittsboro`, `shop_pittsboro`) are login-gated, JS-only, or bot-blocked with no deterministic public form — their adapters carry no recipe and return `needs_manual` after detecting the login wall / captcha / missing form.

Recipe JSON shape (served by `GET /broadcast/jobs/<id>/manual/<site_key>`):

```json
{
  "site_key": "triangle_weekender",
  "name": "The Triangle Weekender",
  "url": "https://thetriangleweekender.com/events/community/add/",
  "fields": [
    {"selector": "#post_title", "type": "text", "value": "Jazz Night",
     "required": true, "label": "Event title", "hint": null},
    {"selector": "#terms", "type": "terms", "value": "true",
     "required": true, "label": "Accept community terms", "hint": null}
  ],
  "captcha_hint": null,
  "submit_selector": "#post"
}
```

### Extension autofill handoff

The SPA requests a recipe via `POST /broadcast/direct-recipe` for each selected site, then calls `sendFill(extensionId, recipe)`. The `broadcastExtension` opens the target form in a new tab, autofills every field **except** the captcha and submit button, and shows a sticky banner. The client reviews the filled form, solves any captcha, and clicks Submit themselves — the only place a captcha token is valid. The SPA tracks per-site status optimistically (client-only).

The legacy `needs_manual` path from the oneshot flow (where a `GET /broadcast/jobs/<id>/manual/<site_key>` recipe was fetched after a Playwright dry-run) still exists in the code and `JobProgress` component, but is not reached in the primary flow since no job is created.

Extension internals: buildless MV3, no static content scripts (dormant until messaged). `background.js` validates `sender.origin`, answers `ping` with its version (SPA detection), and on `fill` opens a tab and injects `content.js` once. `content.js` fills via native setters (so React inputs update) and never clicks submit. Setup and Web Store distribution: [`../broadcastExtension/README.md`](../broadcastExtension/README.md).

## Access control

**Key files:** `broadcast/access.py`, `broadcast/permissions.py`, `broadcast/models.py`, `broadcast/admin.py`.

Two independent code pools, distinguished by `AccessCode.kind`:

- **TRIAL** (`kind="trial"`) — redeemed **anonymously**, no account required. Always tier 2 (`AccessCode.save()` forces it). Time-boxed via `expires_at` rather than metered by uses — `generate_access_code` defaults trial codes to unlimited uses + a 3-day expiry. This is the frictionless "hand someone a code and they're trying the product in 10 seconds" path; nothing here writes to a user account.
- **UPGRADE** (`kind="upgrade"`) — redeemed only by a **logged-in** user via `POST /broadcast/redeem`, and permanently sets that account's `BroadcastAccess.tier` (last code entered wins — no downgrade protection, by design, so support/sales can just say "enter this code"). Never resolves anonymously. Defaults to tier 2, 3 uses, no expiry.

`resolve_access(request, draft_id=None) -> AccessResult(tier, identity, is_trial, uses_remaining, client_label, code)` — the **anonymous/per-request** resolver, used by every gated endpoint except `/broadcast/redeem`:

1. **Bearer JWT** (`Authorization: Bearer <jwt>`) — verified statelessly via `backend/jwt_auth.py` (JWKS); `email` claim → `BroadcastAccess.tier` (default 0 if no row). A JWT header present but invalid → 403; does **not** fall through to the code path.
2. **Access code** (`X-Broadcast-Access-Code` header or body `access_code`) → SHA-256 constant-time match against active **TRIAL-kind only** `AccessCode` rows. UPGRADE codes never match here.
3. **No credentials** → tier 0, 200 (not an error).

`redeem_upgrade_code(email, raw_code) -> int | None` — the **account-permanent** path, called only from `POST /broadcast/redeem` (requires login via `RequiresBroadcastLogin`). Matches UPGRADE-kind codes only; on success, `BroadcastAccess.objects.update_or_create(email=..., tier=code.tier)` and records an `AccessCodeRedemption`. Redemption is idempotent per email (re-entering the same code doesn't consume another `max_uses` slot).

| Tier | Who | Fill + broadcast | AI autofill |
|---|---|---|---|
| **0** | Logged-in user with no grant; or unauthenticated | ✗ | ✗ |
| **1** | `BroadcastAccess.tier=1` — via `set_broadcast_access` or a tier-1 UPGRADE code | ✓ | ✗ |
| **2** | `BroadcastAccess.tier=2` (dev-granted or UPGRADE code), or any valid TRIAL code | ✓ | ✓ |

Permission classes: `RequiresBroadcastTier1` (preview / submit / recipe / job endpoints), `RequiresBroadcastTier2` (ai-autofill only), `RequiresBroadcastLogin` (redeem only — no tier check, just a valid JWT; stamps `request.broadcast_email`). The tier classes stamp `request.broadcast_access` (`AccessResult`) and `request.broadcast_client_label` for downstream views.

**Metering:** TRIAL codes are metered **only at `POST /broadcast/preview`** — `AccessCodeUse.objects.get_or_create(code, draft_id)` (idempotent). Trial callers must include `draft_id` in the preview body; missing → 400. Re-submitting the same `draft_id` (edits) is free. UPGRADE codes are metered by distinct redeeming email (`AccessCodeRedemption`), checked in `redeem_upgrade_code`. Logged-in JWT sessions are never metered on preview.

**`client_label`** on `BroadcastSubmission`: email for JWT users; `AccessCode.label` for TRIAL-code users. Access codes are stored only in the database — there is no env-var code list. `GET /broadcast/access` lets the SPA query the caller's tier and remaining trial uses (JWT or TRIAL code); `POST /broadcast/redeem` is how a logged-in user applies an UPGRADE code.

**Frontend (`broadcastWeb`):** one textfield does double duty, labeled by login state — logged out it's "Access Code" (`getAccess`, anonymous TRIAL resolution, persisted in localStorage); logged in it relabels to "Upgrade Account" (`redeemAccessCode` → `POST /broadcast/redeem`, permanent, nothing persisted client-side since the grant now lives server-side against the account).

**Sign-in:** there is no embedded auth UI in the SPA (the former inline `AuthModal` component was removed). The "Sign in / Create account" button (`App.tsx`'s `handleSignIn`) does a full-page navigation to `${VITE_BETTER_AUTH_URL}/signin?redirect_to=<current broadcast URL>` — i.e. the shared auth **portal** (`theCommonsWeb`'s `src/app/(portal)/`, served at `https://auth.thecommons.town` in prod / `http://localhost:3000` in dev; see [ARCHITECTURE.md#authentication](../ARCHITECTURE.md#authentication)). Because the session cookie is scoped to `.thecommons.town`, completing sign-in in the portal returns the browser to the exact broadcast URL it left, already authenticated. `broadcastWeb/src/lib/authClient.ts` still exists — it's the Better Auth client used to read the session, mint a JWT (`fetchJwt`), and call `signOut()`, not to render any sign-in form.

**Admin (`/admin/broadcast/accesscode/`):** self-serve code creation — `AccessCodeAdmin.save_model` generates and hashes a fresh raw code on creation and shows it once via a success message banner (never stored, never shown again). A `trial_days` convenience field on the add form sets `expires_at` relative to now. `BroadcastAccess` is also registered for visibility into current permanent grants.

## API endpoints

Auth: Bearer JWT or `X-Broadcast-Access-Code` header/body (resolved as a tier). Most endpoints require tier ≥ 1; `ai-autofill` requires tier ≥ 2. `GET /broadcast/access` is open — returns tier 0 for unauthenticated callers, 403 for invalid credentials.

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/broadcast/access` | open (30/m) | Caller's tier + trial metadata — drives the SPA's access UI |
| POST | `/broadcast/redeem` | login required (10/m) | Redeem an UPGRADE code — permanently sets the caller's `BroadcastAccess.tier` |
| POST | `/broadcast/preview` | tier ≥ 1 (10/m) | Eligible/excluded target sites for an event; meters trial use by `draft_id` |
| POST | `/broadcast/ai-autofill` | tier ≥ 2 (5/m) | LLM-extract event fields from pasted text into the form draft |
| **POST** | **`/broadcast/direct-recipe`** | **tier ≥ 1 (30/m)** | **Recipe JSON for a site from event data — no job required** |
| POST | `/broadcast/submit` | tier ≥ 1 (3/m) | Create submission + targets, enqueue — oneshot path |
| GET | `/broadcast/jobs/<uuid>` | tier ≥ 1 | Job status + per-target detail |
| POST | `/broadcast/jobs/<uuid>/retry` | tier ≥ 1 (10/m) | Re-queue selected targets |
| POST | `/broadcast/jobs/<uuid>/submit-real` | tier ≥ 1 (10/m) | Promote dry-run targets to real |
| POST | `/broadcast/jobs/<uuid>/cancel` | tier ≥ 1 (10/m) | Cancel job, skip pending |
| GET | `/broadcast/jobs/<uuid>/screenshots/<site_key>` | tier ≥ 1 | Serve gated screenshot PNG |
| GET | `/broadcast/jobs/<uuid>/manual/<site_key>` | tier ≥ 1 (30/m) | Recipe JSON for a `needs_manual` target |
| GET | `/broadcast/mock-form` | — (`DEBUG` only) | Dev-only mock submission form |

`direct-recipe` gating: 404 (unknown site / no recipe for login-gated sites), 400 (invalid event data), 200 (recipe JSON).

`manual/<site_key>` gating: 404 (unknown site / no recipe / missing target), 409 (status ≠ `needs_manual`), 200 (recipe).

**AI autofill** (`/broadcast/ai-autofill`, `broadcast/autofill.py`) is the *only* place broadcast touches an LLM, and it is strictly operator-side: it turns a pasted blob of free text into a draft event the operator reviews before doing anything. It uses Gemini Flash-Lite, mirrors the `events` ingestion's genai usage but imports nothing from `events`/`ingestion` (isolation contract), filters `locality`/`categories` to the controlled vocab, and only returns field values — it never previews, submits, or fills a calendar. This does **not** relax the adapter rule: adapters still never invoke an LLM at runtime.

## Management commands

| Command | Purpose |
|---------|---------|
| `run_broadcast_worker [--once]` | Debug helper only — `--once` drains one submission via `worker.run_once()` without Celery. Not a service entrypoint; prod/dev dispatch goes through the `broadcast` Celery queue. |
| `broadcast_dry_run --site --fixture` | Run one adapter dry against a fixture (`broadcast/fixtures/`) |
| `capture_broadcast_form <site>` | Capture a live form's HTML/PNG for selector picking |
| `check_recipes [--live]` | Audit recipe selectors offline; `--live` loads each real form (hits third-party sites — run deliberately) |
| `scaffold_adapter --url --key` | Capture a new site's form controls into `adapters/_scaffold/` |
| `set_broadcast_access <email> <0\|1\|2>` | Grant or change a logged-in user's permanent broadcast tier |
| `generate_access_code [--kind trial\|upgrade=trial] [--tier {0,1,2}] [--label TEXT] [--expires ISO8601 \| --trial-days N] [--uses N \| --unlimited]` | Create an access code row; prints the raw code once (never stored). Trial: tier forced 2, defaults unlimited uses + 3-day expiry. Upgrade: `--tier` settable, defaults 3 uses, no expiry. Same as the admin page at `/admin/broadcast/accesscode/add/` |
| `list_access_codes` | List all codes (label, kind, tier, uses, active, expiry — never the raw code) |
| `revoke_access_code <label\|id>` | Set `is_active=False` on a code |

## Environment variables (`BROADCAST_*`)

| Var | Meaning |
|-----|---------|
| `BROADCAST_ENABLE_MOCK` | Add the mock adapter to the registry (CI/dev) |
| `BROADCAST_HEADLESS` | Run Chromium headless (default true) |
| `BROADCAST_DRY_RUN_DEFAULT` | Default dry-run for submissions |
| `BROADCAST_MAX_CONCURRENCY` | Worker concurrency (1 on the prod VM) |
| `BROADCAST_SCREENSHOT_DIR` / `BROADCAST_DOWNLOAD_DIR` | Artifact dirs |
| `BROADCAST_TIMEOUT_MS` | Per-action Playwright timeout |

SPA env (`broadcastWeb/.env`): `VITE_BROADCAST_API_BASE_URL` (Django API), `VITE_BROADCAST_EXTENSION_ID` (required — enables the extension autofill primary flow), `VITE_BETTER_AUTH_URL` (Better Auth base URL — `https://auth.thecommons.town` in prod, `http://localhost:3000` in dev).

## Dispatch model: on-demand Celery (Suite 25)

Dispatch is triggered by the app, not polled by the worker. `services._dispatch_worker()` calls `transaction.on_commit(process_broadcast_queue.delay)` from `create_submission`, `retry_targets`, and `submit_real_targets` — so a submission enqueues its own drain the instant the transaction commits, instead of a worker polling Postgres on a fixed interval.

- **`process_broadcast_queue`** (`broadcast/tasks.py`) — the Celery task that actually drains the queue: loops `worker.run_once()` (which wraps `claim_next` → `SELECT FOR UPDATE SKIP LOCKED` → `adapter.fill_and_submit`) until nothing is left to claim.
- **`recover_broadcast_orphans`** (`broadcast/tasks.py`) — crash-recovery only. Seeded as a django-celery-beat periodic task (`broadcast-orphan-recovery`, migration `0009_seed_orphan_recovery_beat.py`) running every 6 hours on the hour, UTC. It re-queues any submission left `running` by a worker that crashed mid-drain. This is a belt-and-suspenders net, not the normal recovery path (see below).
- **Both tasks share the single `broadcast` Celery queue**, drained by exactly one `-c 1` worker (systemd `broadcast-worker`, `celery -A backend worker -Q broadcast -c 1`). That single-worker invariant is what makes `recover_orphans()`'s "any `running` row is orphaned" assumption safe — a second concurrent worker would let a live drain race orphan recovery.
- **Dev:** there is no autospawned worker. Run `celery -A backend worker -Q broadcast -c 1 -l info` locally to drain the queue, or set `CELERY_TASK_ALWAYS_EAGER=True` (as `settings/test.py` does) to execute tasks synchronously without a worker at all.
- **Normal stalled-target recovery is client-driven, not server-polled.** The SPA's 3s poll loop (`broadcastWeb/src/App.tsx`) flags a target stuck if it's `queued` >30s or `in_progress` >90s, then calls `POST /broadcast/jobs/<id>/retry-stuck` for just those site keys (capped at 2 auto-retries per site before showing "Failed - Worker Stuck"). That endpoint (`views.job_retry_stuck` → `services.force_retry_stuck_target`) only resets a target if its `started_at` is more than 60 seconds old — a server-side floor so a client can't yank a target that's genuinely mid-fill. The 6h beat sweep exists only to catch what a crashed worker leaves behind between client sessions.

See [DEPLOY.md](../DEPLOY.md) for the systemd unit.

## Notable behaviors

- **Timezone:** events are stored aware-UTC. `schema.event_from_submission` converts `start`/`end` to `America/New_York` before adapters format wall-clock date/time (assumes the submitter entered Eastern local time).
- **`triangle_on_the_cheap` captcha:** reCAPTCHA is structural there, so it returns `needs_manual` on both dry and real runs (never auto-submits). Its honeypot field is deliberately never in a recipe.

## Testing

`broadcast/tests/` covers the adapter registry, routing matrix, recipe/schema mapping, mock adapter, runner, worker queue, services (cancel/retry/submit-real), access codes, the API, and `events`-isolation. Run the broadcast suite:

```bash
DJANGO_SETTINGS_MODULE=backend.settings.test uv run python manage.py test broadcast
```

> **CI gap:** most `broadcast/tests/` files carry no `@tag`, and CI runs only `--tag=fast` / `--tag=db` — so these tests **do not run in CI** today. They run under a bare `manage.py test` locally. (If a stale Neon test-DB session blocks the drop, terminate it via `pg_terminate_backend` on `test_neondb`, or use `--keepdb`.)

## Local maps

- [`../broadcastWeb/AGENTS.md`](../broadcastWeb/AGENTS.md) — operator SPA structure, testing, env.
- [`../broadcastExtension/README.md`](../broadcastExtension/README.md) — extension load-unpacked dev + Web Store distribution.
