# theCommonsWeb — Agent Map

Next.js 16 (App Router + Turbopack) + React 19 + TypeScript + Tailwind v4 + TanStack Query v5 + Better Auth. **pnpm-managed** (npm install breaks the symlinked store). This app is also the auth provider: Better Auth runs here and Django verifies its JWTs. See [`../ARCHITECTURE.md`](../ARCHITECTURE.md) for the auth bridge and data layer.

## Directory Map

```
src/
├── app/                           # App Router
│   ├── layout.tsx                 #   Root: QueryProvider → AuthProvider → MessageStackProvider + SiteChrome
│   ├── page.tsx                   #   Home feed/calendar (client)
│   ├── globals.css                #   Design tokens (CSS vars) + newspaper utilities
│   ├── about/ post/ profile/ dashboard/   # Pages (see Routes)
│   ├── (portal)/                  #   Standalone auth portal: signin/join/set-password/forgot-password (see Auth)
│   ├── auth/                      #   Legacy redirect shims → portal (login/signup/page.tsx; AuthFlow + google-popup removed)
│   ├── events/[uuid]/             #   Event detail (server, generateMetadata) + not-found
│   └── api/auth/                  #   [...all]/route.ts (Better Auth), set-password/route.ts
├── components/
│   ├── auth/                      #   SecuritySection (set-password)
│   ├── events/                    #   Feed/calendar/detail/edit components
│   ├── layout/                    #   Header, Footer, Sidebar, banners, selectors, calendar, SiteChrome (hides Header/Footer on portal routes)
│   ├── providers/QueryProvider.tsx#   TanStack QueryClientProvider (+ lazy devtools in dev)
│   └── ui/                        #   Primitives: Badge, Banner, Button, Input, Modal, Select, …
├── hooks/                         # See Hooks (+ __tests__/)
├── lib/                           # auth.ts, lazy-auth-plugin.ts, redirect-allowlist.ts, auth-client.ts,
│                                  #   auth-schema.ts, db.ts (Drizzle/pg), queryClient.ts (+ __tests__/)
├── models/                        # TS types: eventsModels, authModels, businessModels
├── services/                      # Django API clients (+ __tests__/)
├── constants/tags.ts              # FILTER_TAGS
└── data/mockEvents.ts             # UNUSED dead fixtures
```

> Dead/stale (ignore): `dist/` (old Vite output), `src/data/mockEvents.ts`, `src/assets/react.svg`, `eslint.config.js` (fully commented), and `tsconfig.json` references to nonexistent `tsconfig.app.json`/`tsconfig.node.json` (type-check runs via `next build`).

## Routes

| Path | File | Type | Purpose |
|------|------|------|---------|
| `/` | `app/page.tsx` | client | Feed + calendar, filters, detail modal |
| `/about` | `app/about/page.tsx` | server | About page (SEO metadata) |
| `/post` | `app/post/page.tsx` | client | Submit an event (auth-gated) |
| `/profile` | `app/profile/page.tsx` | client | Edit profile, digest prefs, security |
| `/dashboard` | `app/dashboard/page.tsx` | client | Manage submitted events + business listing |
| `/auth`, `/auth/login`, `/auth/signup` | `app/auth/{page,login/page,signup/page}.tsx` | server redirect shim | Legacy entry points — map old `?redirect=`/`?intent=` to `redirect_to` and bounce into the portal |
| `/signin` | `app/(portal)/signin/page.tsx` | client (`PortalShell`) | Portal sign-in |
| `/join` | `app/(portal)/join/page.tsx` | client (`PortalShell`) | Portal passwordless create-account |
| `/set-password` | `app/(portal)/set-password/page.tsx` | client | Set a password on a passwordless account |
| `/forgot-password` | `app/(portal)/forgot-password/page.tsx` | client | Password reset request |
| `/events/[uuid]` | `app/events/[uuid]/page.tsx` | server (async) | Event detail (OpenGraph) |
| `/api/auth/[...all]` | `app/api/auth/[...all]/route.ts` | route | Better Auth handler |
| `/api/auth/set-password` | `app/api/auth/set-password/route.ts` | route | Set password on passwordless account |

The former embedded auth UI (`AuthFlow`, `google-popup`) was removed when the standalone portal shipped — see [Auth](#auth) below.

## Hooks (`src/hooks/`)

| Hook | Purpose |
|------|---------|
| `useAuth` / `AuthProvider` | Better Auth session + Django JWT + profile; `enter/login/setPassword/logout/refreshSession` |
| `useEvents` | Core data hook: paged events + per-month calendar prefetch, window/category/town/tag state |
| `useTowns` / `useCategories` | `useQuery(['towns'])` / `(['categories'])` |
| `useMessageStack` / `MessageStackProvider` | One-at-a-time banner queue |
| `useToggleSet<T>` | Generic multi-select toggle (tags/towns) |
| `useClickOutside` | Outside-click handler |

## Services & data layer

`src/services/` talk to Django over `fetch` at `NEXT_PUBLIC_API_BASE_URL` (default `http://127.0.0.1:8000`):
- `eventService` — events list/detail/create/staged CRUD; maps `BackendEvent → FrontendEvent`. Create falls back to `NEXT_PUBLIC_THE_COMMONS_API_KEY`.
- `profileService` (`/auth/me`) and `businessService` (`/businesses…`) — Bearer JWT; `fetchWithRetry` for Neon cold-starts.

TanStack Query is configured in `src/lib/queryClient.ts` (`staleTime/gcTime: Infinity`, `retry: 1`) and provided by `components/providers/QueryProvider.tsx`. Query keys: `['towns']`, `['categories']`, `['profile', token]`, `['events', …]`, `['myEvents', token]`, `['myBusiness', token]`.

## Auth

Better Auth (`lib/auth.ts`) over Drizzle/`neon_auth` (`lib/auth-schema.ts`, `lib/db.ts`); custom passwordless `POST /enter` (`lib/lazy-auth-plugin.ts`); `databaseHooks.user.create.after` creates the Django `UserProfile` (wrapped in try/catch + `ON CONFLICT DO NOTHING` so a mirror-insert failure can't roll back the Better Auth signup transaction). No `middleware.ts` — route protection is client-side via `useAuth`. **Don't call `authClient` or manage JWTs in components** — go through `useAuth`.

Sign-in/sign-up UI is not embedded in pages anymore — it lives in a standalone **portal**, the `(portal)` route group (`/signin`, `/join`, `/set-password`, `/forgot-password`), chrome'd by `PortalShell` and served at `auth.thecommons.town` in prod (same origin as the app in dev). `components/layout/SiteChrome.tsx` hides the normal `Header`/`Footer`/banners on portal paths. Every redirect into the portal carries `?redirect_to=<absolute URL>`, validated on the way out by `lib/redirect-allowlist.ts`'s `resolveRedirect()` (open-redirect guard — allows `*.thecommons.town` and localhost only). The old embedded flow (`app/auth/AuthFlow.tsx`, `app/auth/google-popup/`) was deleted; `/auth`, `/auth/login`, `/auth/signup` are now thin server-redirect shims into the portal, and in-app entry points (Header, sidebar, post gate, digest CTA) link straight to it. Details: [`../ARCHITECTURE.md#authentication`](../ARCHITECTURE.md#authentication).

## Design system

Tailwind v4 (zero-config) + CSS custom properties in `src/app/globals.css` (newsprint cream/ink, Georgia serif, `.rule-thick`/`.drop-cap` utilities). Never hardcode hex — use `var(--color-*)`. Full conventions: [`../CODING_STYLE.md`](../CODING_STYLE.md).

## Testing & build

Vitest with two projects — `fast` (node, `*.fast.test.*`) and `db` (jsdom, `*.db.test.*`, uses `vitest.setup.ts`). `pnpm build` (`next build`) is the type-check gate.

```bash
pnpm test        # all          pnpm test:fast   # no-DOM tier
pnpm test:db     # jsdom tier   pnpm build       # type-check
```

## Quick Start

```bash
cd theCommonsWeb && pnpm install && pnpm dev
```

Run the backend too for end-to-end auth (Django validates JWTs against this app's JWKS endpoint).
