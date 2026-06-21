# Documentation Index

Guides and references beyond the root-level docs. Each file is a deep dive on a specific subsystem.

| Doc | Purpose | When to read |
|-----|---------|--------------|
| [ingestion-pipeline.md](ingestion-pipeline.md) | End-to-end walkthrough of the scrape → stage → publish flow | Working on `ingestion/` or the cron pipeline |
| [admin-backend.md](admin-backend.md) | Guide to the django-unfold admin UI and review workflows | Modifying admin registration or review flows |
| [safety-scoring.md](safety-scoring.md) | How `safety_scorer.py` works, threshold tuning | Adjusting safety scoring or ingestion quality |
| [dev-db-isolation.md](dev-db-isolation.md) | Neon dev branch setup — isolating local dev from prod DB | Setting up a dev environment or running migrations |
| [broadcast-handoff.md](broadcast-handoff.md) | Manual-review path: recipe layer, browser extension, SPA wiring, auto-spawn worker | Working on broadcast captcha sites or the extension |
| [redis-celery-handoff.md](redis-celery-handoff.md) | Redis + Celery setup: broker/cache, worker + beat services, task conventions | Adding async tasks, scheduled jobs, or touching the worker |

## Root-level docs

| Doc | Purpose |
|-----|---------|
| [AGENTS.md](../AGENTS.md) | Repository map — start here |
| [ARCHITECTURE.md](../ARCHITECTURE.md) | System design: models, endpoints, auth bridge, deployment |
| [CODING_STYLE.md](../CODING_STYLE.md) | Design philosophy, CSS tokens, component + backend conventions |
| [DEPLOY.md](../DEPLOY.md) | Production VM setup, nginx, systemd, deploy commands |
