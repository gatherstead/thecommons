# Documentation Index

Guides and references beyond the root-level docs. Each file is a deep dive on a specific subsystem.

| Doc | Purpose | When to read |
|-----|---------|--------------|
| [ingestion-pipeline.md](ingestion-pipeline.md) | End-to-end walkthrough of the scrape → stage → publish flow | Working on `ingestion/` or the cron pipeline |
| [admin-backend.md](admin-backend.md) | Guide to the django-unfold admin UI and review workflows | Modifying admin registration or review flows |
| [safety-scoring.md](safety-scoring.md) | How `safety_scorer.py` works, threshold tuning | Adjusting safety scoring or ingestion quality |

## Root-level docs

| Doc | Purpose |
|-----|---------|
| [AGENTS.md](../AGENTS.md) | Repository map — start here |
| [ARCHITECTURE.md](../ARCHITECTURE.md) | System design: models, endpoints, auth bridge, deployment |
| [CODING_STYLE.md](../CODING_STYLE.md) | Design philosophy, CSS tokens, component + backend conventions |
| [DEPLOY.md](../DEPLOY.md) | Production VM setup, nginx, systemd, deploy commands |
