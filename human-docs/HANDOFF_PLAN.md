# Human-docs handoff plan

> The paste-ready prompt for a `/handoff-report` session that authors the human-facing
> onboarding docs. The repo has none yet — this plan enumerates every non-obvious subsystem
> to document. Foundational subsystems first; a natural first cut is **overview → auth →
> ingestion → data-model** (what a new owner needs to be dangerous), then the rest.
>
> Naming note: doc filenames below match the routes in [`start-here.md`](start-here.md).
> Register each finished doc in [`README.md`](README.md)'s index.

---

## Prompt

```
Write human-facing onboarding documentation for The Commons into human-docs/. The repo
has NONE yet (human-docs/ holds only README.md + an empty index). Audience: an inheriting
owner / new teammate with general web-dev skill but zero context on THIS codebase — not
agents. Use the /handoff-report skill for each doc (it defines structure, grounding rules,
and the publish checklist): each doc = what the subsystem does + who depends on it, Mermaid
diagrams of REAL behaviour read from the code, data-model / interface tables, and the sharp
edges that bite newcomers. Ground every claim in code — read it, don't trust prose or these
notes blindly; flag drift. Register each doc in human-docs/README.md's index. Keep the
agent-facing docs/ tree untouched (link to it where a human should go deeper). Prose, not
bullet-dumps; the digital-newspaper voice is fine.

The non-obvious "sharp edges" below are SEEDS — confirm each against current code and expand.
Run these as separate /handoff-report passes, foundational subsystems first.

1. SYSTEM OVERVIEW — human-docs/overview.md
   What the product is (local events aggregator for Chapel Hill/Carrboro/Pittsboro), the
   monorepo layout (backendServer / theCommonsWeb / broadcastWeb / broadcastExtension /
   deploy), the end-to-end lifecycle of an event (ingested → standardized → published →
   optionally broadcast → emailed in a digest), and a single architecture diagram. The map
   a newcomer reads first. Sources: README.md, ARCHITECTURE.md, PROJECT_CONTEXT.md, code.

2. AUTH BRIDGE — human-docs/auth.md
   How Better Auth (Next.js) is the source of truth for identity and Django only mirrors it.
   The `accounts` app's neon_auth mirror models (managed=False + the double-quote db_table
   trick), JWKS/JWT verification (backend/jwt_auth.py, backend/permissions.py), the
   auth.thecommons.town cross-subdomain cookie setup. Sharp edges: JWKS fetch needs a
   browser User-Agent or Cloudflare 403s every verify (see docs/... incident); DJANGO_ENV
   must be "prod" in .env or prod silently falls back to dev settings → DisallowedHost 400 →
   "no events"; BetterAuthAccount.user_id is uuid not text (past ORM-join failures);
   password-required accounts + the passwordless-account rollover story. Sources: accounts/,
   backend/jwt_auth.py, backend/permissions.py, theCommonsWeb/src/lib/auth*.ts,
   docs/runbook-auth-cutover.md, docs/prd-centralized-auth.md.

3. INGESTION PIPELINE — human-docs/ingestion.md
   The poll → Gemini-standardize → dedup → safety-score → stage → publish flow, the three
   source types (ICS feed / web scraper / HTTP fetch) and how a source is classified,
   RawEvent/StagedEvent/EventSource, and where the LLM sits. Sharp edges: events.Event PK
   is `uuid` not `id` (Count("id") raises FieldError — use Count("pk")); INGEST_SHARD_COUNT
   makes plain ingest_events poll only a subset (use --shard for all); auto_publish
   early-returns when nothing is pending (call publish_all_approved to flush); source-classifier
   traps (CivicPlus real-ICS path, Tribe ?ical=1 false positive, Akamai vs AWS-WAF, Chatham
   County = Akamai-blocked/headless-only, GET-only no-scroll limits); never use the ORM inside
   sync_playwright. Sources: ingestion/, docs/ingestion-pipeline.md, docs/safety-scoring.md,
   the source-creation skill, memory of classification gotchas.

4. BROADCAST (event syndication) — human-docs/broadcast.md
   What broadcasting is (pushing published events onto third-party town calendars via
   Playwright + a Chrome extension), the adapter pattern, the operator SPA (broadcastWeb),
   and access codes. Sharp edges: broadcast/ is isolated by contract — routing.py must not
   import from events, and no ORM inside sync_playwright; broadcast runs on its own Celery
   queue drained by a SINGLE -c 1 worker (orphan-recovery correctness depends on it); the
   extension only autofills calendar hosts listed in manifest host_permissions (missing host
   = silent no-fill). This is a HUMAN summary — docs/broadcast.md stays the agent source of
   truth; link to it. Sources: broadcast/, broadcastWeb/, broadcastExtension/, docs/broadcast.md.

5. NEWSLETTER & DIGESTS — human-docs/newsletter.md
   The `newsletter` app: email-only subscribe, manage-token (login-free) preference page,
   the weekly + monthly digest engine (recipient resolution across subscribers + user
   profiles, Brevo send), and the Celery-beat schedule. Sharp edge: digest fan-out tasks
   live at newsletter.tasks.* (beat PeriodicTask rows were repointed in Suite 41). Sources:
   newsletter/, backend beat migrations.

6. ASYNC: REDIS + CELERY — human-docs/async-jobs.md
   Redis layout (DB 0 = broker/results, DB 1 = cache), the three queues (default / scrape /
   broadcast) and which worker drains each, and how beat schedules work. Sharp edges:
   CELERY_BEAT_MAX_LOOP_INTERVAL=6h starves beat's _do_sync so last_run_at lags up to 6h
   (fix = CELERY_BEAT_SYNC_EVERY=1) — never tune a staleness window without accounting for it;
   the TzAwareCrontab remaining_estimate tz bug (conversion lives only in is_due()). Sources:
   backend/settings/base.py, backend/celery.py, deploy/ units, docs/redis-celery-handoff.md,
   docs/ingestion-monitoring.md (last_run_at incident).

7. DEPLOYMENT & OPS — human-docs/deploy-ops.md
   The single Oracle Cloud VM, Neon Postgres, nginx + gunicorn (Unix socket), systemd units
   (celery / celerybeat / broadcast-worker / scrape-worker), how deploys happen, and media
   handling (MEDIA_ROOT lives OUTSIDE the checkout so git pull never touches uploads; nginx
   serves /media, never Django). Sharp edges: the DJANGO_ENV prod selector (above); the
   snap-uv user-slice teardown that took out the scheduler (prod incident); dev-DB isolation
   via Neon branches. Sources: DEPLOY.md, deploy/, docs/dev-db-isolation.md,
   docs/prod-incident-2026-07-21-scheduler-outage.md.

8. FRONTEND (main site) — human-docs/frontend.md
   Next.js 16 App Router structure, the services/hooks data layer, TanStack Query usage,
   Better Auth client integration, and the routes. Sharp edge: this is pnpm-managed — `npm
   install` fails on the symlinked store; type-check is `pnpm build`. Sources: theCommonsWeb/,
   theCommonsWeb/AGENTS.md.

9. DESIGN SYSTEM — human-docs/design-system.md
   The digital-newspaper aesthetic as an enforceable spec: Georgia serif, cream/ink palette,
   column rules, drop caps, density over whitespace; the banned list (no gradients, no rounded
   pill buttons, no startup/AI-forward vibes). CSS tokens and component conventions. Sources:
   CODING_STYLE.md, theCommonsWeb/src/app/globals.css, src/components/ui/.

10. DATA MODEL REFERENCE — human-docs/data-model.md
    Every core model and how they relate: Event, Town, Category, Tag; RawEvent, StagedEvent,
    EventSource, SourceRun; accounts (BetterAuth mirrors, UserProfile, BusinessProfile);
    NewsletterSubscriber; broadcast models. One ER-style Mermaid diagram + a table per model
    (fields, key relationships, which app owns it). Call out that Event PK is uuid. Sources:
    each app's models.py, ARCHITECTURE.md §Data Models.

11. TESTING & LOCAL DEV — human-docs/testing.md
    How to run everything locally (uv + pnpm, local Redis), the two backend test tiers
    (--tag=fast no-DB, --tag=db Postgres) and the test settings module, and the frontend test
    setup (vitest). Sharp edges: the Neon test DB is shared — concurrent test runs collide and
    green results are untrustworthy; run serially. Sources: backendServer/AGENTS.md#testing,
    CLAUDE.md, vitest.config.ts.

DEFINITION OF DONE: each doc reads as standalone onboarding for a human who's never seen the
repo; every diagram reflects real code paths (not idealized); every sharp edge is verified
against current code; each doc registered in human-docs/README.md's index with a one-line
purpose; internal links resolve. Docs only — no code changes. Where the agent-facing docs/
already cover something deeply, summarize for humans and link rather than duplicate.
```

---

## Suite 41 addendum (the refactor that prompted this)

When writing **auth.md**, **newsletter.md**, and **data-model.md**, fold in the Suite 41
outcomes: the `accounts` app owns identity (5 Better Auth mirrors + `UserProfile` +
`BusinessProfile`) and `newsletter` owns the digest engine; `backend/urls.py` is
`include()`-only; model moves were `SeparateDatabaseAndState` state-only (zero DDL,
`db_table` preserved, `neon_auth` never migrated). Document the deliberate
`accounts ↔ newsletter` import cycle (email-pref sync ↔ digest tag-filtering) so a reader
doesn't "fix" it by accident. Two agent-facing docs still carry stale references to fix in
the same pass: `docs/admin-backend.md` (`/admin/events/userprofile/` →
`/admin/accounts/userprofile/`) and `docs/redis-celery-handoff.md`
(`events.tasks.fan_out_*` → `newsletter.tasks.*`).
