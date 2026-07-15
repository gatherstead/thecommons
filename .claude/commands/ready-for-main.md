---
description: Run every CI check locally (lint, type-check, tests) and iteratively fix failures — no functional changes — until the repo is clean and push-ready
argument-hint: "[optional: only 'backend' | 'frontend' | 'broadcast' to scope the run]"
---

# Ready for Main

Get the working tree into a state that will pass CI (`.github/workflows/ci.yml`) cleanly, mirroring
its `lint`, `backend`, `frontend-commons`, and `frontend-broadcast` jobs. **Mode:** $ARGUMENTS (if a
scope is given, only run that section's checks; otherwise run everything).

## Ground rules

- **No functional changes.** Only fix what's needed to make lint/type/test checks pass: formatting,
  import order, unused vars/imports, type annotations, obvious lint-flagged bugs the linter itself
  identifies (e.g. unreachable code), snapshot/test updates that reflect current correct behavior.
  Do not change business logic, endpoints, models, or UI behavior to "fix" a failing test — if a test
  failure looks like it's catching a real behavioral bug rather than a lint/type/style issue, stop and
  report it instead of silently changing behavior to make it pass.
- **Never edit `neon_auth` migrations, never run `migrate` against prod, never touch the VM.**
- Prefer auto-fixers first (`ruff check --fix`, `ruff format`, `eslint --fix`) before hand-editing.
- Re-run the full check suite after every round of fixes — don't declare victory on one clean tool
  while another still fails.
- Loop: run checks → fix → re-run → repeat until every check in scope is green, or until a failure
  is not a lint/type/style issue (a real bug, a flaky test, a missing env var) — in which case stop
  and report exactly what's blocking and why it isn't safe to auto-fix.
- Cap at ~8 iterations of a given check; if still failing after that, stop and report rather than
  looping forever.

## Step 1 — Baseline

Run `git status` and `git diff --stat` to see what's already changed. Note the current branch.

## Step 2 — Backend (skip if scope is "frontend" or "broadcast")

From `backendServer/`:

```bash
uv sync --frozen
DATABASE_URL=postgres://user:pass@localhost:5432/dummy uv run ruff check .
DATABASE_URL=postgres://user:pass@localhost:5432/dummy uv run ruff format --check .
DATABASE_URL=postgres://user:pass@localhost:5432/dummy uv run mypy .
```

Fix loop:
1. `uv run ruff check . --fix` for auto-fixable lint issues, then re-check remaining ones by hand.
2. `uv run ruff format .` to apply formatting.
3. For mypy errors, add/correct type annotations — don't change runtime logic to dodge a type error
   unless the annotation reveals an actual bug (then stop and report, don't silently "fix" it).

Then run tests (needs local Postgres reachable, or skip with a note if unavailable):

```bash
DJANGO_SETTINGS_MODULE=backend.settings.test uv run python manage.py test --tag=fast
DJANGO_SETTINGS_MODULE=backend.settings.test uv run python manage.py test --tag=db
```

If DB tests can't run locally (no Postgres), say so explicitly rather than skipping silently.

## Step 3 — Frontend: theCommonsWeb (skip if scope is "backend" or "broadcast")

From `theCommonsWeb/`:

```bash
pnpm install --frozen-lockfile
pnpm lint
```

Fix loop: `pnpm lint:fix`, then hand-fix remaining ESLint errors (unused imports, hook deps, etc.)
without altering behavior.

Type-check (mirrors CI's build-only env vars — placeholders, not real creds):

```bash
DATABASE_URL=postgres://build:build@localhost:5432/build \
BETTER_AUTH_SECRET=build-only-placeholder-secret \
BETTER_AUTH_URL=http://localhost:3000 \
NEXT_PUBLIC_BETTER_AUTH_URL=http://localhost:3000 \
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 \
NEXT_PUBLIC_THE_COMMONS_API_KEY=build-placeholder \
pnpm build
```

Fix any TypeScript errors surfaced by the build without changing runtime behavior. Then:

```bash
pnpm test:fast
pnpm test:db
```

## Step 4 — Frontend: broadcastWeb (skip if scope is "backend" or "frontend")

From `broadcastWeb/`:

```bash
pnpm install --frozen-lockfile
VITE_BROADCAST_API_BASE_URL=http://localhost:8000 pnpm build
pnpm test:fast
pnpm test:db
```

`pnpm build` runs `tsc -b && vite build` — fix any type errors it surfaces, no behavior changes.

## Step 5 — Final verification pass

Re-run every command from steps 2-4 that's in scope, back to back, from a clean state, to confirm
nothing regressed from your own fixes. Only stop looping once this full pass is green.

## Step 6 — Report

Summarize:
- What was fixed (by category: formatting, lint, types, test updates) with file counts, not a full diff dump.
- Any checks that couldn't run locally (e.g. no local Postgres) and what CI will additionally verify.
- Any failure that looked like a real behavioral bug rather than a style/lint issue — flagged, not fixed.
- Confirm working tree is otherwise unchanged in behavior — no logic, endpoints, models, or UI changes.

Do not commit or push. Leave that to the user.
