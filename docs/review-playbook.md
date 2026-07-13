# Repository Review Playbook

**Purpose:** a reusable, multi-agent review of the whole repo, run by the `/repo-review` skill (`.claude/skills/repo-review/SKILL.md`) or by an orchestrator spawning subagents in-session. It fans out five domain reviewers, each returning findings in a shared schema, then merges them into one triaged report with an **Apply Queue** you approve before anything changes.

**When to run:** before a release, after a large feature lands, or on a cadence to catch prod-wiring rot and doc drift.

**Non-negotiables for every run:**
- **Report first, apply after.** A run produces findings + proposed diffs only. Fixes happen in later passes gated by the Apply Queue.
- **Keep all features identical.** No behavior changes. No styling migration.
- **Trust code over docs** and flag drift.
- **Token discipline.** Read excerpts, not whole files. Return `file:line` + conclusions, never file dumps. Cap prose (each agent's narrative ≤ ~10 lines).

---

## How to run it

Two entry points, same playbook:

1. **`/repo-review`** — the skill at `.claude/skills/repo-review/SKILL.md`: a thin dispatcher that reads this file and executes it.
2. **In-session orchestrator** — spawn the five domain subagents below in parallel (Explore or general-purpose), then merge per the Consolidation step.

Copy the **Ground Rules** and **Reviewer Configuration** blocks below into every subagent prompt.

### Ground rules (paste into each subagent)
> Trust code over docs; flag drift. Keep all features identical — propose, don't apply. Read excerpts, not whole files. Return findings in the shared schema (`file:line`, no dumps). Cap your narrative at ~10 lines. If a check couldn't run, say so — never assume it passed.

---

## Severity rubric (shared)

| Sev | Meaning |
|-----|---------|
| **P0** | Prod risk / silent failure — can break in prod with no signal (e.g. `DJANGO_ENV` unset → silent dev fallback → `DisallowedHost` → "no events"; unguarded `migrate` on deploy; a service that won't recover after VM reboot). |
| **P1** | Correctness / missing safety net — a main feature has no test that fails when it breaks. |
| **P2** | Architecture / extensibility — works, but hard to extend or scale. |
| **P3** | Polish / docs / token bloat. |

## Shared finding schema (every subagent returns this)

```
ID | severity | area | file:line | finding | recommended fix | effort (S/M/L) | features-unchanged? (Y)
```

Plus a short "Opportunities" narrative (≤ ~10 lines) per agent.

---

## Reviewer configuration (fed to Fable / the orchestrator)

- **Pointer:** read this playbook first; it defines scope, rubric, and output schema.
- **Guardrails** (restated from `AGENTS.md`/`CLAUDE.md` so they can't be missed; if this list ever disagrees with `AGENTS.md`, trust `AGENTS.md`): never migrate `neon_auth` (mirrors are `managed = False`); `broadcast/` isolation — no `events` import in `backendServer/broadcast/routing.py`, no ORM inside `sync_playwright`; Redis DB 0 = broker/results, DB 1 = cache; pnpm-only (npm breaks the symlinked store); `Town`/`Category` are SQL authorities, don't hardcode; the newspaper aesthetic is intentional.
- **Action limits:** read-only + propose diffs. Do **not** run `migrate`, touch the prod VM, or hit external services (Gemini / Brevo / Neon prod).
- **Priority ordering:** P0 prod-wiring first, then tests, then architecture, then docs/styling.
- **Known-gaps seed list** (don't burn tokens rediscovering these — confirm and deepen instead): untagged tests never run in CI (last known offender `backendServer/ingestion/tests/test_pipeline.py` is now tagged `db` and renamed `test_pipeline_db.py`; re-sweep for new ones); no lint step (eslint config commented; no ruff/mypy/prettier); `DJANGO_ENV` unset-in-prod still silently selects dev — typos now fail loud in `backendServer/backend/settings/__init__.py`, deploy-time smoke + `deploy/healthcheck.sh --require-prod` catch it at deploy; between deploys `deploy/healthcheck.sh` is run manually — a deliberate choice, not a gap; deploy `migrate` is now guarded (`--check` skip + pre-migrate `pg_dump` in ci.yml — verify the guard still holds); pnpm/Node pinned only in CI; thin frontend test coverage in `theCommonsWeb` (recount at run time; last audit: 5 test files — 2 smoke plus `useAuth`/`useEvents`/`eventService` — against ~30 components).
- **Runtime setup notes:** backend tests (run from `backendServer/`) → `DJANGO_SETTINGS_MODULE=backend.settings.test uv run python manage.py test` (Postgres test DB via Neon; cloud sandboxes may only run `--tag=fast`); frontend type-check → `pnpm build`; unit tests → `pnpm test:fast|test:db`.
- **Output location:** consolidated findings → `docs/review/YYYY-MM-DD-findings.md`.

---

## The five domain subagents (parallel fan-out)

### 1. Prod-wiring & deploy integrity
**Scan:** `deploy/*.service`, `deploy/nginx-*.snippet`, `deploy/healthcheck.sh`, `.github/workflows/ci.yml` (gated deploy job), `backendServer/backend/settings/{base,prod,dev,test}.py`, the three `.env.example` files (`backendServer/`, `theCommonsWeb/`, `broadcastWeb/`), `DEPLOY.md`.

**Guiding questions:**
- If the VM reboots, does every service (`gunicorn`, `nextjs`, `redis-server`, `celery`, `celerybeat`, `broadcast-worker`) come back healthy and in the right order? Note: only `celery`, `celerybeat`, and `broadcast-worker` have unit files in `deploy/`; `gunicorn`/`nextjs` units live only on the VM and `redis-server` is the OS package — audit those via `DEPLOY.md`'s service table.
- `healthcheck.sh` is a discrete manual tool by design (not on a timer) — don't flag that as a gap; only check it still runs clean.
- What fails **silently**? (Known: `DJANGO_ENV` unset-in-prod between deploys; required secrets that default instead of erroring at boot.)
- Is there any post-deploy smoke that actually pings `/events/` and an auth-gated route, so we learn a feature is down before users do?
- Is the Redis DB 0/1 split honored in prod config? Are CORS/CSRF/allowed-hosts correct for the three domains?

### 2. Test-suite audit
**Scan:** `backendServer/**/tests/`, `backendServer/backend/test_runner.py`, `theCommonsWeb/src/**/__tests__`, `broadcastWeb/src/**/__tests__`, both `vitest.config.ts` files, CI test tiers.

**Guiding questions:**
- For each user-facing feature — feed loads, event submit → `StagedEvent`, auth/JWT bridge, weekly digest send, broadcast submit → worker → target — does a test **fail when it breaks**? If not, that's a P1.
- What is the **fastest automated signal** that prod is down, and does it exist?
- Which tests are untagged and therefore never run in CI? (`test_pipeline.py` — now `test_pipeline_db.py` — is tagged `db`; find others.)
- Which tests assert nothing meaningful, or only the happy path? Flag missing negative/error-path coverage.
- Frontend: what's the minimum set of tests that would catch a broken feed/auth/submit render?

### 3. Backend architecture & modularity
**Scan:** `backendServer/events/`, `backendServer/ingestion/`, `backendServer/broadcast/` boundaries; each app's `services.py` vs its views; `backendServer/broadcast/adapters/__init__.py` registry; `backendServer/events/cache.py`; Celery fan-out.

**Guiding questions:**
- Where does logic live in views that belongs in `services.py`?
- Is `broadcast/` isolation actually enforced (no `events` import in `routing.py`; no ORM in `sync_playwright`)?
- To add a new `Town`/`Category`/`EventSource`/broadcast adapter, how many files change? Would a registry/plugin pattern shrink that surface?
- Scalability: ingestion sharding, read-cache versioning/invalidation, per-view auth duplication.

### 4. Frontend architecture & agent-extensibility (styling = analyze + recommend, **no migration**)
**Scan:** `theCommonsWeb/src/components/` (count the tsx files at run time), `theCommonsWeb/src/hooks/`, `theCommonsWeb/src/services/`, `theCommonsWeb/src/lib/queryClient.ts`, `theCommonsWeb/src/app/globals.css` (CSS vars + utilities), Tailwind v4 usage.

**Guiding questions:**
- For an AI agent extending the UI, is the current split (Tailwind for layout, CSS custom properties for color) **easier or harder** to reason about than a single documented convention? Recommend a convention; do **not** restyle.
- Where do components bypass the `useAuth`/`useEvents` conventions or manage JWTs directly?
- What's duplicated across components that a shared primitive would remove?
- Is the `FrontendEvent` mapping in `services/` consistent and typed?

### 5. Docs & agent-navigability
**Scan:** `CLAUDE.md`, all `AGENTS.md`, `ARCHITECTURE.md`, `CODING_STYLE.md`, `docs/*`, `PROJECT_CONTEXT.md`.

**Guiding questions:**
- Can an agent landing cold find the right file in **one hop** from `CLAUDE.md`? Propose a tightened roadmap if not.
- Where do docs contradict code (drift)?
- What's redundant/bloated across the doc set (token cost)?

**Deliverables from this agent:** (a) a proposed tightened `CLAUDE.md` roadmap, and (b) a **refreshed `PROJECT_CONTEXT.md`** — token-lean, accurate to current code, suitable as a standalone Claude-desktop project context. Attached as proposed diffs, not applied.

---

## Consolidation step

The orchestrator merges the five outputs into `docs/review/YYYY-MM-DD-findings.md` (create `docs/review/` if missing; if the day's file already exists, suffix `-2`, `-3`, …; the orchestrator writes the file — subagents only return findings):
1. Dedup overlapping findings.
2. Sort by severity (P0 → P3).
3. Append an **Apply Queue**: a checklist grouped by severity. The user checks items to authorize each apply-pass.
4. Attach proposed `PROJECT_CONTEXT.md` and `CLAUDE.md` rewrites as diffs — not applied until approved.

**A run succeeds when** it yields a triaged `findings.md`, an Apply Queue, and proposed doc diffs — with **zero feature changes**.

---

## Out of scope

Applying fixes (separate approved passes), migrating styling, and touching `neon_auth` migrations.
