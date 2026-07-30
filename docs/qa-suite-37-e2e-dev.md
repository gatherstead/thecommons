# Suite 37 — Central Auth Reintegration: dev E2E smoke (ticket 37.10)

**Run:** 2026-07-30, local dev stack (theCommonsWeb `:3000` portal+Better Auth ·
broadcastWeb `:5173` · Django `:8000`), driven in Chrome. Dev DB (Neon), localhost-scoped
session cookie (no `BETTER_AUTH_COOKIE_DOMAIN` in dev). New test account:
`s37e2e-drive1@example.com` (passwordless).

## Result: 6/6 PASS

| # | Step | Result |
|---|------|--------|
| 1 | broadcast (signed out) → "Sign in / Create account" → lands on portal | **PASS** — `localhost:3000/signin?redirect_to=http%3A%2F%2Flocalhost%3A5173%2F` (37.7 + portal shell/gate + tabs preserve `redirect_to`) |
| 2 | Create **brand-new** account on `/join` → session set → redirected back to broadcast signed in | **PASS** — account created passwordlessly, **immediate auth (no 401)**, broadcast returns signed in as the new email. Proves **37.8 signup-hook fix** + cross-app session sharing (`:3000` session read on `:5173`) |
| 3 | New account shows tier 0 + "enter your access code" prompt | **PASS** — "This account has no broadcast access yet — enter the code"; AI-autofill tier-gated |
| 4 | Redeem tier-2 **upgrade** code → 200, tier persists on reload | **PASS** — "✓ Tier 2 access on this account", contact step + AI-autofill unlocked; **survives hard reload** (persisted to account, not just session) |
| 5 | Apex `/auth/login` redirects into the portal; session shared | **PASS** — shim 307 → `/signin` → authenticated-guard → apex home `localhost:3000/` showing **PROFILE / SIGN OUT**; passwordless "Set a password →" banner also renders (37.4 deep-link) |
| 6 | Off-allowlist `redirect_to` falls back to `/` | **PASS** — `?redirect_to=https://evil.example.com/phish` → `resolveRedirect` rejected → landed on `localhost:3000/`, **no off-site navigation** (37.1) |

### Also curl-verified (server-side, no session)
- `/auth/login` → `307 /signin?redirect_to=<absolute apex>`; `/auth/signup` & `/auth` → `/join`.
- Param mapping: `?redirect=/profile` → `…/profile`; `?intent=digest` → `…/profile#digest`.
- Unauth `GET /broadcast/access` → `200 {"tier":0,"is_trial":false,"uses_remaining":null}` (tier-0, not 403).
- No CORS failure on `:5173`→`:8000` redeem in dev (the anticipated dev-CORS caveat did not materialize).

## Not covered here (gated on deploy)
Prod cutover (ticket 37.9) + prod Phase-8 smoke are **blocked until this branch is merged
and deployed** — prod currently runs the pre-portal code, so a live `auth.thecommons.town`
portal token / `GET /broadcast/access` can't be exercised yet. Run `docs/runbook-auth-cutover.md`
Phases 1–8 after deploy; the dev run above exercises the same code paths those phases enable.
