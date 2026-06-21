# Documentation Index

Deep-dive guides beyond the root-level docs. Each file is a focused reference on one subsystem.

| Doc | Purpose | When to read |
|-----|---------|--------------|
| [broadcast.md](broadcast.md) | **Source of truth** for the broadcast subsystem: routing, adapters, worker, access codes, manual-review handoff, env, commands | Working on `broadcast/`, `broadcastWeb/`, or the extension |
| [ingestion-pipeline.md](ingestion-pipeline.md) | End-to-end walkthrough of the poll → standardize → stage → publish flow | Working on `ingestion/` or the cron pipeline |
| [safety-scoring.md](safety-scoring.md) | How `safety_scorer.py` works and threshold tuning | Adjusting safety scoring or ingestion quality |
| [admin-backend.md](admin-backend.md) | Guide to the django-unfold admin UI and review workflows | Modifying admin registration or review flows |
| [redis-celery-handoff.md](redis-celery-handoff.md) | Redis + Celery setup: broker/cache, worker + beat, task conventions | Adding async tasks, scheduled jobs, or touching the worker |
| [dev-db-isolation.md](dev-db-isolation.md) | Neon dev-branch setup — isolating local dev from the prod DB | Setting up a dev environment or running migrations |

## Root-level docs

| Doc | Purpose |
|-----|---------|
| [AGENTS.md](../AGENTS.md) | Repository map — start here |
| [ARCHITECTURE.md](../ARCHITECTURE.md) | System design: models, endpoints, auth bridge, async, deployment |
| [CODING_STYLE.md](../CODING_STYLE.md) | Design philosophy, CSS tokens, component + backend conventions |
| [DEPLOY.md](../DEPLOY.md) | Production VM setup, nginx, systemd, deploy commands (source of truth) |

## Per-directory maps

| Map | Scope |
|-----|-------|
| [backendServer/AGENTS.md](../backendServer/AGENTS.md) | Django backend — apps, endpoints, commands, testing |
| [theCommonsWeb/AGENTS.md](../theCommonsWeb/AGENTS.md) | Main Next.js frontend — routes, hooks, services, data layer |
| [broadcastWeb/AGENTS.md](../broadcastWeb/AGENTS.md) | Broadcast operator SPA |
| [broadcastExtension/README.md](../broadcastExtension/README.md) | Chrome extension for manual broadcast review |
