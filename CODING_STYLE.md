# Coding Style & Design System

## Design Philosophy

The Commons looks like a **digital newspaper** — think old-timey Craigslist crossed with a small-town broadsheet. The aesthetic is intentionally unhip: no gradients, no rounded pill buttons, no startup vibes.

Key principles:
- Ink on newsprint. Dark text on a cream background.
- Serif everywhere. Georgia is the default typeface — loaded from the system, no network requests.
- Column rules and thick border rules instead of cards and shadows.
- Density over whitespace — pack the events in, newspaper-style.

---

## Frontend: CSS Design Tokens

All colors and fonts are defined as CSS custom properties in `theCommonsWeb/src/app/globals.css`. **Do not hardcode hex values in components** — reference the variables.

```css
--color-bg:           #f4f1eb   /* newsprint cream — page background */
--color-bg-alt:       #eae6dd   /* slightly darker cream — secondary surfaces */
--color-text:         #1a1a1a   /* near-black ink */
--color-text-muted:   #555555   /* secondary text */
--color-link:         #1a1a1a   /* links match body text */
--color-link-hover:   #8b0000   /* dark red on hover */
--color-border:       #1a1a1a   /* thick rule / primary border */
--color-border-light: #c8c3b8   /* hairline rule / dividers */
--color-accent:       #8b0000   /* dark red — used sparingly for active/selected state */

--font-headline:  Georgia, "Times New Roman", Times, serif
--font-body:      Georgia, "Times New Roman", Times, serif
--font-sans:      system-ui, ...  /* only for UI chrome that must feel modern */
```

Utility classes defined in `globals.css`:
- `.rule-thick` — `border-top: 3px solid var(--color-border)`
- `.rule-double` — `border-top: 3px double var(--color-border)`
- `.drop-cap` — floated large first letter (headline serif, 3.2rem)
- `.skeleton-block` — ebbing pulse animation for loading skeletons (respects `prefers-reduced-motion`)

---

## Frontend: Component Conventions

- **TypeScript everywhere.** Props interfaces are named `{ComponentName}Props`.
- Components live in `src/components/{category}/`. Add new components to the most specific matching subdirectory.
- Use Tailwind utility classes for layout/spacing; use CSS variables for all colors (via `var(--color-*)` inline or via Tailwind's `bg-[var(--color-bg)]` syntax).
- No `useState` in pure display components — lift state to the nearest shared ancestor or into a hook.
- The main data hook is `useEvents` in `src/hooks/`. Add filtering/sorting logic there, not in components.
- Auth state lives in `useAuth` (context provider in `src/hooks/useAuth.tsx`). Don't manage tokens or user state in components directly.
- Event data flows as `FrontendEvent` (see `src/models/eventsModels.ts`). Map API responses to this type in `eventService.ts`, not in components.
- **Next.js App Router:** Pages live in `src/app/`. Mark interactive components with `'use client'`. Server components are preferred for static/SEO pages (e.g., About). Route-level `metadata` exports provide SEO titles/descriptions.
- Environment variables exposed to the browser must use the `NEXT_PUBLIC_` prefix.

---

## Backend: Django Conventions

- **Apps are domain-scoped**: `events` = public-facing data, `ingestion` = pipeline internals. Don't bleed ingestion logic into the events app.
- DRF serializers live in `{app}/serializers.py`. Views in `{app}/views.py` should stay thin — business logic goes in a `services.py` module.
- Database transactions for anything that touches multiple models (`transaction.atomic()`).
- New models need a migration before any other work.
- Admin registration goes in `{app}/admin.py`. Use django-unfold decorators for custom display.
- The `Town` model is the canonical authority on valid towns. The ingestion pipeline resolves `town` slug from `StagedEvent` to a `Town` FK — if the slug doesn't exist in the `Town` table, the event is skipped during publishing.

---

## General

- No comments explaining *what* code does — use descriptive names.
- Add a comment only when the *why* is non-obvious (a workaround, a subtle invariant, a known limitation).
- No dead code. Delete it rather than commenting it out.
- Keep `.env.example` files up to date when adding new environment variables.
