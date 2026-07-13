---
description: Check all docs for staleness against the actual code and write corrections in place
argument-hint: "[--report-only to propose without writing]"
---

# Refresh Docs

You are the **doc-refresh orchestrator**. Your job is to fan out five read-only subagents across every doc file in the repo, collect stale claims, and apply high-confidence corrections directly to the doc files. Pass `--report-only` to get a proposals-only report without touching any files.

**Mode:** $ARGUMENTS

If `--report-only` is in the arguments, produce proposals only and stop — write nothing. Otherwise apply all high-confidence patches after consolidation and list medium-confidence findings in the report for human review.

---

## What "stale" means

A doc claim is stale if any of these are true:
- **Wrong** — names a file path, function, model field, endpoint, class, env var, or command that no longer exists or has been renamed.
- **Outdated** — describes behavior that used to be true but the code has since changed (e.g. a service method that moved, a flag that was removed, a test file that was renamed).
- **Missing** — a significant subsystem, file, or convention exists in the code but has no mention in the relevant doc.
- **Contradicted by code** — doc says X, code does Y; per CLAUDE.md, trust the code.

Do **not** flag:
- Forward-looking design docs (`prd-*.md`, `tickets-*.md`, `seo-hub-pages.md`) — they describe planned state, not current state.
- Prose framing or editorial tone — only factual claims about code/files/commands.
- Style preferences — already covered by Ruff/ESLint.

---

## Step 1 — Orient yourself

Read these files before spawning anything:
- `CLAUDE.md`, `AGENTS.md` (root), `docs/index.md`
- `backendServer/AGENTS.md`, `theCommonsWeb/AGENTS.md`, `broadcastWeb/AGENTS.md`

This gives you the map so you can brief each subagent precisely, not generically.

---

## Step 2 — Fan out five subagents in parallel

Spawn all five at once. Each is **read-only + propose-only** — no writes. Give each:
1. The ground rules block (below).
2. Their specific doc list and code scan targets.
3. The shared finding schema.

### Ground rules (paste into every subagent)

> You are a doc-staleness reviewer. Read only. Do not modify any file. For each doc you review:
> 1. Read the doc in full.
> 2. For every factual claim (file path, function name, model field, endpoint, env var, command, class name, behavior description) — grep or read the referenced location in the actual code to verify it.
> 3. Report ONLY stale claims using the finding schema below. If a claim checks out, say nothing about it.
> 4. For each stale claim, propose a specific replacement — the exact text that should replace the stale text, or "DELETE" if the section should be removed, or "ADD" with the proposed new content if something is missing.
> 5. Trust code over docs. Never assume the doc is right and the code is wrong.
> 6. Read excerpts, not whole files. Return file:line references. Cap your narrative to ~5 lines per doc.

### Shared finding schema

Each finding must follow this shape:
```
DOC: <doc file path>
LINE: <line number(s) of the stale text>
KIND: wrong | outdated | missing | contradicted
STALE TEXT: <the exact current text that is wrong, or "n/a" for missing>
PROPOSED TEXT: <exact replacement text, or "DELETE", or "ADD: <new text>">
CONFIDENCE: high | medium  (high = you verified by reading the code; medium = you inferred)
```

---

### Subagent 1: Core orientation layer

**Docs:** `CLAUDE.md`, `AGENTS.md` (root), `docs/index.md`, `PROJECT_CONTEXT.md`

**What to verify against the code:**
- Every file path listed in `AGENTS.md`'s directory tree exists (`ls` or `find`).
- Every command listed under "Quick Start" in `CLAUDE.md` actually works as written (verify the paths exist and the commands are plausible, no need to run them).
- Every doc pointer in `docs/index.md` resolves to a real file in `docs/`.
- `PROJECT_CONTEXT.md`'s description of what the project does, who it's for, and its tech stack — cross-check key tech claims against `backendServer/pyproject.toml`, `theCommonsWeb/package.json`, `broadcastWeb/package.json`.
- Any "as of" dates or "last updated" markers.
- Guardrails in `AGENTS.md` that reference specific files/classes (e.g. `neon_auth` managed tables, `broadcast/routing.py` isolation, Redis DB numbers) — spot-check the code.

---

### Subagent 2: Architecture & data model

**Docs:** `ARCHITECTURE.md`

**What to verify against the code:**
- Every Django model named — cross-check fields and relationships against `backendServer/events/models.py`, `backendServer/ingestion/models.py`, `backendServer/broadcast/models.py`.
- Every DRF endpoint and URL pattern mentioned — verify against each app's `urls.py`.
- The auth bridge description (Better Auth → JWKS → `BearerTokenAuthentication`) — verify class names exist in `backendServer/backend/jwt_auth.py` and `backendServer/backend/permissions.py`.
- The Celery/Redis topology (broker DB 0, cache DB 1, beat schedule, worker queues) — verify against `backendServer/backend/settings/base.py` or `prod.py`.
- The deployment topology (Oracle VM, systemd units, nginx) — spot-check service names against `deploy/`.
- The "SQL-authoritative tables" section (Town, Category, EventSource) — verify the model/fixture approach against the code.

---

### Subagent 3: Backend subsystem docs

**Docs:** `backendServer/AGENTS.md`, `docs/ingestion-pipeline.md`, `docs/admin-backend.md`, `docs/redis-celery-handoff.md`, `docs/safety-scoring.md`, `docs/devtools-ingestion-playground.md`

**What to verify against the code:**
- Every management command listed in `backendServer/AGENTS.md` — check it exists under `backendServer/*/management/commands/`.
- Every function/method named in `docs/ingestion-pipeline.md` — spot-check against `backendServer/ingestion/services.py`, `backendServer/ingestion/standardizer.py`, `backendServer/ingestion/deduplicator.py`.
- The admin registration patterns in `docs/admin-backend.md` — check `backendServer/*/admin.py` files.
- The Redis key layout and Celery task names in `docs/redis-celery-handoff.md` — verify against `backendServer/backend/settings/base.py` and `backendServer/*/tasks.py`.
- The safety scorer thresholds and field names in `docs/safety-scoring.md` — verify against `backendServer/ingestion/safety_scorer.py`.
- The devtools playground doc — check it describes what's actually in `backendServer/devtools/` (views, URLs, templates).
- Every test file path or test tag named — verify it exists under `backendServer/**/tests/`.

---

### Subagent 4: Frontend & broadcast docs

**Docs:** `theCommonsWeb/AGENTS.md`, `broadcastWeb/AGENTS.md`, `docs/broadcast.md`

**What to verify against the code:**
- Every route listed in `theCommonsWeb/AGENTS.md` — check the corresponding `theCommonsWeb/src/app/` directory structure.
- Every hook and service named in `theCommonsWeb/AGENTS.md` — verify file existence under `theCommonsWeb/src/hooks/` and `theCommonsWeb/src/services/`.
- The auth hook/lib references (`useAuth`, auth-client path) — verify against `theCommonsWeb/src/lib/` and `theCommonsWeb/src/hooks/`.
- `broadcastWeb/AGENTS.md` component and hook listings — verify against `broadcastWeb/src/`.
- `docs/broadcast.md`: adapter names, worker commands, environment variable names, access-code model fields, manual-review flow steps — verify against `backendServer/broadcast/` source and `broadcastWeb/`.
- Any WebSocket protocol or message-type descriptions in `docs/broadcast.md` — spot-check against `backendServer/broadcast/routing.py` and `backendServer/broadcast/consumers.py` (if present).

---

### Subagent 5: Ops, deploy & validated patterns

**Docs:** `DEPLOY.md`, `docs/dev-db-isolation.md`, `docs/runbook-auth-cutover.md`, `docs/validated-patterns.md`

**What to verify against the code:**
- Every systemd unit file named in `DEPLOY.md` — check it exists under `deploy/`.
- Every nginx config snippet referenced — check `deploy/`.
- Every environment variable listed in `DEPLOY.md` or `docs/dev-db-isolation.md` — cross-check against `.env.example` files in `backendServer/`, `theCommonsWeb/`, `broadcastWeb/`.
- The Neon branch setup steps in `docs/dev-db-isolation.md` — check they still match how `backendServer/backend/settings/dev.py` and `test.py` consume the DB URL.
- `docs/runbook-auth-cutover.md`: any file paths, env var names, or Django settings keys referenced — verify they exist.
- `docs/validated-patterns.md`: every code reference (`file::function`) — verify the file exists and the function/method is at roughly the stated location.
- The `DJANGO_ENV` selector behavior described in DEPLOY.md — verify against `backendServer/backend/settings/__init__.py`.

---

## Step 3 — Consolidate

Once all five subagents return, merge their findings:

1. Deduplicate (same stale text cited by two subagents → one entry).
2. Sort by impact:
   - **Critical** — wrong file path / nonexistent function that would send an agent in the wrong direction.
   - **Moderate** — outdated behavior description or renamed symbol.
   - **Minor** — missing coverage of a new feature; cosmetic drift.
3. Write the consolidated report to `docs/refresh/YYYY-MM-DD.md` (create `docs/refresh/` if missing; if today's file exists, suffix `-2`).

### Report format

```markdown
# Doc Refresh — <date>

## Summary
<total finding count by kind and impact>

## Critical
<findings>

## Moderate
<findings>

## Minor
<findings>

## Proposed patches
For each finding with PROPOSED TEXT, list the exact edit:

### <doc path>
**Line <N>:** replace
> <stale text>
with
> <proposed text>
```

4. **Default (no flag):** after writing the report, apply every **high-confidence** finding. Edit each doc file, making only the changes in the report — nothing else. Mark each applied finding in the report. Stop before applying medium-confidence findings; list them as "needs human review."

5. **If `--report-only` was passed:** do not modify any doc files. Print a one-paragraph summary of what was found and tell the user to run `/refresh-docs` (no flag) to apply the patches, or review the full report at `docs/refresh/YYYY-MM-DD.md`.

---

## Guardrails

- **Never** modify forward-looking design docs (`prd-*.md`, `tickets-*.md`, `seo-hub-pages.md`, `seo-ops-playbook.md`) — they describe intended state, not current state.
- **Never** run `migrate`, touch the prod VM, or call external services.
- **Never** change code to match docs — only change docs to match code.
- If a subagent can't verify a claim (e.g. VM-specific path it can't read), mark `CONFIDENCE: medium` and note why.
- Token discipline: read excerpts, not whole files. Grep before reading.
