# broadcastWeb — Agent Map

Vite 7 + React 19 + TypeScript, pnpm. The operator-facing SPA for the broadcast
event-syndication flow. Talks to the Django API under `/broadcast/` with plain
`fetch` (no QueryClient) and relays manual-review fills to the Chrome extension.

## Directory Map

```
src/
├── main.tsx                       # Entry
├── App.tsx                        # Page shell: access → form → preview → progress; 3s job polling
├── components/
│   ├── EventForm.tsx              # The event draft form
│   ├── SitePicker.tsx             # Eligible/excluded destination picker
│   └── JobProgress.tsx            # Per-target status badges, optimistic submit/manual, retry
├── hooks/
│   └── useExtension.ts            # Detects the Commons Broadcast extension; ping/recheck/sendFill
├── lib/
│   ├── authClient.ts              # better-auth client (createAuthClient at VITE_BETTER_AUTH_URL)
│   └── persist.ts                 # localStorage round-trip for the whole page (key broadcast:state:v1)
├── services/
│   └── broadcastApi.ts            # fetch wrappers (preview/submit/getJob/retry/submitReal/cancel/...)
└── models/
    └── broadcastModels.ts         # Shared types + LOCALITIES/CATEGORIES vocabularies
```

## Quick Start

```bash
cd broadcastWeb && pnpm install && pnpm dev
```

Env vars: see `.env.example`. `VITE_BROADCAST_API_BASE_URL` points at the Django
API; `VITE_BROADCAST_EXTENSION_ID` enables the manual-review button;
`VITE_BETTER_AUTH_URL` points at the Better Auth origin (`https://auth.thecommons.town`
in prod, `http://localhost:3000` in dev) — required for sign-in and for `authClient.signOut()`.

## Auth

There is no embedded login/signup form in this SPA — the former inline `AuthModal`
component was deleted. `App.tsx`'s "Sign in / Create account" button does a full-page
navigation to `${VITE_BETTER_AUTH_URL}/signin?redirect_to=<current broadcast URL>`,
i.e. the shared auth **portal** in `theCommonsWeb` (`src/app/(portal)/`). The
`.thecommons.town`-scoped session cookie means completing sign-in there returns the
browser to this exact page, already authenticated — no token-passing needed.
`lib/authClient.ts` (Better Auth client) still exists in this app, but only to read the
session, mint a JWT (`fetchJwt`), and call `signOut()` — never to render a sign-in form.
Details: [`../ARCHITECTURE.md#authentication`](../ARCHITECTURE.md#authentication).

> pnpm-managed — `npm install` fails on the symlinked store. Use pnpm everywhere.

## Testing

Vitest + React Testing Library, two tiers selected by filename (mirrors theCommonsWeb):

| Tier | File suffix | Environment | Use for |
|------|-------------|-------------|---------|
| fast | `*.fast.test.ts(x)` | `node` (no jsdom) | pure logic — `broadcastApi` wrappers, `persist` round-trip |
| db   | `*.db.test.ts(x)`   | `jsdom`            | components/hooks — `JobProgress`, `useExtension` |

```bash
pnpm test          # both tiers, single run
pnpm test:fast     # fast tier only (no jsdom)
pnpm test:db       # db tier only (jsdom + jest-dom matchers)
pnpm test:watch    # watch mode
```

Type-checking is separate and still happens via `pnpm build`.

Conventions:
- Co-locate tests in a `__tests__/` folder next to the code under test.
- Mock the network with `vi.stubGlobal('fetch', …)`; no test should hit a real server.
- Mock the extension by stubbing `window.chrome.runtime.sendMessage`. `useExtension`
  reads `VITE_BROADCAST_EXTENSION_ID` once at module load, so set it with
  `vi.stubEnv(...)` and `await import('../useExtension')` for a fresh copy.
