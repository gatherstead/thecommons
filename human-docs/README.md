# Human Docs

This folder is for people, not agents. `docs/` is the system of record that Claude reads before
every task (`CLAUDE.md` → `AGENTS.md` → `ARCHITECTURE.md` → `CODING_STYLE.md` → `docs/*.md`) —
keep that tree lean and agent-oriented. Anything written primarily for a human reader — an
inheriting owner, a new teammate, a neighbouring team — lands here instead, so it doesn't dilute
what agents load on every task.

Written mainly by `/handoff-report`. See that skill for structure, grounding rules, and the
publish checklist.

**New here?** Start with [`start-here.md`](start-here.md) — it routes you to the right doc by
what you're trying to do. [`HANDOFF_PLAN.md`](HANDOFF_PLAN.md) tracks which subsystem docs are
still to be written.

## Index

| Doc | Purpose | Written |
|---|---|---|
| [start-here.md](start-here.md) | Task-oriented map: "I want to…" → the right doc | 2026-08-01 |
| [overview.md](overview.md) | System map: product, monorepo layout, event lifecycle, architecture diagram — read this first | 2026-08-01 |
| [local-setup.md](local-setup.md) | Clone to running system: prerequisites, the four env files, backend/frontends/Redis/Celery/Playwright, the Docker path | 2026-08-05 |
| [auth.md](auth.md) | Better Auth (Next.js) is identity's source of truth; Django only mirrors it and verifies JWTs | 2026-08-01 |
| [ingestion.md](ingestion.md) | Source → Gemini standardize → dedupe → safety-score → publish, and how to classify a new source | 2026-08-01 |
| [data-model.md](data-model.md) | Every core model, field by field, and how they relate — the reference to keep open in another tab | 2026-08-01 |
| [broadcast.md](broadcast.md) | Syndicating events out to other towns' calendars: adapters, extension autofill, access codes | 2026-08-01 |
| [newsletter.md](newsletter.md) | Subscription lifecycle, recipient resolution, and the weekly/monthly digest engine | 2026-08-01 |
| [async-jobs.md](async-jobs.md) | Redis layout, the three Celery queues and who drains each, beat scheduling and its lag trap | 2026-08-01 |
| [deploy-ops.md](deploy-ops.md) | Production mental model: the VM, the Docker Compose stack, deploys, and the sharp edges that cause outages | 2026-08-03 |
| [containerization.md](containerization.md) | Why and how the stack is containerized: service topology, the retired-systemd mapping, and the live footguns | 2026-08-03 |
| [frontend.md](frontend.md) | Main site: App Router routes, the TanStack Query data layer, Better Auth on the client | 2026-08-01 |
| [design-system.md](design-system.md) | The digital-newspaper aesthetic as an enforceable spec — tokens, type scale, the banned list | 2026-08-01 |
| [testing.md](testing.md) | Local setup, the backend test tiers, the shared-test-DB hazard, and what CI runs | 2026-08-01 |
| [HANDOFF_PLAN.md](HANDOFF_PLAN.md) | The plan these docs were written from — kept for provenance; all 11 planned docs now exist | 2026-08-01 |
