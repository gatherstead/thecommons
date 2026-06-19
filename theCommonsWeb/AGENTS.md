# theCommonsWeb — Agent Map

Next.js 16 (App Router) + React 19 + TypeScript + Tailwind v4 + Better Auth.

## Directory Map

```
src/
├── app/                                    # Next.js App Router
│   ├── layout.tsx                          # Root layout (server): AuthProvider, Header, Footer
│   ├── page.tsx                            # Home: feed + calendar views (client)
│   ├── about/page.tsx                      # About page (server component, SEO metadata)
│   ├── auth/
│   │   ├── page.tsx                        # Lazy signup/login flow: type → preferences → email (client)
│   │   ├── AuthFlow.tsx                    # Auth flow UI component
│   │   ├── login/page.tsx                  # Direct login page (client)
│   │   ├── signup/page.tsx                 # Direct signup page (client)
│   │   └── google-popup/                   # DISABLED — Google OAuth popup (revisit later)
│   ├── dashboard/page.tsx                  # Manage submitted events (client)
│   ├── post/page.tsx                       # Post new event, auth-gated (client)
│   ├── profile/page.tsx                    # View/edit profile + security section (client)
│   ├── events/[uuid]/page.tsx              # Single event detail page (client)
│   ├── api/auth/[...all]/route.ts          # Better Auth catch-all handler (also serves /api/auth/enter)
│   ├── api/auth/set-password/route.ts      # Secure a passwordless account
│   └── globals.css                         # Design tokens, utility classes, skeleton animation
├── components/
│   ├── auth/
│   │   └── SecuritySection.tsx             # Set-password form (profile page)
│   ├── events/
│   │   ├── EventFeed.tsx                   # Chronological event list
│   │   ├── CalendarView.tsx                # Calendar grid view
│   │   ├── EventRow.tsx                    # Single event row in feed
│   │   ├── EventDetailModal.tsx            # Event detail popup
│   │   ├── EventDetailContent.tsx          # Event detail body content
│   │   ├── EditEventModal.tsx              # Edit event form modal
│   │   └── FeedStatusBar.tsx               # Loading/empty state bar
│   ├── layout/
│   │   ├── Header.tsx, HeaderAuthNav.tsx   # Top navigation + auth state
│   │   ├── Footer.tsx                      # Page footer
│   │   ├── Sidebar.tsx, TopBar.tsx         # Side/top navigation chrome
│   │   ├── PageLayout.tsx                  # Shared page wrapper
│   │   ├── MiniCalendar.tsx                # Small calendar widget (sidebar)
│   │   ├── TagsBar.tsx                     # Tag filter bar
│   │   ├── SectionSelector.tsx             # Feed/calendar view switcher
│   │   ├── TimeWindowSelector.tsx          # Date range filter
│   │   ├── AccountBannerPusher.tsx         # No-password nudge banner
│   │   ├── DigestCTAPusher.tsx             # Newsletter signup prompt
│   │   └── MessageStackBanner.tsx          # Notification banner
│   ├── filters/                            # (empty — reserved)
│   └── ui/                                 # Shared primitives
│       ├── Badge, Banner, Button, Input, Link, Modal, Select, Textarea
│       └── index.ts                        # Re-exports
├── hooks/
│   ├── useAuth.tsx                         # Auth context: session + JWT; profile via ['profile'] query
│   ├── useEvents.ts                        # Main data hook: TanStack queries, filter state, month prefetch
│   ├── useTowns.ts / useCategories.ts      # Static lists via useQuery (['towns'] / ['categories'])
│   ├── useMessageStack.tsx                 # Toast/notification stack
│   ├── useToggleSet.ts                     # Generic multi-select toggle state
│   └── useClickOutside.ts                  # Dismiss-on-click-outside
├── lib/
│   ├── queryClient.ts                      # TanStack Query client singleton (session-fresh defaults)
│   ├── auth.ts                             # betterAuth() server config (Drizzle adapter, plugins)
│   ├── lazy-auth-plugin.ts                 # Custom plugin: POST /api/auth/enter (passwordless)
│   ├── auth-client.ts                      # createAuthClient() — browser-side auth
│   ├── auth-schema.ts                      # Drizzle schema for neon_auth tables
│   └── db.ts                               # Drizzle + pg Pool (DATABASE_URL)
├── models/
│   ├── eventsModels.ts                     # FrontendEvent, BackendEvent, EventPayload, TownOption, etc.
│   ├── authModels.ts                       # AuthUser, UserType, LoginPayload, EnterPayload, EnterResult
│   └── businessModels.ts                   # Business-related types
├── services/
│   ├── eventService.ts                     # Events CRUD API client
│   ├── profileService.ts                   # Profile read/write via /auth/me
│   └── businessService.ts                  # Business profile API client
└── constants/
    └── tags.ts                             # Static tag definitions
```

## Routes

| Path | File | Type | Purpose |
|------|------|------|---------|
| `/` | `app/page.tsx` | client | Feed + calendar views |
| `/about` | `app/about/page.tsx` | server | About page (SEO) |
| `/auth` | `app/auth/page.tsx` | client | Lazy signup/login flow |
| `/auth/login` | `app/auth/login/page.tsx` | client | Direct login |
| `/auth/signup` | `app/auth/signup/page.tsx` | client | Direct signup |
| `/dashboard` | `app/dashboard/page.tsx` | client | Manage submitted events |
| `/post` | `app/post/page.tsx` | client | Submit new event |
| `/profile` | `app/profile/page.tsx` | client | View/edit profile |
| `/events/[uuid]` | `app/events/[uuid]/page.tsx` | client | Event detail |
| `/api/auth/[...all]` | `app/api/auth/[...all]/route.ts` | API | Better Auth handler |
| `/api/auth/set-password` | `app/api/auth/set-password/route.ts` | API | Secure passwordless account |

## Design System

Newspaper aesthetic — serif fonts, cream/ink palette, column rules. No gradients, shadows, or pill buttons. Tokens defined in `globals.css`. See [`/CODING_STYLE.md`](../CODING_STYLE.md) for full reference.

## Quick Start

```bash
cd theCommonsWeb && pnpm install && pnpm dev
```

Env vars: see `.env.example`. Needs `DATABASE_URL` (Neon) and Better Auth vars to run auth.

> pnpm-managed — `npm install` fails on the symlinked store. Use pnpm everywhere.

## Testing

Vitest + React Testing Library, two tiers selected by filename:

| Tier | File suffix | Environment | Use for |
|------|-------------|-------------|---------|
| fast | `*.fast.test.ts(x)` | `node` (no jsdom) | pure logic — services, URL builders, mappers |
| db   | `*.db.test.ts(x)`   | `jsdom`            | hooks/components — anything that renders or uses TanStack Query |

```bash
pnpm test          # both tiers, single run
pnpm test:fast     # fast tier only (no jsdom)
pnpm test:db       # db tier only (jsdom + jest-dom matchers)
pnpm test:watch    # watch mode
```

Type-checking is separate and still happens via `pnpm build` — the runner does not replace it.

Conventions:
- Co-locate tests in a `__tests__/` folder next to the code under test.
- db-tier hook/component tests wrap in a fresh `QueryClient` via the `renderWithClient` /
  `renderHookWithClient` helpers in [`vitest.setup.ts`](vitest.setup.ts) (retries off so error
  paths resolve instead of hanging).
- Mock the network with `vi.stubGlobal('fetch', …)`; let unmocked URLs throw so a missed mock
  is loud. No test should hit a real server.
