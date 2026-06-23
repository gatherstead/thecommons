# Broadcast — Event Syndication

**Single source of truth for everything broadcast.** The broadcast subsystem pushes one event out to multiple third-party community calendars by filling each site's web form with headless Playwright, with a human-in-the-loop fallback for captcha-gated sites.

It spans four places:

| Piece | Path | Role |
|-------|------|------|
| Backend app | `backendServer/broadcast/` | Models, routing, adapters, DB-queue worker, API |
| Operator SPA | `broadcastWeb/` | Vite + React console (review → submit), polls jobs |
| Browser extension | `broadcastExtension/` | Dormant Chrome MV3 helper for manual (captcha) review |
| Worker service | `broadcast-worker` (systemd) | Runs `run_broadcast_worker` continuously in prod |

**Key files:** `broadcast/services.py`, `broadcast/worker.py`, `broadcast/runner.py`, `broadcast/routing.py`, `broadcast/schema.py`, `broadcast/access.py`, `broadcast/adapters/`.

## Design rules (do not break)

- **Isolation from `events/`.** `broadcast/routing.py` must not import from `events` (enforced by `test_isolation.py`). The broadcast app operates on its own denormalized copy of an event (`CanonicalEvent` / `BroadcastSubmission`), never on `events.Event`.
- **No Django ORM inside `sync_playwright`.** `runner.py` fetches everything into plain objects first, then drives the browser. Playwright must never run inside gunicorn.
- **Not Celery.** Broadcast has its own Postgres-backed queue (`SELECT FOR UPDATE SKIP LOCKED`), independent of the Celery/Redis stack.
- **Adapters never invent content, never call an LLM at runtime, and never solve captchas.** Missing required field / captcha / login wall → the target ends `needs_manual`.

## Flow

```
broadcastWeb (SPA)        Backend (Django)              Worker / Runner            Target site
─────────────────        ────────────────              ───────────────            ───────────
POST /preview ──────────▶ CanonicalEvent + routing.eligible_targets()
   ◀──────────────────── eligible[] / excluded[]
POST /submit  ──────────▶ services.create_submission
                          → BroadcastSubmission (queued)
                            + one BroadcastTarget per site
                          (dev: spawn one-shot worker on commit)
                                       │
                                       ▼
                          run_broadcast_worker: claim_next()  ──▶ runner.run_submission
                          (SKIP LOCKED, recover_orphans)            per target: own Chromium,
                                                                    adapter.fill_and_submit
poll GET /jobs/<id> ◀──── per-target status                        (dry_run: fill, screenshot,
                                                                     don't submit) ──────────▶ form
captcha site → needs_manual; "Manual review" → extension path (below)
```

1. **Preview** (`views.preview`) — serializes the event into a `CanonicalEvent` (`schema.py`, ORM-decoupled; converts UTC → `America/New_York`), then `routing.eligible_targets()` matches each adapter's eligibility (locality ∩ category sets) and returns eligible vs excluded-with-reason. Deterministic, no side effects.
2. **Submit** (`views.submit` → `services.create_submission`) — creates one `BroadcastSubmission` (denormalized event copy) + one `BroadcastTarget` per chosen `site_key`, status `queued`. Every broadcast starts **dry-run** (fill + screenshot, no submit). In dev, `BROADCAST_AUTOSPAWN_WORKER` spawns a one-shot worker on commit.
3. **Worker** (`worker.py`, `run_broadcast_worker`) — `claim_next()` claims the oldest `queued` submission with `SELECT FOR UPDATE SKIP LOCKED`; `recover_orphans()` re-queues `running` jobs on startup. `--once` processes one job and exits (used by dev autospawn + tests; skips orphan recovery).
4. **Runner** (`runner.py`, `run_submission`) — per target: launches its own Chromium session, builds a `RunContext`, calls `adapter.fill_and_submit(page, ev, ctx)`. Re-reads `submission.status` between targets to honor a mid-run cancel; screenshots before/after. Records status / `external_url` / error / `screenshot_path` per target.
5. **Review & submit-real** — the SPA shows each straight-through target as **Ready**; the operator clicks **Submit** (or **Submit all ready**) → `submit-real` promotes those targets from dry-run to a real send and re-queues. Captcha targets land **Needs manual** → extension path.

## Models

**Key file:** `broadcast/models.py`

- **`BroadcastSubmission`** — `uuid` PK, `client_label`, a full denormalized copy of the event (title, datetimes, venue/address, locality JSON, categories JSON, urls, price, organizer, contacts), `status` ∈ `queued / running / done / failed / canceled`, timestamps.
- **`BroadcastTarget`** — `uuid` PK, FK→submission, `site_key`, `status` ∈ `pending / in_progress / succeeded / failed / needs_manual / skipped`, `attempts`, `external_url`, `error`, `screenshot_path`, `dry_run`. `UniqueConstraint(submission, site_key)`.

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

### Manual-review handoff (extension)

A `needs_manual` target shows a **Manual review** button in the SPA. Clicking it fetches the recipe and messages the dormant `broadcastExtension`, which opens the target form in a new tab, autofills every field **except** the captcha and submit button, and hands off to the human — the only place a captcha token is valid. The SPA marks it optimistically "Submitted" (client-only; there is no backend success report for the manual path in v1).

Extension internals: buildless MV3, no static content scripts (dormant until messaged). `background.js` validates `sender.origin`, answers `ping` with its version (SPA detection), and on `fill` opens a tab and injects `content.js` once. `content.js` fills via native setters (so React inputs update) and never clicks submit. Setup and Web Store distribution: [`../broadcastExtension/README.md`](../broadcastExtension/README.md).

## Access control

**Key file:** `broadcast/access.py`. All `/broadcast/` endpoints require the `X-Broadcast-Access-Code` header (`HasBroadcastAccessCode`). `access.py` resolves a code → client label via constant-time comparison against the `BROADCAST_ACCESS_CODES` env var (`label:code,label2:code2,...`). The SPA also has a client-only **Verify** stub — there is no `verify` endpoint yet.

## API endpoints

All gated by `X-Broadcast-Access-Code`; mutating endpoints are rate-limited.

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/broadcast/preview` | Eligible/excluded target sites for an event (10/m) |
| POST | `/broadcast/ai-autofill` | LLM-extract event fields from pasted text into the form draft (5/m) |
| POST | `/broadcast/submit` | Create submission + targets, enqueue (3/m) |
| GET | `/broadcast/jobs/<uuid>` | Job status + per-target detail |
| POST | `/broadcast/jobs/<uuid>/retry` | Re-queue selected targets (10/m) |
| POST | `/broadcast/jobs/<uuid>/submit-real` | Promote dry-run targets to real (10/m) |
| POST | `/broadcast/jobs/<uuid>/cancel` | Cancel job, skip pending (10/m) |
| GET | `/broadcast/jobs/<uuid>/screenshots/<site_key>` | Serve gated screenshot PNG |
| GET | `/broadcast/jobs/<uuid>/manual/<site_key>` | Recipe JSON for a `needs_manual` target (30/m) |
| GET | `/broadcast/mock-form` | Dev-only (`DEBUG`) mock submission form |

`manual/<site_key>` gating: 404 (unknown site / no recipe / missing target), 409 (status ≠ `needs_manual`), 200 (recipe).

**AI autofill** (`/broadcast/ai-autofill`, `broadcast/autofill.py`) is the *only* place broadcast touches an LLM, and it is strictly operator-side: it turns a pasted blob of free text into a draft event the operator reviews before doing anything. It uses Gemini Flash-Lite, mirrors the `events` ingestion's genai usage but imports nothing from `events`/`ingestion` (isolation contract), filters `locality`/`categories` to the controlled vocab, and only returns field values — it never previews, submits, or fills a calendar. This does **not** relax the adapter rule: adapters still never invoke an LLM at runtime.

## Management commands

| Command | Purpose |
|---------|---------|
| `run_broadcast_worker [--once]` | The queue worker loop (systemd in prod; `--once` for dev/tests) |
| `broadcast_dry_run --site --fixture` | Run one adapter dry against a fixture (`broadcast/fixtures/`) |
| `capture_broadcast_form <site>` | Capture a live form's HTML/PNG for selector picking |
| `check_recipes [--live]` | Audit recipe selectors offline; `--live` loads each real form (hits third-party sites — run deliberately) |
| `scaffold_adapter --url --key` | Capture a new site's form controls into `adapters/_scaffold/` |

## Environment variables (`BROADCAST_*`)

| Var | Meaning |
|-----|---------|
| `BROADCAST_ACCESS_CODES` | `label:code,...` — access codes → client labels |
| `BROADCAST_AUTOSPAWN_WORKER` | Spawn a one-shot worker on submit/retry (**true in dev**, false in prod) |
| `BROADCAST_ENABLE_MOCK` | Add the mock adapter to the registry (CI/dev) |
| `BROADCAST_HEADLESS` | Run Chromium headless (default true) |
| `BROADCAST_DRY_RUN_DEFAULT` | Default dry-run for submissions |
| `BROADCAST_MAX_CONCURRENCY` | Worker concurrency (1 on the prod VM) |
| `BROADCAST_SCREENSHOT_DIR` / `BROADCAST_DOWNLOAD_DIR` | Artifact dirs |
| `BROADCAST_TIMEOUT_MS` | Per-action Playwright timeout |

SPA env (`broadcastWeb/.env`): `VITE_BROADCAST_API_BASE_URL` (Django API), `VITE_BROADCAST_EXTENSION_ID` (enables the manual-review button).

## Dev vs prod worker

- **Dev:** `BROADCAST_AUTOSPAWN_WORKER=true` → `services` detaches `run_broadcast_worker --once` via `transaction.on_commit` on submit/retry. Safe alongside other workers (`SKIP LOCKED`, separate process, `--once` skips orphan recovery).
- **Prod:** the systemd `broadcast-worker` runs `run_broadcast_worker` continuously (autospawn off; it is authoritative). Tuned for a 6 GB ARM64 VM (concurrency 1, bundled Chromium). See [DEPLOY.md](../DEPLOY.md).

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
