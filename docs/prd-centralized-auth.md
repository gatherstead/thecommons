# PRD — Centralized Auth Origin & DB-Backed Access Codes

**Status:** Implemented (2026-07-07) · **Related:** supersedes the `HostAccessGrant` code→user model from the direct-submission work · **Isolation:** all access/tier/code logic stays in `broadcast/` (verifies JWTs via `backend/jwt_auth.py`; never imports `events`/`ingestion` — `broadcast/tests/test_isolation.py` must stay green)

**Deviations from spec (as shipped):** metering fires at `POST /broadcast/preview` only (not the general "broadcast front door"); `client_label` for JWT users is the full email address; broadcastWeb uses email + password sign-in/sign-up forms (not the lazy one-field "enter" flow).

---

## 1. Background & problem

Auth (Better Auth) runs **embedded inside theCommonsWeb** (Next.js). Django verifies its JWTs statelessly via JWKS (`backend/jwt_auth.py`); users live in the standalone `neon_auth.*` Postgres schema, mirrored read-only into Django. A second frontend — **broadcastWeb** (Vite SPA) — now needs authenticated, tiered feature access, and **more sub-projects are expected**. Two problems:

1. **Auth is coupled to one app's origin.** Every new SPA must re-solve cross-origin sessions/CORS/token-minting. There is no single identity origin.
2. **Access codes are static env strings** (`BROADCAST_ACCESS_CODES`) — they can't be generated, counted, budgeted, expired, or revoked.

## 2. Goals / non-goals

**Goals**
- One **auth origin** every current/future frontend authenticates against, with the cross-origin story solved once.
- **No change** to Django's verification model (stays JWKS/stateless) and **no user-data migration** (`neon_auth.*` untouched).
- Access codes **generated from the terminal**, stored **hashed in a SQL table**, carrying a **tier** and a **usage budget**, revocable — **no env codes**.
- Support broadcast tiered access (Tier 0/1/2; **AI gated to Tier 2**) on top of this foundation.

**Non-goals**
- Rewriting/replacing Better Auth. We relocate its origin and consume it.
- Full physical extraction of the auth server into a standalone service (**deferred** — revisit at the 3rd sub-project).
- A general OAuth provider for third parties. This is internal SSO for our own apps.
- Generalizing access codes beyond broadcast (**stays broadcast-scoped**; generalize later only if a non-broadcast sub-project needs codes).

### 2.1 Source requirements (traceability)

Captured verbatim from the original request, mapped to where each is addressed:

| Original ask | Where handled |
|---|---|
| Access codes are **separate from the account** — a **free trial**, ~**three uses** per code | D2, D6, §5–§6 — codes are anonymous SQL rows, never linked to a user; default `max_uses=3`. |
| A **login button on the broadcast access part** of the page; users can log in and, **if they have feature access, they get it** | §9 (login/signup/signout in the access area), §5 (`BroadcastAccess` tier), §8 (`GET /broadcast/access` drives the UI). |
| **Tier 1:** can put in everything, but **can't use the AI feature** | §5 tier gates + §5 Tier definitions table (Tier 1 → all endpoints except ai-autofill). |
| **Tier 2:** can **use the AI feature** | §5 (ai-autofill requires tier ≥ 2). |
| Developer **terminal command to change a user's access to 0/1/2 by email** — so we **don't have to link access codes to the user** | §7 `set_broadcast_access <email> <tier>`. Rationale: tiers key off **email**, decoupling codes from accounts — this is precisely why the old `HostAccessGrant` code→user link is **dropped** (§5, §11). |

## 3. Locked decisions

| # | Decision |
|---|---|
| D1 | **Phase 1 auth origin only:** reverse-proxy the *existing* Better Auth to a dedicated auth subdomain + shared cookie domain; repoint `BETTER_AUTH_JWKS_URL`. Full extraction deferred. |
| D2 | **Access codes: hard cut to SQL.** Remove `BROADCAST_ACCESS_CODES`. Codes live only in the `AccessCode` table; `client_label` now comes from `AccessCode.label`. |
| D3 | **Access model stays in `broadcast/`.** Isolation preserved. |
| D4 | **Config distribution is manual per-service env** ("dual-read" clarified) — no shared-config service/plumbing. |
| D5 | **Cookie-domain cutover is a one-time forced re-login**, done now while no users are active. |
| D6 | Trial defaults: a generated trial code = `tier=2`, `max_uses=3`. A "use" = one distinct `draft_id` (edits reuse the row → free). |
| D7 | No pre-authorized future origins; add each app's origin to CORS/`trustedOrigins` as it launches. |

## 4. Architecture — auth origin (Phase 1)

- Serve Better Auth at **`auth.thecommons.town`** (subdomain + reverse proxy on the shared VM; still physically served by the existing Next.js app for now).
- Set a **shared cookie domain `.thecommons.town`** so one session is visible to the apex app, `broadcast.thecommons.town`, and future SPAs. Requires `SameSite=None; Secure` (HTTPS) even on one VM.
- Every client: `createAuthClient({ baseURL: 'https://auth.thecommons.town' })`; mint the Django JWT via `GET https://auth.thecommons.town/api/auth/token` with `credentials: 'include'`; send `Authorization: Bearer <jwt>` to `api.thecommons.town`.
- Better Auth `trustedOrigins` + Django CORS allow the app origins (see §10). **Django is unchanged** except `BETTER_AUTH_JWKS_URL` → the new origin.

## 5. Architecture — access & tiers (in `broadcast/`)

**Tier definitions**

| Tier | Who gets it | Fill + broadcast everything | AI autofill |
|---|---|---|---|
| **0** | Logged-in user with no grant (**default**) | ✗ | ✗ |
| **1** | Granted tier 1 by the dev CLI | ✓ | ✗ |
| **2** | Granted tier 2, **or** a valid trial access code | ✓ | ✓ |

Tier 1 = "put in everything but no AI"; Tier 2 = "includes AI". Tier 0 exists so a logged-in account without a grant is cleanly denied (not an error state).

- **`BroadcastAccess(email → tier 0/1/2)`** — logged-in users; **default tier 0** (account exists, no feature) when no row.
- **`AccessCode` (SQL, generated)** + **`AccessCodeUse(code, draft_id)`** — anonymous/trial access; hashed codes; budget by distinct `draft_id`.
- **`resolve_access(request)`** in `broadcast/access.py`:
  1. `Authorization: Bearer <jwt>` verifies (`backend.jwt_auth`) → email → `BroadcastAccess.tier` (0 if none).
  2. Else access code (header/body) → matching active, unexpired `AccessCode` within budget (**or** whose `draft_id` is already counted) → its `tier`.
  3. Else no access.
  Returns `{ tier, identity, is_trial, uses_remaining, client_label }`.
- **Gates:** preview / submit / recipe / job endpoints → **tier ≥ 1**; **ai-autofill → tier ≥ 2**.
- **Metering:** a trial `AccessCodeUse` is recorded **once per `draft_id` at the broadcast front door** (idempotent). `client_label` for `BroadcastSubmission` now derives from the resolved identity (`AccessCode.label` for code users; email/label for logged-in).
- **Ingestion direct-submit:** **drop `HostAccessGrant` + `resolve_host_user`** (+ its migration). `created_by` = JWT-resolved `BetterAuthUser`, else `None` (trial). No second metering point (stays isolation-clean).

## 6. Data model (broadcast app)

```
BroadcastAccess
  email        Char, unique, lowercased
  tier         Int (0|1|2), default 0
  created_at / updated_at

AccessCode
  code_hash    Char(64), unique      # sha256(raw); raw shown ONCE at generation, never stored
  label        Char                  # replaces env client_label
  tier         Int (0|1|2), default 2
  max_uses     Int, null=unlimited, default 3
  is_active    Bool, default True
  expires_at   DateTime, null
  created_at / updated_at

AccessCodeUse
  access_code  FK → AccessCode
  draft_id     Char
  created_at
  unique_together (access_code, draft_id)   # a "use" = one distinct draft_id
```

## 7. Terminal commands (developer UX)

- `manage.py set_broadcast_access <email> <0|1|2>` — grant/change a logged-in user's tier.
- `manage.py generate_access_code [--tier N=2] [--uses N=3|--unlimited] [--expires <ISO>] [--label ...]` — creates a row, **prints the raw code once**, stores only the hash.
- `manage.py list_access_codes` — label, tier, uses_remaining, active, expiry (never the raw code).
- `manage.py revoke_access_code <label|id>` — set `is_active=False`.

## 8. API surface (broadcast)

- **`GET /broadcast/access`** *(new)* → `{ tier, is_trial, uses_remaining }` so the SPA shows/hides AI and renders remaining trial uses.
- Existing preview/submit/recipe/job endpoints: swap `HasBroadcastAccessCode` → tier-aware permission (≥1); **ai-autofill → ≥2**.
- Auth accepted on all: `Authorization: Bearer <jwt>` **or** access code (header `X-Broadcast-Access-Code` / body `access_code`).

## 9. Frontend (broadcastWeb)

- Add `better-auth` client → `createAuthClient({ baseURL: auth origin })`; **login / signup / signout** in the access area; obtain JWT via `/api/auth/token`; attach `Authorization: Bearer` to all API calls.
- Keep the **access-code entry** path for trial/anonymous use.
- **Tier-aware UI:** hide the AI feature below tier 2; show trial `uses_remaining`; reflect logged-in vs. trial state. Driven by `GET /broadcast/access`.

## 10. Config distribution (per D4 — manual per-service env)

Set the same values by hand in each service's env (no shared-config plumbing):

| Var | theCommonsWeb | broadcastWeb | backendServer |
|---|---|---|---|
| Auth base URL | ✓ (`NEXT_PUBLIC_BETTER_AUTH_URL`) | ✓ (`VITE_BETTER_AUTH_URL`) | — |
| JWKS URL | — | — | ✓ (`BETTER_AUTH_JWKS_URL`) |
| Cookie domain `.thecommons.town` | ✓ | — | — |
| `trustedOrigins` / CORS allow-list | ✓ (auth server) | — | ✓ (Django CORS) |
| API base `api.thecommons.town` | ✓ | ✓ (`VITE_BROADCAST_API_BASE_URL`) | — |

**Origins to allow (prod + dev):** `https://thecommons.town`, `https://broadcast.thecommons.town`; dev `http://localhost:3000` (Next), `http://localhost:5173` (Vite), `http://127.0.0.1:8000` (Django).

## 11. Rollout

1. **Backend access foundation** — `BroadcastAccess` / `AccessCode` / `AccessCodeUse` models, `resolve_access`, tier permissions, `GET /broadcast/access`, the four CLI commands; **remove `BROADCAST_ACCESS_CODES`**; **drop `HostAccessGrant`**. Migration + tests. (No frontend dependency.)
2. **Ingestion direct-submit rework** — ownership via JWT else `None`; delete grant model/resolver/migration; update T0/T3 tests.
3. **Auth origin (Phase 1, infra/config)** — auth subdomain, `.thecommons.town` cookie domain, `trustedOrigins`/CORS, repoint `BETTER_AUTH_JWKS_URL`.
4. **broadcastWeb** — embedded Better Auth client, login + tier-aware UI, Bearer on all calls, keep code path.
5. **Docs** — auth topology, access model, CLI, preserved isolation contract.

## 12. Risks & open questions

- **Cookie-domain cutover logs everyone out once** — acceptable now (no active users; D5).
- **Env→DB code cut is hard** — recreate any needed codes in the table via `generate_access_code`. No fallback.
- **Cross-origin cookies need SameSite=None + HTTPS** even on one VM.
- **`client_label` semantics for logged-in users** — derive from email or a label map; finalize in the R1 ticket.
- **Phase-2 auth extraction** — deferred; revisit when a 3rd/4th sub-project lands.

## 13. Success criteria

- A new sub-project adds auth by pointing its Better Auth client at `auth.thecommons.town` and sending the JWT — no bespoke per-app auth plumbing.
- A developer generates a tiered, usage-capped code in one terminal command; the raw code appears once and only the hash persists.
- Broadcast AI is reachable only at Tier 2 (logged-in or trial); `broadcast/tests/test_isolation.py` stays green.

## Appendix — confirmed parameters

- Auth origin: `auth.thecommons.town` · app: `thecommons.town` (apex) · broadcast: `broadcast.thecommons.town` · API: `api.thecommons.town` · cookie domain: `.thecommons.town`
- Trial defaults: tier 2, 3 uses (one use per distinct `draft_id`).
- Access codes: broadcast-scoped, SQL-only, no env.
