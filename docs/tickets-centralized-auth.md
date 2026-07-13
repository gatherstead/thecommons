# Tickets — Centralized Auth Origin & DB-Backed Access Codes

Source PRD: `docs/prd-centralized-auth.md` (locked decisions D1–D7 apply). Confirmed with the user 2026-07-07:
- `client_label` for logged-in users = the **full lowercased email**.
- A trial "use" is recorded **only at `POST /broadcast/preview`** (idempotent per `draft_id`); ai-autofill / direct-recipe / submit never meter.
- broadcastWeb gets **classic email + password** login/signup forms (not the lazy `enter` flow).
- Infra work = repo config + a **manual checklist ticket** (R7); agents never touch DNS/VM.

## Build order

```
Wave 1 (parallel):  R1, R4, R5
Wave 2 (parallel):  R2 (needs R1), R3 (needs R1)
Wave 3:             R6 (needs R2, R5)
Wave 4:             R8 (needs R2, R3, R4, R6) · R7 is non-code, user-run after deploy
```

---

### [R1] Broadcast access foundation — models + `resolve_access`

**Why:** Access codes are static env strings that can't be generated, budgeted, expired, or revoked; logged-in users have no tier concept. This is the SQL + resolver foundation everything else builds on (PRD §5–§6).

**Context / affected files:**
- `backendServer/broadcast/models.py` — append `BroadcastAccess`, `AccessCode`, `AccessCodeUse` (schema verbatim from PRD §6; `AccessCodeUse` gets `related_name="uses"`, `unique_together (access_code, draft_id)`).
- `backendServer/broadcast/access.py` — currently env-code parsing (`resolve_client_label`); replace the module wholesale with `resolve_access`.
- `backendServer/broadcast/migrations/` — latest is `0004_alter_broadcastsubmission_status.py`; add `0005_*`.
- Hashing pattern to mirror: `backendServer/ingestion/access.py` (sha256 hexdigest + `hmac.compare_digest` across active rows so timing doesn't reveal which rows exist).
- JWT verification: `backend/jwt_auth.py::verify_better_auth_jwt(token) -> claims | None`. **Isolation guardrail:** `broadcast/` may import `backend.*` but never `events`/`ingestion` (`broadcast/tests/test_isolation.py`, `FORBIDDEN_ROOTS = {"events", "ingestion"}`). That means NO `BetterAuthUser` lookup — identity comes from the JWT's `email` claim directly.
- Tests: `broadcast/tests/test_access.py` (currently env-code tests, `@tag("fast")`) — rewrite; DB-backed cases go in a new `broadcast/tests/test_access_db.py` with `@tag("db")`.

**Approach:**
1. Models + migration (`uv run python manage.py makemigrations broadcast`).
2. In `access.py`, define a frozen dataclass `AccessResult(tier: int, identity: str | None, is_trial: bool, uses_remaining: int | None, client_label: str | None)` and `resolve_access(request, draft_id: str | None = None) -> AccessResult`:
   - `Authorization: Bearer <jwt>` → `verify_better_auth_jwt` → `claims["email"].lower()` → `BroadcastAccess` row's tier, else tier 0. `client_label` = the email. `is_trial=False`, `uses_remaining=None`. ⚠️ ASSUMPTION: Better Auth's `jwt()` plugin includes `email` in the token payload by default — assert this in a test with a stubbed claims dict; if the live token lacks it, R5 adds `definePayload`. A JWT that verifies but has no email claim → no access.
   - Else code from header `X-Broadcast-Access-Code` or body `access_code` → sha256 → constant-time match over `AccessCode.objects.filter(is_active=True)` → reject if `expires_at` passed → budget: `uses_remaining = max_uses - code.uses.count()` (None when `max_uses` is NULL = unlimited). Over budget is still allowed **iff** `draft_id` is already counted for that code (edits are free, D6). Result: code's tier, `identity`/`client_label` = `AccessCode.label`, `is_trial=True`.
   - Else `AccessResult(tier=0, identity=None, is_trial=False, uses_remaining=None, client_label=None)`.
3. `resolve_access` only *reads*; recording an `AccessCodeUse` is R2's job (preview view).
4. Keep the module docstring accurate (codes now in SQL, raw never stored).

**Acceptance criteria:**
- [ ] Migration applies cleanly; three tables exist with the PRD §6 fields/constraints.
- [ ] `resolve_access` covers: valid JWT + grant row → that tier; valid JWT, no row → tier 0 with email identity; valid code within budget → its tier, `is_trial=True`, correct `uses_remaining`; exhausted code + already-counted `draft_id` → allowed; exhausted + new `draft_id` → tier 0/no access; expired or `is_active=False` → no access; garbage/absent creds → tier 0.
- [ ] `broadcast/tests/test_isolation.py` still green.
- [ ] `DJANGO_SETTINGS_MODULE=backend.settings.test uv run python manage.py test broadcast` passes.

**Depends on:** none
**Can parallelize with:** R4, R5

---

### [R2] Tier-gated broadcast API, `GET /broadcast/access`, preview metering, kill env codes

**Why:** Endpoints must gate on tiers (AI = tier 2), the SPA needs one endpoint to drive tier-aware UI, and D2 is a hard cut: `BROADCAST_ACCESS_CODES` dies.

**Context / affected files:**
- `backendServer/broadcast/permissions.py` — `HasBroadcastAccessCode` (stamps `request.broadcast_client_label`); replace.
- `backendServer/broadcast/views.py` — all views use `@permission_classes([HasBroadcastAccessCode])`; `submit` reads `request.broadcast_client_label` (line ~68); `ai_autofill` is the tier-2 endpoint.
- `backendServer/broadcast/urls.py` — add `path("access", ...)`.
- `backendServer/backend/settings/base.py:111-112` (env-code comment) and `backend/settings/test.py` — remove `BROADCAST_ACCESS_CODES` references; also `backendServer/.env.example`.
- Tests referencing env codes: `broadcast/tests/test_api.py` (`@tag("db")`), `test_autofill.py`, and R1's rewritten access tests.
- Contract from R1: `broadcast.access.resolve_access(request, draft_id=None) -> AccessResult`.

**Approach:**
1. In `permissions.py`: `RequiresBroadcastTier1` / `RequiresBroadcastTier2` (`BasePermission`; shared base with `min_tier`). Each calls `resolve_access(request, draft_id=_draft_id_from(request))` where `_draft_id_from` reads top-level `request.data.get("draft_id")` falling back to `request.data.get("event", {}).get("draft_id")` (SPA sends `draft_id` inside `event` today; R6 adds it top-level on preview). Stamp `request.broadcast_access = result` and keep `request.broadcast_client_label = result.client_label` so `submit` keeps working. `message = "No broadcast access — log in or enter an access code."`
2. Swap decorators: preview / submit / job_detail / job_retry / job_submit_real / job_cancel / job_screenshot / job_manual_recipe / direct_recipe → `RequiresBroadcastTier1`; `ai_autofill` → `RequiresBroadcastTier2`. Rate limits unchanged.
3. **Metering (only here):** in `preview`, after serializer validation, if `request.broadcast_access.is_trial`: require a draft_id (400 `{"draft_id": "required"}` if absent — ⚠️ CONFIRM this shape) and `AccessCodeUse.objects.get_or_create(access_code=..., draft_id=...)`. `resolve_access` needs the matched `AccessCode` reachable — expose it on the result (e.g. private `_code` attr) or refactor as agreed with R1's shape.
4. New view `access_info` (GET, `AllowAny`-style — no permission class): `resolve_access(request)` → 200 `{tier, is_trial, uses_remaining}`. ⚠️ CONFIRM semantics: creds *absent* → 200 with `tier: 0`; creds *present but invalid* (bad code / bad JWT) → 403 so the SPA "Verify" can show failure. Rate-limit 30/m by IP.
5. Delete every `BROADCAST_ACCESS_CODES` code path (R1 already gutted `access.py`); update tests to create `AccessCode`/`BroadcastAccess` rows (db tier) and to stub `verify_better_auth_jwt` via `unittest.mock.patch` for JWT-path tests.
6. `docs/`-level drift (DEPLOY.md, docs/broadcast.md) is R8's — don't touch here.

**Acceptance criteria:**
- [ ] `ai-autofill` returns 403 for tier 1 (grant or code), 200-path for tier 2.
- [ ] All formerly code-gated endpoints accept **either** a Bearer JWT (grant tier ≥1) **or** a valid code, via header or body.
- [ ] Preview with a trial code records exactly one `AccessCodeUse` per `draft_id` (re-preview same draft = no new row, still 200); 4th distinct draft on a 3-use code → 403; the same 4th call with an already-counted draft → 200.
- [ ] `GET /broadcast/access` returns `{tier, is_trial, uses_remaining}` per the semantics above.
- [ ] `submit` stores `client_label` = email (JWT) or `AccessCode.label` (code).
- [ ] `grep -r BROADCAST_ACCESS_CODES backendServer/` → nothing.
- [ ] `DJANGO_SETTINGS_MODULE=backend.settings.test uv run python manage.py test broadcast` passes; `--tag=fast` and `--tag=db` both pass repo-wide.

**Depends on:** R1
**Can parallelize with:** R3

---

### [R3] Access CLI — `set_broadcast_access`, `generate_access_code`, `list_access_codes`, `revoke_access_code`

**Why:** PRD §7 — tiers are granted by email from the terminal (deliberately decoupled from codes), and codes must be mintable/auditable/revocable without env edits.

**Context / affected files:**
- New files in `backendServer/broadcast/management/commands/` (dir exists; style reference: `run_broadcast_worker.py`, `broadcast_dry_run.py`).
- Models from R1 (`broadcast/models.py`); hashing helper from `broadcast/access.py`.
- Tests: new `broadcast/tests/test_commands_db.py`, `@tag("db")`, via `django.core.management.call_command` with `StringIO` stdout.

**Approach:** Four commands:
- `set_broadcast_access <email> <0|1|2>` — `update_or_create` on lowercased email; print old→new tier.
- `generate_access_code [--tier 2] [--uses 3 | --unlimited] [--expires ISO8601] [--label TEXT]` — `secrets.token_urlsafe(24)`; store only sha256; **print the raw code once** with a "will not be shown again" warning. `--unlimited` → `max_uses=None`; mutually exclusive with `--uses`.
- `list_access_codes` — label, tier, uses as `used/max` (`∞` for unlimited), active, expires. Never the hash prefix beyond 8 chars, never a raw code.
- `revoke_access_code <label|id>` — `is_active=False`; error listing candidates if a label is ambiguous.

**Acceptance criteria:**
- [ ] Generated code round-trips: `generate_access_code` output code passes R1's `resolve_access` with the right tier/budget.
- [ ] Raw code appears only in generate output; DB holds only the hash.
- [ ] `set_broadcast_access` is idempotent and case-insensitive on email.
- [ ] `revoke_access_code` makes the code fail resolution immediately.
- [ ] `DJANGO_SETTINGS_MODULE=backend.settings.test uv run python manage.py test broadcast --tag=db` passes.

**Depends on:** R1
**Can parallelize with:** R2

---

### [R4] Ingestion direct-submit: JWT-else-anonymous, drop `HostAccessGrant`

**Why:** PRD §5/§11-2 — tiers key off email now, so the code→user link (`HostAccessGrant`) is superseded. Direct-submit ownership comes from the JWT; anonymous/trial submissions carry no owner. Keeps broadcast/ingestion isolation with no second metering point.

**Context / affected files:**
- `backendServer/ingestion/access.py` — delete (`resolve_host_user`).
- `backendServer/ingestion/models.py:118-130` — delete `HostAccessGrant`.
- `backendServer/ingestion/admin.py` — remove `HostAccessGrantForm`/`HostAccessGrantAdmin` + import (lines ~9, 101-131).
- `backendServer/ingestion/migrations/0008_hostaccessgrant.py` — **delete the file** and repoint `0009_eventsource_direct_source_type.py`'s `dependencies` to `0007_seed_ingest_beat`. ⚠️ ASSUMPTION: 0008/0009 are untracked (never committed/deployed to prod), so rewriting the chain is safe; anyone whose dev DB applied 0008 must manually `DROP TABLE ingestion_hostaccessgrant` and delete its `django_migrations` row.
- `backendServer/ingestion/views.py::direct_submit` (lines 52-93) — swap `resolve_host_user` for JWT auth.
- `backendServer/ingestion/tasks.py::ingest_direct_submission_task(raw_event_id, user_id)` and `ingestion/services.py::ingest_direct_submission` (line 132; does `BetterAuthUser.objects.get(id=user_id)`) — make `user_id` nullable end-to-end (`submitted_by=None`, and any `created_by` attribution skipped when None).
- Tests: `ingestion/tests/test_direct_submission_db.py`, `test_direct_ingest_db.py` update; `ingestion/tests/test_access_db.py` delete.
- Auth plumbing to reuse: `backend/permissions.py::BearerTokenAuthentication` (JWT → `BetterAuthUser`; raises 401 on an invalid token; API-key bearer returns no user).

**Approach:** `direct_submit` becomes `@api_view(["POST"])` + `@authentication_classes([BearerTokenAuthentication])`, no permission class (anonymous allowed; the 10/m IP rate limit stays). `user_id = request.user.id if getattr(request.user, "is_authenticated", False) else None`. Drop the `access_code` read entirely (the SPA still sends it until R6 lands — unknown body keys are ignored, so ordering doesn't matter). Remove the 403 "access code not recognized" branch; update the module docstring/comments and the two test files: anonymous submit → 202 + `submitted_by is None`; Bearer submit → 202 + attributed; invalid Bearer → 401.

⚠️ CONFIRM: this makes `POST /api/events/direct-submit` callable by anyone at 10/m/IP (PRD-locked: "created_by = JWT-resolved BetterAuthUser, else None (trial). No second metering point"). Submissions still pass the standardize → safety-score → review pipeline before publication.

**Acceptance criteria:**
- [ ] `HostAccessGrant` gone from models/admin/migrations; `ingestion/access.py` deleted; migration graph valid (`uv run python manage.py makemigrations --check` clean).
- [ ] Anonymous direct-submit: 202, RawEvent upserted by `draft_id`, pipeline task queued with `user_id=None`, resulting `StagedEvent.submitted_by is None`.
- [ ] Authenticated direct-submit attributes `submitted_by`; invalid token → 401.
- [ ] `DJANGO_SETTINGS_MODULE=backend.settings.test uv run python manage.py test ingestion` passes; full `--tag=db` tier passes.

**Depends on:** none
**Can parallelize with:** R1, R5

---

### [R5] Auth origin (Phase 1) — theCommonsWeb serves `auth.thecommons.town`, shared cookie domain

**Why:** D1/D5 — one auth origin every SPA points at, cross-origin solved once via `.thecommons.town` cookies. Better Auth stays physically inside Next.js; this is config, not extraction.

**Context / affected files:**
- `theCommonsWeb/src/lib/auth.ts` — `betterAuth({ baseURL: process.env.BETTER_AUTH_URL ?? 'http://localhost:3000', plugins: [jwt(), lazyAuth(), nextCookies()], ... })`. No `trustedOrigins`, no cookie config today.
- `theCommonsWeb/src/lib/auth-client.ts` — `createAuthClient` (check/set its baseURL to `NEXT_PUBLIC_BETTER_AUTH_URL`).
- `theCommonsWeb/.env.example` (or `.env.local` example block) and `backendServer/.env.example` — document the new values. **Never touch real `.env` files** (repo guardrail).
- PRD §4/§10 for exact origins; D7: no speculative origins.

**Approach:**
1. `trustedOrigins`: `['https://thecommons.town', 'https://www.thecommons.town', 'https://broadcast.thecommons.town', 'http://localhost:3000', 'http://localhost:5173']` (+ optional comma-split env `BETTER_AUTH_TRUSTED_ORIGINS` for additions without code changes). ⚠️ CONFIRM list — PRD §10 also names `http://127.0.0.1:8000`, but Django never talks *to* the auth server as a browser origin; include only if a real flow needs it.
2. Cookie config, gated so dev (localhost, HTTP) is untouched: when `process.env.BETTER_AUTH_COOKIE_DOMAIN` is set →
   `advanced: { crossSubDomainCookies: { enabled: true, domain: process.env.BETTER_AUTH_COOKIE_DOMAIN }, defaultCookieAttributes: { sameSite: 'none', secure: true } }` (merged with the existing `advanced.database.generateId` setting). Unset in dev → current behavior. Prod sets `.thecommons.town` (one-time forced re-login, D5 — no active users).
3. Verify the JWT payload contains `email` (R1 depends on it). Better Auth `jwt()` includes the user record by default; if a decoded dev token lacks `email`, add `jwt({ jwt: { definePayload: ({ user }) => ({ email: user.email, name: user.name }) } })`.
4. Env examples: theCommonsWeb `BETTER_AUTH_URL=https://auth.thecommons.town`, `NEXT_PUBLIC_BETTER_AUTH_URL=https://auth.thecommons.town`, `BETTER_AUTH_COOKIE_DOMAIN=.thecommons.town` (prod-only comments; dev keeps localhost:3000). backendServer: note `BETTER_AUTH_JWKS_URL=https://auth.thecommons.town/api/auth/jwks` as the prod value (Django code path unchanged — `backend/jwt_auth.py` already reads the env).
5. No Django code changes in this ticket.

**Acceptance criteria:**
- [ ] `pnpm build` in `theCommonsWeb/` passes; `pnpm test:fast` + `test:db` pass.
- [ ] Dev flow unchanged: with no `BETTER_AUTH_COOKIE_DOMAIN`, cookies behave exactly as before (manual smoke: login on localhost:3000 still works).
- [ ] A JWT minted in dev contains an `email` claim (decode and assert in a test or documented manual check).
- [ ] `.env.example` files document every §10 value; real `.env` untouched.

**Depends on:** none
**Can parallelize with:** R1, R4

---

### [R6] broadcastWeb — login/signup/signout, Bearer JWTs, tier-aware UI

**Why:** PRD §9 — the access area gets real accounts (email+password per user decision); AI hides below tier 2; trials see remaining uses; the code path stays for anonymous use.

**Context / affected files:**
- `broadcastWeb/src/App.tsx` — Access section (lines ~363-430: access-code input + client-only "Verify" stub), AI Autofill section (~432-485, gate on `verified`), preview/submit handlers.
- `broadcastWeb/src/services/broadcastApi.ts` — every wrapper takes `accessCode: string` and sends it as body `access_code` or `X-Broadcast-Access-Code` header.
- `broadcastWeb/src/lib/persist.ts` — session persistence (`accessCode`, `verified`); do **not** persist JWTs (short-lived — fetch fresh via cookie).
- `broadcastWeb/src/models/broadcastModels.ts` — add the access-info type.
- New: `broadcastWeb/src/lib/authClient.ts`; `pnpm add better-auth` (pnpm 11 — never npm).
- Style: newspaper aesthetic (serif, cream/ink, no pills/gradients) per `CODING_STYLE.md`; test conventions per `broadcastWeb/AGENTS.md` (fast = node, db = jsdom, `vi.stubGlobal('fetch', …)`).
- Backend contract (from R2): `GET /broadcast/access` → `{tier, is_trial, uses_remaining}` (200 tier 0 when creds absent, 403 when creds invalid); all endpoints accept `Authorization: Bearer <jwt>` or the code header; **preview wants a top-level `draft_id`** for trial metering; `ai-autofill` 403s below tier 2. Direct-submit (R4): Bearer optional, no `access_code`.

**Approach:**
1. `authClient.ts`: `createAuthClient({ baseURL: import.meta.env.VITE_BETTER_AUTH_URL })` from `better-auth/react`; add `VITE_BETTER_AUTH_URL` to `.env.example` (dev `http://localhost:3000`, prod `https://auth.thecommons.town`).
2. Access section becomes two-mode: **Sign in / Create account** (email+password via `authClient.signIn.email` / `signUp.email`, signout button when a session exists, `useSession` for state) *or* the existing **access code** input. JWT minting: `GET ${VITE_BETTER_AUTH_URL}/api/auth/token` with `credentials: 'include'` → hold the token in React state; refetch on 401.
3. `broadcastApi.ts`: replace the `accessCode` first-arg with `auth: { jwt?: string; accessCode?: string }`; one helper builds headers (`Authorization: Bearer` wins, else `X-Broadcast-Access-Code`); stop sending `access_code` in bodies. Add `getAccess(auth)` (GET `/broadcast/access`) and send top-level `draft_id` in `previewBroadcast`. Update `directSubmit` to send only the Bearer header when present (no code).
4. Tier-aware UI driven by `getAccess` (called on login, on Verify click — which now actually verifies — and on app load when a session/code exists): AI Autofill section hidden below tier 2; trial mode shows "N uses remaining" (a use = one event previewed; edits free); logged-in tier 0 sees "This account has no broadcast access yet — contact The Commons." ⚠️ CONFIRM copy.
5. Update `__tests__` (`broadcastApi.fast.test.ts`, `isDraftEmpty.fast.test.ts` untouched logic) + add fast tests for the header-selection helper and access parsing.

**Acceptance criteria:**
- [ ] Logged-in tier-2 user: full flow (AI autofill visible, preview/fill) with only a Bearer header — no code anywhere.
- [ ] Tier-1 user: everything except the AI section (hidden, not just disabled).
- [ ] Trial code: uses_remaining rendered and decrements per new event previewed; exhausted code → clear error from the 403.
- [ ] Signout returns the UI to the access-entry state.
- [ ] `pnpm build` passes; `pnpm test` (fast + db) passes.

**Depends on:** R2 (endpoint + auth contract), R5 (auth client/env story)
**Can parallelize with:** —

---

### [R7] Infra cutover checklist — DNS, nginx, env, code regeneration (non-software)

**Why:** D1/D5 — the auth subdomain, shared cookie domain, and env cutover happen on Cloudflare + the VM by hand; the repo only carries config. One forced re-login is expected and accepted.

**Prompt for AI:** "Generate a numbered checklist of the concrete steps to serve the existing Better Auth (inside Next.js on :3000, single Oracle Cloud VM behind nginx, Cloudflare DNS/TLS Full-strict) at `https://auth.thecommons.town`, switch to a shared `.thecommons.town` cookie domain, and cut access codes over from env to DB. Include: (1) the Cloudflare DNS record; (2) the nginx server block for `auth.thecommons.town` proxying to the Next.js upstream (mirror the existing snippets in `deploy/`) and where TLS comes from under Cloudflare Full-strict; (3) exact env edits on the VM — theCommonsWeb: `BETTER_AUTH_URL`, `NEXT_PUBLIC_BETTER_AUTH_URL`, `BETTER_AUTH_COOKIE_DOMAIN=.thecommons.town`; backendServer: `BETTER_AUTH_JWKS_URL=https://auth.thecommons.town/api/auth/jwks`, ensure `CORS_EXTRA_ORIGINS` covers `https://broadcast.thecommons.town`; broadcastWeb build env: `VITE_BETTER_AUTH_URL`; and **removing `BROADCAST_ACCESS_CODES`**; (4) running `uv run python manage.py generate_access_code --label <operator>` per existing operator and delivering the raw codes; (5) service restarts (`nextjs`, `gunicorn`) + rebuilding both frontends; (6) smoke tests — login at the apex, JWT mint from `auth.thecommons.town`, an authed `/broadcast/access` call from `broadcast.thecommons.town`, and confirming the one-time forced re-login; (7) rollback notes (repoint JWKS + envs back). Where each value lives: `DEPLOY.md` is the source of truth for VM setup."

**Acceptance:** Result recorded as a checklist in `DEPLOY.md` (or a linked runbook), executed on the VM, smoke tests green, `BROADCAST_ACCESS_CODES` absent from the VM env.

**Depends on:** R2, R3, R5 deployed (R6 for the final smoke test)
**Can parallelize with:** R8 (doc writing)

---

### [R8] Docs — auth topology, access model, CLI, isolation contract

**Why:** `docs/broadcast.md` is the broadcast source of truth and `ARCHITECTURE.md`/`AGENTS.md` are read before every task; both now describe a dead model (`HostAccessGrant`) and env codes.

**Context / affected files:**
- `docs/broadcast.md` — "Access control" section (env-code description + "Verify is a client-only stub"), env-vars table (`BROADCAST_ACCESS_CODES` row), API table (add `GET /broadcast/access`, tier column), management-commands table (add the four R3 commands), SPA env (`VITE_BETTER_AUTH_URL`).
- `ARCHITECTURE.md` — Data Models (drop `HostAccessGrant` row; add the three broadcast access tables), API Endpoints (auth column values: `tier≥1` / `tier≥2`; direct-submit row), Authentication (auth-origin topology: `auth.thecommons.town`, shared cookie domain, per-app clients), Settings/env lists.
- `AGENTS.md` — "Where to Find Things" auth row + guardrails if stale.
- `docs/ingestion-pipeline.md` — direct-submit paragraph (host grant → JWT-else-anonymous).
- `broadcastWeb/AGENTS.md` — directory map (authClient), env vars.
- `DEPLOY.md` — env var list (new auth-origin vars, removed `BROADCAST_ACCESS_CODES`); R7's checklist may already have landed here — merge, don't duplicate.
- `docs/prd-centralized-auth.md` — mark status Implemented with any deviations.
- Skip `PROJECT_CONTEXT.md` (generated).

**Approach:** Write docs from the *shipped code* (trust code over PRD where they diverge — e.g. metering at preview only, email-as-client_label). Keep the isolation contract statement: access/tier/code logic lives in `broadcast/`, verifies JWTs via `backend/jwt_auth.py`, never imports `events`/`ingestion`.

**Acceptance criteria:**
- [ ] `grep -ri "HostAccessGrant\|BROADCAST_ACCESS_CODES" docs/ ARCHITECTURE.md AGENTS.md DEPLOY.md backendServer/AGENTS.md broadcastWeb/AGENTS.md` returns only historical/PRD mentions.
- [ ] Every new endpoint/command/env var appears in the right doc with the right tier.
- [ ] A cold reader of `docs/broadcast.md` can mint a code, grant a tier, and explain what a "use" is.

**Depends on:** R2, R3, R4, R6
**Can parallelize with:** R7

---

## Review these (all ⚠️ markers)

1. **R1/R5 — JWT `email` claim**: assumed present in Better Auth's default `jwt()` payload; R5 verifies and adds `definePayload` if not.
2. **R2 — `GET /broadcast/access` semantics**: creds absent → 200 `{tier: 0}`; creds invalid → 403 (so Verify can fail loudly).
3. **R2 — trial preview without a `draft_id`** → 400 `{"draft_id": "required"}`.
4. **R4 — migration rewrite** assumes `0008_hostaccessgrant` was never applied anywhere but local dev DBs (it's uncommitted); manual table cleanup noted.
5. **R4 — direct-submit becomes open** (JWT-else-anonymous, 10/m/IP, pipeline-reviewed) — PRD-locked but worth a conscious nod.
6. **R5 — `trustedOrigins` list**: dropped `http://127.0.0.1:8000` from PRD §10 (Django isn't a browser origin against the auth server).
7. **R6 — tier-0 logged-in copy**: "This account has no broadcast access yet — contact The Commons."
