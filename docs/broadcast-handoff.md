# Broadcast — Review Console & Manual-Review Handoff

Covers the review-first submission console and the human-in-the-loop manual-review
path added on `arya/broadcast-feature`, plus three related fixes (dry-run captcha
status, timezone, auto-spawn worker). Background on the broadcast feature itself:
`DESIGN_BROADCAST.md`, `backendServer/broadcast/`.

## Review-first console (fill → review → submit)

Every broadcast now starts as a **dry-run fill**: the worker fills each target's
form (and screenshots it) but never submits. In the SPA's Progress panel each
straight-through site then shows a light-green **Ready** badge with a **Submit**
(real send) and **Screenshot** (review the fill) action; a **Submit all ready**
button sits above the list. Captcha sites land **Needs manual** (yellow) and use
the extension path below. Submitting optimistically flips the badge to dark-green
**Submitted**; a real failure overrides to red **Error**. A **Stop all jobs**
button cancels the in-flight job. This replaces the old single auto-submit button
and the dry-run checkbox — fill-first makes a separate toggle redundant.

## The problem it solves

The worker fills each site's form headlessly (`broadcast/runner.py`). Sites with
a captcha can't be solved headlessly, so those targets end `needs_manual` and
nothing happens. Manual review adds a human-in-the-loop path: a `needs_manual`
target shows a **Manual review** button in the SPA; clicking it opens the
target form in a new tab where a dormant browser extension autofills every field
**except** the captcha and the submit button. The human solves the captcha and
clicks submit in their own session — the only place a captcha token is valid.

```
SPA (broadcastWeb)            Backend (Django)          Extension (Chrome)        Target site
─────────────────            ───────────────           ─────────────────        ───────────
event submitted ───────────▶ worker fills headless
                             captcha site → needs_manual
"Manual review" button
 (extension detected via ping)
   │
   ▼
GET jobs/<id>/manual/<site> ▶ adapter.recipe(ev)
   ◀──────────────────────── {url, fields[], submit_selector, captcha_hint}
sendMessage({type:"fill"}) ─────────────────────────▶ bg opens tab, injects
optimistic "Event submitted"                          content.js, fills all
 (client-side only)                                   fields (skips captcha
                                                       + submit) ──────────────▶ human solves
                                                                                 captcha + submits
```

Three recipe-enabled sites so far: `abc11_community`, `triangle_on_the_cheap`,
`triangle_weekender`.

## Backend: declarative recipe layer

The imperative `fill_and_submit` is still the source of truth for the headless
path. A parallel **declarative** recipe shares the same field/selector defs so
the two can't drift.

- `adapters/base.py`
  - `RecipeField(selector, type, resolve, required, label, hint, recipe_only)` —
    `resolve(ev)` returns the pre-formatted string (use the same `_helpers`
    formatters the imperative code uses). `recipe_only=True` → exported in the
    recipe but skipped by the shared fill loop (the adapter's imperative code
    drives it on the server path).
  - `SiteAdapter.recipe_fields`, `submit_selector`, `captcha_hint`,
    `recipe_field_specs(ev)` (override when the field set depends on the event),
    and `recipe(ev) -> dict`.
  - `FILLABLE_TYPES = {text, textarea, date, time, select}` — what the shared
    loop fills. Widget types (`radio/checkbox/file/select2/terms/manual_widget`)
    are always emitted by `recipe()` even when empty.
- `adapters/_helpers.py` — `apply_specs(page, specs, ev, timeout_ms)`: one shared
  fill loop, replaces the three old per-adapter `_apply` functions (semantics
  preserved: `min(timeout, 5000)`, same missing-field descriptor strings).
- The three adapters lifted their inline `fills` lists into module-level
  `recipe_fields`. Event-dependent / widget fields are built in
  `recipe_field_specs` (e.g. weekender appends time fields only when `not
  all_day`; county checkboxes per mapped locality; on-the-cheap's image-dependent
  radios). The on-the-cheap honeypot `#input_5_26` is deliberately never in a
  recipe.

### Recipe JSON shape

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

### Endpoint

`GET /broadcast/jobs/<job_id>/manual/<site_key>` (`views.job_manual_recipe`,
`services.manual_recipe`). Gated by the same `X-Broadcast-Access-Code` header the
SPA already holds. Mirrors `job_screenshot` gating:

- 404 — unknown site, adapter has no `recipe_fields`, submission/target missing
- 409 — target status ≠ `needs_manual`
- 200 — `adapter.recipe(event_from_submission(submission))`

## Backend: submission control

Two endpoints drive the review console (both POST, gated by the access-code
header/body, rate-limited 10/m, 404 on unknown job):

- `POST /broadcast/jobs/<job_id>/submit-real` (`views.job_submit_real`,
  `services.submit_real_targets`) — promotes the given `site_keys` from
  `dry_run=True` to a real submission: sets them back to `pending`, clears
  error/url/screenshot, and re-queues the job. Only touches targets still in
  dry-run, so an already-real target can't be re-sent. Body `{site_keys: [...]}`;
  returns `{job_id, submitted}`.
- `POST /broadcast/jobs/<job_id>/cancel` (`views.job_cancel`,
  `services.cancel_submission`) — skips every still-`pending` target and marks the
  submission `canceled` (new submission status, migration `0004`). `claim_next`
  only picks `queued`, so a canceled job is never started. Returns
  `{job_id, status, skipped}`.

`runner.run_submission` re-fetches `submission.status` between targets and stops
early when it sees `canceled`; a post-loop guard keeps a mid-run cancel from being
clobbered by the normal done/failed write. The site already in-flight finishes;
remaining pending targets are skipped.

## Browser extension — `broadcastExtension/`

Buildless plain-JS MV3 (no bundler). **Dormant** until the SPA messages it (no
static content scripts).

- `manifest.json` — permissions `scripting/tabs/storage`; `host_permissions` for
  trumba.com / triangleonthecheap.com / thetriangleweekender.com;
  `externally_connectable.matches` = SPA origins.
- `background.js` — validates `sender.origin`; `{type:"ping"}` → version (SPA
  detection); `{type:"fill", payload}` → stash recipe, open tab, inject
  `content.js` once on load, then forget the tab (one-shot → dormant).
- `content.js` — per-type handlers (text/textarea/date/time/select via native
  setter so React inputs update; radio/checkbox; file → hint only; select2 +
  terms hardcoded for weekender; label→input fallback). Renders a banner and
  highlights the submit button. **Never clicks submit.**
- `README.md` — load-unpacked dev + unlisted Web Store distribution (pinned
  `key`, privacy policy, zip + submit).

## SPA — `broadcastWeb/`

- `models/broadcastModels.ts` — `Recipe` / `RecipeField` types; `JobDetail.status`
  now includes `canceled`.
- `services/broadcastApi.ts` — `getManualRecipe`, plus `submitReal(accessCode,
  jobId, siteKeys)` and `cancelJob(accessCode, jobId)`.
- `hooks/useExtension.ts` — pings `VITE_BROADCAST_EXTENSION_ID` on load
  (`installed`); `sendFill()` relays the recipe; `recheck()` re-pings once/sec for
  ~60s. The install link calls `recheck()`, so every install link flips to
  **Manual review** the moment the user finishes installing — no SPA reload (one
  shared `installed` state backs the whole list). Degrades to "not installed"
  off-Chromium.
- `components/JobProgress.tsx` — a `displayStatus(t)` helper maps each target to
  `ready | submitted | error | needs_manual | pending | in_progress | skipped`
  from `t.status` + `t.dry_run` + optimistic local sets. Ready rows render
  **Submit** (→ `onSubmitReal`) and **Preview fill** (the dry-run `before-submit`
  screenshot); a **Submit all ready** button sits above the list. Real-submitted
  rows (`succeeded` + `!dry_run`) render **View confirmation** — the adapter's
  `after-submit` capture of the site's "thank you for submitting" page — which
  replaced the old `external_url` **listing** link. The two screenshots are
  deliberately labelled differently (Preview fill vs. View confirmation) so the
  filled-form review and the post-submit receipt aren't confused. `needs_manual`
  rows keep the **Manual review** / install path (optimistic "Submitted") and a
  **Screenshot** of where the run stalled. A real `failed` overrides any optimism
  to **Error**. When every non-skipped target reaches **Submitted**, a warm
  `.job-complete` acknowledgement closes out the list.
- `App.tsx` — owns the console: a stubbed **Verify** button beside the access code
  (dims the form via `form-dim` and gates Preview until verified — no backend yet);
  the initial broadcast forced to dry-run ("Fill & review N calendars", black
  `.dark` button); `handleSubmitReal` / `handleCancel` mirror `handleRetry`; a
  **Stop all jobs** (`.danger`) button while the job is active; a bottom **Submit
  another event** that resets every field except the access code; a disabled **AI
  Autofill** section between Access and The Event; masthead title **BROADCAST
  SYNDICATE**.
- **Reload persistence** — the whole page (incl. the access code, by request) is
  saved to `localStorage` (`broadcast:state:v1`) so a reload restores work and
  resumes polling an in-flight job. Once the job is terminal
  (`done`/`failed`/`canceled`) the key is cleared, so reloading a finished
  broadcast starts from a clean slate.

## Related fixes

- **Dry-run captcha status** — `triangle_on_the_cheap` used to return `succeeded`
  on dry runs. reCAPTCHA is structural there (no automated submit ever), so it
  now returns `needs_manual` on both dry and real runs, and `JobProgress` shows
  the Manual review link for dry-run `needs_manual` targets too.
- **Timezone** — events are stored aware-UTC (`USE_TZ=True`) but adapters
  formatted the raw UTC time (4pm rendered as 8pm; late-night events slipped a
  day). `schema.event_from_submission` now converts `start`/`end` to
  `America/New_York` (`EVENT_TZ`) before adapters format wall-clock date+time.
  Assumes the submitter entered Eastern local time (correct for Triangle events).
- **Auto-spawn worker** — `worker.spawn_worker_once()` detaches a
  `run_broadcast_worker --once` process; `services` calls it via
  `transaction.on_commit` on submit/retry. Gated by `BROADCAST_AUTOSPAWN_WORKER`
  (**on in dev**, off in prod where the systemd worker is authoritative). Safe
  alongside other workers — `claim_next` uses `SKIP LOCKED`, it's a separate
  process (Playwright never in gunicorn), and `--once` skips orphan recovery.

## Health harness

`python manage.py check_recipes` — offline structural audit of every
recipe-enabled adapter (valid field types, non-empty selectors, a submit
selector). `--live` also loads each form and asserts every selector resolves
(searches all frames for iframe-embedded forms). **Live mode hits real
third-party sites — only run it deliberately.** Use it to catch DOM drift.

## Tests

- `broadcast/tests/test_recipe.py` — recipe shape, honeypot omission, weekender
  conditional times, image-field tracking, timezone (no DB).
- `broadcast/tests/test_api.py::ManualRecipeTest` — recipe endpoint gating (200/409/403/404).
- `broadcast/tests/test_api.py::SubmitRealTest` — promote dry→real & re-queue,
  skip already-real targets, 400/403/404.
- `broadcast/tests/test_api.py::CancelJobTest` — skip pending + mark canceled,
  leave finished targets alone, no-op on a done job, 403/404.
- Run: `uv run python manage.py test broadcast`. (Neon test DB: if a prior run
  left a stale session blocking the drop, terminate it via `pg_terminate_backend`
  on `test_neondb`, or use `--keepdb`. See `project_gotchas` memory.)

## Outstanding / placeholders (TODO before prod)

- **Prod SPA origin** in `manifest.json` `externally_connectable.matches` and
  `background.js` `ALLOWED_ORIGINS` (currently `broadcast.thecommons.example`).
- `VITE_BROADCAST_EXTENSION_ID` in `broadcastWeb/.env`; `WEB_STORE_URL` in
  `hooks/useExtension.ts`; pinned `key` in `manifest.json` (see extension README).
- Verify `triangle_on_the_cheap` `submit_selector` (`#gform_submit_button_5`)
  against a `capture_broadcast_form` dump.
- **Access-code Verify** is a client-only stub (marks verified when the field is
  non-empty); there's no `verify` endpoint yet — wire one if real validation
  should gate Preview.

## Out of scope (v1)

Firefox; a backend success-report API / DB status flip for the manual (captcha)
path — the extension submit stays client-optimistic; porting the full server-side
imperative logic into JS beyond the hardcoded select2/terms drivers; the other 8
adapters (extend the same `recipe_fields` pattern later).
