# Design System

> **Last updated:** 2026-08-03, commit `9a38379`, branch `suite-47-tags-and-filters`. Every token, class, and component in the Deep Dive was read out of `theCommonsWeb/src/app/globals.css` and `theCommonsWeb/src/components/ui/` directly — not inferred from prose. Where `CODING_STYLE.md` (the repo's canonical style statement, which this doc complements and does not replace) disagrees with the stylesheet, both are stated and the disagreement is called out. For the Next.js routing/data-fetching layer these components sit inside, see `frontend.md`; for the product as a whole, see `overview.md`.

## Overview

- **What it is:** The Commons is styled to look like a broadsheet newspaper's classifieds page crossed with early Craigslist — serif type, cream newsprint background, black ink, hairline/thick column rules doing the separation work that cards and shadows do in most modern products, and a bias toward density over whitespace. This is the whole visual vocabulary, not a retro skin on a normal SaaS layout.
- **Why it's this way:** The Commons is a local events bulletin for three small towns, not a venture-backed platform. It wants to read like a community notice board a neighbor posted, not a pitch deck — so density, rules, and serifs are load-bearing for trust, not decoration.
- **Who depends on it:** Every component under `theCommonsWeb/src/components/ui/` and the layout components (`Header.tsx`, `Sidebar.tsx`, `Footer.tsx`, `EventFeed.tsx`, etc.) consume the same small set of CSS custom properties defined once in `globals.css`. There is no Tailwind config file and no `@theme` block — Tailwind v4 is used with its bare default scale plus these tokens.
- **The one or two facts that matter most:** (1) There are exactly four separation devices — hairline rule, standard rule, thick rule, and one specific hard-edged "print" shadow — and no soft/blurred shadows or `border-radius` anywhere except a handful of sub-20px decorative dots and skeleton blocks. (2) There's only one serif stack (Georgia) used for all headlines and body copy, and one sans-serif stack reserved strictly for button/chrome labels, never for content.
- **Known live bug:** `--color-ink` is referenced in two components but never defined anywhere in the stylesheet — see Deep Dive §2 and §8.
- **Where to jump for a given task:**
  - Adding/changing a color or font → Deep Dive §2 (Tokens)
  - Sizing text → Deep Dive §3 (Type scale)
  - Laying out a page or section → Deep Dive §4 (Spacing and layout)
  - Deciding between a border, a rule, or a shadow → Deep Dive §5
  - Reusing or extending a `ui/` component → Deep Dive §6
  - Checking whether something you're about to write is disallowed → Deep Dive §7 (Banned)
  - Known inconsistencies and open gaps → Deep Dive §8

**note**
- We are taking inspiration from craigslist in the sense of prioritizing UX over UI. If there is ever a decision to be made between the two, it should aways fall towards UX. Always prioritize making things clear and easy for the user.

**future work**
- "thecommonsweb" needs to have a UI update. It is too confusing and dense- but has a nice look to it. Suggested approach is to ask users if they can figure out
how to do something simple (like find an event they'd want to go to), and documenting how they go about it. For example, where do they look first, where do they
get stuck etc- then mold the changes to the website strucutre to facilitate the usage of the broad majority and eliminating blockers, etc. 

## Deep Dive

### 1. What this is, in one paragraph

The Commons is styled to look like a broadsheet newspaper's classifieds page had a baby with early Craigslist: serif type, cream newsprint, black ink, hairline and thick column rules doing the job cards and shadows do everywhere else, and a bias toward packing information in rather than giving it room to breathe. This isn't a retro skin bolted onto a normal SaaS layout — it's the whole vocabulary. A contributor who reaches for a rounded card with a soft shadow because that's what every other product looks like is not making a small stylistic choice; they're building the wrong product. The reason it matters: The Commons is a *local* events bulletin for three small towns, not a venture-backed platform, and it wants to read like a community notice board someone would trust a neighbor posted to — not like a pitch deck. Density, rules, and serifs are load-bearing for that trust, not decoration.

### 2. Tokens

All color and font values are CSS custom properties declared once, on `:root`, in `globals.css`. **Nothing else defines colors or fonts** — Tailwind v4 is configured with a bare `@import "tailwindcss";` at the top of that same file and no `@theme` block, no `tailwind.config.js`/`.ts` anywhere in the repo. Components consume the tokens either as Tailwind arbitrary values (`bg-[var(--color-bg)]`) or the newer Tailwind v4 shorthand (`border-(--color-border)`) — both forms are in active use side by side; neither is preferred over the other in the current code.

| Token | Value | What it's for |
|---|---|---|
| `--color-bg` | `#f4f1eb` | Page background — the "newsprint cream." Default surface for everything. |
| `--color-bg-alt` | `#eae6dd` | A shade darker than `--color-bg`. Hover states on rows/cards, secondary surfaces (the digest box border-panel, dropdown item hover). |
| `--color-text` | `#1a1a1a` | Near-black ink. Body text, and (deliberately) also the default link color — links are not blue here. |
| `--color-text-muted` | `#555555` | Secondary text: bylines, metadata lines, captions, timestamps. |
| `--color-link` | `#1a1a1a` | Same value as `--color-text` — links read as ink, not as a distinct color, until hovered. |
| `--color-link-hover` | `#8b0000` | Dark red. Link hover state. |
| `--color-border` | `#1a1a1a` | Primary rule color — same near-black as text. Used for thick rules, card outlines, the hard "print" shadow (see §5). |
| `--color-border-light` | `#c8c3b8` | Hairline rule color. Dividers, `<hr>`, subordinate borders (e.g., the sidebar's column rule). |
| `--color-accent` | `#8b0000` | Dark red. Same value as `--color-link-hover`. Used sparingly: active/selected states, the "Verified" stamp, kicker labels, the accent rule under section nameplates. Not a general-purpose brand color — it means "selected" or "emphasis," and overusing it dilutes that. |
| `--font-headline` | `Georgia, "Times New Roman", Times, serif` | Headings (`h1`–`h6`, applied globally in `globals.css`), and anywhere a component sets `fontFamily: 'var(--font-headline)'` inline for a display-sized headline (e.g. the masthead `<h1>` in `Header.tsx`, the section nameplate in `EventFeed.tsx`, the footer watermark). |
| `--font-body` | `Georgia, "Times New Roman", Times, serif` | Body copy. Identical value to `--font-headline` today — there is exactly one serif stack in this system, split into two token names for future flexibility, not because they currently differ. |
| `--font-sans` | `-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif` | The *only* sanctioned escape from serif — reserved for small-caps UI chrome that needs to read as a control rather than as editorial copy: `Button.tsx`'s base class, the "Verified" stamp's inline style. Don't reach for it for anything a reader would read as content. |
| `--focus-ring` | `2px solid #1a1a1a` | Keyboard focus outline, applied globally via `:focus-visible`. |
| `--focus-ring-offset` | `2px` | Offset for the above. |

**Georgia is real, and it's loaded for free.** There is no `next/font` call anywhere in `src/app/layout.tsx` or elsewhere in the tree, no `@font-face`, no font files in an `assets/` directory (there isn't one). Georgia is a system font on essentially every OS that ships a browser; the stack falls through to Times New Roman / Times / generic serif if it's somehow missing. This is a deliberate performance and simplicity choice, not an oversight — it means zero font network requests, ever.

**CODING_STYLE.md drift:** its `--font-sans` snippet says `system-ui, ...` — the real value in `globals.css` starts with `-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif` and never mentions `system-ui` at all. Trust the CSS. Everything else in `CODING_STYLE.md`'s token table matches the stylesheet exactly.

**A token that's referenced but doesn't exist:** `TimeWindowSelector.tsx` and `SectionSelector.tsx` both reference `var(--color-ink)` (e.g. `text-[var(--color-ink)]`). There is no `--color-ink` custom property defined anywhere in `globals.css` or any other stylesheet in the repo — it isn't a synonym that resolves elsewhere. An undefined CSS custom property used without a fallback makes the property using it invalid at computed-value time, which for `color` means it falls back to the inherited value rather than doing anything the author intended. In practice this makes the inactive state of the time-window and section dropdowns render in whatever color they'd inherit rather than the near-black ink the rest of the system uses. This is a live bug, not a stylistic choice — the fix is renaming both usages to `--color-text`.

### 3. Type scale

There is no declared type scale (no `@theme` font-size tokens, no Tailwind config extending `fontSize`). What exists is the Tailwind v4 default scale (`text-xs` through `text-6xl`) plus a lot of arbitrary pixel values and `clamp()` expressions for display headlines that need to be fluid. Reading across `Header.tsx`, `EventFeed.tsx`, `EventRow.tsx`, `Sidebar.tsx`, `Footer.tsx`, and `MiniCalendar.tsx`, the sizes actually in use settle into these bands:

| Use | Typical value | Example |
|---|---|---|
| Masthead / site title | `clamp(2.75rem, 8vw, 6rem)`, `--font-headline`, `font-black` | `Header.tsx`'s `<h1>` |
| Section nameplate / featured headline | `clamp(1.6rem, 3.2vw, 3.25rem)` (varies by context), `--font-headline` | `SectionNameplate` and `FeaturedCard` in `EventFeed.tsx` |
| Card headline (non-featured) | `text-base` (1rem) to `text-2xl`/`text-3xl` for featured rows, `font-bold` | `EventRow.tsx` |
| Body copy | default `15px` set on `body` in `globals.css`, `line-height: 1.6` | site-wide default |
| Metadata / byline line | `text-xs` (0.75rem) or `text-[10px]`/`text-[11px]` | venue/time lines, footer copyright |
| Kicker / eyebrow labels | `text-[9px]`–`text-[10px]`, `uppercase`, `tracking-[0.18em]`–`tracking-[0.25em]`, `font-black` | "Featured Event," "Towns:," section labels throughout `Sidebar.tsx` and `Footer.tsx` |
| Calendar grid cells | `text-[8px]`–`text-[9px]` | `MiniCalendar.tsx` |
| Drop cap first letter | `3.2rem`, `--font-headline`, `font-weight: 700` | `.drop-cap::first-letter` in `globals.css` |

The pattern to copy: headlines are large and fluid via `clamp()` set inline (`style={{ fontSize: '...' }}`), everything else is small, uppercase, and letter-spaced when it's a label rather than content. There is no `text-4xl`/`text-5xl`/`text-6xl` Tailwind class in use anywhere — display sizes are handled by `clamp()`, not the static scale, because they need to shrink on mobile without a breakpoint ladder.

### 4. Spacing and layout

No custom spacing scale — Tailwind's default spacing scale (the `p-1`, `px-4`, `gap-6`, etc. system) is used directly, no `@theme` override. Two layout constants recur:

- **Content max-width `960px`** — `PageLayout.tsx`'s `<main>` (`max-w-[960px]`), the reading column.
- **Chrome max-width `1200px`** (written as Tailwind's `max-w-300`, i.e. `300 × 4px = 1200px`) — `Header.tsx`, `Footer.tsx`, `TopBar.tsx`, `TagsBar.tsx` all use this wider band for the masthead and nav strips that span above/below the reading column.

The sidebar/content split (`PageLayout.tsx`) is a 4-column CSS grid, sidebar taking 1 of 4 columns on large screens (`lg:grid-cols-4`, `lg:col-span-1` / `lg:col-span-3`), stacking to a single column below `lg`. The sidebar is separated from content by a `border-r border-[var(--color-border-light)]` hairline rule, not a gap-only whitespace split — this is the density-over-whitespace principle showing up structurally, not just typographically.

Density in practice: `Sidebar.tsx` stacks a dozen-plus distinct blocks (post button, date, calendar, view toggle, social link, tag filters, clear-filters, count, digest box) separated only by `<hr>` hairlines with no card wrapper around any of them. That's the intended texture — a long, rule-divided column, not a stack of padded cards.

### 5. Rules, borders, and the one shadow that's allowed

This is the section that replaces "cards with shadows for elevation." The system has exactly four separation devices, and reaching for anything outside this list should be treated as a smell.

| Device | CSS | Where it shows up |
|---|---|---|
| Hairline rule | `border-*-[var(--color-border-light)]`, 1px | Dividers between list rows, sidebar `<hr>`, footer link-column separators |
| Standard rule | `border-*-[var(--color-border)]`, 1–2px | Card/panel outlines (`EventRow.tsx` non-featured, `Modal.tsx`), the header's rule under the tagline |
| Thick rule | `.rule-thick` (`border-top: 3px solid`) / `.rule-double` (`border-top: 3px double`), both against `--color-border` | Section breaks that need more visual weight than a standard rule; declared as utility classes in `globals.css` but not currently called from any component in `src/components/` — available, underused |
| Hard "print" shadow | `shadow-[3px_3px_0px_var(--color-border)]` — a flat, zero-blur, fully-opaque offset box, not a soft/blurred elevation shadow | `Modal.tsx`, the featured variant of `EventRow.tsx` |

That fourth row is the one to read carefully, because "no drop shadows" (the banned-list rule in §7) sounds like it should ban this too, and it doesn't — this is a hard-edged, zero-blur, fully-opaque offset that reads as a printed card stacked on newsprint (think a paper cutout with a solid ink-black edge behind it), not a soft ambient shadow implying elevation off the page. The distinguishing test: if the shadow has any blur radius, or any transparency, it's the banned kind. `shadow-[3px_3px_0px_var(--color-border)]` is the *only* shadow value used anywhere in `theCommonsWeb/src`, and it's used in exactly two places. Don't invent a second shadow value — reuse this one if a component genuinely needs the "stacked card" effect, and default to a hairline or standard rule (row 1 or 2) for everything else.

**Decision procedure:** reaching for a shadow to create separation between a block and its background? First ask whether a rule (row 1–3) does the job — it almost always does, since most separation here is "this is a distinct row/section," not "this is floating above the page." If the block genuinely needs to read as a card sitting on top of the page (a modal, a featured/pinned item), use the exact hard-shadow value above, never a new blurred one.

### 6. Component inventory — `src/components/ui/`

Eight components, seven exported from `index.ts` (`Banner.tsx` exists in the directory but is not re-exported — import it directly from `../ui/Banner` if needed, or add it to the barrel if this omission isn't intentional; nothing else in the tree currently imports it that way, so it's unclear whether the omission was deliberate).

| Component | Purpose | Notable behavior |
|---|---|---|
| `Button` | The only button styling in the system | Three variants: `primary` (filled ink-black, inverts to accent-red on hover), `secondary` (outlined, transparent, bg-alt on hover — the default), `link` (looks like an inline text link, no border/padding). Two sizes (`sm`, `md`). Uppercase, letter-spaced, bold, `--font-sans` — buttons are chrome, not editorial content, hence the one place `--font-sans` is baked into a component rather than opted into. |
| `Badge` | Small inline tag/label pill — but square, not pill-shaped | `active` boolean toggles between an inverted (filled ink, cream text) and outlined (hairline border, muted text) treatment. No `border-radius` at all. |
| `Banner` | Dismissible strip, optionally sticky with scroll-direction hide/reveal | Two variants (`default`, `accent`) that only change the border color. Not in the `ui` barrel export — see above. |
| `Input` | Labeled text input | Label is a separate `<label>` above the field, uppercase/letter-spaced/bold — every form control in this system labels itself this way, not via placeholder text. Square corners, hairline border that changes to accent-red on focus. Error message renders as accent-red text below the field with `role="alert"`. |
| `Link` | Styled `<a>` wrapper | Adds `target="_blank" rel="noopener noreferrer"` automatically when `external` is set. Otherwise just underline + accent-red hover. |
| `Modal` | Dialog with focus trap | Full accessibility handling: restores focus to the trigger on close, traps `Tab`/`Shift+Tab` inside itself, closes on `Escape` or backdrop click, uses `role="dialog"` + `aria-modal` + `aria-labelledby`. Visually: the hard print-shadow from §5, a 2px border, square corners, a title bar separated from the body by a rule rather than padding alone. |
| `Select` | Labeled `<select>` | Same label/error pattern as `Input`. |
| `Textarea` | Labeled `<textarea>`, not resizable (`resize-none`) | Same label/error pattern as `Input`/`Select`. |

**Pattern to notice and reuse:** `Input`, `Select`, and `Textarea` are near-identical in structure (label above field, `useId()` for a stable id when none is passed, `aria-describedby` wired to an error paragraph, same border/focus-color treatment) — deliberately, not by accident. A new form control should copy this shape rather than inventing a new labeling convention.

**When to reuse vs. add a new component:** if what you need is a differently-colored button, a differently-sized input, or a badge with a third state, that's a prop on the existing component, not a new file — none of the existing `ui/` components take a `variant` prop that isn't exhaustive of what's actually used elsewhere in the app. Add a new component only when the *shape* is new (nothing here is a modal-with-a-form, a toast, a tooltip, a dropdown-menu-as-a-primitive — `TimeWindowSelector.tsx` and `SectionSelector.tsx` in `layout/` each hand-roll their own dropdown rather than sharing one, which is itself worth noticing as duplication if you're about to build a third one).

### 7. Banned — enforceable in code review

If a diff introduces any of the following, it doesn't match this system regardless of how good it looks in isolation:

| Banned | Why | Use instead |
|---|---|---|
| Any CSS `gradient` (`bg-gradient-*`, `linear-gradient`, `radial-gradient`) | Zero occurrences anywhere in `theCommonsWeb/src` today. Gradients are the single fastest way to make this look like a SaaS landing page. | Flat fills from the token table (§2). |
| Soft/blurred `box-shadow`, any elevation shadow implying the element floats above the page | Reads as Material/modern-web "card elevation," which is exactly the vibe this system rejects. | A rule (§5, rows 1–3) for ordinary separation; the one hard, zero-blur, fully-opaque offset shadow (§5, row 4) for the rare case that genuinely needs a "stacked card" read. |
| `border-radius` on buttons, cards, badges, panels, inputs (`rounded-lg`, `rounded-md`, `rounded-xl`, pill shapes) | This is the single most likely muscle-memory violation — `rounded-lg` is many developers' unthinking default. Square corners are load-bearing for the newsprint/broadsheet read. | No radius. If you must round something, look at what's actually rounded in this codebase today (below) before adding a new instance. |
| `backdrop-blur`, translucent frosted-glass panels (glassmorphism) | Zero occurrences in the codebase. Directly contradicts "ink on paper" — glass implies a screen-native, modern-app surface. | Opaque fills only, from `--color-bg` / `--color-bg-alt`. |
| Sans-serif for headlines or body copy | `--font-sans` exists on purpose but is scoped to button/chrome labels — see §2. | `--font-headline` / `--font-body` (both Georgia). |
| Placeholder-text-as-label on form fields | Every form control in `ui/` puts the label outside the field, always visible — not inside it as placeholder text that disappears on focus. | Copy the `Input`/`Select`/`Textarea` label pattern. |
| Bright/saturated brand colors beyond the palette in §2 | There are exactly nine color tokens and two of them are duplicates of each other. Adding a tenth ad hoc hex value (a "brand blue," a success-green, etc.) is scope creep on the palette. | Reuse `--color-accent` for emphasis; reuse `--color-text-muted` for de-emphasis. If a genuinely new semantic color is needed (e.g. an error state distinct from the accent-red used for links), that's a design decision to raise, not a component-level choice. |

**The one real exception, so it doesn't get cited to justify a bigger one:** `rounded-full` and `rounded-sm` show up in exactly four places, all decorative and all under 20px square — the tiny unread-notification dot in `HeaderAuthNav.tsx`, the tag-filter selection dot in `Sidebar.tsx`, the "has events" dot under a calendar day in `MiniCalendar.tsx`, and the loading-skeleton blocks (`.skeleton-block`, `MiniCalendar.tsx`, `CalendarView.tsx`) which round to 1px via `border-radius: 1px` in `globals.css` — barely perceptible, there to keep skeleton blocks from reading as harsh rectangles mid-pulse. None of these is a button, a card, or a container. If a new use of `rounded-*` isn't a sub-20px indicator dot or a skeleton block, it's a violation, not precedent.

**Before/after — button:**

```
// Wrong — reads as a generic web-app button
<button className="rounded-lg shadow-md bg-blue-600 text-white px-4 py-2">
  Post an Event
</button>

// Right — use the existing component
<Button variant="primary">Post an Event</Button>
```

**Before/after — a card-like block:**

```
// Wrong — soft shadow + radius reads as Material/SaaS
<div className="rounded-xl shadow-lg p-4 bg-white">
  {event.title}
</div>

// Right — square corners, a rule (or the hard print-shadow if it must look stacked)
<div className="border border-[var(--color-border)] p-5 shadow-[3px_3px_0px_var(--color-border)]">
  {event.title}
</div>
```

### 8. Known drift and gaps

- **`--color-ink` is used but never defined** (§2) — a live bug in `TimeWindowSelector.tsx` and `SectionSelector.tsx`, not a documented token. Fix by renaming both usages to `--color-text`.
- **`Banner.tsx` is not exported from `src/components/ui/index.ts`** — every other `ui/` component is. Unclear whether this is intentional; flagged rather than silently fixed since fixing it is a code change outside this doc's scope.
- **`CODING_STYLE.md`'s `--font-sans` value is stale** (§2) — it shows `system-ui, ...`, the real stack starts `-apple-system, BlinkMacSystemFont, ...` and never mentions `system-ui`.
- **`.rule-thick` and `.rule-double` are declared but unused** in current components — available utilities, not dead weight to remove, but don't assume every declared utility class is actively demonstrated somewhere; check before copying a pattern that "must" exist because the CSS defines it.
- **Two dropdown implementations that could be one:** `TimeWindowSelector.tsx` and `SectionSelector.tsx` each hand-roll near-identical hover/click-to-lock dropdown logic rather than sharing a primitive. Not a visual-design violation, but worth knowing before adding a third bespoke dropdown.
- **Not verified:** whether any page outside `src/components/` (route-level files directly in `src/app/`) introduces styling that bypasses these tokens — this doc was grounded in `globals.css`, `components/ui/`, `components/layout/`, and `components/events/`, not an exhaustive read of every route file.
