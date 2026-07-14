---
description: Classify one or more URLs as an ICS Feed, Web Scraper, or HTTP Fetch ingestion source and build the extractor code
argument-hint: "[url | comma/newline-separated list of urls]"
---

# Classify & Build Ingestion Source

Turn a raw URL (or list of URLs) into a working ingestion source: classify which of the
three strategies it needs, then write the code for it. **Does not create the `EventSource`
DB row or run the live pipeline** — the user wires that up and tests it themselves via the
devtools playground (`/devtools/ingestion-playground`) or Django admin.

## Input

$ARGUMENTS

If empty, ask for a URL or list before proceeding.

## The three source types

`EventSource.source_type` (`backendServer/ingestion/models.py`) is one of `"ics"`,
`"scraper"`, `"http"`. Dispatch:

| Type | Fetch | Extract | Browser? |
|---|---|---|---|
| `ics` | `ingestion/importers/ics_importer.py:fetch_ics_feed` — generic iCalendar parser | built-in, no per-site code | no |
| `scraper` | `ingestion/importers/scraper_importer.py:fetch_scraper_source` → `ingestion/scraping/browser.py:render_page` (Playwright) | per-site `Scraper.extract(html)` | **yes** |
| `http` | `ingestion/importers/scraper_importer.py:fetch_http_source` — plain `requests.get()` | same per-site `Scraper.extract(html)` class as `scraper` | no |

`scraper` and `http` share the exact same `Scraper` subclass
(`ingestion/scraping/scrapers/base.py`, registered by `key` in
`ingestion/scraping/scrapers/__init__.py:_SCRAPERS`). They differ only in how the HTML is
obtained — so classification between the two only changes one field
(`source_type`) and whether the extractor needs the rendered DOM or the page fetches fine
over plain HTTP. `ics` needs no per-site code at all.

Reference example (all three concepts): `ingestion/scraping/scrapers/visitpittsboro.py` —
reads `<script type="application/ld+json">` schema.org `Event` blocks rather than scraping
CSS classes, because JSON-LD is stable across theme/plugin updates. Prefer this approach
whenever a target page has it.

## Step 1 — Classify each URL

For each URL, in order:

1. **Check for an ICS feed.** WebFetch the page and look for `<link rel="alternate"
   type="text/calendar">`, a visible `webcal://` or `.ics` href, or an "Export/Subscribe"
   control. Also try platform-specific patterns worth one fetch each even if not linked
   from the page:
   - WordPress "The Events Calendar" (Tribe) sites — look for `tribe-events` in class names
     — often expose `?ical=1` or `/events/list/?ical=1`.
   - Google Calendar embeds (`calendar.google.com/calendar/embed?src=...`) → the public
     export is `https://calendar.google.com/calendar/ical/<src>/public/basic.ics`.
   - Luma (`lu.ma`) calendars usually surface a direct `.ics` export link on the page.
   - Common blind guesses: `/events.ics`, `/calendar.ics`, `/feed.ics`.
   - Confirm a candidate by fetching it and checking it parses as `VEVENT` content, not just
     that the URL returns 200 — a guessed path can 200 into an HTML error page.
   - Found and confirmed → classify **`ics`**, confidence **high**.

2. **If no ICS, WebFetch the raw page** (no JS execution). If the *plain-HTTP* response
   already contains the event data — schema.org JSON-LD, a visible server-rendered listing,
   or a JSON API endpoint the page calls that you can hit directly — classify **`http`**.
   Confidence is **high** if it's structured data (JSON-LD/JSON API), **medium** if it would
   require scraping loosely-structured HTML text.

3. **If the plain-fetch HTML is a near-empty JS app shell** (a bare root `<div>`, no event
   markup in the server response) → classify **`scraper`**. Use `claude-in-chrome` (load
   `mcp__claude-in-chrome__*` tools via ToolSearch, per its skill) to render the page and
   inspect the real DOM before writing the extractor — don't guess selectors from the
   static fetch.

4. **If genuinely ambiguous** (site blocks fetches, conflicting signals, auth-gated) → mark
   confidence **low** and do not silently pick a type. Flag it for the user rather than
   building against a guess.

## Step 2 — Confirm before building

Present a table before writing any code:

```
URL | classified type | confidence | reasoning (1 line) | ICS URL (if found)
```

Ask the user to confirm or correct, especially anything at `low`/`medium` confidence — a
wrong scraper-vs-http call means re-inspecting the DOM and rewriting the extractor.

## Step 3 — Build

- **`ics`** — no code needed. Report the confirmed ICS URL back to the user; that's all
  `devtools/ingestion-playground` needs (`source_type=ics`, `url=<ics feed url>`).

- **`scraper` / `http`** — for each confirmed source:
  1. Get one real HTML sample. For `http`, the WebFetch result is sufficient. For `scraper`,
     use `claude-in-chrome` to get the fully-rendered HTML (JS executed).
  2. Save a **trimmed** real fixture at `ingestion/tests/fixtures/<key>.html` — representative
     events only, not the full page (mirror `visitpittsboro_month.html`).
  3. Write `ingestion/scraping/scrapers/<key>.py`: subclass `Scraper`
     (`ingestion/scraping/scrapers/base.py`), set `key`, `url`, `name` (human-readable
     attribution — becomes `Event.source_name`), implement
     `extract(self, html: str) -> list[RawEventData]`. Prefer JSON-LD extraction if the site
     has it (see `visitpittsboro.py`); otherwise parse the real markup with `lxml.html`
     against the saved fixture — don't invent selectors you haven't seen.
  4. Register it in `ingestion/scraping/scrapers/__init__.py`: import the class, add an
     instance to `_SCRAPERS`. Check the key isn't already taken.
  5. Write a fast test at `ingestion/tests/test_<key>_extract_fast.py`, modeled on
     `ingestion/tests/test_scraper_extract_fast.py` — pure `extract()` against the saved
     fixture, `@tag("fast")`, no DB/browser/network. If the extractor filters past events,
     mock/freeze `timezone.now()` to a fixed time the fixture's dates were built against.
  6. **Do not create the `EventSource` row or touch the DB/run the live pipeline** — report
     back exactly what the user needs to enter in `/devtools/ingestion-playground` to wire
     it up: `source_type=<scraper|http>`, `scraper_key=<key>`, `url=<url>`.

## Step 4 — Orchestrating batches

If given more than ~4 URLs, don't process them serially in your own context — the raw HTML
per site is bulky and drowns useful context. Spawn one subagent per URL (or small group) in
parallel to do Step 1 classification and (for scraper/http types) gather the HTML
sample + draft an `extract()` implementation against it. Have each report back: classified
type, confidence, reasoning, and a draft scraper file. You then:
- reconcile before writing anything for real (no duplicate `key`s across sources, consistent
  naming),
- write the actual files yourself,
- run the fast test suite once at the end for everything that was built.

## Done when

- Every URL has a classification the user confirmed (not a silent guess).
- `ics` sources: confirmed ICS URL reported, zero code written.
- `scraper`/`http` sources: `Scraper` subclass + registry entry + fixture + fast test exist,
  and `DJANGO_SETTINGS_MODULE=backend.settings.test uv run python manage.py test ingestion --tag=fast`
  passes.
- No `EventSource` DB rows were created and no live pipeline run was triggered — that's the
  user's job via devtools.
- The user has, for every source, the exact `source_type`/`scraper_key`/`url` to paste into
  the playground.
