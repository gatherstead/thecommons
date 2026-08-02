# Notion Sync — State

**This file is the source of truth for suite numbering. It persists — never delete it.**
Claude Code reads `Next suite number` before minting a new suite, then bumps it.
The ledger mirrors what *should* be on the Notion board so the desktop app can reconcile.

---

**Next suite number:** `45`

## Suite ledger

One row per suite = one card on the board. `Column` is the suite card's board column;
per-ticket status lives on each ticket subpage (see OUTBOX preamble).

| Suite | Title | Column | Tickets | Last synced |
|-------|-------|--------|---------|-------------|
| 17 | Fable code-review infrastructure | Needs QA | 17.1–17.4 | _(pending)_ |
| 18 | DB-backed broadcast access codes (centralized auth) | Needs QA | R1–R8 (18.1–18.8; R7 Open) | _(pending)_ |
| 19 | Sales codes | Needs QA | 19.1–19.6 | _(pending)_ |
| 20 | Scraper ingestion pipeline (visitpittsboro) | Needs QA | 20.1–20.5 | _(pending)_ |
| 21 | SEO hub pages | Needs QA | 21.1–21.3 | _(pending)_ |
| 22 | Code-quality hardening (lint / types / CI) | Needs QA | T0–T7, T12 | _(pending)_ |
| 23 | Dev tooling / slash-commands | Needs QA | 23.1–23.6 | _(pending)_ |
| 24 | Notion sync (outbox → Kanban) | Needs QA | 24.1–24.2 | _(pending)_ |
| 25 | Broadcast dispatch on Celery (kill the 3s Neon poll) | Needs QA | 25.1–25.9 | _(pending)_ |
| 29 | Standalone auth portal (auth.thecommons.town) | Open | 29.1–29.7 (never built → superseded by suite 37) | _(pending)_ |
| 30 | Broadcast auth + access-code debugging (JWT bridge, sign-in 401, tier-0, request reduction, hard reset) | Needs QA | 30.1,30.5–30.8 shipped; 30.2–30.4 → suite 37 | _(pending)_ |
| 31 | Broadcast client-feedback fixes (organizer/contact fields, AI autofill, TW tags + image uploads, ABC11 identity + date/time) | In Prod | 31.1–31.11 | _(pending)_ |
| 32 | Ingestion observability devtool (run history, live probe, funnel metrics, health flags) | In Prod | 32.1–32.8 | _(pending)_ |
| 33 | Ingestion monitor diagnostics correctness (health levels, zero legibility, GRANT detection) | In Prod | 33.1–33.5 | _(pending)_ |
| 34 | Ingestion pipeline resilience (dedupe corpus, standardizer fallback, direct-submission delivery) | In Prod | 34.1–34.5 | _(pending)_ |
| 35 | Prod scheduler outage (snap-uv user-slice teardown) + monitor correctness | In Prod | 35.1–35.11, 35.13, 35.14 (35.12 merged into 35.8) | _(pending)_ |
| 36 | Ingestion funnel dead-ends (out-of-coverage limbo, town-less events, missed sends, beat bookkeeping) | Needs QA | 36.1–36.4, 36.6–36.7 (36.5 closed won't-fix; 36.8 investigation → benign, no code) | _(pending)_ |
| 37 | Central auth reintegration — standalone portal + fix the live JWT bridge | Needs QA | 37.1–37.8, 37.10, 37.11 built+Needs QA (dev E2E 6/6); 37.9 Needs QA (prod cutover executed 2026-07-30, live JWT bridge verified); completes 29 + unbuilt half of 30 | _(pending)_ |
| 38 | Password-required accounts + decoupled newsletter | Open | 38.A1–38.A4, 38.B1–38.B4, 38.D1 (planned, not built) | _(pending)_ |
| 39 | Password-reset flow wiring (unblock passwordless rollover) + auth model drift | Open | 39.1–39.2 (planned, not built) | _(pending)_ |
| 40 | Monitor dashboard rebuild + direct-submission attribution | Needs QA | 40.1–40.6 all built (40.3 = read-only prod audit, no code; confirmed 4/4 live direct Events orphaned → 40.4 shipped) | _(pending)_ |
| 41 | Backend domain-boundary refactor (accounts/newsletter extraction, include()-only urls, devtools split) | Needs QA | 41.1–41.10 BUILT 2026-08-01 (business folded into accounts; digest-engine move 41.8 done; 41.9 envelope=document-only, no code change). Full suite green (fast 253, db 446). Follow-ups: accounts↔newsletter import cycle; stale docs/admin-backend.md + docs/redis-celery-handoff.md → Phase 3 | _(pending)_ |
| 42 | Dockerize the stack (compose + containerized nginx/Redis, CI cutover) | In Prod | 42.1–42.8 BUILT 2026-08-01; **CUTOVER EXECUTED ON THE PROD VM 2026-08-02** (PR #41). All cutover blockers cleared: Docker installed, `docker` group proven non-interactively, `.env` repointed to the `redis` service, 6 suite-41 migrations applied after a pre-migrate pg_dump, host nginx retired. healthcheck.sh all-green (8/8 services, both Redis DBs, 3 Celery nodes, 5 beat schedules); all 5 origins good through Cloudflare. Five VM-only bugs found+fixed: missing `auth.thecommons.town` nginx block, unquoted `DATABASE_URL` with `&` silently emptying build args, `ubuntu` is uid **1001** not 1000, §6 Redis repoint breaking the live host stack, 12-day-hung apt lock. Follow-ups → suite 44 | _(pending)_ |
| 43 | Human onboarding docs (`human-docs/` subsystem set) | Needs QA | 43.1–43.12 BUILT 2026-08-01 via `/orchestrate` from `human-docs/HANDOFF_PLAN.md`, one `/handoff-report` pass each. 12 docs + index/route-map updates; 2 stale agent-doc refs fixed (`docs/admin-backend.md`, `docs/redis-celery-handoff.md`). Docs only, no code. **Findings needing owner action:** CI's deploy job already runs `docker compose` on push to `main` but the VM has no Docker (next merge to main fails); `--color-ink` referenced in two components but never defined (silent CSS fallback); the eslint `no-restricted-imports` authClient guard is dead (alias vs. relative imports) | _(pending)_ |
| 44 | Post-Docker-cutover follow-ups (kernel reboot, stray migration, untested calendar work) | Open | 44.1–44.3 planned 2026-08-02, not built | _(pending)_ |

<!--
Columns (left→right): Idea · Open · In Progress · Needs QA · Staged for Prod · In Prod
When a suite is created here it starts in `Open` (or `Idea` if it's just a sketch).
Update a suite's Column as its tickets progress; the desktop app moves the card to match.
`Last synced` = date the desktop app last pushed this suite to Notion (it fills this in / you do).
-->
