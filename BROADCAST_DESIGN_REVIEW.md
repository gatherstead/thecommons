# Broadcast Design Doc — Repo Cross-Check & Missing Context

> **Read this alongside `BROADCAST_DESIGN.md` (or whatever the design doc file is named).** This document audits that doc against the actual state of the `thecommons` repo on the `arya/deployment-spike` branch (as of 2026-06-09) and supplies the concrete file paths, line numbers, code snippets, and patches the implementing agent (Claude Code / "fable") will need so it does not have to re-derive repo conventions during a one-shot build.
>
> **Trust order on conflict:** code > canonical repo docs (`AGENTS.md`, `ARCHITECTURE.md`, `CODING_STYLE.md`, `DEPLOY.md`) > the broadcast design doc > this review. If anything below contradicts the code on disk, the code wins.

---

## Table of Contents

1. [What the design doc already gets right](#1-what-the-design-doc-already-gets-right)
2. [Inaccuracies in the design doc — must be corrected](#2-inaccuracies-in-the-design-doc--must-be-corrected)
3. [Missing repo context — add to the doc](#3-missing-repo-context--add-to-the-doc)
4. [Concrete patches to apply to the design doc](#4-concrete-patches-to-apply-to-the-design-doc)
5. [Repo conventions cheat sheet (paste as an appendix)](#5-repo-conventions-cheat-sheet-paste-as-an-appendix)
6. [Verification checklist](#6-verification-checklist)

---

## 1. What the design doc already gets right

These claims hold against the actual repo — no change needed, listed for completeness so reviewers know what was checked:

- **Python 3.13, Django 6, `uv` package manager**, `python manage.py migrate`, `python manage.py test` — matches `backendServer/pyproject.toml` (`requires-python = ">=3.13"`, `django ==6.0.1`).
- **Oracle ARM64 VM, 6 GB RAM, Ubuntu 24.04** — matches `DEPLOY.md` §VM Specs. Bundled-Chromium-only stance is correct: Playwright's branded Chrome channel is unsupported on arm64 Linux.
- **nginx + Cloudflare proxied DNS, Full strict TLS**, origin cert at `/etc/ssl/cloudflare/thecommons.town.{pem,key}` — matches `DEPLOY.md` lines 20–22.
- **systemd service pattern** (`gunicorn.service`, `nextjs.service`) — adding `broadcast-worker.service` fits cleanly (`DEPLOY.md` §Services).
- **`neon_auth` owned by Better Auth, mirrored with `managed = False`**, never migrated by Django — matches `events/models.py:31–116` and `ARCHITECTURE.md` §Auth Bridge. The `db_table = 'neon_auth"."user'` double-quote injection trick is used to reference cross-schema tables.
- **DB-backed queue with `FOR UPDATE SKIP LOCKED`** is the right call — there is no Celery, Redis, django-tasks, or background-worker library in the project today (confirmed via grep of `pyproject.toml`).
- **`views.py` (thin) + `services.py` (business logic) split** is already the house pattern — `CODING_STYLE.md` line 60 mandates it; `ingestion/services.py` + `ingestion/views.py` demonstrate it.
- **django-unfold** is the admin (`backend/settings/base.py:108–153`) — adding `broadcast/admin.py` with Unfold registrations is consistent.
- **`python-dotenv`** loads env vars (`backend/settings/base.py:6`) — `BROADCAST_*` keys plug straight in via `os.getenv()`.
- **Newspaper aesthetic claims** (cream bg, Georgia, dark red accent, no shadows / pills / gradients / web fonts) match `theCommonsWeb/src/app/globals.css` exactly.
- **CORS / CSRF env conventions** (`CORS_EXTRA_ORIGINS`, `CSRF_TRUSTED_ORIGINS`, comma-separated, appended to defaults) exist at `backend/settings/base.py:40,43`.
- **No `broadcast/` Django app and no `broadcastWeb/` directory exist yet** — clear runway.

---

## 2. Inaccuracies in the design doc — must be corrected

### 2.1 The source for design tokens is `globals.css`, not a separate `tokens.css`

**Doc claim (§2.1, §11, §17):** "Design tokens are **copied** into `broadcastWeb/src/styles/tokens.css`" — implying a `tokens.css` exists in `theCommonsWeb` to copy from.

**Reality:** There is no `tokens.css` file in `theCommonsWeb`. The newspaper tokens live in `theCommonsWeb/src/app/globals.css`, mingled with Tailwind v4 base imports (`@import "tailwindcss"`) and a small set of utility classes:

```
--color-bg:           #f4f1eb   /* newsprint cream */
--color-bg-alt:       #eae6dd
--color-text:         #1a1a1a
--color-text-muted:   #555555
--color-link:         #1a1a1a
--color-link-hover:   #8b0000
--color-border:       #1a1a1a
--color-border-light: #c8c3b8
--color-accent:       #8b0000

--font-headline: Georgia, "Times New Roman", serif
--font-body:     Georgia, "Times New Roman", serif
--font-sans:     system-ui, -apple-system, "Segoe UI", sans-serif

/* utilities */
.rule-thick   { border-top: 3px solid var(--color-border); }
.rule-double  { border-top: 3px double var(--color-border); }
.drop-cap::first-letter { ... }
.skeleton-block { animation: ebb 1.8s ease-in-out infinite; }
@keyframes ebb { ... }
```

**Fix:** Spell out exactly what to copy and what to leave behind. See §4 patch 2.1.

### 2.2 The doc once calls the broadcast frontend "Next.js" in the architecture diagram

**Doc claim (§3 ASCII diagram):**
```
broadcast.thecommons.town  (Next.js /broadcast)
```

**Reality:** The rest of the doc commits to a standalone Vite + React SPA served as static files by nginx. The label in the diagram is leftover from an earlier draft and will confuse the implementer.

**Fix:** Replace the label with `(static Vite SPA via nginx)`. See §4 patch 3.

### 2.3 DRF has no global authentication / permission config — per-view is the pattern

**Doc claim (§9):** *"Use `BearerTokenAuthentication` is **not** appropriate here (no users). Use a tiny custom permission that checks the access code…"*

The conclusion is right but the implementer needs to know there is **no `REST_FRAMEWORK` dict** in `backend/settings/base.py`. Auth in this codebase is always per-view via decorators or `APIView` class attributes (see `events/views.py`, `ingestion/views.py`). There is no global default to override.

There is also already a `backend/permissions.py` containing:

```python
class HasCommonsAPIKey(BasePermission): ...
class HasCommonsAPIKeyOrUser(BasePermission): ...
class BearerTokenAuthentication(BaseAuthentication): ...
```

To respect the broadcast isolation contract (broadcast app imports nothing from the rest of the project), put the new permission at **`broadcast/permissions.py`** with a non-colliding name, e.g. `HasBroadcastAccessCode`.

### 2.4 `npm install` is forbidden — `pnpm` is mandatory

**Doc claim:** `broadcastWeb` uses `pnpm install` ✓ (correct).

**Risk:** The repo's root `CLAUDE.md` has a one-line "Quick Start" that shows `npm install` for `theCommonsWeb`. `DEPLOY.md` lines 103–104 are explicit:

> "Never use `npm install` — it re-resolves deps and breaks peer dependency pinning. Use `pnpm install` and `pnpm run build`."

An agent skimming `CLAUDE.md` for the install command could mis-pick `npm` for `broadcastWeb` too. Add a guardrail in §17.

### 2.5 The frontend service layer uses raw `fetch`, no shared wrapper

**Doc claim (§9):** "API layer in `src/services/broadcastApi.ts` … No raw `fetch` in components."

**Reality:** `theCommonsWeb/src/services/eventService.ts`, `businessService.ts`, `profileService.ts` all use **plain `fetch`** directly inside the service functions — no axios, no shared `apiClient.ts` wrapper, just `await fetch(...)` with manual `response.ok` checks and a `transformBackendX → FrontendX` mapping function per endpoint. The constants `API_BASE` and `API_KEY` are read from `process.env.NEXT_PUBLIC_*` at module top.

For consistency, `broadcastWeb/src/services/broadcastApi.ts` should follow the same pattern, just substituting `import.meta.env.VITE_BROADCAST_API_BASE_URL`.

### 2.6 nginx is a **single** config file, not per-site files

**Doc claim (§11):** "new server block `broadcast.thecommons.town`".

**Reality (DEPLOY.md line 84):** *"Config: `/etc/nginx/sites-available/thecommons` (symlinked into `sites-enabled/`)"* — one file with multiple `server { }` blocks. The implementer must **edit the existing `thecommons` file** and add another `server { }` block, not create `/etc/nginx/sites-available/broadcast.thecommons.town`.

### 2.7 The existing Cloudflare origin cert almost certainly does not cover `broadcast.thecommons.town`

**Doc claim (§11):** "use a **wildcard** origin cert (`*.thecommons.town`) or add the SAN. Verify before enabling the subdomain."

**Reality:** `DEPLOY.md` only documents `/etc/ssl/cloudflare/thecommons.town.pem` / `.key` — no wildcard mentioned. Cloudflare's default origin cert covers the exact hostnames you ask for at issuance time. The implementer should **assume the existing cert does not cover the new subdomain** and reissue (wildcard `*.thecommons.town` or a SAN-extended cert) before enabling the nginx block. Make this a **prerequisite step**, not a "verify" item.

### 2.8 Cloudflare DNS — record type matters

**Doc claim (§11):** "add `broadcast` record (proxied / orange cloud), like the others".

**Detail to add:** `DEPLOY.md` only documents A records for `thecommons.town` and `api.thecommons.town` pointing at `129.80.229.41`. Specify the new record as an **A record → `129.80.229.41`** (not a CNAME), proxied.

### 2.9 Quick Start in `CLAUDE.md` uses `npm install` for theCommonsWeb

**Drift to flag:** Repo root `CLAUDE.md`:

```
cd theCommonsWeb && npm install && npm run dev
```

contradicts `DEPLOY.md`'s pnpm mandate. Not your bug to fix, but worth knowing the contradiction exists so the implementer doesn't trust the wrong one.

---

## 3. Missing repo context — add to the doc

These aren't wrong in the doc — they're just missing. The implementing agent will want them. Add as a "Repo Conventions Cheat Sheet" appendix (see §5 below for paste-ready text).

### 3.1 Exact files to wire into

| Thing to wire | File | Lines |
|---|---|---|
| Register `broadcast` in `INSTALLED_APPS` | `backendServer/backend/settings/base.py` | 10–22 |
| Mount `/broadcast/` URLs | `backendServer/backend/urls.py` | (alongside `events.urls`, `ingestion.urls`) |
| Read `CORS_EXTRA_ORIGINS` | `backendServer/backend/settings/base.py` | 40 |
| Read `CSRF_TRUSTED_ORIGINS` | `backendServer/backend/settings/base.py` | 43 |
| `corsheaders` middleware | `backendServer/backend/settings/base.py` MIDDLEWARE | already present |
| Existing permissions (do NOT import from broadcast app) | `backendServer/backend/permissions.py` | 7–73 |
| Better Auth JWT verification (not used by broadcast) | `backendServer/backend/jwt_auth.py` | 48–68 |
| Newspaper tokens to copy | `theCommonsWeb/src/app/globals.css` | `:root { … }` and utility blocks |
| Service-layer pattern to mirror | `theCommonsWeb/src/services/eventService.ts` | whole file |
| `.env.example` location convention | `backendServer/.env.example`, `theCommonsWeb/.env.example` | per-project root |

### 3.2 No rate-limiter exists today — pick a concrete approach in the doc

The doc says "rate-limit … (e.g. simple DB or cache counter)". The repo has none. Pick one in the doc so fable doesn't pick a third:

**Recommended:** add [`django-ratelimit`](https://django-ratelimit.readthedocs.io/) to `backendServer/pyproject.toml`, decorate the broadcast views:

```python
from django_ratelimit.decorators import ratelimit
@ratelimit(key="ip", rate="10/m", method="POST", block=True)  # /preview
@ratelimit(key="ip", rate="3/m",  method="POST", block=True)  # /submit
```

Default cache backend in `base.py` will need to be confirmed; if it's local-memory (Django default), that's fine for the single-VM deployment. If a real cache is configured, double-check.

**Alternative (no new dep):** a tiny `BroadcastRateLimit(ip, window_start, count)` model checked inside `HasBroadcastAccessCode.has_permission`.

### 3.3 Existing background-work pattern is `CRON_SECRET`-bearer + management command

`ingestion/views.py:35–42` exposes `GET /api/cron/ingest` guarded by a `CRON_SECRET` bearer token; it shells out to `manage.py ingest_events` (the importer pipeline). That is the **only** existing async-ish path in the project.

Broadcast intentionally diverges: a long-running `systemd` service (`broadcast-worker`) consuming a DB queue, not a webhook-triggered command. Call this out in §3 so the implementer doesn't reach for the cron pattern out of muscle memory.

### 3.4 The iptables REJECT-before-ACCEPT gotcha

`DEPLOY.md` §Firewall (lines 170–185):

> Ubuntu OCI images ship with a catch-all `REJECT` rule. The ACCEPT rules for 80/443 must appear **before** that rule in the INPUT chain. Use `sudo iptables -I INPUT 5 -p tcp --dport 443 -m state --state NEW -j ACCEPT` (insert at position 5), not `-A` (append).

**Relevance:** Adding the broadcast subdomain reuses ports 80/443, so **no new firewall rules are needed**. But if `curl https://broadcast.thecommons.town/` returns nothing after deploy, *this is the cause*. Promote the parenthetical pointer in the doc to a numbered debugging callout in §11.

### 3.5 The `dev` vs `prod` settings split

Layout: `backendServer/backend/settings/{base,dev,prod}.py`. `DATABASE_URL` is parsed in both `dev.py:11–22` and `prod.py:11–22`. New `BROADCAST_*` env-driven settings live in `base.py` (single source). No environment-specific behavior needed.

### 3.6 Tag taxonomy overlap with `events.Category` / `events.Town`

The repo already has canonical `Town` and `Category` SQL tables in the `events` app (`AGENTS.md` notes town slug → FK resolution at ingest). The broadcast `locality` / `categories` controlled lists in §6 are **intentionally independent** because `broadcast/` imports nothing from `events/` (isolation contract).

Add one explicit sentence to §6 so the implementer doesn't try to DRY this up:

> The locality / category vocabularies here are duplicated by design — `broadcast/` must not import from `events/`. If a future client demands taxonomy syncing, that is a migration, not a v1 concern.

### 3.7 Brevo email is available if v2 wants completion notifications

`events/email_service.py` wraps Brevo transactional email. v1 polls for status (correct, per design doc). If "email me when the broadcast finishes" gets added later, the integration point already exists. Note in §16 / Open Question #3 for future reference.

### 3.8 Frontend types live in `src/models/` as per-domain files

`theCommonsWeb/src/models/`:
- `authModels.ts` — `UserType`, `AuthUser`, `EnterPayload`, `LoginPayload`
- `businessModels.ts` — `BusinessProfile`, `BusinessPayload`
- `eventsModels.ts` — `FrontendEvent`, `BackendEvent`, `EventPayload`, `transformBackendEvent(...)`

Mirror this in `broadcastWeb/src/models/broadcastModels.ts` (or split: `broadcastModels.ts` + `siteModels.ts`). The repo pattern is to keep both `FrontendX` and `BackendX` types in the same file with a transformation function between them.

### 3.9 Isolation test — paste-ready snippet

The doc says *"Enforce with a small test that asserts no such imports exist."* Concrete recipe for `broadcastServer/broadcast/tests/test_isolation.py`:

```python
import ast
import pathlib
from django.test import SimpleTestCase

FORBIDDEN_ROOTS = {"events", "ingestion"}

class IsolationTest(SimpleTestCase):
    def test_broadcast_imports_nothing_from_events_or_ingestion(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        offenders = []
        for path in root.rglob("*.py"):
            if "tests" in path.parts:
                continue
            tree = ast.parse(path.read_text(), filename=str(path))
            for node in ast.walk(tree):
                mods = []
                if isinstance(node, ast.ImportFrom) and node.module:
                    mods.append(node.module)
                if isinstance(node, ast.Import):
                    mods.extend(a.name for a in node.names)
                for m in mods:
                    if m.split(".")[0] in FORBIDDEN_ROOTS:
                        offenders.append((str(path), m))
        self.assertFalse(offenders, f"isolation breach: {offenders}")
```

(Refine to taste — the point is to give fable an enforceable concrete test, not a vague directive.)

### 3.10 Existing management commands (precedents to learn from)

```
events/management/commands/
  delete_user.py, seed_dev.py, send_digest.py, send_test_digest.py, send_weekly_digest.py
ingestion/management/commands/
  ingest_events.py, cleanup_old_events.py
```

The implementer can mimic the structure of `ingest_events.py` for `run_broadcast_worker`, `scaffold_adapter`, and `broadcast_dry_run`.

### 3.11 Static files and admin CSS — already handled

`DEPLOY.md` line 90 routes `api.thecommons.town/static/` → `backendServer/staticfiles/` for Django admin assets. Since broadcast uses django-unfold via the same admin, no additional nginx static config is needed.

### 3.12 ARM64 Chromium specifics for `playwright install`

Worth being explicit in the deploy section: `uv run playwright install chromium` downloads the Chromium build to `~/.cache/ms-playwright/` (per-user). The `broadcast-worker` systemd unit runs as `ubuntu`, so the cache will land under `/home/ubuntu/.cache/ms-playwright/` — that path must be readable by the service user. `playwright install-deps chromium` installs system libs via `apt` and requires `sudo`.

**Never** run `playwright install chrome` or set `channel="chrome"` — Google's branded Chrome is not built for arm64 Linux, and Playwright will fail at runtime.

---

## 4. Concrete patches to apply to the design doc

Apply these inline to the design doc before handing it to fable. Each row is a "find → replace" or insertion at the named section.

### Patch 1 — §2.1 "Frontend (hard separation)" bullet

**Find:**
> Design tokens are **copied** into `broadcastWeb/src/styles/tokens.css`, not imported.

**Replace with:**
> Design tokens are **copied** from `theCommonsWeb/src/app/globals.css` into `broadcastWeb/src/styles/tokens.css`. Copy the `:root { --color-* ; --font-* ; --focus-ring }` block and the utility classes (`.rule-thick`, `.rule-double`, `.drop-cap`, `.skeleton-block`, the `@keyframes ebb`). **Do not** pull `@import "tailwindcss"` or any Tailwind directive — `broadcastWeb` is hand-written CSS only. If the palette changes later, copy the new values over; the two apps are not meant to stay byte-identical.

### Patch 2 — §3 architecture diagram label

**Find:**
```
broadcast.thecommons.town  (Next.js /broadcast)
```
**Replace with:**
```
broadcast.thecommons.town  (static Vite SPA via nginx)
```

### Patch 3 — §7 "Access-code gate" — pin the rate-limit strategy

**Add after the existing rate-limit bullet:**
> **Concrete choice:** add `django-ratelimit` to `backendServer/pyproject.toml`. Decorate `/preview` with `@ratelimit(key="ip", rate="10/m", method="POST", block=True)` and `/submit` with `@ratelimit(key="ip", rate="3/m", method="POST", block=True)`. The repo currently has no rate-limit infrastructure; do not roll a custom counter unless adding the dep is rejected.

### Patch 4 — §9 "API" intro paragraph

**Find:**
> Use `BearerTokenAuthentication` is **not** appropriate here (no users). Use a tiny custom permission that checks the access code in the body/header, plus per-IP rate limiting.

**Replace with:**
> The repo has no global `REST_FRAMEWORK` config — DRF auth/permissions are set **per-view** via decorators (see `events/views.py`, `ingestion/views.py`). Existing `backend/permissions.py` holds `HasCommonsAPIKey`, `HasCommonsAPIKeyOrUser`, `BearerTokenAuthentication`; do **not** reuse those for broadcast. Add a new permission `HasBroadcastAccessCode` at `broadcastServer/broadcast/permissions.py` (the broadcast app imports nothing from the rest of the project — isolation contract). Apply it via `@permission_classes([HasBroadcastAccessCode])` on each broadcast view.

### Patch 5 — §9 frontend service-layer note

**Append to the "API layer in `src/services/broadcastApi.ts`" bullet:**
> Mirror the pattern in `theCommonsWeb/src/services/eventService.ts`: plain `fetch` per call, `await response.ok` checks, log `console.error` on failure, transform `BackendX → FrontendX` via a per-endpoint function. No shared `apiClient` wrapper exists in the repo; do not introduce one for v1.

### Patch 6 — §11 nginx subsection

**Find:**
> **nginx:** new server block `broadcast.thecommons.town`…

**Replace with:**
> **nginx:** edit the existing single config file at `/etc/nginx/sites-available/thecommons` (symlinked into `sites-enabled/`) and **add a new `server { }` block** for `broadcast.thecommons.town`. Do not create a new sites-available file. Serve the static SPA directly: `root /home/ubuntu/thecommons/broadcastWeb/dist; try_files $uri /index.html;`. No proxy to a Node process. The form POSTs to `api.thecommons.town`, which already proxies to gunicorn — broadcast adds Django routes only, no new server block for the API.

### Patch 7 — §11 TLS subsection — make wildcard a prerequisite

**Find:**
> **TLS:** the Cloudflare origin cert must cover `broadcast.thecommons.town` — use a **wildcard** origin cert (`*.thecommons.town`) or add the SAN. Verify before enabling the subdomain.

**Replace with:**
> **TLS (prerequisite, not a verify-step):** the existing origin cert at `/etc/ssl/cloudflare/thecommons.town.{pem,key}` was issued for the exact hostnames `thecommons.town` and `api.thecommons.town` and **does not cover `broadcast.thecommons.town`**. Before enabling the new nginx block, in the Cloudflare dashboard reissue an origin cert covering `*.thecommons.town` (wildcard) or `thecommons.town, *.thecommons.town`, replace both files on the VM, and `sudo nginx -t && sudo systemctl reload nginx`. **Skipping this step makes the subdomain throw a 526 / SSL handshake error from Cloudflare.**

### Patch 8 — §11 firewall subsection

**Find:**
> **Firewall:** no change — same 80/443 already open (mind the iptables REJECT-before-ACCEPT gotcha from `DEPLOY.md`).

**Replace with:**
> **Firewall:** no rule changes (80/443 already open). **If `curl https://broadcast.thecommons.town/` returns nothing after deploy:** OCI Ubuntu images ship with a catch-all `REJECT` rule in iptables INPUT chain; verify with `sudo iptables -L INPUT -n --line-numbers` that the 80/443 ACCEPT rules sit *above* the REJECT. If not, `sudo iptables -I INPUT 5 -p tcp --dport 443 -m state --state NEW -j ACCEPT` (insert at position 5; `-A` is wrong). See `DEPLOY.md` lines 170–185.

### Patch 9 — §11 Cloudflare DNS

**Find:**
> **Cloudflare DNS:** add `broadcast` record (proxied / orange cloud), like the others.

**Replace with:**
> **Cloudflare DNS:** add an **A record** `broadcast` → `129.80.229.41`, proxied (orange cloud). The existing records are all A records (no CNAMEs) — match the pattern.

### Patch 10 — §14 testing — reference the isolation snippet

**Append to §14:**
> **Isolation test (mandatory):** drop the AST-walking test from `BROADCAST_DESIGN_REVIEW.md §3.9` into `broadcastServer/broadcast/tests/test_isolation.py`. CI must fail if any non-test file under `broadcast/` imports from `events.` or `ingestion.`.

### Patch 11 — §15 build order, insert step 9.5

**Insert between current steps 9 and 10:**
> 9.5. **Cloudflare origin cert reissue** as `*.thecommons.town` wildcard (or SAN-extended). Replace `/etc/ssl/cloudflare/thecommons.town.{pem,key}` on the VM, `sudo nginx -t`, `sudo systemctl reload nginx`. This must land **before** the nginx server block for `broadcast.thecommons.town` is enabled.

### Patch 12 — §17 guardrails — add three lines

**Append to the bullet list:**
> - **`broadcastWeb` is pnpm-only** — `DEPLOY.md` is emphatic that `npm install` breaks peer-dependency pinning across the repo. The root `CLAUDE.md` Quick Start mentions `npm` for `theCommonsWeb`; treat `DEPLOY.md` as the canon.
> - **No global DRF auth** — apply `HasBroadcastAccessCode` per-view, do not register a global `DEFAULT_PERMISSION_CLASSES`.
> - **Bundled Chromium only** — `uv run playwright install chromium`; never `chrome`, never set `channel="chrome"`. arm64 has no branded Chrome.

### Patch 13 — §6 taxonomy note

**Append to §6 intro:**
> The locality / category vocabularies below are **deliberately independent of `events.Town` and `events.Category`**. The `broadcast/` app must not import from `events/` (isolation contract, §2.1). Do not "DRY this up" by reusing the events choices — if a third client later needs synced taxonomies, that is a v2 migration.

### Patch 14 (optional) — Appendix B "Repo Conventions Cheat Sheet"

Paste the table and snippets from §5 below as a new appendix.

---

## 5. Repo conventions cheat sheet (paste as an appendix)

### File-path map

| Concern | Path |
|---|---|
| Django settings (base) | `backendServer/backend/settings/base.py` |
| Django settings (dev) | `backendServer/backend/settings/dev.py` |
| Django settings (prod) | `backendServer/backend/settings/prod.py` |
| Root URLconf | `backendServer/backend/urls.py` |
| Existing permissions / JWT auth | `backendServer/backend/permissions.py`, `backendServer/backend/jwt_auth.py` |
| Existing apps to mimic structure of | `backendServer/events/`, `backendServer/ingestion/` |
| Existing services pattern | `backendServer/ingestion/services.py` |
| Existing management commands | `backendServer/{events,ingestion}/management/commands/` |
| Existing email integration | `backendServer/events/email_service.py` (Brevo) |
| Frontend design tokens (source) | `theCommonsWeb/src/app/globals.css` |
| Frontend service-layer pattern | `theCommonsWeb/src/services/eventService.ts` |
| Frontend model/type pattern | `theCommonsWeb/src/models/eventsModels.ts` |
| Frontend env example | `theCommonsWeb/.env.example` |
| Backend env example | `backendServer/.env.example` |
| nginx config | `/etc/nginx/sites-available/thecommons` (one file, many `server { }` blocks) |
| systemd units | `/etc/systemd/system/{gunicorn,nextjs,broadcast-worker}.service` |
| TLS certs | `/etc/ssl/cloudflare/thecommons.town.{pem,key}` (reissue as wildcard) |
| Gunicorn socket | `/run/gunicorn/gunicorn.sock` |
| VM IP | `129.80.229.41` |

### Versions (as of 2026-06-09, branch `arya/deployment-spike`)

- Python `>=3.13` · Django `==6.0.1` · DRF `==3.16.1` · PyJWT
- Node frontend: Next.js 16 · React 19 · TypeScript ~5.9 · Tailwind CSS v4 · pnpm
- Postgres on Neon (shared between Better Auth's `neon_auth` schema and Django's `public` schema)

### Auth model — at a glance

- **Django has no app-level user accounts.** `BetterAuthUser` is a read-only mirror of `neon_auth.user` with `managed = False` (`events/models.py:31–116`).
- DRF auth is per-view. Existing patterns: `HasCommonsAPIKey`, `HasCommonsAPIKeyOrUser`, `BearerTokenAuthentication` (JWT verified against Better Auth JWKS).
- Broadcast does **not** use any of these. It uses an access code from the env, validated server-side per request via `HasBroadcastAccessCode` (`broadcast/permissions.py`, new file).
- Never touch `neon_auth.*` — Better Auth (the Next.js side) owns it.

### Background-work pattern (existing) vs broadcast (new)

| Aspect | Existing (`ingest_events`) | Broadcast (new) |
|---|---|---|
| Trigger | `GET /api/cron/ingest` with `CRON_SECRET` bearer (`ingestion/views.py:35–42`) | `systemd` long-running service consuming a DB queue |
| Implementation | shells out to `manage.py ingest_events` | `manage.py run_broadcast_worker` (loop) |
| Concurrency | one-shot per cron tick | `BROADCAST_MAX_CONCURRENCY` env, default 1 |
| Why different | ingestion is bursty + idempotent; broadcast is interactive + long-tail |

### Env conventions

- **Loader:** `python-dotenv` (`backend/settings/base.py:6`), read via `os.getenv(...)`.
- **Comma-separated extra origins:** `CORS_EXTRA_ORIGINS` (append to defaults, `base.py:40`), `CSRF_TRUSTED_ORIGINS` (`base.py:43`). Add `https://broadcast.thecommons.town` to both.
- **Frontend env:** Next.js uses `NEXT_PUBLIC_*`. The new SPA uses Vite's `VITE_*` (`import.meta.env.VITE_BROADCAST_API_BASE_URL`). These are exposed to the browser — never put the access code in either.
- **`.env.example` lives at each project root** (`backendServer/.env.example`, `theCommonsWeb/.env.example`). Add `broadcastWeb/.env.example` likewise.

### Deploy commands (consolidated; supersedes the design doc's §11 if both drift)

```bash
# Backend (shared with broadcast Django app)
cd /home/ubuntu/thecommons && git pull
cd backendServer
uv sync                                      # if pyproject.toml changed
uv run playwright install chromium           # first deploy / version bump (bundled Chromium ONLY — never "chrome")
uv run playwright install-deps chromium      # system libs (apt; needs sudo)
uv run python manage.py migrate              # broadcast migrations
uv run python manage.py collectstatic --noinput   # if static changed
sudo systemctl restart gunicorn
sudo systemctl restart broadcast-worker      # NEW unit

# Existing frontend (UNCHANGED — do not run npm install)
cd ../theCommonsWeb
pnpm install
pnpm run build
sudo systemctl restart nextjs

# Broadcast frontend (NEW — static, no service)
cd ../broadcastWeb
pnpm install
pnpm run build                                # → broadcastWeb/dist/, served directly by nginx
sudo nginx -t && sudo systemctl reload nginx  # if nginx config changed
```

### Isolation test (paste into `broadcast/tests/test_isolation.py`)

```python
import ast
import pathlib
from django.test import SimpleTestCase

FORBIDDEN_ROOTS = {"events", "ingestion"}

class IsolationTest(SimpleTestCase):
    def test_broadcast_imports_nothing_from_events_or_ingestion(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        offenders = []
        for path in root.rglob("*.py"):
            if "tests" in path.parts:
                continue
            tree = ast.parse(path.read_text(), filename=str(path))
            for node in ast.walk(tree):
                mods = []
                if isinstance(node, ast.ImportFrom) and node.module:
                    mods.append(node.module)
                if isinstance(node, ast.Import):
                    mods.extend(a.name for a in node.names)
                for m in mods:
                    if m.split(".")[0] in FORBIDDEN_ROOTS:
                        offenders.append((str(path), m))
        self.assertFalse(offenders, f"isolation breach: {offenders}")
```

### Things absent from the repo that the design doc assumes you'll add

- Playwright (`uv add playwright`)
- `django-ratelimit` (recommended; see §3.2)
- `broadcastServer/broadcast/` Django app (new)
- `broadcastWeb/` Vite + React TS project (new)
- `broadcast-worker.service` systemd unit (new)
- A new `server { }` block in `/etc/nginx/sites-available/thecommons` (edit existing file)
- A wildcard `*.thecommons.town` Cloudflare origin cert (reissue and replace existing files)
- A Cloudflare DNS A record `broadcast` → `129.80.229.41`, proxied

---

## 6. Verification checklist

After patches are applied to the design doc and fable executes, sanity-check by:

1. **Tokens match disk.** Open `theCommonsWeb/src/app/globals.css` and `broadcastWeb/src/styles/tokens.css` side-by-side — every `--color-*` and `--font-*` should be byte-identical. If a token name has drifted (e.g., `--color-accent` renamed), update the SPA copy.
2. **No global DRF config sneaked in.** `grep REST_FRAMEWORK backendServer/backend/settings/base.py` → empty. (If non-empty, the per-view auth advice may need revision.)
3. **Isolation test passes.** `cd backendServer && uv run python manage.py test broadcast.tests.test_isolation`.
4. **Mock-form end-to-end runs.** `uv run python manage.py broadcast_dry_run --site triangle_on_the_cheap --fixture pittsboro_music.json` produces a screenshot and a `succeeded [DRY RUN]` row in `BroadcastTarget`.
5. **`api.thecommons.town` accepts the new routes.** `curl -X POST https://api.thecommons.town/broadcast/preview -d '{}'` returns 403 (no access code), not 404.
6. **`broadcast.thecommons.town` serves the SPA.** `curl -I https://broadcast.thecommons.town/` returns 200 with `text/html`. If it returns 526 / SSL handshake error → origin cert wasn't reissued (§2.7).
7. **Firewall sanity.** If 6 fails with a hang / no response, run `sudo iptables -L INPUT -n --line-numbers` and confirm 80/443 ACCEPT lines are above the REJECT (§3.4).
8. **No cross-app imports.** `grep -rE "from (events|ingestion)" backendServer/broadcast/` → empty. `grep -rE "from broadcast" backendServer/{events,ingestion}/` → empty.
9. **Worker survives a kill -9.** `sudo systemctl kill -s SIGKILL broadcast-worker` → systemd restarts it; an in-progress `BroadcastTarget` row is re-claimed by the next loop (via `FOR UPDATE SKIP LOCKED` plus the unique `(submission, site_key)` constraint protecting against duplicate work).
10. **No Chrome channel anywhere.** `grep -rE "channel.*chrome|playwright install chrome" backendServer/` → empty.

If all 10 pass, the implementation matches both the design doc and the repo's invariants.
