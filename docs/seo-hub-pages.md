# SEO Hub Pages — Town & Category Landing Pages

> ⚠️ **Partly superseded (suite 50, 2026-08-05).** Event categories were retired
> entirely — `Category`, `/events/categories/`, and the `?category=` filter no
> longer exist. Neither `/towns/[slug]` nor `/categories/[slug]` was ever built,
> so nothing here is live; the **town** half of this design still stands, the
> **category** half does not. Do not implement the category routes.

Design doc for the town and category hub pages identified as the highest long-term
SEO play for The Commons. This is a 2–3 day build; implement after the quick wins
(JSON-LD, sitemap, metadataBase) are live and indexed.

## Why

Individual event pages (`/events/<uuid>`) index well once JSON-LD and the sitemap are
in place, but they only capture searches for specific events. Hub pages capture
*intent-level* searches: "things to do in Carrboro this weekend", "live music Chapel
Hill", "family events near me." These are the queries that drive discovery traffic
from people who don't yet know what event they want.

The backend already has everything needed: `/events/towns/` and `/events/categories/`
list endpoints, and `/events/?town=<slug>` and `/events/?category=<slug>` filtering.
The frontend has none of it wired up as crawlable routes.

## Routes to build

| Route | File to create | Example |
|-------|---------------|---------|
| `/towns/[slug]` | `theCommonsWeb/src/app/towns/[slug]/page.tsx` | `/towns/carrboro` |
| `/categories/[slug]` | `theCommonsWeb/src/app/categories/[slug]/page.tsx` | `/categories/music` |

Both are Next.js App Router server components with `generateStaticParams` +
`generateMetadata`.

## Page anatomy

### Town page (`/towns/carrboro`)

```
[Masthead rule]
H1: "Events in Carrboro, NC"                   ← keyword-rich, not cute
Dateline: "Updated [date]"                     ← freshness signal for Google

[Short paragraph — 2–3 sentences]
Describe the town: what it's known for, what kinds of events happen here.
This is the only hand-authored copy on the page. It's what earns the rich
snippet excerpt in search results.

[Rule]

[Event list — server-rendered]
Same layout as the homepage feed, filtered to town slug.
Show upcoming events, paginated or load-more.
Each event links to /events/<uuid>.

[Footer links to other towns]
"Also see: Chapel Hill · Pittsboro → " etc.
```

### Category page (`/categories/music`)

Same pattern. H1: `"Music Events — Chapel Hill Area"`. Short paragraph about the
category. Event list filtered by category slug.

## Implementation notes

### generateStaticParams

Fetch towns/categories at build time and pre-render:

```ts
export async function generateStaticParams() {
  const towns = await getTowns(); // already in eventService.ts
  return towns.map(t => ({ slug: t.slug }));
}
```

This makes pages fully static at build time (SSG). Revalidate every 24h via
`export const revalidate = 86400` on the page module.

### generateMetadata

```ts
export async function generateMetadata({ params }) {
  const { slug } = await params;
  const town = towns.find(t => t.slug === slug);
  return {
    title: `Events in ${town.name}, NC — The Commons`,
    description: `Upcoming events in ${town.name}. Farmers markets, live music,
      community gatherings, and more from The Commons.`,
  };
}
```

Both the `<title>` and `<meta description>` should be keyword-forward. Don't use
the cute taglines here — Google is parsing these for relevance signals.

### "Last updated" dateline

Inject a server-side date in ISO format as a visible element:

```tsx
<time dateTime={new Date().toISOString()} className="text-xs text-[var(--color-text-muted)]">
  Updated {new Date().toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' })}
</time>
```

This tells Googlebot the page is fresh — important for "this weekend" intent queries.

### Linking from existing pages

Hub pages only work if Googlebot can find them. Add links in:

1. **Header** — a "Towns" dropdown or section in `Header.tsx`
2. **Homepage sidebar** — the existing town filter buttons in the sidebar should link
   to `/towns/<slug>` (not just trigger a client-side filter) so they're crawlable
3. **Footer** — add a "Browse by Town" section alongside the existing footer columns
4. **Event detail page** — the "Town" label in `EventDetailContent.tsx`'s sidebar
   should be an `<a href="/towns/<slug>">` link

### Design

Follow the newspaper aesthetic exactly. Treat the short paragraph like a newspaper
dateline paragraph — dense, factual, local. Drop cap on the first paragraph.
Column rule above the event list. No hero images, no gradient headers.

## SEO copy for each town

The short paragraph on each town page is the only content that differentiates it
from a filtered list. It needs to be written once and stored somewhere. Options:

**Option A:** Hardcode in a `src/data/towns.ts` map `{ slug → description }`. Simple,
no backend changes. Update by editing the file.

**Option B:** Add a `description` field to the `Town` model in Django and expose it
through the `/events/towns/` endpoint. More flexible, editable via admin. ~1 day
extra work.

**Recommendation:** Start with Option A. The town list is small and stable; a flat
data file is fine. Upgrade to Option B if/when the town list grows or marketing
wants to update copy without a deploy.

## Sitemap integration

Once hub pages exist, add them to `sitemap.ts` (T3):

```ts
const towns = await getTowns();
const townRoutes = towns.map(t => ({
  url: `${SITE}/towns/${t.slug}`,
  lastModified: now,
  changeFrequency: 'daily' as const,
  priority: 0.9,
}));
```

Category routes follow the same pattern. Hub pages should have *higher* priority
than individual event pages (0.9 vs 0.8) because they aggregate multiple events
and rank for higher-volume queries.

## Acceptance criteria

- [ ] `/towns/[slug]` and `/categories/[slug]` render as SSG pages with correct
  `<title>` and `<meta description>`
- [ ] Both pages have a "Last updated" dateline
- [ ] `generateStaticParams` pre-renders all known towns/categories at build time
- [ ] Hub pages are linked from Header and/or Sidebar so Googlebot can crawl them
- [ ] Town/category slugs from the API are the URL slugs (no manual mapping needed)
- [ ] `pnpm build` passes
- [ ] Sitemap includes hub page URLs at priority 0.9
