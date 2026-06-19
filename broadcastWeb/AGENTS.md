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
API; `VITE_BROADCAST_EXTENSION_ID` enables the manual-review button.

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
