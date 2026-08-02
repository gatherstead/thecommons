# Ingestion Source Buildout — Handoff (8-1)

**Run:** 2026-07-31 → 08-01 · **Branch:** `all-things-ingestion` · **Base commit:** `f583963`

A batch classification + build pass over ~48 candidate Triangle-area event sources. Each URL
was classified as `ics` / `http` / `scraper` per `EventSource.source_type`, and every
`http`/`scraper` source got a `Scraper` subclass, a trimmed real HTML fixture, and a fast test.

**Status (updated 2026-08-02): merged to `main` via PR #41 and deployed.** Five sources were
wired up in production by hand with `manage.py add_source` — Patch Raleigh (23), Thriving in
Raleigh (24), Eventbrite Morrisville (25), Patch Morrisville (26), Morrisville Chamber (27).
The remaining built scrapers and the confirmed ICS feeds below still have no `EventSource`
rows; adding them is a manual step (see "Wiring these up").

## Results at a glance

| Outcome | Count | Meaning |
|---|---|---|
| 🔨 Built | 20 | Scraper + fixture + fast test written and registered |
| ✅ ICS | 7 | Confirmed `VEVENT` feed — **zero code needed** |
| ❌ Not feasible | 15 | Rejected, with reason |
| ⚠️ Duplicate | 3 | Same data as a stronger source already covered |
| ⏭️ Pre-existing | 4 | Already built before this run |

Verification at the base commit: `ingestion` fast tier **112 tests, all passing**;
`ruff check ingestion/` clean; scraper registry holds **24 entries, no key collisions**.

---

## Durham

| Source | Verdict | Key | ICS link | Reasoning |
|---|---|---|---|---|
| City of Durham | ✅ ICS | `durhamnc` | `https://www.durhamnc.gov/common/modules/iCalendar/iCalendar.aspx?catID=14&feed=calendar` | CivicPlus. Community Calendar (catID=14) confirmed but sparse; City Council (catID=29) carries 54 events |
| Downtown Durham Inc. | ✅ ICS | `downtowndurham` | `https://downtowndurham.com/downtown-events/?ical=1` | WordPress/Tribe `?ical=1`, 30 events, `America/New_York` VTIMEZONE |
| Durham Central Park | ✅ ICS | `durhamcentralpark` | `https://durhamcentralpark.org/events/?ical=1` | WordPress/Tribe `?ical=1`, 30 events |
| Patch Durham | ⏭️ Pre-existing | `patchdurham` | — | Built prior to this run |
| Discover Durham | ❌ | — | — | Craft CMS, not the Simpleview widget the other DMO sites use. Events widget calls an **auth-gated Meilisearch** endpoint requiring a `Bearer` header, and only fires after the widget scrolls into view (`data-x-async="intersect"`). Both are outside what the importer and renderer can do |
| durhamdowntown.com | ❌ | — | — | A different organization from Downtown Durham Inc. Static marketing page listing recurring highlights by month name only ("MAR — Durham Mardi Gras"), with no year-specific dates. Structurally undated, not a seasonality artifact |

## Raleigh

| Source | Verdict | Key | ICS link | Reasoning |
|---|---|---|---|---|
| **City of Raleigh events** ⭐ | 🔨 Built (`http`) | `raleighnc` | — | Not on the original candidate list — discovered as the real Drupal citywide calendar that the two dead hub pages both link to. Server-rendered with ISO8601 `<time datetime>` per event |
| Visit Raleigh | 🔨 Built (`scraper`) | `visitraleigh` | — | Classic Simpleview `rest_v2` widget, same shape as the existing Visit Chapel Hill scraper |
| Downtown Raleigh | 🔨 Built (`http`) | `downtownraleigh` | — | Third-party vendor JSON API. See sharp edge below — the URL is not org-owned |
| Thriving in Raleigh | 🔨 Built (`http`) | `thrivinginraleigh` | — | Squarespace Events block, server-rendered |
| Triangle on the Cheap | 🔨 Built (`http`) | `triangleonthecheap` | — | Regional aggregator. Real listing lives at `/events/`. **Not** WordPress/Tribe despite the platform's prevalence locally — it's a custom "Living on the Cheap" network theme |
| Eventbrite Raleigh | 🔨 Built (`http`) | `eventbriteraleigh` | — | Reads `window.__SERVER_DATA__`. See the Eventbrite quality caveat below |
| Patch Raleigh | 🔨 Built (`http`) | `patchraleigh` | — | |
| Event Calendars hub | ❌ | — | — | Redirects to a URL that returns 403 to both plain fetch and headless render; content recovered via the Wayback Machine to confirm it is purely a directory of links, with no first-party feed of its own |
| Special Events Calendar | ❌ | — | — | **Not** permit records — genuine resident-facing events. Blocked on architecture: data lives behind a POST JSON-RPC endpoint, and the HTTP importer only issues a plain GET. See "Known gaps" |
| Arts & Cultural Events | ❌ | — | — | Pure link hub — arts orgs and galleries, no event markup or JSON-LD of its own |

## Pittsboro / Chatham

| Source | Verdict | Key | ICS link | Reasoning |
|---|---|---|---|---|
| Pittsboro Town Calendar | ✅ ICS | `pittsboronc` | `https://www.pittsboronc.gov/common/modules/iCalendar/iCalendar.aspx?catID=14&feed=calendar` | CivicPlus, catID=14 confirmed |
| MOSAIC at Chatham Park | ✅ ICS | `mosaicchathampark` | `https://www.mosaicatchathampark.com/events/list/?ical=1` | Tribe `?ical=1`, 19 events. **The real domain is `mosaicatchathampark.com`** — note the "at" |
| Chatham Chamber | 🔨 Built (`http`) | `chathamchamber` | — | GrowthZone/ChamberMaster site |
| Eventbrite Pittsboro | 🔨 Built (`http`) | `eventbritepittsboro` | — | |
| Patch Pittsboro | 🔨 Built (`http`) | `patchpittsboro` | — | |
| Visit Pittsboro | ⏭️ Pre-existing | `visitpittsboro` | — | |
| The Plant NC | ⏭️ Pre-existing | `theplantnc` | — | |
| Explore Pittsboro | ❌ | — | — | Wix site whose events page embeds a Google Calendar through a Wix custom-HTML app. That app returns "App Unavailable" both on full render and on direct iframe fetch — a dead third-party embed on their end, not a render-timing problem |
| Chatham County Government | ⏭️ Skipped | — | — | Evaluated and rejected earlier; Akamai fingerprint-blocks headless regardless of user agent, and it exposes no ICS or JSON-LD. Deliberately not re-probed |

## Chapel Hill

| Source | Verdict | Key | ICS link | Reasoning |
|---|---|---|---|---|
| Chapel Hill Arts | 🔨 Built (`http`) | `chapelhillarts` | — | The listed festivals page is undated marketing copy, but its own nav links to a `/calendar/` FullCalendar widget backed by a clean public JSON REST API. Built against the API, not the listed page |
| Town Calendar | ⚠️ Built (`scraper`), low fidelity | `chapelhillnc` | — (none found; not CivicPlus) | Granicus **OpenCities**, not CivicPlus — the CivicPlus feed playbook does not apply, and no ICS exists anywhere on the site. See sharp edge below |
| Visit Chapel Hill | ⏭️ Pre-existing | `visitchapelhill` | — | |
| Downtown Chapel Hill | ❌ | — | — | Duda-platform marketing page — copy, an Instagram embed, and a "Submit Your Event" call to action. No dated listing even after a full JS render, and no separate listing page exists. The `http://` URL works fine; there is no certificate or redirect problem |
| Chapelboro | ❌ | — | — | **Real and plentiful data — 86 events confirmed for August 2026** — but unreachable. See "Known gaps" |

## Carrboro

| Source | Verdict | Key | ICS link | Reasoning |
|---|---|---|---|---|
| Speakeasy Carrboro | ✅ ICS | `speakeasycarrboro` | `https://calendar.google.com/calendar/ical/c_2c7c15deea70b1fcc8830b6fa63919fbb2d86735551fd446dadd68abf00f7c67%40group.calendar.google.com/public/basic.ics` | The `/events/` page lists only undated recurring series names, but `/calendar/` embeds a public Google Calendar carrying **602 events**. Highest-volume find of the run |
| Town of Carrboro | ⚠️ ICS, likely duplicate | `carrboronc` | `https://www.townofcarrboro.org/common/modules/iCalendar/iCalendar.aspx?catID=46&feed=calendar` | CivicPlus catID=46, 62 events. Very likely the same feed as the long-running production Carrboro source — **diff before adding a second row** |
| Carrboro Music Festival | ❌ | — | — | Vanity domain served by the same CivicPlus install as the Town of Carrboro site. A "Signature Events" link hub of program names and blurbs with no machine-readable dates |

## Cary

No ICS feed was found for any Cary source — this town's coverage is entirely `http`/`scraper`.

| Source | Verdict | Key | Reasoning |
|---|---|---|---|
| Cary Chamber | 🔨 Built (`http`) | `carychamber` | Weebly page with an empty WeblinkConnect widget; its XHR resolves to a plain unauthenticated XML endpoint reachable without a browser. **43 upcoming events**, stable per-event ids |
| Downtown Cary | 🔨 Built (`http`) | `downtowncarync` | Tribe, server-rendered as a **month grid** rather than a list. 26 events. No venue markup in month view, so `location` is left blank. `?ical=1` was checked and rejected — see the Tribe false-positive gotcha below |
| Cary Sister Cities | 🔨 Built (`http`) | `carysistercities` | Squarespace stock Events collection — **not Wix**, despite the `/events-1` URL |
| Visit Raleigh — Cary | ⚠️ Built (`scraper`), currently empty | `visitraleigh_cary` | Same Simpleview widget as the main Visit Raleigh calendar. See sharp edge below |
| Cary Downtown Events Calendar | ❌ | — | Akamai 403 on both plain fetch and headless render; the page never renders at all, so it could not even be classified |
| Cary Recreation & Entertainment | ❌ | — | Same Akamai block. The open question of whether this is a program-registration catalog rather than public events remains unanswered |
| Downtown Cary Park | ⚠️ Duplicate | — | FullCalendar widget behind an AWS WAF challenge. Its events are the same organization's downtown-park programming already covered by Downtown Cary, plus some recurring drop-ins. The weaker route: needs a browser where the alternative needs a plain GET |
| Cary Spotlight | ❌ | — | Remix/Beehiiv newsletter — **not Wix**. The events page is a single hand-authored prose digest ("Nov 25th 2025 (Tuesday) — Stroller Stretch — 9:30AM-10:30AM") with no ids, links, or ISO dates, covering one date range that is roughly eight months stale |

## Morrisville

No ICS feed was found for any Morrisville source (the town's `.gov` calendar has no
CivicPlus-style export, and `mymorrisville.com`'s working Tribe feed belongs to the wrong state
— see below).

| Source | Verdict | Key | Reasoning |
|---|---|---|---|
| Morrisville Events Directory | ⚠️ Built, **blocked in prod** | `morrisvilleevents` | Extractor is correct against the fixture, but `morrisvillenc.gov` Akamai-blocks the prod egress IP domain-wide (root path 403s too) while allowing normal residential fetches — which is why it looked clean during classification. See sharp edge below |
| Morrisville Chamber | 🔨 Built (`http`) | `morrisvillechamber` | ChamberMate SPA shell; its own public unauthenticated JSON API is reachable with a plain GET. See sharp edge — the source URL is an API endpoint, not a page |
| Eventbrite Morrisville | 🔨 Built (`http`) | `eventbritemorrisville` | |
| Patch Morrisville | 🔨 Built (`http`) | `patchmorrisville` | The listed section landing page has no calendar data; the `/calendar` sibling does and is what the scraper targets |
| Morrisville Special Events | ⚠️ Duplicate | — | Prose plus a client-side-only calendar widget with no dates in the static HTML. A curated, tagged subset of the Events Directory calendar — several Events Directory items already carry the "Special Events" tag |
| **mymorrisville.com** | ❌ | — | **Morrisville, Pennsylvania** (Bucks County), not North Carolina — confirmed from the site's own JSON-LD `addressRegion`. It is a working Tribe calendar (its own `?ical=1` would resolve), which is precisely the hazard: building it would have silently injected out-of-state events |
| Meetup Morrisville | ❌ | — | Not auth-blocked as expected — a plain fetch returns usable `__NEXT_DATA__`. The problem is scoping: it is a metro-wide "near me" discovery feed where **none of the eight results had a Morrisville venue** (all Raleigh, Cary, or Durham). Building it would misattribute other cities' events |
| Visit Raleigh — Morrisville | ❌ | — | Not a dynamic listing at all — a static editorial page of hand-written paragraphs naming a few annual events, with no dates and no widget markup |

---

## Confirmed ICS feeds

The same links appear inline in each city's table above; this is the quick copy-paste version,
sorted by volume. These need **no code** — add each in the playground as `source_type=ics`
with the URL below.

| Key | Feed URL | Events |
|---|---|---|
| `speakeasycarrboro` | `https://calendar.google.com/calendar/ical/c_2c7c15deea70b1fcc8830b6fa63919fbb2d86735551fd446dadd68abf00f7c67%40group.calendar.google.com/public/basic.ics` | 602 |
| `carrboronc` | `https://www.townofcarrboro.org/common/modules/iCalendar/iCalendar.aspx?catID=46&feed=calendar` | 62 |
| `downtowndurham` | `https://downtowndurham.com/downtown-events/?ical=1` | 30 |
| `durhamcentralpark` | `https://durhamcentralpark.org/events/?ical=1` | 30 |
| `mosaicchathampark` | `https://www.mosaicatchathampark.com/events/list/?ical=1` | 19 |
| `pittsboronc` | `https://www.pittsboronc.gov/common/modules/iCalendar/iCalendar.aspx?catID=14&feed=calendar` | 2 |
| `durhamnc` | `https://www.durhamnc.gov/common/modules/iCalendar/iCalendar.aspx?catID=14&feed=calendar` | 1 (see note) |

The Durham city feed is per-category. catID=14 is the Community Calendar and is the best
semantic match for public events, but it is nearly empty right now. Higher-volume siblings, if
meeting coverage is ever wanted: catID=29 City Council (54), catID=34 Boards & Committees (23),
catID=46 Public Hearings (6).

## Wiring these up

Nothing here creates database rows. For each built scraper, enter in
`/devtools/ingestion-playground`: `source_type` and `url` as declared on the scraper class,
plus `scraper_key` from the Key column above.

For local dev, `python manage.py seed_sources` projects the whole registry into `EventSource`
rows in one step — it keys on URL, so it is idempotent and will adopt a row already made by
hand rather than duplicating it. It refuses to run when `DEBUG` is off unless forced.

## Sharp edges

**Morrisville Events Directory is Akamai-blocked from the production host, not from a
classification workstation.** Verified 2026-08-02: the exact request the scraper makes (same
UA, same URL) returns `200` from a normal residential/dev network but `403` from the prod
Oracle Cloud VM's egress IP, with an Akamai `server-timing: ak_p` fingerprint and a
`x-reference-error` id — the same signature already seen on Chatham County and `carync.gov`.
The block is domain-wide (the bare root and `Things-To-Do/Special-Events` both 403 too), not
scoped to the `/Events-directory` path. Spot-checking eight other newly-confirmed sources from
the same prod IP all returned `200`, so this is not a general Oracle Cloud ASN block — it is
specific to `morrisvillenc.gov`. The scraper's `extract()` is correct; this is purely a
fetch-layer failure that a classification pass run from a different network cannot catch. No
fix exists within this project's current importer (no proxy/relay layer) — treat this source as
**not usable from prod** until that changes, despite being "built."

**Chapel Hill Town Calendar returns titles and dates only.** The rendered DOM carries a title,
a day-of-month, and a stable per-series GUID — and nothing else. Time of day, location,
description, and permalink exist only in an XHR response body that `extract()` never sees, so
start times default to midnight, matching the precedent the Visit Chapel Hill scraper already
set. This is a deliberate fidelity tradeoff, not a bug to fix in the extractor: getting the
missing fields requires capturing the XHR, which the current renderer cannot do. Decide whether
title-and-date-only clears the quality bar before enabling it.

**Visit Raleigh — Cary will fail until Cary's calendar has events.** The town-scoped widget
reproducibly returns "No events were found." Because its wait selector therefore never
populates, `render_page` times out and returns an empty string, and the source will report
`REFUSAL_EMPTY_FETCH` in production. This reflects real site state rather than a code defect,
but it will look like a broken source on the monitor dashboard. Its test fixture necessarily
reuses real event blocks from the same widget template, since the live page had none to capture.

**The Downtown Raleigh URL is a third-party vendor endpoint with an embedded key.** This looks
alarming and mostly isn't: Downtown Raleigh Alliance has no first-party calendar, and their own
marketing page calls this same endpoint. The `key=` parameter turns out not to be validated at
all — the feed returns identically with the live key, a garbage key, or no key, and the key
committed in the module has already silently drifted from the current live one while continuing
to work. Don't "fix" it by chasing key rotation; there is nothing to rotate.

**The Morrisville Chamber source URL is a JSON API endpoint, not an HTML page.** This works
because the HTTP importer simply fetches the URL and hands the response body to `extract()` as
a string, but it is a different shape from every other `http` scraper in the codebase, which
fetch real pages. Its fixture carries JSON despite the `.html` extension the fixture naming
convention requires.

**Patch's two event shapes.** Durham and Raleigh carry Patch-authored event nodes with ISO
dates and a body. Pittsboro and Morrisville carry **zero** of those — their calendars are built
entirely from syndicated `patchAmFreeEvent` nodes, which use a date-only field plus a separate
twelve-hour time string, link off-site, and have no description field at all. The shared
`PatchScraper` base reads both. A scraper copied from the Durham module alone would return zero
events for those two cities with no error.

**Eventbrite discovery pages are noisy by nature.** They mix in promoted listings, recurring
class spam, and events well outside the nominal city. Extraction works; whether the output is
worth ingesting is a separate judgment worth making per city after a dry run.

## Known gaps

**Two real feeds are blocked by importer and renderer limits, not by the sites.** Both are
worth revisiting if the fetch layer ever grows:

- *Raleigh Special Events* — the data is clean structured JSON, but only reachable by POST to a
  JSON-RPC endpoint. The HTTP importer issues a plain GET and cannot send a body; GET against
  that endpoint returns 404, and GET with a query string is firewall-blocked. Adding a
  POST-capable fetch strategy would unlock it with no HTML parsing at all.
- *Chapelboro* — the EventON plugin surfaces only the current day on initial load; everything
  beyond it requires a second POST carrying a nonce minted by that page load. The renderer
  performs a single navigation and wait, with no interaction or injection hook, and plain
  fetches are Akamai-blocked, so there is no fallback path.

**Also blocked by the no-scroll renderer:** Discover Durham's widget only fires its fetch once
scrolled into view, so any wait selector against it will time out in production.

**Unverifiable:** both `carync.gov` pages are Akamai-blocked to headless clients, so the
question of whether the Recreation & Entertainment page is a public-events calendar or a
program-registration catalog could not be answered either way.

**Not done:** the five sources wired up in prod (ids 23-27) have not yet completed a live poll —
prod runs `INGEST_SHARD_COUNT=3` with `n = day_of_year % 3`, so they come up over the following
three daily runs rather than immediately. Sources beyond those five still have no `EventSource`
rows, and the two duplicate candidates (Town of Carrboro against the existing production feed,
Downtown Cary Park against Downtown Cary) have not been diffed against what is already
configured.

## Platform gotchas worth carrying forward

Four traps cost real time in this run and will recur on the next batch of candidate sources.

**CivicPlus feed discovery.** The obvious `iCalendar.aspx?CID=N` sibling of a CivicPlus
calendar returns HTTP 200 with an HTML subscribe-picker page — not a feed. The actual
per-category feed is at `/common/modules/iCalendar/iCalendar.aspx?catID=<N>&feed=calendar`, and
the picker page's own links enumerate the valid catIDs. Confirmed on three separate sites. Any
check that tests only for a 200 will false-positive here.

**Tribe's `?ical=1` can be a false positive.** On Downtown Cary's site it returned 200 with
valid `VEVENT` content containing only the current day's single event rather than the calendar
— which is why `downtowncarync` above is built as `http` against the month-grid DOM instead of
using its `?ical=1` link. Always check the event count, not merely that `BEGIN:VEVENT` appears.
The seven ICS links in the tables above were each verified by count.

**A 403 is not one thing.** An Akamai fingerprint block (403, often referencing
`errors.edgesuite.net`) fails for headless clients regardless of user agent — only a headed
browser passes, so production ingestion can never reach it and the source should be rejected
permanently. An AWS WAF challenge (HTTP 202 with an `x-amzn-waf-action: challenge` header) is
cleared by a headless render, so it merely rules out the plain-GET `http` path.

**Don't infer platform from URL shape, and confirm the town.** The `/events-1` path is the Wix
default slug, but two sites using it turned out to be Remix and Squarespace respectively.
Separately, one candidate domain was the same-named town in another state — verify the region
against the site's own structured data before building.
