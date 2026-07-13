# PR Review Rubric — The Commons

This rubric is the source of truth for automated and scheduled PR reviews on this repo.
Work through each section in order. Stop at the first blocker and note it; keep going for
warnings and suggestions.

---

## 1. Do NOT flag

**Do not comment on formatting or style mechanics.** Ruff owns Python formatting; ESLint owns
JS/TS formatting. Spending review bandwidth on indentation, trailing commas, import order, or
line length is noise — those tools enforce the rules automatically. Restrict review comments to
correctness, architecture, and the guardrails below.

---

## 2. Backend guardrails

### 2.1 No `neon_auth` migrations

Flag as a **blocker** any migration file that touches models in the `neon_auth` schema
(`BetterAuthUser`, `BetterAuthSession`, `BetterAuthAccount`, `BetterAuthVerification`,
`BetterAuthJwks`). Those models carry `managed = False` — Better Auth (Next.js) owns those
tables. A Django migration touching them will corrupt the shared schema.

**Signal:** migration file references `neon_auth`, or the `Meta.managed` flag on any of the
above models is changed to `True`.

### 2.2 Hardcoded Town or Category values

Flag as a **warning** any code that hardcodes `Town` slugs/names or `Category`
slugs/display names as string literals outside of fixture/seed files. `Town` and `Category`
are SQL-authoritative tables (ARCHITECTURE.md §Data Models); the canonical list lives in the
database, not in source code. Queries and filters must reference these tables dynamically (FK
or slug lookup), not match against a baked-in list.

### 2.3 `django.contrib.auth.User` in app code

Flag as a **blocker** any new import or reference to `django.contrib.auth.User` (or
`from django.contrib.auth import get_user_model` used as a substitute for `BetterAuthUser`)
in app code. This project uses `BetterAuthUser` (`events/models.py`) as the user identity
model — `UserProfile` and `Event.created_by` both key to it. Direct use of Django's built-in
`User` will produce incorrect auth behavior or broken FK joins.

### 2.4 New authenticated endpoints missing correct auth and permission classes

Flag as a **blocker** any new DRF view or `@api_view` endpoint that requires authentication
but does not explicitly declare both an authentication class and a permission class.

The project has **no global DRF auth config** — every view sets its own decorators (house
pattern; ARCHITECTURE.md §API Endpoints). The correct classes are:

| Scenario | Authentication class | Permission class |
|---|---|---|
| User-only endpoint | `BearerTokenAuthentication` | `IsAuthenticated` |
| App-level (API key only) | `BearerTokenAuthentication` | `HasCommonsAPIKey` |
| User or app-level | `BearerTokenAuthentication` | `HasCommonsAPIKeyOrUser` |

All three classes live in `backendServer/backend/permissions.py`.
`BearerTokenAuthentication` accepts a Better Auth JWT (verified against the JWKS endpoint in
`backend/jwt_auth.py`) or the shared `THE_COMMONS_API_KEY`. A view that omits
`authentication_classes` or `permission_classes` falls back to DRF defaults, which is wrong.

---

## 3. Frontend guardrails

### 3.1 Hardcoded hex colors

Flag as a **warning** any hardcoded hex color value (e.g. `#f4f1eb`, `#8b0000`) appearing
in a component file — whether as an inline style, a Tailwind arbitrary value, or a CSS
declaration outside `globals.css`. All colors are defined as CSS custom properties in
`theCommonsWeb/src/app/globals.css` and must be referenced via `var(--color-*)` or the
Tailwind `bg-[var(--color-bg)]` syntax (CODING_STYLE.md §CSS Design Tokens).

### 3.2 `useState` added to a pure display component

Flag as a **warning** any PR that adds `useState` (or `useReducer`) to a component under
`theCommonsWeb/src/components/`. Those components are intended to be pure/presentational.
State belongs either in the nearest shared ancestor page/layout component or in a dedicated
hook under `src/hooks/`. If the PR genuinely needs component-local state, it should move the
component out of `src/components/` (e.g. into the page file) or introduce a named hook —
flag the placement and suggest the correct destination.

---

## 4. Doc-sync flag-and-suggest

If a PR changes a model field, serializer, or endpoint/route, check whether `ARCHITECTURE.md`
§Data Models or §API Endpoints describes the old behavior. If so, note the drift as a review
comment, and if it's a one-line factual fix, include the corrected snippet inline for the
author to paste. **Flag-and-suggest only — never auto-edit the docs.**

The same rule applies to `PROJECT_CONTEXT.md` if it describes the affected behavior.

---

## 5. Reference map

| Topic | Where to look |
|---|---|
| Auth classes | `backendServer/backend/permissions.py`, `backendServer/backend/jwt_auth.py` |
| Data models | `backendServer/events/models.py`, `backendServer/ingestion/models.py`, `backendServer/broadcast/models.py` |
| Endpoint list | `ARCHITECTURE.md` §API Endpoints |
| CSS tokens | `theCommonsWeb/src/app/globals.css` |
| Component conventions | `CODING_STYLE.md` §Frontend: Component Conventions |
| Broadcast isolation rules | `docs/broadcast.md`, `AGENTS.md` |
| `neon_auth` ownership | `ARCHITECTURE.md` §Better Auth mirrors |
